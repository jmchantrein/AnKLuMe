#!/usr/bin/env bash
# bootstrap.sh — Prépare un hôte GNU/Linux pour AnKLuMe
#
# Distributions supportées :
#   - CachyOS (recommandé — kernels optimisés, GPU récent out of the box)
#   - Arch Linux
#   - Debian 13+
#
# Point de départ : OS fraîchement installé (LUKS + btrfs sur NVMe système)
# Résultat : ZFS chiffré (mirror) + Incus + AnKLuMe prêt à l'emploi
#
# Matériel cible (exemple ThinkPad) :
#   nvme2n1  — Samsung 512G  — système (LUKS + btrfs, déjà installé)
#   nvme0n1  — Corsair 3.6T  — ZFS mirror leg 1
#   nvme1n1  — Corsair 3.6T  — ZFS mirror leg 2
#
# Usage :
#   sudo ./bootstrap.sh [options]
#
# Options :
#   --skip-nvidia         Ne pas vérifier le driver NVIDIA
#   --skip-toram          Ne pas configurer le mode toram
#   --force-toram         Forcer la reconstruction complète du toram
#   --skip-zfs-pool       Ne pas créer/recréer le pool ZFS
#   --skip-incus          Ne pas configurer Incus
#   --zfs-passphrase      Lire la passphrase depuis stdin (non interactif)
#   --zfs-disk1 <disque>  Disque ZFS mirror leg 1 (obligatoire si pool à créer)
#                         Accepte : by-id nu, chemin complet, ou /dev/nvmeXnY
#   --zfs-disk2 <disque>  Disque ZFS mirror leg 2 (obligatoire si pool à créer)
#
# Ce script est idempotent : il peut être relancé sans danger.
# Shellcheck clean : shellcheck -o all bootstrap.sh

set -euo pipefail

# Chemin absolu du script, capturé AVANT le cd /root
# (sinon les chemins relatifs dans BASH_SOURCE[0] sont résolus depuis /root).
SCRIPT_REAL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Toujours travailler depuis un répertoire stable (btrfs rootfs).
# Les montages ZFS (ex: tank/_home → /home) peuvent invalider le cwd.
cd /root

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

readonly POOL="tank"
readonly INCUS_STORAGE="tank-zfs"
readonly ZFS_KEY_DIR="/etc/zfs"
readonly ZFS_KEY_FILE="${ZFS_KEY_DIR}/tank.key"       # 32 bytes raw
readonly ZFS_KEY_ENC="${ZFS_KEY_DIR}/tank.key.enc"    # backup chiffré (passphrase)

# Chemin du repo source (celui d'où tourne ce script).
# Calculé une fois, avant que mount_zfs_home ne masque /home btrfs.
BOOTSTRAP_REPO_DIR=""

# Couleurs
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Flags
SKIP_NVIDIA=false
SKIP_TORAM=false
FORCE_TORAM=false
SKIP_ZFS_POOL=false
SKIP_INCUS=false
PASSPHRASE_STDIN=false
ZFS_DISK_1=""
ZFS_DISK_2=""

# Détection de la distribution (rempli par detect_distro)
DISTRO=""          # "cachyos", "arch", "debian"
DISTRO_FAMILY=""   # "arch" ou "debian"
PKG_INSTALL=""     # commande d'installation de paquets

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-nvidia)       SKIP_NVIDIA=true; shift ;;
        --skip-toram)        SKIP_TORAM=true; shift ;;
        --force-toram)       FORCE_TORAM=true; shift ;;
        --skip-zfs-pool)     SKIP_ZFS_POOL=true; shift ;;
        --skip-incus)        SKIP_INCUS=true; shift ;;
        --zfs-passphrase)    PASSPHRASE_STDIN=true; shift ;;
        --zfs-disk1)
            [[ -z "${2:-}" ]] && { printf "Erreur : --zfs-disk1 nécessite un disque.\n" >&2; exit 1; }
            ZFS_DISK_1="$2"; shift 2 ;;
        --zfs-disk2)
            [[ -z "${2:-}" ]] && { printf "Erreur : --zfs-disk2 nécessite un disque.\n" >&2; exit 1; }
            ZFS_DISK_2="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,/^$/s/^# \?//p' "$0"
            exit 0
            ;;
        *)
            printf "Option inconnue : %s\n" "$1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

info()  { printf "${GREEN}[INFO]${NC}  %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
error() { printf "${RED}[ERREUR]${NC} %s\n" "$1" >&2; }
step()  { printf "\n${BLUE}── %s${NC}\n\n" "$1"; }

check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "Ce script doit être exécuté en root."
        exit 1
    fi
}

# Demande la passphrase de secours (interactif ou stdin)
ask_passphrase() {
    local passphrase=""

    if [[ "${PASSPHRASE_STDIN}" == true ]]; then
        IFS= read -r passphrase
        printf '%s' "${passphrase}"
        return
    fi

    local confirm=""
    while true; do
        IFS= read -r -s -p "Passphrase de secours (pour récupérer le keyfile) : " passphrase
        echo ""
        IFS= read -r -s -p "Confirmer : " confirm
        echo ""
        if [[ "${passphrase}" == "${confirm}" ]]; then
            break
        fi
        warn "Les passphrases ne correspondent pas."
    done

    if [[ ${#passphrase} -lt 8 ]]; then
        error "La passphrase doit faire au moins 8 caractères."
        exit 1
    fi

    printf '%s' "${passphrase}"
}

# ---------------------------------------------------------------------------
# 0. Détection de la distribution
# ---------------------------------------------------------------------------

detect_distro() {
    step "Détection de la distribution"

    if [[ ! -f /etc/os-release ]]; then
        error "/etc/os-release introuvable. Distribution non supportée."
        exit 1
    fi

    # shellcheck source=/dev/null
    source /etc/os-release

    case "${ID:-}" in
        cachyos)
            DISTRO="cachyos"
            DISTRO_FAMILY="arch"
            ;;
        arch|endeavouros|manjaro)
            DISTRO="arch"
            DISTRO_FAMILY="arch"
            ;;
        debian)
            DISTRO="debian"
            DISTRO_FAMILY="debian"
            ;;
        *)
            error "Distribution '${ID:-inconnue}' non supportée."
            error "Distributions supportées : CachyOS, Arch, Debian."
            exit 1
            ;;
    esac

    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        PKG_INSTALL="pacman -S --noconfirm --needed"
    else
        PKG_INSTALL="apt-get install -y -qq"
    fi

    info "Distribution détectée : ${PRETTY_NAME:-${ID}} (famille ${DISTRO_FAMILY})"
}

# ---------------------------------------------------------------------------
# 1. Paquets de base
# ---------------------------------------------------------------------------

install_base_packages() {
    step "Installation des paquets de base"

    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        install_packages_arch
    else
        install_packages_debian
    fi

    # uv (Python package manager) — commun
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="/root/.local/bin:${PATH}"
        info "uv installé."
    fi

    info "Paquets de base OK."
}

