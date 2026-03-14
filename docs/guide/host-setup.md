# Préparation de l'hôte

Guide de déploiement de référence pour un hôte anklume :
Debian 13 + btrfs (multiboot) + ZFS chiffré (données) + NVIDIA GPU.

## Vue d'ensemble

```
NVMe système                              Pool ZFS "tank" (2x NVMe mirror)
┌──────────────────────────────┐           ┌──────────────────────────────┐
│ p1  512M   EFI (FAT32)      │           │ tank/_home        → /home   │
│ p2  ~200G  NTFS (Windows)   │  chiffré  │ tank/_incus       → (Incus) │
│ p3  reste  btrfs            │  ───────→ │ tank/_srv_models  → /srv/…  │
│   @debian      → /          │           │ tank/_srv_shared  → /srv/…  │
│   @debian-boot → /boot      │           │ tank/_srv_backups → /srv/…  │
│   @fedora      → /          │           │ tank/_var_lib_anklume → …   │
│   @fedora-boot → /boot      │           └──────────────────────────────┘
│   @snapshots                │
└──────────────────────────────┘
```

**Principes** :

- **Pas de LUKS sur `/`** — le système est jetable et remplaçable
- Données persistantes sur **ZFS chiffré** — seul point de chiffrement
- `/` sur btrfs avec subvolumes — multiboot, snapshots, espace partagé
- Chaque distro a son propre subvolume `/boot` (kernel + initramfs isolés)
- **Injection de credentials** — hash mot de passe stocké sur ZFS chiffré,
  injecté dans `/etc/shadow` au montage → pas de login possible sans ZFS
- Secrets NetworkManager sur ZFS → pas de fuite WiFi en clair
- Mode toram optionnel — `/` chargé en RAM, immutable au runtime
- GPU NVIDIA via `.run` + DKMS — compatible kernel updates

---

## 1. Installation Debian + partitionnement btrfs

### Ordre d'installation (multiboot)

1. **Windows d'abord** — il crée la partition EFI et écrase le bootloader
2. **Debian ensuite** — GRUB détecte Windows et l'ajoute au menu
3. **Autre Linux** — dans un subvolume btrfs, GRUB le détecte aussi

### Schéma de partitions

| Partition | Taille | Type | Usage |
|---|---|---|---|
| `/dev/nvmeXn1p1` | 512 MB | EFI (FAT32) | `/boot/efi` (partagé) |
| `/dev/nvmeXn1p2` | ~200 GB | NTFS | Windows (optionnel) |
| `/dev/nvmeXn1p3` | Reste | btrfs | Subvolumes Linux |

!!! note "Sans Windows"
    Sans Windows, supprimer p2 et donner tout l'espace à p3.

### Installation Debian depuis l'installeur

1. Choisir le partitionnement **« Manuel »** (pas le guidé avec LVM chiffré)
2. Créer p1 (EFI) si elle n'existe pas déjà (Windows la crée)
3. Créer p3, formater en **btrfs**, monter sur `/`
4. Mettre un **mot de passe temporaire** (sera migré vers ZFS par le bootstrap)
5. Terminer l'installation normalement

### Restructuration en subvolumes (après le premier boot)

L'installeur Debian met tout à la racine du btrfs (pas de subvolume).
Il faut restructurer pour le multiboot.

```bash
# Depuis un live USB
mount /dev/nvmeXn1p3 /mnt

# Créer les subvolumes
btrfs subvolume snapshot /mnt /mnt/@debian
btrfs subvolume create /mnt/@snapshots

# Déplacer /boot dans son propre subvolume
btrfs subvolume create /mnt/@debian-boot
cp -a /mnt/@debian/boot/* /mnt/@debian-boot/
rm -rf /mnt/@debian/boot/*

# Nettoyer la racine (garder uniquement les subvolumes)
find /mnt -maxdepth 1 -not -name '@*' -not -path /mnt -exec rm -rf {} +

umount /mnt
```

### Mise à jour fstab et GRUB

