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

1. Détecte la distribution (CachyOS, Arch, Debian)
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

| Distribution | Support GPU récent | Remarques |
|---|---|---|
| **CachyOS** (recommandé) | Out of the box | Kernels optimisés, drivers NVIDIA pré-packagés, modules ZFS pré-compilés |
| Arch Linux | Manuellement | `nvidia-open-dkms` disponible, configuration manuelle requise |
| Debian 13+ | Limité | Kernel stock trop ancien pour Blackwell (RTX 50xx), nécessite `.run` NVIDIA |

**Pourquoi CachyOS ?** Les GPU NVIDIA récents (architecture Blackwell)
nécessitent un kernel ≥ 6.12 et les open kernel modules. CachyOS
fournit tout cela out of the box. Sur Debian, le kernel stock est
souvent trop ancien. Sur Arch vanilla, ça fonctionne mais demande
plus de configuration manuelle.

### Exécuter le bootstrap

```bash
# 1. Récupérer le dépôt
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe/host

# 2. Lire le script (1200+ lignes, bien commenté)
less bootstrap.sh

# 3. Identifier les disques ZFS
ls /dev/disk/by-id/ | grep nvme

# 4. Exécuter
sudo ./bootstrap.sh \
    --zfs-disk1 nvme-Corsair_MP600_XXX \
    --zfs-disk2 nvme-Corsair_MP600_YYY
```

!!! warning "Alternative non recommandée"
    ```bash
    curl -fsSL https://raw.githubusercontent.com/jmchantrein/AnKLuMe/main/host/bootstrap.sh \
        | sudo bash -s -- --zfs-disk1 nvme-XXX --zfs-disk2 nvme-YYY
    ```

### Options

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

### Ce que fait le script

1. Détecte la distribution (CachyOS, Arch, Debian)
2. Installe les paquets (dkms, zfs, incus, ansible, uv)
3. Crée le pool ZFS chiffré (keyfile raw + backup passphrase)
4. Crée les datasets ZFS (Incus, /home, modèles IA, backups, etc.)
5. Configure systemd (déverrouillage ZFS → montage → Incus)
6. Configure le storage pool Incus sur ZFS
7. Détecte le GPU NVIDIA et installe le driver adapté
8. Installe le hook toram + entrée bootloader (Limine ou GRUB)
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
│   @cachyos  → /         │           │ tank/_srv_models       → /srv/…    │
│   @snapshots            │           │ tank/_srv_models_ollama → /srv/…   │
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
- GPU NVIDIA via paquets distro (CachyOS/Arch) ou `.run` + DKMS (Debian)

### Détails techniques

Le script `bootstrap.sh` est exhaustivement commenté (1200+ lignes).
Pour comprendre le détail de chaque étape, lire directement le script.
Les sections principales :

| Fonction | Rôle |
|---|---|
| `detect_distro()` | Détection CachyOS/Arch/Debian, choix du gestionnaire de paquets |
| `install_base_packages()` | dkms, zfs, incus, ansible, uv |
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