install_packages_arch() {
    # Synchroniser, upgrader et installer en une passe
    pacman -Syu --noconfirm --needed \
        base-devel dkms pkg-config \
        curl git tmux jq \
        ansible-core python \
        > /dev/null 2>&1

    # ZFS
    if ! command -v zfs &> /dev/null; then
        info "Installation de ZFS..."
        ${PKG_INSTALL} zfs-utils > /dev/null 2>&1

        if [[ "${DISTRO}" == "cachyos" ]]; then
            # CachyOS fournit des modules ZFS pré-compilés
            ${PKG_INSTALL} cachyos-zfs > /dev/null 2>&1 || {
                warn "cachyos-zfs indisponible, fallback sur zfs-dkms..."
                ${PKG_INSTALL} zfs-dkms > /dev/null 2>&1
            }
        else
            ${PKG_INSTALL} zfs-dkms > /dev/null 2>&1
        fi
    fi

    # Charger le module ZFS
    if ! lsmod | grep -q "^zfs "; then
        modprobe zfs
        info "Module ZFS chargé."
    fi

    # Incus
    if ! command -v incus &> /dev/null; then
        ${PKG_INSTALL} incus > /dev/null 2>&1
    fi
}

install_packages_debian() {
    apt-get update -qq || { error "apt-get update échoué"; exit 1; }

    apt-get install -y -qq \
        build-essential dkms pkg-config \
        curl git tmux jq \
        ansible-core python3 \
        "linux-headers-$(uname -r)" \
        > /dev/null

    # ZFS (userspace + DKMS pour les kernels non-stock)
    if ! command -v zfs &> /dev/null; then
        apt-get install -y -qq zfsutils-linux zfs-dkms > /dev/null
    fi

    # Charger le module ZFS
    if ! lsmod | grep -q "^zfs "; then
        modprobe zfs
        info "Module ZFS chargé."
    fi

    # Incus
    if ! command -v incus &> /dev/null; then
        apt-get install -y -qq incus > /dev/null
    fi
}

# ---------------------------------------------------------------------------
# 2. Pool ZFS chiffré (mirror) + keyfile
# ---------------------------------------------------------------------------

create_zfs_pool() {
    if [[ "${SKIP_ZFS_POOL}" == true ]]; then
        info "Pool ZFS : ignoré (--skip-zfs-pool)."
        return
    fi

    step "Pool ZFS"

    # Si le pool existe déjà, on ne le recrée pas (idempotence)
    if zpool list "${POOL}" &> /dev/null; then
        info "Pool ZFS '${POOL}' existe déjà."
        unlock_zfs_pool
        return
    fi

    # Vérifier que les disques sont spécifiés
    if [[ -z "${ZFS_DISK_1}" || -z "${ZFS_DISK_2}" ]]; then
        error "Disques ZFS non spécifiés."
        error "Utilisez --zfs-disk1 et --zfs-disk2 avec les noms by-id ou chemins complets."
        error "Exemples :"
        error "  --zfs-disk1 nvme-Corsair_MP600_XXX          (by-id, recommandé)"
        error "  --zfs-disk1 /dev/disk/by-id/nvme-Corsair_XXX (chemin complet by-id)"
        error "  --zfs-disk1 /dev/nvme0n1                     (chemin classique)"
        error ""
        error "Disques disponibles :"
        ls /dev/disk/by-id/nvme-* 2>/dev/null | head -20 || true
        exit 1
    fi

    # Résoudre les chemins de disques : accepter by-id nu, chemin complet,
    # ou device classique (/dev/nvmeXnY, /dev/sdX)
    resolve_disk_path() {
        local disk="$1"
        if [[ -e "${disk}" ]]; then
            # Chemin complet valide (/dev/nvme0n1, /dev/disk/by-id/xxx, etc.)
            echo "${disk}"
        elif [[ -e "/dev/disk/by-id/${disk}" ]]; then
            # Nom by-id nu (sans préfixe)
            echo "/dev/disk/by-id/${disk}"
        else
            echo ""
        fi
    }

    local disk1_path disk2_path
    disk1_path=$(resolve_disk_path "${ZFS_DISK_1}")
    disk2_path=$(resolve_disk_path "${ZFS_DISK_2}")

    if [[ -z "${disk1_path}" ]]; then
        error "Disque 1 introuvable : ${ZFS_DISK_1}"
        error "Essayé : ${ZFS_DISK_1} et /dev/disk/by-id/${ZFS_DISK_1}"
        exit 1
    fi
    if [[ -z "${disk2_path}" ]]; then
        error "Disque 2 introuvable : ${ZFS_DISK_2}"
        error "Essayé : ${ZFS_DISK_2} et /dev/disk/by-id/${ZFS_DISK_2}"
        exit 1
    fi

    # Mettre à jour les variables pour la création du pool
    ZFS_DISK_1="${disk1_path}"
    ZFS_DISK_2="${disk2_path}"

    info "Création du pool ZFS '${POOL}' (mirror, chiffré AES-256-GCM)..."

    # 1. Générer un keyfile aléatoire de 32 bytes (clé raw)
    mkdir -p "${ZFS_KEY_DIR}"
    (umask 077 && dd if=/dev/urandom of="${ZFS_KEY_FILE}" bs=32 count=1 2>/dev/null)
    chmod 400 "${ZFS_KEY_FILE}"
    chown root:root "${ZFS_KEY_FILE}"
    info "Keyfile généré : ${ZFS_KEY_FILE} (32 bytes aléatoires)"

    # 2. Chiffrer une copie du keyfile avec une passphrase (backup de secours)
    local passphrase
    passphrase=$(ask_passphrase)

    openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
        -salt -in "${ZFS_KEY_FILE}" -out "${ZFS_KEY_ENC}" \
        -pass "pass:${passphrase}"
    chmod 400 "${ZFS_KEY_ENC}"
    chown root:root "${ZFS_KEY_ENC}"
    info "Backup chiffré : ${ZFS_KEY_ENC} (déchiffrable avec la passphrase)"

    # 3. Créer le pool avec la clé raw
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
        -O keylocation="file://${ZFS_KEY_FILE}" \
        -O mountpoint=none \
        "${POOL}" mirror \
        "${ZFS_DISK_1}" \
        "${ZFS_DISK_2}"

    info "Pool '${POOL}' créé (mirror, chiffré, keyformat=raw)."
}