```bash
mount -o subvol=@debian /dev/nvmeXn1p3 /mnt
mount -o subvol=@debian-boot /dev/nvmeXn1p3 /mnt/boot
mount /dev/nvmeXn1p1 /mnt/boot/efi

# Éditer fstab
cat > /mnt/etc/fstab << 'EOF'
# <device>         <mount>      <type>  <options>                                    <dump> <pass>
/dev/nvmeXn1p3     /            btrfs   subvol=@debian,compress=zstd,noatime         0 1
/dev/nvmeXn1p3     /boot        btrfs   subvol=@debian-boot,compress=zstd,noatime    0 2
/dev/nvmeXn1p1     /boot/efi    vfat    umask=0077                                   0 1
/dev/nvmeXn1p3     /.snapshots  btrfs   subvol=@snapshots,compress=zstd,noatime      0 2
EOF

# Mettre à jour GRUB
mount --bind /dev /mnt/dev
mount --bind /proc /mnt/proc
mount --bind /sys /mnt/sys
chroot /mnt update-grub
umount /mnt/sys /mnt/proc /mnt/dev
umount -R /mnt
```

### Ajouter un autre Linux (Fedora, NixOS…)

```bash
mount /dev/nvmeXn1p3 /mnt
btrfs subvolume create /mnt/@fedora
btrfs subvolume create /mnt/@fedora-boot
umount /mnt

# Installer dans le subvolume
mount -o subvol=@fedora /dev/nvmeXn1p3 /mnt
# dnf --installroot=/mnt ... (Fedora)
# nixos-install --root /mnt  (NixOS)
```

Chaque distro a son propre fstab avec son subvolume :

```
# fstab de @fedora
/dev/nvmeXn1p3  /      btrfs  subvol=@fedora,compress=zstd,noatime       0 1
/dev/nvmeXn1p3  /boot  btrfs  subvol=@fedora-boot,compress=zstd,noatime  0 2
```

!!! tip "Avantage btrfs"
    L'espace disque est partagé dynamiquement entre tous les Linux.
    Pas besoin de deviner les tailles à l'avance. Supprimer un subvolume
    libère l'espace pour les autres.

---

## 2. Pool ZFS — données persistantes chiffrées

Le pool ZFS est le **seul point de chiffrement**. Toutes les données
sensibles (home, modèles, credentials, secrets NM) y résident.

### Convention de nommage

Les datasets portent le nom du chemin de montage avec `/` remplacé
par `_`. Cette convention rend la correspondance dataset ↔ mountpoint
immédiate.

| Dataset | Mountpoint | Raison |
|---|---|---|
| `tank/_incus` | (none — géré par Incus) | Storage pool Incus |
| `tank/_home` | `/home` | Données utilisateur |
| `tank/_srv_models` | `/srv/models` | Modèles IA |
| `tank/_srv_models_ollama` | `/srv/models/ollama` | Modèles Ollama |
| `tank/_srv_models_stt` | `/srv/models/stt` | Modèles STT/Whisper |
| `tank/_var_lib_anklume` | `/var/lib/anklume` | État anklume |
| `tank/_srv_shared` | `/srv/shared` | Volumes partagés inter-domaines |
| `tank/_srv_backups` | `/srv/backups` | Golden images, exports |

### Création du pool

```bash
zpool create \
  -o ashift=12 \
  -o autotrim=on \
  -O acltype=posixacl \
  -O xattr=sa \
  -O atime=off \
  -O compression=zstd \
  -O dedup=off \
  -O mountpoint=none \
  -O encryption=aes-256-gcm \
  -O keyformat=passphrase \
  -O keylocation=prompt \
  -o compatibility=openzfs-2.3-linux \
  tank mirror /dev/disk/by-id/<nvme-corsair-1> /dev/disk/by-id/<nvme-corsair-2>
```

### Création des datasets

