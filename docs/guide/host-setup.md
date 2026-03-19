# Préparation de l'hôte

AnKLuMe tourne sur n'importe quelle distribution GNU/Linux disposant
d'Incus. Deux chemins d'installation :

| Chemin | Script | Pour qui |
|---|---|---|
| **Installation rapide** | `host/quickstart.sh` | Découvrir AnKLuMe sur un système existant |
| **Configuration complète** | `host/bootstrap.sh` | Station dédiée, ZFS chiffré, GPU récent, toram |

---

## Installation rapide

Le script `host/quickstart.sh` installe le minimum pour utiliser
AnKLuMe : Incus, uv, Ansible, AnKLuMe et l'alias `ank`.

Pas de ZFS, pas de toram, pas de partitionnement. Idéal pour un
premier contact.

### Méthode recommandée : télécharger, lire, exécuter

```bash
# 1. Récupérer le script
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe/host

# 2. Lire le script avant de l'exécuter
less quickstart.sh

# 3. Exécuter
sudo ./quickstart.sh

# Avec support GPU (pour tester ai-tools)
sudo ./quickstart.sh --gpu
```

!!! warning "Alternative non recommandée"
    ```bash
    curl -fsSL https://raw.githubusercontent.com/jmchantrein/AnKLuMe/main/host/quickstart.sh | sudo bash
    ```
    Préférer toujours télécharger et lire un script avant de l'exécuter
    en root.

### Options

| Flag | Effet |
|---|---|
| `--gpu` | Installer aussi le driver NVIDIA |
| `-h`, `--help` | Afficher l'aide |

### Ce que fait le script

1. Détecte la distribution (Arch Linux, Debian)
2. Installe les paquets de base (curl, git, jq, tmux, ansible)
3. Configure Incus (init minimal, groupe `incus-admin`)
4. Installe AnKLuMe via uv + alias `ank` (bash, zsh, fish)
5. Optionnel : détecte le GPU NVIDIA et installe le driver adapté

Le script est **idempotent** : il peut être relancé sans danger.

### Après l'installation

```bash
# Créer un premier projet
anklume init mon-infra && cd mon-infra

# Éditer les domaines
anklume tui

# Déployer
anklume apply all
anklume status
```

!!! tip "Raccourci"
    `ank` est un alias pour `anklume`, configuré automatiquement
    par le script dans bash, zsh et fish.

---

## Configuration complète

Pour une station dédiée avec du matériel récent (GPU Blackwell,
multi-NVMe). Le script `host/bootstrap.sh` automatise l'ensemble :
ZFS chiffré en mirror, systemd, GPU, toram optionnel, AnKLuMe.

### Prérequis matériel (exemple)

- 1 NVMe système (OS déjà installé avec LUKS + btrfs)
- 2 NVMe données (pour le pool ZFS en mirror)
- GPU NVIDIA (optionnel)

### Choix de la distribution

