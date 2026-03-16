#!/usr/bin/env bash
# bootstrap-cachyos.sh — Prépare un hôte CachyOS (Arch) pour AnKLuMe
#
# Point de départ : CachyOS fresh install (LUKS + btrfs sur NVMe système)
# Résultat : ZFS chiffré (mirror) + Incus + AnKLuMe prêt à l'emploi
#
# Matériel cible (ThinkPad) :
#   nvme2n1  — Samsung 512G  — système (LUKS + btrfs, déjà installé)
#   nvme0n1  — Corsair 3.6T  — ZFS mirror leg 1
#   nvme1n1  — Corsair 3.6T  — ZFS mirror leg 2
#
# Usage :
#   sudo ./bootstrap-cachyos.sh [options]
#
# Options :
#   --skip-nvidia         Ne pas vérifier le driver NVIDIA
#   --skip-toram          Ne pas configurer le mode toram
#   --skip-zfs-pool       Ne pas créer/recréer le pool ZFS
#   --skip-incus          Ne pas configurer Incus
#   --zfs-passphrase      Lire la passphrase depuis stdin (non interactif)
#
# Ce script est idempotent : il peut être relancé sans danger.
# Shellcheck clean : shellcheck -o all bootstrap-cachyos.sh

set -euo pipefail

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

# Disques ZFS (by-id pour la stabilité)
readonly ZFS_DISK_1="nvme-Corsair_MP600_PRO_LPX_A5KOB412202JOL"
readonly ZFS_DISK_2="nvme-Corsair_MP600_PRO_LPX_A5KOB412202QAL"

# Couleurs
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly NC='\033[0m'

# Flags
SKIP_NVIDIA=false
SKIP_TORAM=false
SKIP_ZFS_POOL=false
SKIP_INCUS=false
PASSPHRASE_STDIN=false

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --skip-nvidia)       SKIP_NVIDIA=true; shift ;;
        --skip-toram)        SKIP_TORAM=true; shift ;;
        --skip-zfs-pool)     SKIP_ZFS_POOL=true; shift ;;
        --skip-incus)        SKIP_INCUS=true; shift ;;
        --zfs-passphrase)    PASSPHRASE_STDIN=true; shift ;;
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

info()  { printf "${GREEN}[INFO]${NC} %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC} %s\n" "$1"; }
error() { printf "${RED}[ERREUR]${NC} %s\n" "$1" >&2; }

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
# 1. Paquets de base (pacman)
# ---------------------------------------------------------------------------

install_base_packages() {
    info "Installation des paquets de base..."

    # Synchroniser et installer en une passe
    pacman -Sy --noconfirm --needed \
        base-devel dkms pkg-config \
        curl git tmux jq vim \
        ansible-core python \
        > /dev/null 2>&1

    # ZFS : zfs-utils + module pré-compilé CachyOS
    if ! command -v zfs &> /dev/null; then
        info "  Installation de ZFS..."
        pacman -S --noconfirm --needed zfs-utils > /dev/null 2>&1
        # cachyos-zfs tire le module ZFS pré-compilé pour les kernels CachyOS
        pacman -S --noconfirm --needed cachyos-zfs > /dev/null 2>&1 || {
            # Fallback : compilation DKMS
            warn "  cachyos-zfs indisponible, fallback sur zfs-dkms..."
            pacman -S --noconfirm --needed zfs-dkms > /dev/null 2>&1
        }
    fi

    # Charger le module ZFS
    if ! lsmod | grep -q "^zfs "; then
        modprobe zfs
        info "  Module ZFS chargé."
    fi

    # Incus
    if ! command -v incus &> /dev/null; then
        pacman -S --noconfirm --needed incus > /dev/null 2>&1
    fi

    # uv (Python package manager)
    if ! command -v uv &> /dev/null; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="${HOME}/.local/bin:${PATH}"
        info "  uv installé."
    fi

    info "Paquets de base OK."
}

# ---------------------------------------------------------------------------
# 2. Pool ZFS chiffré (mirror) + keyfile
# ---------------------------------------------------------------------------

