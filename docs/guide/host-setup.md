# Préparation de l'hôte

Guide de déploiement de référence pour un hôte AnKLuMe.

## Choix de la distribution

AnKLuMe est compatible avec n'importe quelle distribution GNU/Linux
disposant d'Incus et de ZFS. Le script de bootstrap supporte :

| Distribution | Support GPU récent | Remarques |
|---|---|---|
| **CachyOS** (recommandé) | Out of the box | Kernels optimisés (CachyOS, BORE scheduler), drivers NVIDIA pré-packagés, modules ZFS pré-compilés |
| Arch Linux | Manuellement | `nvidia-open-dkms` disponible, configuration manuelle requise |
| Debian 13+ | Limité | Kernel stock trop ancien pour les GPU très récents (Blackwell RTX 5000/5090), nécessite un `.run` NVIDIA |

**Pourquoi CachyOS ?** Les GPU NVIDIA récents (architecture Blackwell :
RTX PRO 5000, RTX 5090, etc.) nécessitent un kernel récent (≥ 6.12) et
les open kernel modules. CachyOS fournit tout cela out of the box via
ses dépôts (`nvidia-open-dkms`, modules ZFS pré-compilés, kernels
optimisés). Sur Debian, le kernel stock est souvent trop ancien pour le
matériel récent. Sur Arch vanilla, le support GPU fonctionne mais
demande plus de configuration manuelle.

AnKLuMe lui-même ne dépend pas de la distribution — seul le script de
bootstrap s'adapte au gestionnaire de paquets et au bootloader.

---

## Vue d'ensemble

```
Disque système (NVMe interne)         Pool ZFS "tank" (2x NVMe mirror)
┌─────────────────────────┐           ┌─────────────────────────────────────┐
│ p1  512M  EFI           │           │ tank/_home             → /home     │
│ p2  reste LUKS → btrfs  │           │ tank/_incus            → (Incus)   │
│   @cachyos  → /         │           │ tank/_srv_models       → /srv/…    │
│   @snapshots            │           │ tank/_srv_models_ollama → /srv/…   │
└─────────────────────────┘           │ tank/_srv_models_stt   → /srv/…    │
                                      │ tank/_srv_shared       → /srv/…    │
                                      │ tank/_srv_backups      → /srv/…    │
                                      │ tank/_var_lib_anklume  → …         │
                                      └─────────────────────────────────────┘
```

**Principes** :

- `/` sur btrfs avec subvolumes — multiboot, snapshots, espace partagé
- Données persistantes sur ZFS — chiffrement natif (keyfile raw), compression, mirror
- Mode toram optionnel — `/` chargé en RAM, immutable au runtime
- GPU NVIDIA via paquets distro (CachyOS/Arch) ou `.run` + DKMS (Debian)

---

## 1. Partitionnement et btrfs

### Schéma de partitions

| Partition | Taille | Type | Chiffrement | Usage |
|---|---|---|---|---|
| `/dev/nvmeXn1p1` | 512 MB | EFI (FAT32) | Non | `/boot/efi` |
| `/dev/nvmeXn1p2` | Reste | btrfs sur LUKS | Oui | Subvolumes `/` |

!!! note "Partition /boot séparée"
    Certaines distributions (Debian) nécessitent une partition `/boot`
    séparée (ext4, 1 Go). CachyOS et Arch n'en ont généralement pas
    besoin — le kernel est sur la partition EFI ou dans le subvolume.

### Création LUKS + btrfs

```bash
cryptsetup luksFormat /dev/nvmeXn1p2
cryptsetup open /dev/nvmeXn1p2 crypt-root
mkfs.btrfs -L rootfs /dev/mapper/crypt-root
```

### Subvolumes btrfs

Le multiboot utilise des subvolumes indépendants. Chaque OS a son
subvolume, ils partagent l'espace disque dynamiquement.