unlock_zfs_pool() {
    local keystatus
    keystatus=$(zfs get -H -o value keystatus "${POOL}" 2>/dev/null || echo "unknown")

    if [[ "${keystatus}" == "available" ]]; then
        info "Pool ZFS '${POOL}' déjà déverrouillé."
        zfs mount -a 2>/dev/null || true
        return
    fi

    info "Déverrouillage du pool ZFS '${POOL}'..."

    # 1. Essayer la keylocation configurée
    if zfs load-key "${POOL}" 2>/dev/null; then
        info "Déverrouillé via keylocation configurée."
        zfs mount -a 2>/dev/null || true
        return
    fi

    # 2. Essayer le keyfile explicitement
    if [[ -f "${ZFS_KEY_FILE}" ]]; then
        if zfs load-key -L "file://${ZFS_KEY_FILE}" "${POOL}" 2>/dev/null; then
            info "Déverrouillé via keyfile."
            zfs mount -a 2>/dev/null || true
            return
        fi
    fi

    # 3. Fallback : déchiffrer le backup avec la passphrase
    if [[ -f "${ZFS_KEY_ENC}" ]]; then
        warn "Keyfile absent ou invalide. Déchiffrement du backup..."
        local tmp_key
        tmp_key=$(mktemp)
        local attempts=3
        while (( attempts-- > 0 )); do
            local pass=""
            IFS= read -r -s -p "Passphrase de secours : " pass
            echo ""
            if openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
                    -d -in "${ZFS_KEY_ENC}" -out "${tmp_key}" \
                    -pass "pass:${pass}" 2>/dev/null; then
                if zfs load-key -L "file://${tmp_key}" "${POOL}" 2>/dev/null; then
                    # Restaurer le keyfile pour les prochains boots
                    cp "${tmp_key}" "${ZFS_KEY_FILE}"
                    chmod 400 "${ZFS_KEY_FILE}"
                    chown root:root "${ZFS_KEY_FILE}"
                    rm -f "${tmp_key}"
                    info "Déverrouillé via passphrase. Keyfile restauré."
                    zfs mount -a 2>/dev/null || true
                    return
                fi
            fi
            warn "Passphrase incorrecte ou backup corrompu."
        done
        rm -f "${tmp_key}"
    fi

    error "Impossible de déverrouiller le pool '${POOL}'."
    exit 1
}

# ---------------------------------------------------------------------------
# 3. Datasets ZFS
# ---------------------------------------------------------------------------

create_zfs_datasets() {
    step "Datasets ZFS"
    info "Création des datasets ZFS (idempotent)..."

    # Helper : créer un dataset s'il n'existe pas
    ensure_dataset() {
        local name="$1"
        shift
        if ! zfs list "${name}" &> /dev/null; then
            zfs create "$@" "${name}"
            info "  Créé : ${name}"
        else
            info "  Existe : ${name}"
        fi
    }

    # Incus — mountpoint legacy, Incus gère ses sous-datasets
    ensure_dataset "${POOL}/_incus" -o mountpoint=legacy

    # Modèles IA — gros blobs séquentiels, déjà compressés
    ensure_dataset "${POOL}/_srv_models" \
        -o mountpoint=/srv/models -o recordsize=1M -o compression=off
    ensure_dataset "${POOL}/_srv_models_ollama" -o mountpoint=/srv/models/ollama
    ensure_dataset "${POOL}/_srv_models_stt"    -o mountpoint=/srv/models/stt

    # Home — canmount=noauto : ne se monte pas automatiquement à la création.
    # On le monte explicitement à la fin du script (mount_zfs_home) pour
    # éviter de masquer /home btrfs pendant que mkinitcpio/initramfs tourne.
    ensure_dataset "${POOL}/_home" -o mountpoint=/home -o canmount=noauto

    # État anklume (JSON, logs) — quota de sécurité
    ensure_dataset "${POOL}/_var_lib_anklume" \
        -o mountpoint=/var/lib/anklume -o quota=10G

    # Volumes partagés inter-domaines
    ensure_dataset "${POOL}/_srv_shared" -o mountpoint=/srv/shared

    # Backups, golden images — gros fichiers séquentiels
    ensure_dataset "${POOL}/_srv_backups" \
        -o mountpoint=/srv/backups -o recordsize=1M

    info "Datasets ZFS OK."
}

# ---------------------------------------------------------------------------
# 3b. Montage /home + droits utilisateur
# ---------------------------------------------------------------------------

mount_zfs_home() {
    step "Montage /home ZFS"

    # Activer le montage automatique pour les futurs boots
    zfs set canmount=on "${POOL}/_home" 2>/dev/null || true

    # Identifier l'utilisateur principal (celui qui a lancé sudo)
    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-}")

    local home_fstype
    home_fstype=$(findmnt -no FSTYPE /home 2>/dev/null) || home_fstype=""
    if ! mountpoint -q /home || [[ "${home_fstype}" != "zfs" ]]; then
        zfs mount "${POOL}/_home" 2>/dev/null || true
        info "/home monté depuis ZFS (${POOL}/_home)."
    else
        info "/home déjà monté depuis ZFS."
    fi

    # S'assurer que le répertoire home de l'utilisateur existe avec les bons droits
    if [[ -n "${main_user}" ]]; then
        local user_home user_uid user_gid
        user_home=$(getent passwd "${main_user}" | cut -d: -f6)
        user_uid=$(id -u "${main_user}")
        user_gid=$(id -g "${main_user}")

        if [[ -n "${user_home}" && ! -d "${user_home}" ]]; then
            mkdir -p "${user_home}"
            info "Répertoire ${user_home} créé."
        fi

        if [[ -n "${user_home}" && -d "${user_home}" ]]; then
            chown "${user_uid}:${user_gid}" "${user_home}"
            chmod 700 "${user_home}"
            info "Droits ${user_home} : ${main_user} (${user_uid}:${user_gid})"
        fi
    fi
}

# ---------------------------------------------------------------------------
# 4. Systemd — déverrouillage ZFS + ordering Incus
# ---------------------------------------------------------------------------

