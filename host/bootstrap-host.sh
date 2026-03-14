#!/usr/bin/env bash
# bootstrap-host.sh — Prépare un hôte Debian 13 pour anklume
#
# Prérequis :
#   - Debian 13 installé (btrfs recommandé, voir docs/guide/host-setup.md)
#   - Pool ZFS "tank" déjà créé (chiffrement, mirror, etc.)
#   - Exécuter en root
#
# Usage :
#   sudo ./bootstrap-host.sh [options]
#
# Options :
#   --skip-nvidia         Ne pas installer le driver NVIDIA
#   --skip-toram          Ne pas configurer le mode toram
#   --skip-zfs-datasets   Ne pas créer les datasets ZFS
#   --skip-credentials    Ne pas migrer les credentials vers ZFS
#   --nvidia-run <path>   Chemin vers le .run NVIDIA (défaut : auto-détecté)
#
# Ce script est idempotent : il peut être relancé sans danger.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

POOL="tank"
INCUS_STORAGE="tank-zfs"
SYSTEM_DIR="/home/.system"

# Driver NVIDIA par défaut pour RTX PRO 5000 Blackwell (open kernel modules)
# Surcharger avec --nvidia-run <chemin> si nécessaire.
NVIDIA_RUN=""
NVIDIA_INSTALL_FLAGS=(--dkms --open --silent)

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

# Flags
SKIP_NVIDIA=false
SKIP_TORAM=false
SKIP_ZFS_DATASETS=false
SKIP_CREDENTIALS=false

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-nvidia)       SKIP_NVIDIA=true; shift ;;
        --skip-toram)        SKIP_TORAM=true; shift ;;
        --skip-zfs-datasets) SKIP_ZFS_DATASETS=true; shift ;;
        --skip-credentials)  SKIP_CREDENTIALS=true; shift ;;
        --nvidia-run)
            if [[ -z "${2:-}" ]]; then
                echo "Erreur : --nvidia-run nécessite un chemin." >&2
                exit 1
            fi
            NVIDIA_RUN="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '2,/^$/s/^# \?//p' "$0"
            exit 0
            ;;
        *)
            echo "Option inconnue : $1" >&2
            echo "Usage : $0 [--skip-nvidia] [--skip-toram] [--skip-zfs-datasets] [--skip-credentials] [--nvidia-run <path>]"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERREUR]${NC} $1" >&2; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "Ce script doit être exécuté en root (sudo)."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# 1. Paquets de base
# ---------------------------------------------------------------------------

install_base_packages() {
    info "Installation des paquets de base..."

    apt-get update -qq || { error "apt-get update échoué (miroirs injoignables ?)"; exit 1; }

    # Essentiels
    apt-get install -y -qq \
        build-essential \
        dkms \
        pkg-config \
        curl \
        git \
        tmux \
        jq \
        "linux-headers-$(uname -r)" \
        > /dev/null

    # ZFS (si pas déjà installé)
    if ! command -v zfs &> /dev/null; then
        apt-get install -y -qq zfsutils-linux > /dev/null
    fi

    # Incus
    if ! command -v incus &> /dev/null; then
        apt-get install -y -qq incus > /dev/null
        incus admin init --minimal || { error "incus admin init échoué"; exit 1; }
        info "Incus installé et initialisé."
    else
        info "Incus déjà installé."
    fi

    # Ansible
    if ! command -v ansible-playbook &> /dev/null; then
        apt-get install -y -qq ansible-core > /dev/null
    fi

    # uv (Python package manager)
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        info "uv installé. Ajouter ~/.local/bin au PATH si nécessaire."
    fi

    info "Paquets de base OK."
}

# ---------------------------------------------------------------------------
# 2. Datasets ZFS
# ---------------------------------------------------------------------------