```bash
# Incus — mountpoint=none, Incus gère ses sous-datasets
zfs create -o mountpoint=none tank/_incus

# Modèles IA — gros blobs séquentiels, déjà compressés
zfs create -o mountpoint=/srv/models -o recordsize=1M -o compression=off tank/_srv_models
zfs create tank/_srv_models_ollama
zfs create tank/_srv_models_stt

# Home
zfs create -o mountpoint=/home tank/_home

# État anklume (JSON, logs) — petit, quota de sécurité
zfs create -o mountpoint=/var/lib/anklume -o quota=10G tank/_var_lib_anklume

# Volumes partagés inter-domaines
zfs create -o mountpoint=/srv/shared tank/_srv_shared

# Backups, golden images — gros fichiers séquentiels
zfs create -o mountpoint=/srv/backups -o recordsize=1M tank/_srv_backups
```

### Propriétés par dataset

| Dataset | recordsize | compression | dedup | Justification |
|---|---|---|---|---|
| `tank/_incus` | 128K | zstd | off | Incus utilise les clones ZFS (partage de blocs natif) |
| `tank/_srv_models` | 1M | off | off | Blobs de plusieurs GB, déjà quantisés/compressés |
| `tank/_home` | 128K | zstd | off | Fichiers variés |
| `tank/_var_lib_anklume` | 128K | zstd | off | Petit dataset JSON/logs |
| `tank/_srv_shared` | 128K | zstd | off | Fichiers échangés via portails |
| `tank/_srv_backups` | 1M | zstd | off | Exports tar/images |

### Intégration Incus

```bash
incus storage create tank-zfs zfs source=tank/_incus
```

Incus crée ses propres sous-datasets (`tank/_incus/containers/xxx`,
`tank/_incus/images/yyy`, etc.) et les gère en autonomie.

---

## 3. Sécurité sans LUKS — injection de credentials

### Problème

Sans LUKS sur `/`, `/etc/shadow` contient le hash du mot de passe
en clair sur le disque. Même si un hash solide (yescrypt) est difficile
à brute-forcer, on peut faire mieux.

### Solution : shadow vide + injection au montage ZFS

Le hash du mot de passe est stocké sur ZFS chiffré. Le système boot
avec un compte verrouillé (aucun login possible). Au déverrouillage
du pool ZFS, un service systemd injecte le hash dans `/etc/shadow`.

```
Boot → /etc/shadow : compte verrouillé → aucun login possible
  ↓
Déverrouillage ZFS (passphrase)
  ↓
Service inject-shadow → usermod -p "$(cat hash)" user
  ↓
Login possible
```

En mode toram, `/etc/shadow` est en tmpfs → le hash disparaît au reboot.

### Configuration

**Stocker le hash sur ZFS** :

```bash
mkdir -p /home/.system
# Extraire le hash depuis shadow (après l'install avec mdp temporaire)
grep "^$(whoami):" /etc/shadow | cut -d: -f2 > /home/.system/shadow-hash
echo "$(whoami)" > /home/.system/shadow-user
chmod 600 /home/.system/shadow-hash /home/.system/shadow-user
```

**Verrouiller le compte** :

```bash
# Remplacer le hash par '!' (compte verrouillé)
sudo usermod -L $(whoami)
```

**Service systemd** :

```ini
# /etc/systemd/system/inject-shadow.service
[Unit]
Description=Injecter le hash utilisateur depuis ZFS chiffré
After=zfs-mount.service
Before=getty@.service display-manager.service sshd.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/inject-shadow.sh

[Install]
WantedBy=multi-user.target
```

**Script d'injection** :

```bash
#!/bin/sh
# /usr/local/sbin/inject-shadow.sh
set -eu
HASH_FILE="/home/.system/shadow-hash"
USER_FILE="/home/.system/shadow-user"
[ -f "$HASH_FILE" ] || exit 0
[ -f "$USER_FILE" ] || exit 0
USER=$(cat "$USER_FILE")
HASH=$(cat "$HASH_FILE")
usermod -p "$HASH" "$USER"
```

### Secrets NetworkManager sur ZFS

