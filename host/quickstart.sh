#!/usr/bin/env bash
# quickstart.sh — Installe AnKLuMe sur un système existant
#
# Script minimal pour essayer AnKLuMe sans modifier la configuration
# système (pas de ZFS, pas de toram, pas de partitionnement).
# Installe uniquement : Incus + uv + AnKLuMe + alias ank.
#
# Distributions supportées : Arch Linux, Debian 13+
#
# Usage :
#   sudo ./quickstart.sh [options]
#
# Options :
#   --gpu       Installer aussi le driver NVIDIA (pour tester ai-tools)
#   -h, --help  Afficher l'aide
#
# Ce script est idempotent : il peut être relancé sans danger.

set -euo pipefail

# ---------------------------------------------------------------------------
# Couleurs et flags
# ---------------------------------------------------------------------------

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

INSTALL_GPU=false

# Détection de la distribution
DISTRO=""
DISTRO_FAMILY=""

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --gpu)  INSTALL_GPU=true; shift ;;
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
        error "Ce script doit être exécuté en root (sudo)."
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# 0. Détection de la distribution
# ---------------------------------------------------------------------------

detect_distro() {
    step "Détection de la distribution"

    if [[ ! -f /etc/os-release ]]; then
        error "/etc/os-release introuvable."
        exit 1
    fi

    # shellcheck source=/dev/null
    source /etc/os-release

    case "${ID:-}" in
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
            error "Distributions supportées : Arch Linux, Debian."
            exit 1
            ;;
    esac

    info "Distribution détectée : ${PRETTY_NAME:-${ID}} (famille ${DISTRO_FAMILY})"
}

# ---------------------------------------------------------------------------
# 1. Paquets essentiels
# ---------------------------------------------------------------------------

install_packages() {
    step "Installation des paquets essentiels"

    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        pacman -Syu --noconfirm --needed \
            curl git jq ansible-core python \
            > /dev/null 2>&1

        if ! command -v incus &> /dev/null; then
            pacman -S --noconfirm --needed incus > /dev/null 2>&1
        fi
    else
        apt-get update -qq || { error "apt-get update échoué"; exit 1; }

        apt-get install -y -qq \
            curl git jq ansible-core python3 \
            > /dev/null

        if ! command -v incus &> /dev/null; then
            apt-get install -y -qq incus > /dev/null
        fi
    fi

    info "Paquets essentiels OK."
}

# ---------------------------------------------------------------------------
# 2. Incus (démarrage + init)
# ---------------------------------------------------------------------------

setup_incus() {
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

    # Initialisation minimale si pas déjà fait
    if ! incus profile show default &> /dev/null 2>&1; then
        incus admin init --minimal
        info "Incus initialisé (minimal)."
    fi

    # Groupe incus-admin pour l'utilisateur
    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-}")
    if [[ -n "${main_user}" ]] && ! id -nG "${main_user}" 2>/dev/null | grep -qw incus-admin; then
        usermod -aG incus-admin "${main_user}"
        info "Utilisateur '${main_user}' ajouté au groupe incus-admin."
    fi

    info "Incus OK."
}

# ---------------------------------------------------------------------------
# 3. NVIDIA GPU (optionnel, --gpu)
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

detect_nvidia_gpu() {
    # Retourne : "blackwell", "supported", ou "none"
    if ! lspci -nn 2>/dev/null | grep -qi "nvidia"; then
        echo "none"
        return
    fi

    # Vérifier si c'est un GPU Blackwell
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

install_nvidia() {
    if [[ "${INSTALL_GPU}" != true ]]; then
        return
    fi

    step "Installation NVIDIA GPU"

    # Déjà installé ?
    if command -v nvidia-smi &> /dev/null; then
        info "NVIDIA driver déjà installé :"
        nvidia-smi --query-gpu=driver_version,name,memory.total \
            --format=csv,noheader 2>/dev/null || true
        return
    fi

    local gpu_gen
    gpu_gen=$(detect_nvidia_gpu)

    case "${gpu_gen}" in
        none)
            warn "Aucun GPU NVIDIA détecté. Rien à installer."
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
        info "Installation via apt (nvidia-driver)..."
        # S'assurer que non-free est activé
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
        # Arch : le driver 570+ est dans les dépôts
        info "Installation via pacman (nvidia-open-dkms, 570+)..."
        pacman -S --noconfirm --needed \
            nvidia-open-dkms nvidia-utils > /dev/null 2>&1
        info "NVIDIA Blackwell driver installé."
    else
        # Debian : le driver 570+ n'est PAS dans les dépôts.
        # Fallback : télécharger et installer le .run NVIDIA.
        warn "Blackwell nécessite le driver ${NVIDIA_BLACKWELL_VERSION}."
        warn "Ce driver n'est pas dans les dépôts Debian — installation via .run"

        # Prérequis
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
            update-initramfs -u 2>/dev/null || true
            info "Module nouveau blacklisté."
        fi

        # Vérifier que nouveau n'est pas chargé
        if lsmod | grep -q nouveau; then
            warn "Le module nouveau est encore chargé."
            warn "Un reboot est nécessaire avant d'installer le driver Blackwell."
            warn "Après reboot, relancez : sudo ./quickstart.sh --gpu"
            return
        fi

        # Télécharger le .run
        local run_file="/tmp/NVIDIA-Linux-x86_64-${NVIDIA_BLACKWELL_VERSION}.run"
        if [[ ! -f "${run_file}" ]]; then
            info "Téléchargement du driver ${NVIDIA_BLACKWELL_VERSION}..."
            curl -L -o "${run_file}" "${NVIDIA_BLACKWELL_RUN}" || {
                error "Échec du téléchargement. URL : ${NVIDIA_BLACKWELL_RUN}"
                exit 1
            }
        fi

        # Installer
        chmod +x "${run_file}"
        info "Installation du driver NVIDIA ${NVIDIA_BLACKWELL_VERSION} (open kernel modules)..."
        "${run_file}" --dkms --open --silent || {
            error "Échec de l'installation. Vérifier les logs : /var/log/nvidia-installer.log"
            exit 1
        }

        rm -f "${run_file}"
        info "NVIDIA Blackwell driver ${NVIDIA_BLACKWELL_VERSION} installé."
    fi
}