create_zfs_datasets() {
    if [[ "$SKIP_ZFS_DATASETS" == true ]]; then
        info "Datasets ZFS : ignoré (--skip-zfs-datasets)."
        return
    fi

    if ! zpool list "$POOL" &> /dev/null; then
        error "Pool ZFS '$POOL' introuvable. Créez-le d'abord (voir docs/guide/host-setup.md)."
        exit 1
    fi

    info "Création des datasets ZFS (idempotent)..."

    # Helper : créer un dataset s'il n'existe pas
    ensure_dataset() {
        local name="$1"
        shift
        if ! zfs list "$name" &> /dev/null; then
            zfs create "$@" "$name"
            info "  Créé : $name"
        else
            info "  Existe : $name"
        fi
    }

    # Incus — mountpoint=none, Incus gère ses sous-datasets
    ensure_dataset "${POOL}/_incus" -o mountpoint=none

    # Modèles IA — gros blobs, déjà compressés
    ensure_dataset "${POOL}/_srv_models" -o mountpoint=/srv/models -o recordsize=1M -o compression=off
    ensure_dataset "${POOL}/_srv_models_ollama"
    ensure_dataset "${POOL}/_srv_models_stt"

    # Home
    ensure_dataset "${POOL}/_home" -o mountpoint=/home

    # État anklume
    ensure_dataset "${POOL}/_var_lib_anklume" -o mountpoint=/var/lib/anklume -o quota=10G

    # Volumes partagés
    ensure_dataset "${POOL}/_srv_shared" -o mountpoint=/srv/shared

    # Backups
    ensure_dataset "${POOL}/_srv_backups" -o mountpoint=/srv/backups -o recordsize=1M

    # Incus storage pool
    if ! incus storage show "$INCUS_STORAGE" &> /dev/null 2>&1; then
        incus storage create "$INCUS_STORAGE" zfs source="${POOL}/_incus"
        info "Storage pool Incus '${INCUS_STORAGE}' créé."
    else
        info "Storage pool Incus '${INCUS_STORAGE}' existe déjà."
    fi

    info "Datasets ZFS OK."
}

# ---------------------------------------------------------------------------
# 3. Migration des credentials vers ZFS
# ---------------------------------------------------------------------------