setup_systemd() {
    step "Configuration systemd"

    # --- Script de déverrouillage ---
    local unlock_script="/usr/local/bin/zfs-unlock-tank"
    cat > "${unlock_script}" << 'SCRIPT'
#!/usr/bin/env bash
# Déverrouille le pool ZFS tank :
#   1. keyfile raw  (/etc/zfs/tank.key)
#   2. passphrase → déchiffre le backup → raw key
set -euo pipefail

POOL="tank"
KEY_FILE="/etc/zfs/tank.key"
KEY_ENC="/etc/zfs/tank.key.enc"

keystatus=$(zfs get -H -o value keystatus "$POOL" 2>/dev/null || echo "unknown")
[[ "$keystatus" == "available" ]] && exit 0

# 1. Tentative via keyfile raw
if [[ -f "$KEY_FILE" ]] && zfs load-key -L "file://${KEY_FILE}" "$POOL" 2>/dev/null; then
    echo "Pool ZFS $POOL déverrouillé via keyfile." > /dev/kmsg 2>/dev/null || true
    exit 0
fi

# 2. Tentative via keylocation du pool
if zfs load-key "$POOL" 2>/dev/null; then
    echo "Pool ZFS $POOL déverrouillé via keylocation." > /dev/kmsg 2>/dev/null || true
    exit 0
fi

# 3. Fallback : passphrase → déchiffrer le backup du keyfile
if [[ -f "$KEY_ENC" ]]; then
    echo ">>> Keyfile absent. Entrez la passphrase de secours pour $POOL <<<" \
        > /dev/console 2>/dev/null || true
    tmp_key=$(mktemp)
    attempts=3
    while (( attempts-- > 0 )); do
        read -r -s -p "Passphrase de secours : " pass
        echo ""
        if openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
                -d -in "$KEY_ENC" -out "$tmp_key" \
                -pass "pass:${pass}" 2>/dev/null; then
            if zfs load-key -L "file://${tmp_key}" "$POOL" 2>/dev/null; then
                # Restaurer le keyfile pour les prochains boots
                cp "$tmp_key" "$KEY_FILE"
                chmod 400 "$KEY_FILE"
                chown root:root "$KEY_FILE"
                rm -f "$tmp_key"
                echo "Pool ZFS $POOL déverrouillé via passphrase. Keyfile restauré." \
                    > /dev/kmsg 2>/dev/null || true
                exit 0
            fi
        fi
        echo "Passphrase incorrecte." > /dev/console 2>/dev/null || true
    done
    rm -f "$tmp_key"
fi

echo "ÉCHEC : impossible de déverrouiller le pool ZFS $POOL." >&2
exit 1
SCRIPT
    chmod 755 "${unlock_script}"
    info "Script ${unlock_script} installé."

    # --- Service systemd ---
    local key_service="/etc/systemd/system/zfs-load-key-tank.service"
    cat > "${key_service}" << 'UNIT'
[Unit]
Description=Déverrouiller le pool ZFS tank (keyfile puis passphrase)
DefaultDependencies=no
Before=zfs-mount.service
After=zfs-import.target
ConditionPathExists=/dev/zfs
# Ne jamais causer un emergency mode si le déverrouillage échoue
FailureAction=none

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/zfs-unlock-tank
StandardInput=tty-force
StandardOutput=journal+console
StandardError=journal+console
# Timeout pour ne pas bloquer le boot indéfiniment sur la passphrase
TimeoutStartSec=120

[Install]
WantedBy=zfs-mount.service
UNIT
    info "Service zfs-load-key-tank.service installé."

    # --- Drop-in Incus : après ZFS ---
    local incus_dropin="/etc/systemd/system/incus.service.d"
    mkdir -p "${incus_dropin}"
    cat > "${incus_dropin}/after-zfs.conf" << 'DROPIN'
[Unit]
After=zfs-mount.service
Requires=zfs-mount.service
DROPIN
    info "Drop-in Incus after-zfs.conf installé."

    # --- Drop-in zfs-mount : ne pas causer d'emergency mode ---
    local zfs_mount_dropin="/etc/systemd/system/zfs-mount.service.d"
    mkdir -p "${zfs_mount_dropin}"
    cat > "${zfs_mount_dropin}/no-emergency.conf" << 'DROPIN'
[Unit]
# Empêcher le montage ZFS de bloquer le boot en emergency mode.
# Si ZFS échoue, le système démarre quand même (dégradé mais accessible).
FailureAction=none

[Service]
# Empêcher zfs mount -a de bloquer si un dataset est stuck
TimeoutStartSec=90
DROPIN
    info "Drop-in zfs-mount no-emergency.conf installé."

    # --- Activation ---
    systemctl daemon-reload

    local -a zfs_services=(
        zfs-import-cache.service
        zfs-import.target
        zfs-mount.service
        zfs-share.service
        zfs.target
        zfs-load-key-tank.service
    )
    for svc in "${zfs_services[@]}"; do
        systemctl enable "${svc}" 2>/dev/null || true
    done

    info "Systemd OK."
}

# ---------------------------------------------------------------------------
# 5. Incus
# ---------------------------------------------------------------------------

setup_incus() {
    if [[ "${SKIP_INCUS}" == true ]]; then
        info "Incus : ignoré (--skip-incus)."
        return
    fi

    step "Configuration Incus"

    systemctl enable --now incus.socket incus.service 2>/dev/null || true

    # Attendre que le daemon soit prêt
    local retries=15
    while ! incus info &> /dev/null && (( retries-- > 0 )); do
        sleep 1
    done

    if ! incus info &> /dev/null; then
        error "Incus ne démarre pas. Vérifier : journalctl -xeu incus"
        exit 1
    fi
    info "Incus actif."

    # Initialisation minimale
    if ! incus profile show default &> /dev/null 2>&1; then
        incus admin init --minimal
        info "Incus initialisé (minimal)."
    fi

    # Storage pool ZFS
    if ! incus storage show "${INCUS_STORAGE}" &> /dev/null 2>&1; then
        incus storage create "${INCUS_STORAGE}" zfs source="${POOL}/_incus"
        info "Storage pool '${INCUS_STORAGE}' créé."
    else
        info "Storage pool '${INCUS_STORAGE}' existe déjà."
    fi

    # Groupe incus-admin
    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-}")
    if [[ -n "${main_user}" ]] && ! id -nG "${main_user}" 2>/dev/null | grep -qw incus-admin; then
        usermod -aG incus-admin "${main_user}"
        info "Utilisateur '${main_user}' ajouté au groupe incus-admin."
    fi

    info "Incus OK."
}

# ---------------------------------------------------------------------------
# 6. NVIDIA GPU (détection auto + installation)
# ---------------------------------------------------------------------------

# PCI device IDs Blackwell (RTX 50xx) : nécessite driver 570+ et open kernel modules
# Source : lspci 10de:XXXX confirmés sur hardware réel
readonly -a BLACKWELL_IDS=(
    "2b85" # RTX 5090  (GB202)
    "2c02" # RTX 5080  (GB203)
    "2c05" # RTX 5070 Ti (GB203)
    "2f04" # RTX 5070  (GB205)
    "2bb3" # RTX PRO 5000 (GB202)
)

readonly NVIDIA_BLACKWELL_VERSION="570.195.03"
readonly NVIDIA_BLACKWELL_RUN="https://download.nvidia.com/XFree86/Linux-x86_64/${NVIDIA_BLACKWELL_VERSION}/NVIDIA-Linux-x86_64-${NVIDIA_BLACKWELL_VERSION}.run"

# Retourne "blackwell", "supported" ou "none"
detect_nvidia_gpu() {
    if ! lspci -nn 2>/dev/null | grep -qi "nvidia"; then
        echo "none"
        return
    fi

    local pci_ids
    pci_ids=$(lspci -nn | grep -i nvidia | grep -oP '10de:\K[0-9a-f]{4}' || true)

    for id in ${pci_ids}; do
        for blackwell_id in "${BLACKWELL_IDS[@]}"; do
            if [[ "${id,,}" == "${blackwell_id,,}" ]]; then
                echo "blackwell"
                return
            fi
        done
    done

    echo "supported"
}

setup_nvidia() {
    if [[ "${SKIP_NVIDIA}" == true ]]; then
        info "NVIDIA : ignoré (--skip-nvidia)."
        return
    fi

    step "NVIDIA GPU"

    # Déjà installé ?
    if command -v nvidia-smi &> /dev/null; then
        info "NVIDIA driver OK :"
        nvidia-smi --query-gpu=driver_version,name,memory.total \
            --format=csv,noheader 2>/dev/null || true
        return
    fi

    local gpu_gen
    gpu_gen=$(detect_nvidia_gpu)

    case "${gpu_gen}" in
        none)
            info "Aucun GPU NVIDIA détecté."
            return
            ;;
        blackwell)
            info "GPU NVIDIA Blackwell détecté."
            install_nvidia_blackwell
            ;;
        supported)
            info "GPU NVIDIA détecté (pré-Blackwell)."
            install_nvidia_standard
            ;;
    esac
}