```bash
mount /dev/mapper/crypt-root /mnt
btrfs subvolume create /mnt/@cachyos
btrfs subvolume create /mnt/@snapshots
# Pour un second OS plus tard :
# btrfs subvolume create /mnt/@cachyos2
umount /mnt
```

**Montage dans fstab** (après installation) :

```
# /etc/fstab
/dev/mapper/crypt-root  /            btrfs  subvol=@cachyos,compress=zstd,noatime  0 1
/dev/mapper/crypt-root  /.snapshots  btrfs  subvol=@snapshots,compress=zstd,noatime  0 2
```

!!! tip "Snapshots avant mise à jour"
    ```bash
    btrfs subvolume snapshot / /.snapshots/@cachyos-$(date +%F)
    pacman -Syu   # ou apt upgrade sur Debian
    ```
    En cas de problème, booter sur le snapshot via le bootloader.

---

## 2. Pool ZFS — données persistantes

### Chiffrement par keyfile raw

Le pool ZFS est chiffré avec un keyfile aléatoire de 32 bytes
(`/etc/zfs/tank.key`). Ce keyfile est lui-même protégé par le LUKS du
disque système. Un backup chiffré par passphrase (`/etc/zfs/tank.key.enc`)
permet la récupération si le keyfile est perdu.

```
Déverrouillage automatique :
  LUKS (disque système) → keyfile /etc/zfs/tank.key → ZFS déverrouillé

Récupération de secours :
  passphrase → déchiffre tank.key.enc → keyfile → ZFS déverrouillé
```

### Convention de nommage

Les datasets portent le nom du chemin de montage avec `/` remplacé
par `_`. Cette convention rend la correspondance dataset ↔ mountpoint
immédiate.

| Dataset | Mountpoint | Raison |
|---|---|---|
| `tank/_incus` | (legacy — géré par Incus) | Storage pool Incus |
| `tank/_home` | `/home` | Données utilisateur |
| `tank/_srv_models` | `/srv/models` | Modèles IA (parent) |
| `tank/_srv_models_ollama` | `/srv/models/ollama` | Modèles Ollama |
| `tank/_srv_models_stt` | `/srv/models/stt` | Modèles STT/Whisper |
| `tank/_var_lib_anklume` | `/var/lib/anklume` | État anklume |
| `tank/_srv_shared` | `/srv/shared` | Volumes partagés inter-domaines |
| `tank/_srv_backups` | `/srv/backups` | Golden images, exports |

### Création du pool

```bash
# 1. Générer le keyfile (32 bytes aléatoires)
mkdir -p /etc/zfs
umask 077 && dd if=/dev/urandom of=/etc/zfs/tank.key bs=32 count=1
chmod 400 /etc/zfs/tank.key

# 2. Créer le pool avec chiffrement par keyfile raw
zpool create \
  -o ashift=12 \
  -o autotrim=on \
  -O acltype=posixacl \
  -O xattr=sa \
  -O dnodesize=auto \
  -O normalization=formD \
  -O relatime=on \
  -O compression=zstd \
  -O encryption=aes-256-gcm \
  -O keyformat=raw \
  -O keylocation=file:///etc/zfs/tank.key \
  -O mountpoint=none \
  tank mirror /dev/disk/by-id/<nvme-1> /dev/disk/by-id/<nvme-2>
```

!!! warning "Sauvegarder le keyfile"
    ```bash
    # Chiffrer une copie avec une passphrase de secours
    openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
        -salt -in /etc/zfs/tank.key -out /etc/zfs/tank.key.enc \
        -pass pass:<votre-passphrase>
    chmod 400 /etc/zfs/tank.key.enc
    ```
    Conserver la passphrase en lieu sûr. Elle permet de restaurer le
    keyfile et déverrouiller le pool si le disque système est perdu.

### Création des datasets