create_zfs_pool() {
    if [[ "${SKIP_ZFS_POOL}" == true ]]; then
        info "Pool ZFS : ignoré (--skip-zfs-pool)."
        return
    fi

    # Si le pool existe déjà, on ne le recrée pas (idempotence)
    if zpool list "${POOL}" &> /dev/null; then
        info "Pool ZFS '${POOL}' existe déjà."
        unlock_zfs_pool
        return
    fi

    # Vérifier que les disques existent
    for disk in "${ZFS_DISK_1}" "${ZFS_DISK_2}"; do
        if [[ ! -e "/dev/disk/by-id/${disk}" ]]; then
            error "Disque introuvable : /dev/disk/by-id/${disk}"
            exit 1
        fi
    done

    info "Création du pool ZFS '${POOL}' (mirror, chiffré AES-256-GCM)..."

    # 1. Générer un keyfile aléatoire de 32 bytes (clé raw)
    mkdir -p "${ZFS_KEY_DIR}"
    (umask 077 && dd if=/dev/urandom of="${ZFS_KEY_FILE}" bs=32 count=1 2>/dev/null)
    chmod 400 "${ZFS_KEY_FILE}"
    chown root:root "${ZFS_KEY_FILE}"
    info "  Keyfile généré : ${ZFS_KEY_FILE} (32 bytes aléatoires)"

    # 2. Chiffrer une copie du keyfile avec une passphrase (backup de secours)
    local passphrase
    passphrase=$(ask_passphrase)

    openssl enc -aes-256-cbc -pbkdf2 -iter 600000 \
        -salt -in "${ZFS_KEY_FILE}" -out "${ZFS_KEY_ENC}" \
        -pass "pass:${passphrase}"
    chmod 400 "${ZFS_KEY_ENC}"
    chown root:root "${ZFS_KEY_ENC}"
    info "  Backup chiffré : ${ZFS_KEY_ENC} (déchiffrable avec la passphrase)"

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
        "/dev/disk/by-id/${ZFS_DISK_1}" \
        "/dev/disk/by-id/${ZFS_DISK_2}"

    info "  Pool '${POOL}' créé (mirror, chiffré, keyformat=raw)."
    info "  Boot auto  : ${ZFS_KEY_FILE}"
    info "  Secours    : passphrase → déchiffre ${ZFS_KEY_ENC} → unlock"
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

    # 1. Essayer la keylocation configurée (normalement file:// vers le keyfile)
    if zfs load-key "${POOL}" 2>/dev/null; then
        info "  Déverrouillé via keylocation configurée."
        zfs mount -a 2>/dev/null || true
        return
    fi

    # 2. Essayer le keyfile explicitement
    if [[ -f "${ZFS_KEY_FILE}" ]]; then
        if zfs load-key -L "file://${ZFS_KEY_FILE}" "${POOL}" 2>/dev/null; then
            info "  Déverrouillé via keyfile."
            zfs mount -a 2>/dev/null || true
            return
        fi
    fi

    # 3. Fallback : déchiffrer le backup avec la passphrase
    if [[ -f "${ZFS_KEY_ENC}" ]]; then
        warn "  Keyfile absent ou invalide. Déchiffrement du backup..."
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
                    info "  Déverrouillé via passphrase. Keyfile restauré."
                    zfs mount -a 2>/dev/null || true
                    return
                fi
            fi
            warn "  Passphrase incorrecte ou backup corrompu."
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
    ensure_dataset "${POOL}/_srv_models_ollama" -o mountpoint=none
    ensure_dataset "${POOL}/_srv_models_stt"    -o mountpoint=none

    # Home — canmount=noauto : ne se monte pas automatiquement à la création.
    # On le monte explicitement à la fin du script (mount_zfs_home) pour
    # éviter de masquer /home btrfs pendant que mkinitcpio tourne.
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
# 3b. Montage final de /home (après mkinitcpio)
# ---------------------------------------------------------------------------

mount_zfs_home() {
    # Activer le montage automatique pour les futurs boots
    zfs set canmount=on "${POOL}/_home" 2>/dev/null || true

    local home_fstype
    home_fstype=$(findmnt -no FSTYPE /home 2>/dev/null) || home_fstype=""
    if ! mountpoint -q /home || [[ "${home_fstype}" != "zfs" ]]; then
        zfs mount "${POOL}/_home" 2>/dev/null || true
        info "/home monté depuis ZFS (${POOL}/_home)."
    else
        info "/home déjà monté depuis ZFS."
    fi
}

# ---------------------------------------------------------------------------
# 4. Systemd — déverrouillage ZFS + ordering Incus
# ---------------------------------------------------------------------------

setup_systemd() {
    info "Configuration systemd..."

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
    info "  Script ${unlock_script} installé."

    # --- Service systemd ---
    local key_service="/etc/systemd/system/zfs-load-key-tank.service"
    cat > "${key_service}" << 'UNIT'
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
UNIT
    info "  Service zfs-load-key-tank.service installé."

    # --- Drop-in Incus : après ZFS ---
    local incus_dropin="/etc/systemd/system/incus.service.d"
    mkdir -p "${incus_dropin}"
    cat > "${incus_dropin}/after-zfs.conf" << 'DROPIN'
[Unit]
After=zfs-mount.service
Requires=zfs-mount.service
DROPIN
    info "  Drop-in Incus after-zfs.conf installé."

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

    info "Configuration Incus..."

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
    info "  Incus actif."

    # Initialisation minimale
    if ! incus profile show default &> /dev/null 2>&1; then
        incus admin init --minimal
        info "  Incus initialisé (minimal)."
    fi

    # Storage pool ZFS
    if ! incus storage show "${INCUS_STORAGE}" &> /dev/null 2>&1; then
        incus storage create "${INCUS_STORAGE}" zfs source="${POOL}/_incus"
        info "  Storage pool '${INCUS_STORAGE}' créé."
    else
        info "  Storage pool '${INCUS_STORAGE}' existe déjà."
    fi

    # Groupe incus-admin
    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-}")
    if [[ -n "${main_user}" ]] && ! id -nG "${main_user}" 2>/dev/null | grep -qw incus-admin; then
        usermod -aG incus-admin "${main_user}"
        info "  Utilisateur '${main_user}' ajouté au groupe incus-admin."
    fi

    info "Incus OK."
}