install_nvidia_standard() {
    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        info "Installation via pacman (nvidia-open-dkms)..."
        pacman -S --noconfirm --needed \
            nvidia-open-dkms nvidia-utils > /dev/null 2>&1
        info "NVIDIA driver installé (open kernel modules)."
    else
        # Debian : activer non-free si nécessaire
        if ! grep -q "non-free" /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null; then
            warn "Activation des dépôts non-free/contrib..."
            sed -i 's/main$/main contrib non-free non-free-firmware/' \
                /etc/apt/sources.list 2>/dev/null || true
            apt-get update -qq
        fi

        apt-get install -y -qq \
            "linux-headers-$(uname -r)" \
            nvidia-driver nvidia-open-kernel-dkms \
            firmware-nvidia-gsp \
            > /dev/null 2>&1
        info "NVIDIA driver installé."
    fi
}

install_nvidia_blackwell() {
    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        # CachyOS/Arch : le driver 570+ est dans les dépôts
        info "Installation via pacman (nvidia-open-dkms, 570+)..."
        pacman -S --noconfirm --needed \
            nvidia-open-dkms nvidia-utils > /dev/null 2>&1
        info "NVIDIA Blackwell driver installé."
    else
        # Debian : le driver 570+ n'est PAS dans les dépôts.
        warn "Blackwell nécessite le driver ${NVIDIA_BLACKWELL_VERSION}."
        warn "Ce driver n'est pas dans les dépôts Debian — installation via .run"

        apt-get install -y -qq \
            "linux-headers-$(uname -r)" \
            build-essential dkms pkg-config \
            > /dev/null

        # Blacklister nouveau
        if ! grep -q "blacklist nouveau" /etc/modprobe.d/blacklist-nouveau.conf 2>/dev/null; then
            cat > /etc/modprobe.d/blacklist-nouveau.conf << 'CONF'
blacklist nouveau
options nouveau modeset=0
CONF
            if [[ "${DISTRO_FAMILY}" == "debian" ]]; then
                update-initramfs -u 2>/dev/null || true
            else
                regenerate_initramfs 2>/dev/null || true
            fi
            info "Module nouveau blacklisté."
        fi

        if lsmod | grep -q nouveau; then
            warn "Le module nouveau est encore chargé."
            warn "Rebootez puis relancez ce script."
            return
        fi

        local run_file="/tmp/NVIDIA-Linux-x86_64-${NVIDIA_BLACKWELL_VERSION}.run"
        if [[ ! -f "${run_file}" ]]; then
            info "Téléchargement du driver ${NVIDIA_BLACKWELL_VERSION}..."
            curl -L -o "${run_file}" "${NVIDIA_BLACKWELL_RUN}" || {
                error "Échec du téléchargement. URL : ${NVIDIA_BLACKWELL_RUN}"
                exit 1
            }
        fi

        chmod +x "${run_file}"
        info "Installation du driver NVIDIA ${NVIDIA_BLACKWELL_VERSION} (open kernel modules)..."
        "${run_file}" --dkms --open --silent || {
            error "Échec de l'installation. Vérifier : /var/log/nvidia-installer.log"
            exit 1
        }

        rm -f "${run_file}"
        info "NVIDIA Blackwell driver ${NVIDIA_BLACKWELL_VERSION} installé."
    fi
}

# ---------------------------------------------------------------------------
# 7. Mode toram (bootloader spécifique à la distro)
# ---------------------------------------------------------------------------

setup_toram() {
    if [[ "${SKIP_TORAM}" == true ]]; then
        info "Mode toram : ignoré (--skip-toram)."
        return
    fi

    step "Configuration du mode toram"

    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        if command -v dracut &> /dev/null; then
            setup_toram_dracut
        elif command -v mkinitcpio &> /dev/null; then
            setup_toram_mkinitcpio
        else
            error "Aucun générateur d'initramfs trouvé (mkinitcpio ou dracut)."
            return 1
        fi
    else
        setup_toram_initramfs
    fi

    info "Mode toram OK."
}

# Régénère l'initramfs avec le bon outil :
#   1. limine-mkinitcpio si présent (CachyOS + Limine : gère les chemins /boot/<machine-id>/)
#   2. mkinitcpio -P sinon (Arch standard)
#   3. dracut --force (Fedora, CachyOS avec dracut)
regenerate_initramfs() {
    if command -v limine-mkinitcpio &> /dev/null; then
        limine-mkinitcpio
        info "Initramfs regénéré via limine-mkinitcpio."
    elif command -v mkinitcpio &> /dev/null; then
        mkinitcpio -P
        info "Initramfs regénéré via mkinitcpio -P."
    elif command -v dracut &> /dev/null; then
        dracut --force
        info "Initramfs regénéré via dracut."
    else
        warn "Aucun outil de génération d'initramfs trouvé."
        return 1
    fi
}

# --- Arch / CachyOS : mkinitcpio + Limine/GRUB ---
setup_toram_mkinitcpio() {
    # Hook mkinitcpio (install)
    local hook_install="/usr/lib/initcpio/install/toram"
    cat > "${hook_install}" << 'EOF'
#!/bin/bash
build() {
    add_module overlay
    add_runscript
}

help() {
    cat <<HELPEOF
Enables toram overlay when BOOT_MODE=toram is on the kernel cmdline.
Loads the overlay kernel module and sets up a tmpfs-backed overlayfs
so that all writes go to RAM, leaving the root filesystem immutable.
HELPEOF
}
EOF
    chmod +x "${hook_install}"

    # Hook mkinitcpio (runtime — latehook, après montage racine sur /new_root)
    local hook_runtime="/usr/lib/initcpio/hooks/toram"
    cat > "${hook_runtime}" << 'EOF'
#!/usr/bin/ash
run_latehook() {
    grep -q "BOOT_MODE=toram" /proc/cmdline || return

    mkdir -p /mnt/lower /mnt/upper-tmpfs
    mount -o remount,ro /new_root
    mount -o move /new_root /mnt/lower
    mount -t tmpfs -o size=80% tmpfs /mnt/upper-tmpfs
    mkdir -p /mnt/upper-tmpfs/upper /mnt/upper-tmpfs/work
    mount -t overlay overlay \
        -o "lowerdir=/mnt/lower,upperdir=/mnt/upper-tmpfs/upper,workdir=/mnt/upper-tmpfs/work" \
        /new_root
    mkdir -p /new_root/mnt/rootfs-disk
    mount -o move /mnt/lower /new_root/mnt/rootfs-disk
}
EOF
    chmod +x "${hook_runtime}"
    info "Hooks mkinitcpio toram installés."

    # Ajouter à HOOKS si absent (après filesystems — c'est un latehook)
    local need_regen=false
    if ! grep -q "toram" /etc/mkinitcpio.conf; then
        sed -i 's/\(HOOKS=.*filesystems\)/\1 toram/' /etc/mkinitcpio.conf
        need_regen=true
        info "Hook toram ajouté après filesystems."
    elif grep -q 'toram filesystems' /etc/mkinitcpio.conf; then
        # Si toram est AVANT filesystems (ancienne version), corriger
        sed -i 's/toram filesystems/filesystems toram/' /etc/mkinitcpio.conf
        need_regen=true
        info "Position du hook toram corrigée (déplacé après filesystems)."
    else
        info "Hook toram déjà dans mkinitcpio.conf (position correcte)."
    fi

    if [[ "${need_regen}" == true ]] || [[ "${FORCE_TORAM}" == true ]]; then
        regenerate_initramfs
    fi

    # Entrée bootloader (Limine si présent, sinon GRUB)
    if [[ -f "/boot/limine.conf" ]]; then
        setup_toram_limine
    elif command -v grub-mkconfig &> /dev/null; then
        setup_toram_grub
    else
        warn "Aucun bootloader supporté détecté pour l'entrée toram."
    fi
}