# ---------------------------------------------------------------------------
# 4. uv + AnKLuMe + alias ank
# ---------------------------------------------------------------------------

install_anklume() {
    step "Installation d'AnKLuMe"

    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-}")
    local user_home=""
    if [[ -n "${main_user}" ]]; then
        user_home=$(getent passwd "${main_user}" | cut -d: -f6)
    fi

    # Installer uv pour l'utilisateur
    if [[ -n "${main_user}" && "${main_user}" != "root" ]]; then
        if [[ ! -x "${user_home}/.local/bin/uv" ]]; then
            su - "${main_user}" -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' 2>/dev/null || true
            info "uv installé pour ${main_user}."
        fi
    else
        if ! command -v uv &> /dev/null; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
            export PATH="/root/.local/bin:${PATH}"
        fi
    fi

    # Créer le wrapper CLI si le repo existe
    local anklume_dir="${user_home}/AnKLuMe"
    local uv_bin="${user_home}/.local/bin/uv"
    [[ "${main_user}" == "root" ]] && anklume_dir="/root/AnKLuMe" && uv_bin="/root/.local/bin/uv"

    if [[ -x "${uv_bin}" && -d "${anklume_dir}" && -f "${anklume_dir}/pyproject.toml" ]]; then
        local bin_dir="${user_home}/.local/bin"
        [[ "${main_user}" == "root" ]] && bin_dir="/root/.local/bin"
        mkdir -p "${bin_dir}"

        cat > "${bin_dir}/anklume" << WRAPPER
#!/usr/bin/env bash
exec ${uv_bin} run --directory '${anklume_dir}' anklume "\$@"
WRAPPER
        chmod +x "${bin_dir}/anklume"
        [[ -n "${main_user}" && "${main_user}" != "root" ]] && \
            chown "$(id -u "${main_user}"):$(id -g "${main_user}")" "${bin_dir}/anklume"

        # Sync les dépendances
        if [[ "${main_user}" != "root" ]]; then
            su - "${main_user}" -c "cd '${anklume_dir}' && ${uv_bin} sync --quiet" 2>/dev/null || true
        else
            cd "${anklume_dir}" && "${uv_bin}" sync --quiet 2>/dev/null || true
        fi

        info "CLI installée : ${bin_dir}/anklume (wrapper vers ${anklume_dir})"
    else
        warn "Repo AnKLuMe introuvable dans ${anklume_dir}."
        warn "  git clone https://github.com/jmchantrein/AnKLuMe.git ${anklume_dir}"
    fi

    # Alias ank dans les shells
    setup_shell_alias "${main_user}" "${user_home}"

    info "AnKLuMe OK."
}

setup_shell_alias() {
    local main_user="$1"
    local user_home="$2"

    [[ -z "${user_home}" ]] && return

    local shell_block
    shell_block=$(cat << 'BLOCK'
# AnKLuMe — PATH + alias
export PATH="${HOME}/.local/bin:${PATH}"
command -v anklume &> /dev/null && alias ank='anklume'
BLOCK
)

    # Bash
    local bashrc="${user_home}/.bashrc"
    if [[ -f "${bashrc}" ]] && ! grep -q "alias ank=" "${bashrc}" 2>/dev/null; then
        printf '\n%s\n' "${shell_block}" >> "${bashrc}"
        info "bash : alias ank ajouté"
    elif [[ ! -f "${bashrc}" ]]; then
        printf '%s\n' "${shell_block}" > "${bashrc}"
        info "bash : ${bashrc} créé avec alias ank"
    fi

    # Zsh (seulement si .zshrc existe)
    local zshrc="${user_home}/.zshrc"
    if [[ -f "${zshrc}" ]] && ! grep -q "alias ank=" "${zshrc}" 2>/dev/null; then
        printf '\n%s\n' "${shell_block}" >> "${zshrc}"
        info "zsh  : alias ank ajouté"
    fi

    # Fish
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
            info "fish : alias ank ajouté"
        fi
    fi

    # Fixer les droits
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
# 5. Résumé
# ---------------------------------------------------------------------------

summary() {
    step "Résumé"

    local label result

    label="Distribution"
    printf "  %-20s %s\n" "${label}" "${DISTRO} (${DISTRO_FAMILY})"

    label="Incus"
    result=$(systemctl is-active incus 2>/dev/null) || result="?"
    printf "  %-20s %s\n" "${label}" "${result}"

    if [[ "${INSTALL_GPU}" == true ]]; then
        label="NVIDIA"
        result=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null) || result="non détecté"
        printf "  %-20s %s\n" "${label}" "${result}"
    fi

    echo ""
    local -a tools=(incus ansible-playbook uv git jq anklume)
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
    echo "=== quickstart.sh — Installation rapide AnKLuMe ==="
    echo ""

    check_root
    detect_distro
    install_packages
    setup_incus
    install_nvidia
    install_anklume
    summary

    info "Installation terminée."
    echo ""
    echo "Prochaines étapes :"
    echo "  1. Se reloguer (groupe incus-admin + alias ank)"
    echo "  2. anklume init mon-infra && cd mon-infra"
    echo "  3. anklume tui"
    echo "  4. anklume apply all"
    echo ""
}

main