setup_credentials() {
    if [[ "$SKIP_CREDENTIALS" == true ]]; then
        info "Migration credentials : ignoré (--skip-credentials)."
        return
    fi

    # Vérifier que /home est bien monté (ZFS)
    if ! mountpoint -q /home; then
        warn "/home n'est pas un point de montage. Credentials non migrés."
        warn "Relancez après le montage ZFS."
        return
    fi

    info "Migration des credentials vers ZFS chiffré..."

    mkdir -p "$SYSTEM_DIR"
    chmod 700 "$SYSTEM_DIR"

    # --- Shadow hash ---
    # Détecter le premier utilisateur non-root avec un vrai shell
    local target_user
    target_user=$(awk -F: '$3 >= 1000 && $7 ~ /\/(bash|zsh|fish)$/ { print $1; exit }' /etc/passwd)

    if [[ -z "$target_user" ]]; then
        warn "Aucun utilisateur standard trouvé. Shadow hash non migré."
    elif [[ -f "${SYSTEM_DIR}/shadow-hash" ]]; then
        info "  Shadow hash déjà migré (${SYSTEM_DIR}/shadow-hash)."
    else
        # Extraire le hash du mot de passe
        local hash
        hash=$(grep "^${target_user}:" /etc/shadow | cut -d: -f2)

        if [[ "$hash" == "!" ]] || [[ "$hash" == "*" ]] || [[ -z "$hash" ]]; then
            warn "  Utilisateur '${target_user}' n'a pas de mot de passe. Shadow non migré."
        else
            echo "$hash" > "${SYSTEM_DIR}/shadow-hash"
            echo "$target_user" > "${SYSTEM_DIR}/shadow-user"
            chmod 600 "${SYSTEM_DIR}/shadow-hash" "${SYSTEM_DIR}/shadow-user"

            # Verrouiller le compte dans /etc/shadow
            usermod -L "$target_user"

            info "  Hash de '${target_user}' migré vers ZFS. Compte verrouillé."
        fi
    fi

    # --- Script d'injection ---
    local inject_script="/usr/local/sbin/inject-shadow.sh"
    if [[ ! -f "$inject_script" ]]; then
        cat > "$inject_script" << 'SCRIPT'
#!/bin/sh
set -eu
HASH_FILE="/home/.system/shadow-hash"
USER_FILE="/home/.system/shadow-user"
[ -f "$HASH_FILE" ] || exit 0
[ -f "$USER_FILE" ] || exit 0
USER=$(cat "$USER_FILE")
HASH=$(cat "$HASH_FILE")
usermod -p "$HASH" "$USER"
SCRIPT
        chmod 755 "$inject_script"
        info "  Script inject-shadow.sh installé."
    else
        info "  Script inject-shadow.sh existe déjà."
    fi

    # --- Service systemd ---
    local service_file="/etc/systemd/system/inject-shadow.service"
    if [[ ! -f "$service_file" ]]; then
        cat > "$service_file" << 'UNIT'
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
UNIT
        systemctl daemon-reload
        systemctl enable inject-shadow.service
        info "  Service inject-shadow activé."
    else
        info "  Service inject-shadow existe déjà."
    fi

    # --- NetworkManager : secrets WiFi sur ZFS ---
    local nm_zfs_dir="${SYSTEM_DIR}/nm-connections"
    local nm_conf="/etc/NetworkManager/conf.d/secrets-on-zfs.conf"

    if [[ ! -f "$nm_conf" ]]; then
        mkdir -p "$nm_zfs_dir"
        chmod 700 "$nm_zfs_dir"

        # Migrer les connexions existantes
        if [[ -d /etc/NetworkManager/system-connections ]]; then
            local count
            count=$(find /etc/NetworkManager/system-connections -maxdepth 1 -type f 2>/dev/null | wc -l)
            if [[ "$count" -gt 0 ]]; then
                cp -a /etc/NetworkManager/system-connections/* "$nm_zfs_dir/"
                info "  ${count} connexion(s) NM migrée(s) vers ZFS."
            fi
        fi

        cat > "$nm_conf" << NMCONF
[keyfile]
path=${nm_zfs_dir}
NMCONF
        info "  NetworkManager configuré pour stocker les secrets sur ZFS."
        info "  Redémarrer NetworkManager pour appliquer : systemctl restart NetworkManager"
    else
        info "  NetworkManager déjà configuré pour ZFS."
    fi

    info "Credentials OK."
}

# ---------------------------------------------------------------------------
# 4. Systemd — ZFS avant Incus + injection credentials
# ---------------------------------------------------------------------------

setup_systemd_ordering() {
    info "Configuration systemd : ZFS → credentials → Incus..."

    # Service de déverrouillage ZFS
    local key_service="/etc/systemd/system/zfs-load-key-tank.service"
    if [[ ! -f "$key_service" ]]; then
        cat > "$key_service" << 'UNIT'
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
UNIT
        systemctl daemon-reload
        systemctl enable zfs-load-key-tank.service
        info "  Service zfs-load-key-tank créé et activé."
    else
        info "  Service zfs-load-key-tank existe déjà."
    fi

    # Drop-in Incus : démarrer après ZFS
    local incus_dropin="/etc/systemd/system/incus.service.d"
    if [[ ! -f "${incus_dropin}/after-zfs.conf" ]]; then
        mkdir -p "$incus_dropin"
        cat > "${incus_dropin}/after-zfs.conf" << 'DROPIN'
[Unit]
After=zfs-mount.service
Requires=zfs-mount.service
DROPIN
        systemctl daemon-reload
        info "  Drop-in Incus after-zfs.conf créé."
    else
        info "  Drop-in Incus after-zfs.conf existe déjà."
    fi

    info "Systemd ordering OK."
}

# ---------------------------------------------------------------------------
# 5. Mode toram (optionnel)
# ---------------------------------------------------------------------------

setup_toram() {
    if [[ "$SKIP_TORAM" == true ]]; then
        info "Mode toram : ignoré (--skip-toram)."
        return
    fi

    info "Installation du mode toram (overlayfs)..."

    local hook="/etc/initramfs-tools/scripts/init-bottom/toram"
    if [[ ! -f "$hook" ]]; then
        cat > "$hook" << 'HOOK'
#!/bin/sh
PREREQ=""
prereqs() { echo "$PREREQ"; }
case $1 in prereqs) prereqs; exit 0;; esac

# Actif seulement si BOOT_MODE=toram dans la cmdline kernel
grep -q "BOOT_MODE=toram" /proc/cmdline || exit 0

mkdir -p /mnt/lower /mnt/upper-tmpfs

# Déplacer le rootfs réel en read-only
mount -o remount,ro "${rootmnt}"
mount -o move "${rootmnt}" /mnt/lower

# tmpfs pour les écritures (80% RAM)
mount -t tmpfs -o size=80% tmpfs /mnt/upper-tmpfs
mkdir -p /mnt/upper-tmpfs/upper /mnt/upper-tmpfs/work

# overlayfs : lower (disque ro) + upper (tmpfs rw)
mount -t overlay overlay \
  -o "lowerdir=/mnt/lower,upperdir=/mnt/upper-tmpfs/upper,workdir=/mnt/upper-tmpfs/work" \
  "${rootmnt}"

# Rendre le disque accessible pour les mises à jour
mkdir -p "${rootmnt}/mnt/rootfs-disk"
mount -o move /mnt/lower "${rootmnt}/mnt/rootfs-disk"
HOOK
        chmod +x "$hook"
        info "  Hook initramfs toram installé."
    else
        info "  Hook initramfs toram existe déjà."
    fi

    # Entrée GRUB
    local grub_entry="/etc/grub.d/42_toram"
    if [[ ! -f "$grub_entry" ]]; then
        # Récupérer l'UUID du rootfs et le subvolume
        local root_uuid
        root_uuid=$(findmnt -no UUID /)
        local root_subvol
        root_subvol=$(findmnt -no OPTIONS / | grep -oP 'subvol=\K[^,]+' || true)

        local rootflags=""
        if [[ -n "$root_subvol" ]]; then
            rootflags=" rootflags=subvol=${root_subvol}"
        fi

        cat > "$grub_entry" << GRUB
#!/bin/sh
cat << 'EOF'
menuentry "Debian (toram -- immutable)" {
    linux /vmlinuz root=UUID=${root_uuid} ro BOOT_MODE=toram${rootflags}
    initrd /initrd.img
}
EOF
GRUB
        chmod +x "$grub_entry"
        info "  Entrée GRUB toram ajoutée."
    else
        info "  Entrée GRUB toram existe déjà."
    fi

    update-initramfs -u
    update-grub

    info "Mode toram OK. Sélectionner 'Debian (toram -- immutable)' dans GRUB pour l'activer."
}

# ---------------------------------------------------------------------------
# 6. NVIDIA GPU (optionnel)
# ---------------------------------------------------------------------------

setup_nvidia() {
    if [[ "$SKIP_NVIDIA" == true ]]; then
        info "NVIDIA : ignoré (--skip-nvidia)."
        return
    fi

    # Vérifier si déjà installé
    if command -v nvidia-smi &> /dev/null; then
        info "NVIDIA driver déjà installé :"
        nvidia-smi --query-gpu=driver_version,name,memory.total --format=csv,noheader
        return
    fi

    info "Configuration NVIDIA GPU..."

    # Blacklist nouveau
    local blacklist="/etc/modprobe.d/blacklist-nouveau.conf"
    if [[ ! -f "$blacklist" ]]; then
        cat > "$blacklist" << 'CONF'
blacklist nouveau
options nouveau modeset=0
CONF
        update-initramfs -u
        info "  Nouveau blacklisté. Un reboot est nécessaire avant d'installer le driver."
    fi

    # Chercher le .run : d'abord --nvidia-run, sinon auto-détection
    if [[ -z "$NVIDIA_RUN" ]]; then
        NVIDIA_RUN=$(find . -maxdepth 1 -name 'NVIDIA-Linux-x86_64-*.run' -print -quit 2>/dev/null || true)
    fi

    if [[ -z "$NVIDIA_RUN" ]]; then
        warn "Aucun fichier NVIDIA .run trouvé."
        warn "Téléchargez le driver depuis https://www.nvidia.com/drivers/"
        warn "Puis relancez avec : $0 --nvidia-run /chemin/vers/NVIDIA-Linux-x86_64-xxx.run"
        warn "Si nouveau vient d'être blacklisté, rebootez d'abord."
        return
    fi

    if [[ ! -f "$NVIDIA_RUN" ]]; then
        error "Fichier introuvable : $NVIDIA_RUN"
        exit 1
    fi

    # Vérifier que nouveau est bien déchargé
    if lsmod | grep -q nouveau; then
        warn "Le module nouveau est encore chargé. Rebootez d'abord, puis relancez ce script."
        return
    fi

    info "  Installation de ${NVIDIA_RUN} (flags: ${NVIDIA_INSTALL_FLAGS[*]})..."
    info "  RTX PRO 5000 Blackwell : open kernel modules requis (--open)."
    chmod +x "$NVIDIA_RUN"
    "$NVIDIA_RUN" "${NVIDIA_INSTALL_FLAGS[@]}"

    info "NVIDIA driver installé."
    nvidia-smi --query-gpu=driver_version,name,memory.total --format=csv,noheader
}

# ---------------------------------------------------------------------------
# 7. anklume
# ---------------------------------------------------------------------------

install_anklume() {
    if command -v anklume &> /dev/null; then
        info "anklume déjà installé."
        return
    fi

    info "Installation d'anklume..."

    if command -v uv &> /dev/null; then
        uv tool install anklume
        info "anklume installé via uv."
    else
        warn "uv introuvable. Installez anklume manuellement : uv tool install anklume"
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo "=== bootstrap-host.sh — Préparation hôte anklume ==="
    echo ""

    check_root

    install_base_packages
    create_zfs_datasets
    setup_credentials
    setup_systemd_ordering
    setup_toram
    setup_nvidia
    install_anklume

    echo ""
    info "Bootstrap terminé."
    echo ""
    echo "Prochaines étapes :"
    echo "  1. Rebooter si nouveau a été blacklisté"
    echo "  2. Vérifier l'injection shadow : systemctl status inject-shadow"
    echo "  3. mkdir mon-infra && cd mon-infra"
    echo "  4. anklume init"
    echo "  5. anklume tui  (éditer les domaines)"
    echo "  6. anklume apply all"
    echo ""
}

main