# --- Arch / CachyOS : dracut + Limine/GRUB ---
setup_toram_dracut() {
    local module_dir="/usr/lib/dracut/modules.d/90toram"
    mkdir -p "${module_dir}"

    # module-setup.sh — déclare le module dracut
    cat > "${module_dir}/module-setup.sh" << 'EOF'
#!/bin/bash
check() { return 0; }
depends() { return 0; }
install() {
    inst_hook pre-pivot 90 "$moddir/toram-overlay.sh"
    instmods overlay
}
EOF
    chmod +x "${module_dir}/module-setup.sh"

    # Script overlay (pre-pivot = après montage racine sur $NEWROOT)
    cat > "${module_dir}/toram-overlay.sh" << 'EOF'
#!/bin/sh
grep -q "BOOT_MODE=toram" /proc/cmdline || exit 0

NEWROOT="${NEWROOT:-/sysroot}"

mkdir -p /mnt/lower /mnt/upper-tmpfs
mount -o remount,ro "${NEWROOT}"
mount -o move "${NEWROOT}" /mnt/lower
mount -t tmpfs -o size=80% tmpfs /mnt/upper-tmpfs
mkdir -p /mnt/upper-tmpfs/upper /mnt/upper-tmpfs/work
mount -t overlay overlay \
    -o "lowerdir=/mnt/lower,upperdir=/mnt/upper-tmpfs/upper,workdir=/mnt/upper-tmpfs/work" \
    "${NEWROOT}"
mkdir -p "${NEWROOT}/mnt/rootfs-disk"
mount -o move /mnt/lower "${NEWROOT}/mnt/rootfs-disk"
EOF
    chmod +x "${module_dir}/toram-overlay.sh"
    info "Module dracut toram installé dans ${module_dir}."

    # Ajouter le module toram à la config dracut
    local dracut_conf="/etc/dracut.conf.d/toram.conf"
    local need_regen=false
    if [[ ! -f "${dracut_conf}" ]] || [[ "${FORCE_TORAM}" == true ]]; then
        cat > "${dracut_conf}" << 'CONF'
# Module toram overlay (AnKLuMe)
add_dracutmodules+=" toram "
CONF
        info "Config dracut toram ajoutée."
        need_regen=true
    else
        info "Config dracut toram déjà présente."
    fi

    if [[ "${need_regen}" == true ]] || [[ "${FORCE_TORAM}" == true ]]; then
        regenerate_initramfs
    fi

    # Entrée bootloader (Limine si présent, sinon GRUB)
    if [[ -f "/boot/limine.conf" ]]; then
        setup_toram_limine
    elif command -v grub-mkconfig &> /dev/null; then
        setup_toram_grub
    else
        warn "Aucun bootloader supporté détecté pour l'entrée toram."
    fi
}

setup_toram_limine() {
    local limine_conf="/boot/limine.conf"

    if grep -q "BOOT_MODE=toram" "${limine_conf}" && [[ "${FORCE_TORAM}" != true ]]; then
        info "Entrée Limine toram existe déjà."
        return
    fi

    # En mode force, supprimer l'ancienne entrée toram avant de recréer
    if [[ "${FORCE_TORAM}" == true ]] && grep -q "toram -- immutable" "${limine_conf}"; then
        info "Mode force : suppression de l'ancienne entrée Limine toram."
        # Supprimer le bloc : de "/...toram -- immutable)" jusqu'à la prochaine ligne vide ou fin
        sed -i '/toram -- immutable/,/^$/d' "${limine_conf}"
    fi

    local luks_uuid luks_name root_subvol
    root_subvol=$(findmnt -no OPTIONS / | grep -oP 'subvol=\K[^,]+' || true)
    luks_uuid=$(blkid -t TYPE=crypto_LUKS -o value -s UUID | head -1)

    # Trouver le device mapper LUKS
    luks_name=""
    for mapper in /dev/mapper/luks-*; do
        if [[ -e "${mapper}" ]]; then
            luks_name=$(basename "${mapper}")
            break
        fi
    done

    local cmdline="root=/dev/mapper/${luks_name}"
    cmdline+=" rd.luks.uuid=${luks_uuid}"
    cmdline+=" ro BOOT_MODE=toram"
    if [[ -n "${root_subvol}" ]]; then
        cmdline+=" rootflags=subvol=${root_subvol}"
    fi

    # Détecter le kernel CachyOS
    local kernel_name="linux-cachyos"
    if [[ -f "/boot/vmlinuz-linux-cachyos-lts" ]]; then
        kernel_name="linux-cachyos-lts"
    fi

    cat >> "${limine_conf}" << ENTRY

/CachyOS (toram -- immutable)
    protocol: linux
    kernel_path: boot():/vmlinuz-${kernel_name}
    kernel_cmdline: ${cmdline}
    module_path: boot():/intel-ucode.img
    module_path: boot():/initramfs-${kernel_name}.img
ENTRY
    info "Entrée Limine toram ajoutée."
}

# --- Debian : initramfs-tools + GRUB ---
setup_toram_initramfs() {
    local hook="/etc/initramfs-tools/scripts/init-bottom/toram"
    if [[ ! -f "${hook}" ]] || [[ "${FORCE_TORAM}" == true ]]; then
        cat > "${hook}" << 'HOOK'
#!/bin/sh
PREREQ=""
prereqs() { echo "$PREREQ"; }
case $1 in prereqs) prereqs; exit 0;; esac

grep -q "BOOT_MODE=toram" /proc/cmdline || exit 0

modprobe overlay 2>/dev/null || true

mkdir -p /mnt/lower /mnt/upper-tmpfs
mount -o remount,ro "${rootmnt}"
mount -o move "${rootmnt}" /mnt/lower
mount -t tmpfs -o size=80% tmpfs /mnt/upper-tmpfs
mkdir -p /mnt/upper-tmpfs/upper /mnt/upper-tmpfs/work
mount -t overlay overlay \
  -o "lowerdir=/mnt/lower,upperdir=/mnt/upper-tmpfs/upper,workdir=/mnt/upper-tmpfs/work" \
  "${rootmnt}"
mkdir -p "${rootmnt}/mnt/rootfs-disk"
mount -o move /mnt/lower "${rootmnt}/mnt/rootfs-disk"
HOOK
        chmod +x "${hook}"
        info "Hook initramfs toram installé."
    fi

    # S'assurer que le module overlay est inclus dans l'initramfs
    if ! grep -q "^overlay$" /etc/initramfs-tools/modules 2>/dev/null; then
        echo "overlay" >> /etc/initramfs-tools/modules
        info "Module overlay ajouté à /etc/initramfs-tools/modules."
    fi

    update-initramfs -u
    setup_toram_grub
}