Les connexions WiFi (contenant les mots de passe) sont stockées sur
ZFS chiffré au lieu de `/etc` :

```ini
# /etc/NetworkManager/conf.d/secrets-on-zfs.conf
[keyfile]
path=/home/.system/nm-connections
```

```bash
mkdir -p /home/.system/nm-connections
# Migrer les connexions existantes
mv /etc/NetworkManager/system-connections/* /home/.system/nm-connections/
systemctl restart NetworkManager
```

Avant le déverrouillage ZFS, NetworkManager ne voit aucune connexion
enregistrée — pas de fuite de credentials.

---

## 4. Boot ordering — ZFS avant les services

### Déverrouillage automatique du pool chiffré

```ini
# /etc/systemd/system/zfs-load-key-tank.service
[Unit]
Description=Déverrouiller le pool ZFS tank
Before=zfs-mount.service
After=zfs-import.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/zfs load-key tank

[Install]
WantedBy=zfs-mount.service
```

### Incus après ZFS

```ini
# /etc/systemd/system/incus.service.d/after-zfs.conf
[Unit]
After=zfs-mount.service
Requires=zfs-mount.service
```

**Ordre de boot** :

```
zfs-import → zfs-load-key-tank → zfs-mount → inject-shadow → incus → getty/sshd
```

!!! warning "Passphrase au boot"
    Le service `zfs-load-key-tank` attend la passphrase sur la console.
    C'est la seule passphrase nécessaire — elle déverrouille les données
    ET active le login (via inject-shadow).
    Pour un serveur headless, envisager `keylocation=file:///root/.zfs-key`
    stocké sur une clé USB amovible.

---

## 5. Mode toram — OS immutable au runtime

Optionnel. Charge `/` en RAM au boot via overlayfs : le disque est
read-only, toutes les écritures vont en tmpfs (perdues au reboot).
Les données persistent via le pool ZFS.

Bonus sécurité : `/etc/shadow` est en tmpfs, le hash injecté disparaît
au reboot.

### Hook initramfs

```bash
#!/bin/sh
# /etc/initramfs-tools/scripts/init-bottom/toram
PREREQ=""
prereqs() { echo "$PREREQ"; }
case $1 in prereqs) prereqs; exit 0;; esac

# Actif seulement si BOOT_MODE=toram dans la cmdline kernel
grep -q "BOOT_MODE=toram" /proc/cmdline || exit 0

mkdir -p /mnt/lower /mnt/upper-tmpfs

# Déplacer le rootfs réel en read-only
mount -o remount,ro ${rootmnt}
mount -o move ${rootmnt} /mnt/lower

# tmpfs pour les écritures (taille = 80% RAM disponible)
mount -t tmpfs -o size=80% tmpfs /mnt/upper-tmpfs
mkdir -p /mnt/upper-tmpfs/upper /mnt/upper-tmpfs/work

# overlayfs : lower (disque ro) + upper (tmpfs rw)
mount -t overlay overlay \
  -o lowerdir=/mnt/lower,upperdir=/mnt/upper-tmpfs/upper,workdir=/mnt/upper-tmpfs/work \
  ${rootmnt}

# Rendre le disque accessible pour les mises à jour manuelles
mkdir -p ${rootmnt}/mnt/rootfs-disk
mount -o move /mnt/lower ${rootmnt}/mnt/rootfs-disk
```

```bash
chmod +x /etc/initramfs-tools/scripts/init-bottom/toram
update-initramfs -u
```

### Entrée GRUB

```bash
# /etc/grub.d/42_toram
#!/bin/sh
cat << 'EOF'
menuentry "Debian (toram — immutable)" {
    linux /vmlinuz root=UUID=<uuid-partition> ro BOOT_MODE=toram rootflags=subvol=@debian
    initrd /initrd.img
}
EOF
```

```bash
chmod +x /etc/grub.d/42_toram
update-grub
```

**Cycle de mise à jour** :