```bash
# Incus — mountpoint=legacy, Incus gère ses sous-datasets
zfs create -o mountpoint=legacy tank/_incus

# Modèles IA — gros blobs séquentiels, déjà compressés
zfs create -o mountpoint=/srv/models -o recordsize=1M -o compression=off tank/_srv_models
zfs create -o mountpoint=/srv/models/ollama tank/_srv_models_ollama
zfs create -o mountpoint=/srv/models/stt tank/_srv_models_stt

# Home (canmount=noauto pour ne pas masquer /home pendant l'installation)
zfs create -o mountpoint=/home -o canmount=noauto tank/_home

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

### Script de déverrouillage

Le bootstrap installe `/usr/local/bin/zfs-unlock-tank` qui tente dans
l'ordre :

1. Keyfile raw (`/etc/zfs/tank.key`)
2. Keylocation du pool (fallback)
3. Passphrase interactive → déchiffre le backup → restaure le keyfile

### Service systemd

```ini
# /etc/systemd/system/zfs-load-key-tank.service
[Unit]
Description=Déverrouiller le pool ZFS tank (keyfile puis passphrase)
DefaultDependencies=no
Before=zfs-mount.service
After=zfs-import.target
ConditionPathExists=/dev/zfs

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/zfs-unlock-tank
StandardInput=tty-force
StandardOutput=journal+console
StandardError=journal+console

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
zfs-import → zfs-unlock-tank → zfs-mount → incus → services applicatifs
```

---

## 4. Mode toram — OS immutable au runtime

Optionnel. Charge `/` en RAM au boot via overlayfs : le disque est
read-only, toutes les écritures vont en tmpfs (perdues au reboot).
Les données persistent via le pool ZFS.

Le bootstrap configure automatiquement le hook initcpio/initramfs et
l'entrée bootloader selon la distribution :

| Distribution | Hook | Bootloader |
|---|---|---|
| CachyOS / Arch | mkinitcpio (`/usr/lib/initcpio/hooks/toram`) | Limine ou GRUB |
| Debian | initramfs-tools (`/etc/initramfs-tools/scripts/init-bottom/toram`) | GRUB |

**Cycle de mise à jour** :

1. Booter en mode normal (sans `BOOT_MODE=toram`)
2. `pacman -Syu` (ou `apt upgrade`), configurations, etc.
3. Optionnel : `btrfs subvolume snapshot / /.snapshots/@pre-toram`
4. Rebooter en mode toram — le système est immutable

---

## 5. NVIDIA GPU

### CachyOS / Arch (recommandé)

```bash
sudo pacman -S nvidia-open-dkms nvidia-utils
```

CachyOS fournit les drivers pré-packagés et les open kernel modules
requis par les GPU Blackwell. Rien d'autre à faire.

### Debian

Le bootstrap détecte automatiquement le GPU et installe le bon driver :

- **GPU pré-Blackwell** (Turing, Ampere, Ada Lovelace) : `nvidia-driver` +
  `nvidia-open-kernel-dkms` depuis les dépôts Debian (non-free activé auto)
- **GPU Blackwell** (RTX 50xx) : le driver 570+ n'est pas dans les dépôts
  Debian. Le bootstrap télécharge et installe automatiquement le `.run`
  NVIDIA avec `--dkms --open --silent`

Installation manuelle (si besoin) :

```bash
# Prérequis
apt install linux-headers-$(uname -r) build-essential dkms pkg-config

# Blacklist nouveau
cat > /etc/modprobe.d/blacklist-nouveau.conf << 'EOF'
blacklist nouveau
options nouveau modeset=0
EOF
update-initramfs -u && reboot

# Installer (après reboot, en mode texte)
chmod +x NVIDIA-Linux-x86_64-*.run
./NVIDIA-Linux-x86_64-*.run --dkms --open
```

### Vérification

```bash
nvidia-smi
# Doit afficher le GPU (modèle, VRAM, driver version)
```

---

## 6. Premier déploiement AnKLuMe

Une fois l'hôte prêt :

```bash
# Créer un projet AnKLuMe
anklume init mon-infra && cd mon-infra

# Éditer domains/*.yml selon les besoins
anklume tui