setup_toram_grub() {
    local grub_entry="/etc/grub.d/42_toram"

    if [[ -f "${grub_entry}" ]] && [[ "${FORCE_TORAM}" != true ]]; then
        info "Entrée GRUB toram existe déjà."
        return
    fi

    local root_uuid root_subvol rootflags=""
    root_uuid=$(findmnt -no UUID /)
    root_subvol=$(findmnt -no OPTIONS / | grep -oP 'subvol=\K[^,]+' || true)
    if [[ -n "${root_subvol}" ]]; then
        rootflags=" rootflags=subvol=${root_subvol}"
    fi

    local os_name
    # shellcheck source=/dev/null
    os_name="$(. /etc/os-release && echo "${NAME:-Linux}")"
    local menu_label="${os_name} (toram -- immutable)"

    cat > "${grub_entry}" << GRUB
#!/bin/sh
cat << 'EOF'
menuentry "${menu_label}" {
    linux /vmlinuz root=UUID=${root_uuid} ro BOOT_MODE=toram${rootflags}
    initrd /initrd.img
}
EOF
GRUB
    chmod +x "${grub_entry}"
    update-grub 2>/dev/null || grub-mkconfig -o /boot/grub/grub.cfg 2>/dev/null || true
    info "Entrée GRUB toram ajoutée."
}

# ---------------------------------------------------------------------------
# 7b. Sauvegarde du repo source avant montage ZFS
# ---------------------------------------------------------------------------