# ---------------------------------------------------------------------------
# 6. NVIDIA (vérification)
# ---------------------------------------------------------------------------

check_nvidia() {
    if [[ "${SKIP_NVIDIA}" == true ]]; then
        info "NVIDIA : ignoré (--skip-nvidia)."
        return
    fi

    if command -v nvidia-smi &> /dev/null; then
        info "NVIDIA driver OK :"
        nvidia-smi --query-gpu=driver_version,name,memory.total \
            --format=csv,noheader 2>/dev/null || true
    else
        warn "NVIDIA driver non détecté."
        warn "  sudo pacman -S nvidia-open-dkms nvidia-utils"
    fi
}

# ---------------------------------------------------------------------------
# 7. Mode toram (Limine + mkinitcpio)
# ---------------------------------------------------------------------------

setup_toram() {
    if [[ "${SKIP_TORAM}" == true ]]; then
        info "Mode toram : ignoré (--skip-toram)."
        return
    fi

    info "Configuration du mode toram..."

    # --- Hook mkinitcpio (install) ---
    local hook_install="/usr/lib/initcpio/install/toram"
    cat > "${hook_install}" << 'EOF'
#!/bin/bash
build() {
    add_runscript
}

help() {
    cat <<HELPEOF
Enables toram overlay when BOOT_MODE=toram is on the kernel cmdline.
HELPEOF
}
EOF
    chmod +x "${hook_install}"

    # --- Hook mkinitcpio (runtime) ---
    local hook_runtime="/usr/lib/initcpio/hooks/toram"
    cat > "${hook_runtime}" << 'EOF'
#!/usr/bin/ash
run_hook() {
    grep -q "BOOT_MODE=toram" /proc/cmdline || return

    mkdir -p /mnt/lower /mnt/upper-tmpfs
    mount -o remount,ro "$root"
    mount -o move "$root" /mnt/lower
    mount -t tmpfs -o size=80% tmpfs /mnt/upper-tmpfs
    mkdir -p /mnt/upper-tmpfs/upper /mnt/upper-tmpfs/work
    mount -t overlay overlay \
        -o "lowerdir=/mnt/lower,upperdir=/mnt/upper-tmpfs/upper,workdir=/mnt/upper-tmpfs/work" \
        "$root"
    mkdir -p "${root}/mnt/rootfs-disk"
    mount -o move /mnt/lower "${root}/mnt/rootfs-disk"
}
EOF
    chmod +x "${hook_runtime}"
    info "  Hooks mkinitcpio toram installés."

    # Ajouter à HOOKS si absent
    if ! grep -q "toram" /etc/mkinitcpio.conf; then
        sed -i 's/\(HOOKS=.*\)filesystems/\1toram filesystems/' /etc/mkinitcpio.conf
        mkinitcpio -P
        info "  mkinitcpio regénéré avec hook toram."
    else
        info "  Hook toram déjà dans mkinitcpio.conf."
    fi

    # --- Entrée Limine ---
    local limine_conf="/boot/limine.conf"
    if [[ -f "${limine_conf}" ]] && ! grep -q "BOOT_MODE=toram" "${limine_conf}"; then
        local luks_uuid luks_name root_subvol
        root_subvol=$(findmnt -no OPTIONS / | grep -oP 'subvol=\K[^,]+' || true)
        luks_uuid=$(blkid -t TYPE=crypto_LUKS -o value -s UUID | head -1)

        # Trouver le device mapper LUKS sans ls|grep
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

        # Ajouter avant la section /EFI fallback (ou à la fin)
        cat >> "${limine_conf}" << ENTRY

/CachyOS (toram -- immutable)
    protocol: linux
    kernel_path: boot():/vmlinuz-linux-cachyos-lts
    kernel_cmdline: ${cmdline}
    module_path: boot():/intel-ucode.img
    module_path: boot():/initramfs-linux-cachyos-lts.img
ENTRY
        info "  Entrée Limine toram ajoutée."
    else
        info "  Entrée Limine toram existe déjà."
    fi

    info "Mode toram OK."
}