1. Booter en mode normal (sans `BOOT_MODE=toram`)
2. `apt upgrade`, configurations, etc.
3. Optionnel : `btrfs subvolume snapshot / /.snapshots/@debian-$(date +%F)`
4. Rebooter en mode toram — le système est immutable

---

## 6. NVIDIA GPU — driver .run + DKMS

### Prérequis

```bash
apt install linux-headers-$(uname -r) build-essential dkms pkg-config
```

### Blacklist nouveau

```bash
cat > /etc/modprobe.d/blacklist-nouveau.conf << 'EOF'
blacklist nouveau
options nouveau modeset=0
EOF
update-initramfs -u
reboot
```

### Installation

```bash
# Passer en mode texte (pas de serveur graphique)
systemctl isolate multi-user.target

# Installer avec DKMS (reconstruit le module à chaque kernel update)
chmod +x NVIDIA-Linux-x86_64-*.run
./NVIDIA-Linux-x86_64-*.run --dkms
```

### Vérification

```bash
nvidia-smi
# Doit afficher le GPU (modèle, VRAM, driver version)
```

!!! tip "Kernel updates"
    DKMS reconstruit automatiquement le module NVIDIA à chaque mise à
    jour du kernel. Vérifier après reboot avec `nvidia-smi`.

---

## 7. Premier déploiement anklume

Une fois l'hôte prêt :

```bash
# Installer anklume
uv tool install anklume

# Configurer le storage pool Incus sur ZFS
incus storage create tank-zfs zfs source=tank/_incus

# Créer un projet anklume
mkdir mon-infra && cd mon-infra
anklume init

# Éditer domains/*.yml selon les besoins
anklume tui

# Déployer
anklume apply all
anklume status
```

---

## 8. Script de bootstrap automatisé

Le script `host/bootstrap-host.sh` automatise les étapes 2 à 7
(sauf la création du pool ZFS et le partitionnement, qui restent
manuels par sécurité).

```bash
sudo ./host/bootstrap-host.sh
```

**Options** :

| Flag | Effet |
|---|---|
| `--skip-nvidia` | Ne pas installer le driver NVIDIA |
| `--skip-toram` | Ne pas configurer le mode toram |
| `--skip-zfs-datasets` | Ne pas créer les datasets ZFS |
| `--skip-credentials` | Ne pas migrer les credentials vers ZFS |
| `--nvidia-run <path>` | Chemin vers un `.run` NVIDIA spécifique |
| `-h`, `--help` | Afficher l'aide |

**Driver NVIDIA** : par défaut, le script auto-détecte un fichier
`NVIDIA-Linux-x86_64-*.run` dans le répertoire courant et l'installe
avec `--dkms --open --silent`. Le flag `--open` est requis pour les
GPU Blackwell (RTX PRO 5000, RTX 5090, etc.) qui exigent les open
kernel modules. Pour un GPU plus ancien (Turing, Ampere, Ada Lovelace),
les open modules fonctionnent aussi mais les propriétaires restent
supportés.

Pour surcharger le driver :

```bash
# GPU spécifique ou version précise
sudo ./host/bootstrap-host.sh --nvidia-run /tmp/NVIDIA-Linux-x86_64-595.44.run
```

Le script est **idempotent** : il détecte les composants déjà installés
et ne les recrée pas.

**Ce que fait le script** :

1. Installe les paquets (build-essential, dkms, zfs, incus, ansible, uv)
2. Crée les datasets ZFS selon la convention `_path` + le storage pool Incus
3. Migre les credentials vers ZFS (shadow hash, NetworkManager)
4. Configure systemd (déverrouillage ZFS → injection shadow → Incus)
5. Installe le hook initramfs toram + entrée GRUB
6. Blackliste nouveau et installe le driver NVIDIA `.run` avec DKMS
7. Installe anklume via uv

**Ce que le script ne fait PAS** (opérations manuelles) :

- Partitionnement du disque système (btrfs + subvolumes)
- Création du pool ZFS (`zpool create ... tank mirror ...`)
- Téléchargement du driver NVIDIA `.run`
