# Préparation de l'hôte

Guide de déploiement de référence pour un hôte anklume :
Debian 13 + LUKS + btrfs (multiboot) + ZFS (données) + NVIDIA GPU.

## Vue d'ensemble

```
Disque système (NVMe interne)         Pool ZFS "tank" (2x NVMe mirror)
┌─────────────────────────┐           ┌──────────────────────────────┐
│ p1  512M  EFI           │           │ tank/_home        → /home   │
│ p2  1G    /boot (ext4)  │           │ tank/_incus       → (Incus) │
│ p3  reste LUKS → btrfs  │           │ tank/_srv_models  → /srv/…  │
│   @debian   → /         │           │ tank/_srv_shared  → /srv/…  │
│   @debian2  → / (spare) │           │ tank/_srv_backups → /srv/…  │
│   @snapshots            │           │ tank/_var_lib_anklume → …   │
└─────────────────────────┘           └──────────────────────────────┘
```

**Principes** :

- `/` sur btrfs avec subvolumes — multiboot, snapshots, espace partagé
- Données persistantes sur ZFS — chiffrement natif, compression, mirror
- Mode toram optionnel — `/` chargé en RAM, immutable au runtime
- GPU NVIDIA via `.run` + DKMS — compatible kernel updates

---

## 1. Partitionnement et btrfs

### Schéma de partitions

| Partition | Taille | Type | Chiffrement | Usage |
|---|---|---|---|---|
| `/dev/nvmeXn1p1` | 512 MB | EFI (FAT32) | Non | `/boot/efi` |
| `/dev/nvmeXn1p2` | 1 GB | ext4 | Non | `/boot` (kernels, initramfs) |
| `/dev/nvmeXn1p3` | Reste | btrfs sur LUKS | Oui | Subvolumes `/` |

### Création LUKS + btrfs

```bash
cryptsetup luksFormat /dev/nvmeXn1p3
cryptsetup open /dev/nvmeXn1p3 crypt-root
mkfs.btrfs -L rootfs /dev/mapper/crypt-root
```

### Subvolumes btrfs

Le multiboot utilise des subvolumes indépendants. Chaque OS a son
subvolume, ils partagent l'espace disque dynamiquement.

```bash
mount /dev/mapper/crypt-root /mnt
btrfs subvolume create /mnt/@debian
btrfs subvolume create /mnt/@snapshots
# Pour un second OS plus tard :
# btrfs subvolume create /mnt/@debian2
umount /mnt
```

**Montage dans fstab** (après installation) :

```
# /etc/fstab
/dev/mapper/crypt-root  /            btrfs  subvol=@debian,compress=zstd,noatime  0 1
/dev/mapper/crypt-root  /.snapshots  btrfs  subvol=@snapshots,compress=zstd,noatime  0 2
```

**Multiboot** — chaque subvolume peut être booté indépendamment via
GRUB (`rootflags=subvol=@debianN`). L'espace disque est partagé :
supprimer un subvolume libère l'espace pour les autres.

!!! tip "Snapshots avant mise à jour"
    ```bash
    btrfs subvolume snapshot / /.snapshots/@debian-$(date +%F)
    apt upgrade
    ```
    En cas de problème, booter sur le snapshot via GRUB.

---

## 2. Pool ZFS — données persistantes

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

## 3. Boot ordering — ZFS avant les services

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
zfs-import → zfs-load-key-tank → zfs-mount → incus → services applicatifs
```

!!! warning "Passphrase au boot"
    Le service `zfs-load-key-tank` attend la passphrase sur la console.
    Pour un serveur headless, envisager `keylocation=file:///root/.zfs-key`
    (protégé par le LUKS du disque système).

---

## 4. Mode toram — OS immutable au runtime

Optionnel. Charge `/` en RAM au boot via overlayfs : le disque est
read-only, toutes les écritures vont en tmpfs (perdues au reboot).
Les données persistent via le pool ZFS.

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
    linux /vmlinuz root=UUID=<uuid-luks> ro BOOT_MODE=toram rootflags=subvol=@debian
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
3. Optionnel : `btrfs subvolume snapshot / /.snapshots/@pre-toram`
4. Rebooter en mode toram — le système est immutable

---

## 5. NVIDIA GPU — driver .run + DKMS

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

## 6. Premier déploiement anklume

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

## 7. Script de bootstrap automatisé

Le script `host/bootstrap-host.sh` automatise les étapes 1 à 6
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
3. Configure systemd (déverrouillage ZFS → montage → Incus)
4. Installe le hook initramfs toram + entrée GRUB
5. Blackliste nouveau et installe le driver NVIDIA `.run` avec DKMS
6. Installe anklume via uv

**Ce que le script ne fait PAS** (opérations manuelles) :

- Partitionnement du disque système (LUKS + btrfs)
- Création du pool ZFS (`zpool create ... tank mirror ...`)
- Téléchargement du driver NVIDIA `.run`