# ---------------------------------------------------------------------------
# 8. AnKLuMe
# ---------------------------------------------------------------------------

install_anklume() {
    export PATH="${HOME}/.local/bin:/root/.local/bin:${PATH}"

    if command -v anklume &> /dev/null; then
        info "anklume déjà installé."
        return
    fi

    info "Installation d'anklume..."
    if command -v uv &> /dev/null; then
        if uv tool install anklume 2>/dev/null; then
            info "anklume installé via uv."
        else
            warn "anklume pas encore publié sur PyPI. Installer manuellement."
        fi
    else
        warn "uv introuvable. Installer manuellement : uv tool install anklume"
    fi
}

# ---------------------------------------------------------------------------
# 9. Résumé
# ---------------------------------------------------------------------------

summary() {
    echo ""
    echo "=== Résumé ==="
    echo ""

    local label result

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
    echo "=== bootstrap-cachyos.sh — Préparation hôte AnKLuMe (CachyOS) ==="
    echo ""

    check_root
    install_base_packages
    create_zfs_pool
    create_zfs_datasets
    setup_systemd
    setup_incus
    check_nvidia
    setup_toram          # mkinitcpio tourne ici — /home doit être btrfs
    mount_zfs_home       # maintenant on peut masquer /home btrfs par ZFS
    install_anklume
    summary

    info "Bootstrap terminé."
    echo ""
    echo "Prochaines étapes :"
    echo "  1. Se reloguer (groupe incus-admin)"
    echo "  2. anklume init mon-infra && cd mon-infra"
    echo "  3. anklume tui"
    echo "  4. anklume apply all"
    echo ""
    echo "Sécurité ZFS :"
    echo "  - Keyfile raw  : ${ZFS_KEY_FILE} (32B, déverrouillage auto au boot)"
    echo "  - Backup chiffré : ${ZFS_KEY_ENC} (déchiffrable avec passphrase)"
    echo "  - Si keyfile perdu → passphrase demandée au boot → keyfile restauré"
    echo "  - Clé et passphrase sont INDÉPENDANTES (keyformat=raw)"
    echo ""
}

main