| Distribution | GPU récent (Blackwell) | ZFS | Remarques |
|---|---|---|---|
| **Arch Linux** | `nvidia-open` dans les dépôts | Dépôt [archzfs](https://github.com/archzfs/archzfs) (auto-configuré) | Recommandé pour le matériel récent |
| **Debian 13+** | `.run` NVIDIA nécessaire | `zfsutils-linux` dans les dépôts | Recommandé sinon — stable, prévisible |

**Arch Linux** est recommandé quand le matériel est récent (GPU NVIDIA
Blackwell RTX 50xx, NVMe récents). Le kernel rolling fournit les
drivers nécessaires (`nvidia-open`) directement dans les dépôts.

**Debian** est recommandé pour le matériel plus ancien ou quand la
stabilité prime. Le kernel stock peut être trop ancien pour les GPU
Blackwell, nécessitant le driver `.run` NVIDIA.

!!! note "ZFS sur Arch Linux"
    ZFS n'est pas dans les dépôts officiels d'Arch (incompatibilité
    de licence CDDL/GPL). Le bootstrap configure automatiquement le
    dépôt [archzfs](https://github.com/archzfs/archzfs) (clé PGP
    importée, signature vérifiée) et installe **linux-lts** comme
    kernel obligatoire. Le kernel rolling d'Arch peut casser ZFS
    entre deux mises à jour — `linux-lts` garantit la compatibilité.
    Après le bootstrap, **booter sur linux-lts dans GRUB**.

!!! tip "Configuration système attendue"
    Le bootstrap suppose la configuration suivante :

    - **Bootloader** : GRUB
    - **Kernel** : `linux-lts` (installé par le bootstrap sur Arch, obligatoire pour ZFS)
    - **Chiffrement** : LUKS2 sur la partition système
    - **Filesystem** : btrfs avec deux sous-volumes : `@` (/) et `@.snapshots` (/.snapshots)
    - **Partition EFI** : FAT32 montée sur `/boot/efi`
    - **Home** : sur ZFS (créé par le bootstrap)
    - **Snapshots** : Snapper (config `root`) + snap-pac + grub-btrfs + btrfs-assistant
    - **GPU** : `nvidia-open` (modules open source)

!!! tip "Paquets recommandés pour les snapshots"
    Sur Arch Linux, installer `snap-pac` (snapshots automatiques
    avant/après chaque `pacman`) et `btrfs-assistant` (interface
    graphique pour gérer les snapshots et rollbacks) :

    ```bash
    sudo pacman -S snap-pac btrfs-assistant
    ```

### Exécuter le bootstrap

```bash
# 1. Récupérer le dépôt
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe/host

# 2. Lire le script (1400+ lignes, bien commenté)
less bootstrap.sh

# 3. Exécuter — n'importe quel format de disque accepté
sudo ./bootstrap.sh \
    --zfs-disk1 /dev/nvme0n1 \
    --zfs-disk2 /dev/nvme1n1
```

Le script résout automatiquement tout format vers **by-id** avant de
créer le pool ZFS. Les trois formats suivants sont équivalents :

| Format | Exemple | Résolu vers |
|---|---|---|
| Device classique | `/dev/nvme0n1` | `/dev/disk/by-id/nvme-Corsair_MP600_XXX` |
| by-id nu | `nvme-Corsair_MP600_XXX` | `/dev/disk/by-id/nvme-Corsair_MP600_XXX` |
| by-id complet | `/dev/disk/by-id/nvme-Corsair_MP600_XXX` | (utilisé tel quel) |

!!! info "Pourquoi by-id ?"
    Les chemins `/dev/nvmeXnY` dépendent de l'ordre d'énumération du
    kernel au boot. Ajouter un NVMe, mettre à jour le BIOS ou changer
    un slot peut réassigner les numéros. `by-id` utilise le numéro de
    série hardware du disque : **stable et unique**.

    `/dev/disk/by-uuid/` ne fonctionne pas ici : les UUIDs sont des
    identifiants de **filesystem**. Un disque vierge destiné à ZFS n'a
    pas de filesystem — donc pas d'UUID. Le by-id est le seul
    identifiant stable pour un block device brut.

!!! warning "Alternative non recommandée"
    ```bash
    curl -fsSL https://raw.githubusercontent.com/jmchantrein/AnKLuMe/main/host/bootstrap.sh \
        | sudo bash -s -- --zfs-disk1 /dev/nvme0n1 --zfs-disk2 /dev/nvme1n1
    ```

### Options

| Flag | Effet |
|---|---|
| `--zfs-disk1 <disque>` | Disque ZFS mirror leg 1 — tout format accepté (auto-résolu vers by-id) |
| `--zfs-disk2 <disque>` | Disque ZFS mirror leg 2 — tout format accepté (auto-résolu vers by-id) |
| `--skip-nvidia` | Ne pas vérifier le driver NVIDIA |
| `--skip-toram` | Ne pas configurer le mode toram |
| `--skip-zfs-pool` | Ne pas créer le pool ZFS |
| `--skip-incus` | Ne pas configurer Incus |
| `--zfs-passphrase` | Lire la passphrase depuis stdin (non interactif) |
| `-h`, `--help` | Afficher l'aide |

### Ce que fait le script

1. Détecte la distribution (Arch, Debian)
2. Configure le dépôt archzfs + linux-lts (Arch) ou apt (Debian), installe ZFS, Incus, Ansible, uv
3. Crée le pool ZFS chiffré (keyfile raw + backup passphrase)
4. Crée les datasets ZFS (Incus, /home, modèles IA, backups, etc.)
5. Configure systemd (déverrouillage ZFS → montage → Incus)
6. Configure le storage pool Incus sur ZFS
7. Détecte le GPU NVIDIA et installe le driver adapté
8. Installe le hook toram + entrée bootloader GRUB
9. Monte `/home` ZFS avec les bons droits utilisateur
10. Installe AnKLuMe via uv + alias `ank`

**Ce que le script ne fait PAS** (opérations manuelles) :

- Partitionnement du disque système (LUKS + btrfs)
- Installation de la distribution

Le script est **idempotent** : il détecte les composants déjà installés
et ne les recrée pas.

### Architecture résultante

```
Disque système (NVMe)                 Pool ZFS "tank" (2x NVMe mirror)
┌─────────────────────────┐           ┌─────────────────────────────────────┐
│ p1  512M  EFI           │           │ tank/_home             → /home     │
│ p2  reste LUKS → btrfs  │           │ tank/_incus            → (Incus)   │
│   @           → /        │           │ tank/_srv_models       → /srv/…    │
│   @.snapshots → /.snapshots │       │ tank/_srv_models_ollama → /srv/…   │
└─────────────────────────┘           │ tank/_srv_models_stt   → /srv/…    │
                                      │ tank/_srv_shared       → /srv/…    │
                                      │ tank/_srv_backups      → /srv/…    │
                                      │ tank/_var_lib_anklume  → …         │
                                      └─────────────────────────────────────┘
```

**Principes** :

- `/` sur btrfs avec subvolumes — multiboot, snapshots
- Données persistantes sur ZFS — chiffrement natif (keyfile raw), compression, mirror
- Mode toram optionnel — `/` chargé en RAM, immutable au runtime
- Kernel `linux-lts` obligatoire sur Arch (stabilité ZFS)
- GPU NVIDIA via `nvidia-open` (Arch) ou `.run` + DKMS (Debian)

### Détails techniques

Le script `bootstrap.sh` est exhaustivement commenté (1200+ lignes).
Pour comprendre le détail de chaque étape, lire directement le script.
Les sections principales :

| Fonction | Rôle |
|---|---|
| `detect_distro()` | Détection Arch/Debian, choix du gestionnaire de paquets |
| `setup_archzfs_repo()` | (Arch) Dépôt archzfs + clé PGP dans pacman.conf |
| `install_base_packages()` | linux-lts, dkms, zfs, incus, ansible, uv |
| `create_zfs_pool()` | Pool chiffré AES-256-GCM, keyfile raw 32 bytes, mirror |
| `create_zfs_datasets()` | 7 datasets avec mountpoints et propriétés adaptées |
| `setup_systemd()` | Service de déverrouillage ZFS + dépendance Incus |
| `setup_incus()` | Init minimal + storage pool sur `tank/_incus` |
| `setup_nvidia()` | Auto-détection GPU, driver standard ou Blackwell (.run 570+) |
| `setup_toram()` | Hook initcpio/initramfs + entrée bootloader |
| `install_anklume()` | uv + alias ank (bash/zsh/fish) |

### Chiffrement ZFS

```
Déverrouillage automatique :
  LUKS (disque système) → keyfile /etc/zfs/tank.key → ZFS déverrouillé

Récupération de secours :
  passphrase → déchiffre tank.key.enc → keyfile → ZFS déverrouillé
```

Le keyfile de 32 bytes est protégé par le LUKS du disque système.
Un backup chiffré par passphrase permet la récupération si le keyfile
est perdu. Le script gère la création des deux automatiquement.

### Ordre de boot

```
zfs-import → zfs-unlock-tank → zfs-mount → incus → services applicatifs
```

---

## Test matériel via ISO live (FAI.me)

Avant d'installer sur du matériel neuf, générer une ISO via le service
web [FAI.me](https://fai-project.org/FAIme/) pour tester la
compatibilité (GPU, réseau, stockage).

| Type | URL | Usage |
|---|---|---|
| Debian live | [FAIme/live](https://fai-project.org/FAIme/live) | Test matériel sans toucher au disque |
| Debian install | [FAIme/](https://fai-project.org/FAIme/) | Installation hors-ligne sur disque |
| Ubuntu / Mint | [FAIme-ubuntu](https://fai-project.org/FAIme-ubuntu) | Ubuntu 24.04, Mint 22.2 |

**Réglages recommandés** sur le formulaire :

- Distribution : **trixie** (Debian) ou **Ubuntu 24.04**
- Backports / HWE : coché (kernel récent pour matériel récent)
- Non-free firmware : coché
- Paquets : `curl git jq tmux build-essential dkms ansible-core zfsutils-linux incus nftables pciutils lshw`
- Custom script : uploader `host/faime/postinst.sh`
- Execute during first boot : coché

Le `postinst.sh` détecte le GPU NVIDIA, installe le driver adapté,
configure Incus et installe AnKLuMe.

**Workflow** :

1. Remplir le formulaire FAI.me → "Create image" (~30 min)
2. Télécharger l'ISO → `dd if=fai-*.iso of=/dev/sdX bs=4M`
3. Booter → tester GPU (`nvidia-smi`), réseau, stockage
4. Si OK → installer ou lancer `bootstrap.sh`