save_repo_source() {
    step "Sauvegarde du dépôt source"

    # Le script tourne depuis host/bootstrap.sh → le repo est le parent
    # SCRIPT_REAL_DIR a été capturé au lancement, avant cd /root.
    local repo_dir
    repo_dir=$(cd "${SCRIPT_REAL_DIR}/.." && pwd)

    if [[ ! -f "${repo_dir}/pyproject.toml" ]]; then
        warn "Repo source introuvable (${repo_dir}). Le clone sera fait depuis GitHub."
        return
    fi

    # Si le repo est sous /home, il sera masqué par le montage ZFS.
    # Le copier dans /tmp pour pouvoir le restaurer après.
    # Si le repo est ailleurs (/root, /opt, etc.), pas besoin de copier.
    if [[ "${repo_dir}" == /home/* ]]; then
        local tmp_repo="/tmp/anklume-repo-backup"
        rm -rf "${tmp_repo}"
        cp -a "${repo_dir}" "${tmp_repo}"
        BOOTSTRAP_REPO_DIR="${tmp_repo}"
        info "Repo sauvegardé dans ${tmp_repo} (source : ${repo_dir})"
    else
        BOOTSTRAP_REPO_DIR="${repo_dir}"
        info "Repo source : ${repo_dir} (pas sous /home, pas besoin de sauvegarde)"
    fi
}

# ---------------------------------------------------------------------------
# 8. AnKLuMe + alias ank (bash, zsh, fish)
# ---------------------------------------------------------------------------

install_anklume() {
    step "Installation d'AnKLuMe"

    # Identifier l'utilisateur principal
    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-}")
    local user_home=""
    if [[ -n "${main_user}" ]]; then
        user_home=$(getent passwd "${main_user}" | cut -d: -f6)
    fi

    if [[ -z "${user_home}" || -z "${main_user}" ]]; then
        warn "Impossible de déterminer l'utilisateur principal."
        return
    fi

    local user_uid user_gid
    user_uid=$(id -u "${main_user}")
    user_gid=$(id -g "${main_user}")

    # --- 1. uv pour l'utilisateur ---
    local uv_bin=""
    if [[ -x "${user_home}/.local/bin/uv" ]]; then
        uv_bin="${user_home}/.local/bin/uv"
    elif command -v uv &> /dev/null; then
        uv_bin=$(command -v uv)
    elif [[ -x "/root/.local/bin/uv" ]]; then
        uv_bin="/root/.local/bin/uv"
    fi

    if [[ "${main_user}" != "root" && ! -x "${user_home}/.local/bin/uv" ]]; then
        su - "${main_user}" -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' 2>/dev/null || true
        uv_bin="${user_home}/.local/bin/uv"
        info "uv installé pour ${main_user}."
    fi

    # --- 2. Dépôt AnKLuMe dans la home ZFS ---
    # Après le montage ZFS, le repo btrfs est masqué.
    # On utilise le repo sauvegardé par save_repo_source() (dans /tmp)
    # ou le repo déjà présent dans la home ZFS (re-bootstrap).
    local anklume_dir="${user_home}/AnKLuMe"

    if [[ -d "${anklume_dir}/.git" ]]; then
        # Déjà présent dans la home ZFS → pull pour MAJ
        info "Dépôt AnKLuMe existant dans ${anklume_dir}, mise à jour..."
        su - "${main_user}" -c "cd '${anklume_dir}' && git pull --ff-only" 2>/dev/null || {
            warn "git pull échoué (modifications locales ?). Dépôt conservé tel quel."
        }
    elif [[ -n "${BOOTSTRAP_REPO_DIR}" && -d "${BOOTSTRAP_REPO_DIR}/.git" ]]; then
        # Copier depuis la sauvegarde /tmp (repo source sauvé avant montage ZFS)
        info "Restauration du dépôt depuis ${BOOTSTRAP_REPO_DIR}..."
        cp -a "${BOOTSTRAP_REPO_DIR}" "${anklume_dir}"
        chown -R "${user_uid}:${user_gid}" "${anklume_dir}"
        info "Dépôt restauré dans ${anklume_dir}"
        # Nettoyage de la copie temporaire
        if [[ "${BOOTSTRAP_REPO_DIR}" == /tmp/* ]]; then
            rm -rf "${BOOTSTRAP_REPO_DIR}"
        fi
    else
        # Dernier recours : cloner depuis GitHub
        warn "Repo source introuvable. Clonage depuis GitHub..."
        su - "${main_user}" -c \
            "git clone https://github.com/jmchantrein/AnKLuMe.git '${anklume_dir}'" 2>/dev/null || {
            error "git clone échoué. Installer manuellement :"
            error "  git clone https://github.com/jmchantrein/AnKLuMe.git ${anklume_dir}"
            error "  cd ${anklume_dir} && uv tool install --with textual ."
            return
        }
    fi

    # Fixer les droits
    if [[ -d "${anklume_dir}" ]]; then
        chown -R "${user_uid}:${user_gid}" "${anklume_dir}"
    fi

    # --- 3. Installer la CLI via uv depuis le repo local ---
    if [[ -n "${uv_bin}" && -d "${anklume_dir}" && ! -f "${anklume_dir}/pyproject.toml" ]]; then
        warn "pyproject.toml introuvable dans ${anklume_dir}. Installation CLI ignorée."
    elif [[ -n "${uv_bin}" && -d "${anklume_dir}" ]]; then
        info "Installation de la CLI anklume depuis ${anklume_dir}..."
        if [[ "${main_user}" != "root" ]]; then
            su - "${main_user}" -c \
                "${uv_bin} tool install --force --with textual '${anklume_dir}'" || {
                warn "Installation CLI échouée. Installer manuellement :"
                warn "  cd ${anklume_dir} && uv tool install --with textual ."
            }
        else
            "${uv_bin}" tool install --force --with textual "${anklume_dir}" || {
                warn "Installation CLI échouée."
            }
        fi
    else
        warn "uv ou repo local absent. Installation CLI ignorée."
    fi

    # --- 4. PATH + alias ank ---
    setup_shell_integration "${main_user}" "${user_home}"

    info "AnKLuMe OK."
}

setup_shell_integration() {
    local main_user="$1"
    local user_home="$2"

    if [[ -z "${user_home}" ]]; then
        warn "Impossible de déterminer le home de l'utilisateur."
        return
    fi

    # Bloc à injecter dans bash/zsh
    local shell_block
    shell_block=$(cat << 'BLOCK'
# AnKLuMe — PATH + alias
export PATH="${HOME}/.local/bin:${PATH}"
command -v anklume &> /dev/null && alias ank='anklume'
BLOCK
)

    # --- Bash ---
    local bashrc="${user_home}/.bashrc"
    if [[ -f "${bashrc}" ]] && ! grep -q "alias ank=" "${bashrc}" 2>/dev/null; then
        printf '\n%s\n' "${shell_block}" >> "${bashrc}"
        info "bash : alias ank ajouté dans ${bashrc}"
    elif [[ ! -f "${bashrc}" ]]; then
        printf '%s\n' "${shell_block}" > "${bashrc}"
        info "bash : ${bashrc} créé avec alias ank"
    else
        info "bash : alias ank déjà présent."
    fi

    # --- Zsh ---
    local zshrc="${user_home}/.zshrc"
    if [[ -f "${zshrc}" ]] && ! grep -q "alias ank=" "${zshrc}" 2>/dev/null; then
        printf '\n%s\n' "${shell_block}" >> "${zshrc}"
        info "zsh  : alias ank ajouté dans ${zshrc}"
    elif [[ -f "${zshrc}" ]]; then
        info "zsh  : alias ank déjà présent."
    fi
    # On ne crée pas .zshrc s'il n'existe pas (l'utilisateur n'utilise peut-être pas zsh)

    # --- Fish ---
    local fish_conf_dir="${user_home}/.config/fish"
    local fish_conf="${fish_conf_dir}/config.fish"
    if command -v fish &> /dev/null || [[ -d "${fish_conf_dir}" ]]; then
        mkdir -p "${fish_conf_dir}"
        if ! grep -q "alias ank" "${fish_conf}" 2>/dev/null; then
            cat >> "${fish_conf}" << 'FISH'

# AnKLuMe — PATH + alias
fish_add_path ~/.local/bin
alias ank='anklume'
FISH
            info "fish : alias ank ajouté dans ${fish_conf}"
        else
            info "fish : alias ank déjà présent."
        fi
    fi

    # Fixer les droits (les fichiers ont été écrits en root)
    if [[ -n "${main_user}" && "${main_user}" != "root" ]]; then
        local user_uid user_gid
        user_uid=$(id -u "${main_user}")
        user_gid=$(id -g "${main_user}")
        for f in "${bashrc}" "${zshrc}" "${fish_conf}"; do
            [[ -f "${f}" ]] && chown "${user_uid}:${user_gid}" "${f}"
        done
        [[ -d "${fish_conf_dir}" ]] && chown -R "${user_uid}:${user_gid}" "${fish_conf_dir}"
    fi
}

# ---------------------------------------------------------------------------
# 9. Résumé
# ---------------------------------------------------------------------------

summary() {
    step "Résumé"

    local label result

    label="Distribution"
    result="${DISTRO} (${DISTRO_FAMILY})"
    printf "  %-20s %s\n" "${label}" "${result}"

    label="ZFS pool"
    result=$(zpool list "${POOL}" -H -o health 2>/dev/null) || result="?"
    printf "  %-20s %s\n" "${label}" "${result}"

    label="ZFS keystatus"
    result=$(zfs get -H -o value keystatus "${POOL}" 2>/dev/null) || result="?"
    printf "  %-20s %s\n" "${label}" "${result}"

    label="ZFS keylocation"
    result=$(zfs get -H -o value keylocation "${POOL}" 2>/dev/null) || result="?"
    printf "  %-20s %s\n" "${label}" "${result}"

    label="ZFS keyfile"
    if [[ -f "${ZFS_KEY_FILE}" ]]; then result="présent (raw 32B)"; else result="absent"; fi
    printf "  %-20s %s\n" "${label}" "${result}"

    label="ZFS backup chiffré"
    if [[ -f "${ZFS_KEY_ENC}" ]]; then result="présent"; else result="absent"; fi
    printf "  %-20s %s\n" "${label}" "${result}"

    label="Incus"
    result=$(systemctl is-active incus 2>/dev/null) || result="?"
    printf "  %-20s %s\n" "${label}" "${result}"

    label="Incus storage"
    result=$(incus storage list -f csv -c n 2>/dev/null | head -1) || result="absent"
    [[ -z "${result}" ]] && result="absent"
    printf "  %-20s %s\n" "${label}" "${result}"

    label="NVIDIA"
    result=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null) || result="non détecté"
    printf "  %-20s %s\n" "${label}" "${result}"

    echo ""
    local -a tools=(ansible-playbook uv git tmux jq anklume)
    local tool
    for tool in "${tools[@]}"; do
        if command -v "${tool}" &> /dev/null; then
            printf "  %-20s OK\n" "${tool}"
        else
            printf "  %-20s MANQUANT\n" "${tool}"
        fi
    done

    echo ""
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo "=== bootstrap.sh — Préparation hôte AnKLuMe ==="
    echo ""

    check_root
    detect_distro
    install_base_packages
    create_zfs_pool
    create_zfs_datasets
    setup_systemd
    setup_incus
    setup_nvidia
    setup_toram          # mkinitcpio/initramfs tourne ici — /home doit être btrfs
    save_repo_source     # sauvegarder le repo dans /tmp AVANT que ZFS masque /home
    mount_zfs_home       # maintenant on peut masquer /home btrfs par ZFS
    install_anklume
    summary

    info "Bootstrap terminé."
    echo ""
    warn "IMPORTANT : un redémarrage est nécessaire."
    echo ""
    echo "Le montage ZFS sur /home a remplacé le contenu btrfs d'origine."
    echo "Au redémarrage, systemd recréera les répertoires utilisateur"
    echo "standard (Desktop, Documents, etc.) et le shell sera correctement"
    echo "initialisé avec le PATH et les alias."
    echo ""
    echo "Prochaines étapes :"
    echo "  1. sudo reboot"
    echo "  2. anklume init mon-infra && cd mon-infra"
    echo "  3. anklume tui"
    echo "  4. anklume apply all"
    echo ""
    echo "Sécurité ZFS :"
    echo "  - Keyfile raw  : ${ZFS_KEY_FILE} (32B, déverrouillage auto au boot)"
    echo "  - Backup chiffré : ${ZFS_KEY_ENC} (déchiffrable avec passphrase)"
    echo "  - Si keyfile perdu → passphrase demandée au boot → keyfile restauré"
    echo ""
}

main
