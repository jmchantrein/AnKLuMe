# shellcheck shell=bash
# host/lib/nvidia.sh — Détection et installation NVIDIA GPU
#
# Source guard : évite le double-chargement
[[ -n "${_LIB_NVIDIA_SH:-}" ]] && return; _LIB_NVIDIA_SH=1

# Dépend de common.sh pour les fonctions de logging
SCRIPT_DIR_NVIDIA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=host/lib/common.sh
source "${SCRIPT_DIR_NVIDIA}/common.sh"

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

# Installation standard (pré-Blackwell) — nécessite DISTRO_FAMILY
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

# Installation Blackwell (driver 570+) — nécessite DISTRO_FAMILY
install_nvidia_blackwell() {
    if [[ "${DISTRO_FAMILY}" == "arch" ]]; then
        # Arch : le driver 570+ est dans les dépôts
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