# Déployer
anklume apply all
anklume status
```

!!! note "Raccourci"
    `ank` est un alias pour `anklume`, configuré automatiquement
    par le bootstrap dans bash, zsh et fish.

---

## 7. Script de bootstrap automatisé

Le script `host/bootstrap.sh` automatise toutes les étapes ci-dessus.
Il détecte automatiquement la distribution (CachyOS, Arch, Debian) et
adapte les commandes en conséquence.

```bash
sudo ./host/bootstrap.sh \
    --zfs-disk1 nvme-Corsair_MP600_XXX \
    --zfs-disk2 nvme-Corsair_MP600_YYY
```

**Options** :

| Flag | Effet |
|---|---|
| `--zfs-disk1 <by-id>` | Disque ZFS mirror leg 1 (obligatoire si pool à créer) |
| `--zfs-disk2 <by-id>` | Disque ZFS mirror leg 2 (obligatoire si pool à créer) |
| `--skip-nvidia` | Ne pas vérifier le driver NVIDIA |
| `--skip-toram` | Ne pas configurer le mode toram |
| `--skip-zfs-pool` | Ne pas créer le pool ZFS |
| `--skip-incus` | Ne pas configurer Incus |
| `--zfs-passphrase` | Lire la passphrase depuis stdin (non interactif) |
| `-h`, `--help` | Afficher l'aide |

Le script est **idempotent** : il détecte les composants déjà installés
et ne les recrée pas.

**Ce que fait le script** :

1. Détecte la distribution (CachyOS, Arch, Debian)
2. Installe les paquets (dkms, zfs, incus, ansible, uv)
3. Crée le pool ZFS chiffré (keyfile raw + backup passphrase)
4. Crée les datasets ZFS selon la convention `_path`
5. Configure systemd (déverrouillage ZFS → montage → Incus)
6. Configure le storage pool Incus sur ZFS
7. Détecte le GPU NVIDIA et installe le driver adapté (Blackwell → .run auto)
8. Installe le hook toram + entrée bootloader (Limine ou GRUB)
9. Monte `/home` ZFS avec les bons droits utilisateur
10. Installe AnKLuMe via uv + alias `ank` (bash, zsh, fish)

**Ce que le script ne fait PAS** (opérations manuelles) :

- Partitionnement du disque système (LUKS + btrfs)
- Installation de la distribution

---

## 8. Installation rapide (quickstart)

Pour essayer AnKLuMe sur un système existant, sans ZFS ni toram :

```bash
# Minimum : Incus + AnKLuMe
sudo ./host/quickstart.sh

# Avec support GPU (pour tester ai-tools)
sudo ./host/quickstart.sh --gpu
```

Le quickstart installe uniquement : Incus, uv, Ansible, AnKLuMe et
l'alias `ank`. Pas de ZFS, pas de toram, pas de partitionnement.
Idéal pour découvrir AnKLuMe avant de passer au bootstrap complet.

---

## 9. Test matériel via ISO live (FAI.me)

Avant d'installer sur du matériel neuf, il est possible de générer une
ISO Debian live via [FAI.me](https://fai-project.org/FAIme/live/) pour
tester la compatibilité (GPU, réseau, stockage).

```bash
# Voir la commande sans exécuter
./host/faime/build-iso.sh --dry-run

# Générer l'ISO (KDE, backports, NVIDIA auto-detect)
./host/faime/build-iso.sh --email moi@example.com

# Sans bureau (headless)
./host/faime/build-iso.sh --desktop none
```

L'ISO inclut :

- Debian trixie + **backports** (kernel récent)
- Firmware non-free (WiFi, GPU)
- Incus, ZFS, Ansible pré-installés
- Détection NVIDIA automatique (Blackwell → driver .run 570+)
- AnKLuMe pré-installé avec alias `ank`

**Workflow** :

1. Générer l'ISO → télécharger → `dd` sur clé USB
2. Booter → tester GPU (`nvidia-smi`), réseau, stockage
3. Si tout fonctionne → installer ou lancer `bootstrap.sh`
