#!/usr/bin/env bash
# postinst.sh — Script post-installation pour ISO FAI.me AnKLuMe
#
# Ce script est exécuté au premier boot de l'ISO live/installée.
# Il installe AnKLuMe, détecte le GPU NVIDIA et installe le driver adapté.
#
# Conçu pour être uploadé dans le champ "post-install script" de FAI.me.

set -euo pipefail

readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly RED='\033[0;31m'
readonly NC='\033[0m'

info()  { printf "${GREEN}[INFO]${NC}  %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
error() { printf "${RED}[ERREUR]${NC} %s\n" "$1" >&2; }

# ---------------------------------------------------------------------------
# NVIDIA — détection auto + installation
# ---------------------------------------------------------------------------

# PCI device IDs Blackwell (RTX 50xx)
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
    if command -v nvidia-smi &> /dev/null; then
        info "NVIDIA driver déjà installé."
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
            info "GPU NVIDIA Blackwell détecté — driver ${NVIDIA_BLACKWELL_VERSION} requis."

            # Blacklister nouveau
            if ! grep -q "blacklist nouveau" /etc/modprobe.d/blacklist-nouveau.conf 2>/dev/null; then
                cat > /etc/modprobe.d/blacklist-nouveau.conf << 'CONF'
blacklist nouveau
options nouveau modeset=0
CONF
                update-initramfs -u 2>/dev/null || true
            fi

            # Si nouveau est chargé, on ne peut pas installer maintenant
            if lsmod | grep -q nouveau; then
                warn "Le module nouveau est chargé. Le driver sera installé au prochain boot."
                # Créer un service oneshot pour installer au prochain boot
                create_nvidia_install_service
                return
            fi

            install_nvidia_run
            ;;
        supported)
            info "GPU NVIDIA détecté — installation depuis les dépôts."

            # S'assurer que non-free est activé
            if ! grep -q "non-free" /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null; then
                sed -i 's/main$/main contrib non-free non-free-firmware/' \
                    /etc/apt/sources.list 2>/dev/null || true
                apt-get update -qq
            fi

            apt-get install -y -qq \
                "linux-headers-$(uname -r)" \
                nvidia-driver nvidia-open-kernel-dkms \
                firmware-nvidia-gsp \
                > /dev/null 2>&1 || {
                warn "Échec de l'installation via apt. GPU peut-être trop récent."
                warn "Tentative via le .run NVIDIA..."
                install_nvidia_run
            }
            ;;
    esac
}

install_nvidia_run() {
    apt-get install -y -qq \
        "linux-headers-$(uname -r)" \
        build-essential dkms pkg-config \
        > /dev/null 2>&1

    local run_file="/tmp/NVIDIA-Linux-x86_64-${NVIDIA_BLACKWELL_VERSION}.run"
    if [[ ! -f "${run_file}" ]]; then
        info "Téléchargement du driver ${NVIDIA_BLACKWELL_VERSION}..."
        curl -L -o "${run_file}" "${NVIDIA_BLACKWELL_RUN}" || {
            error "Échec du téléchargement."
            return 1
        }
    fi

    chmod +x "${run_file}"
    "${run_file}" --dkms --open --silent || {
        error "Échec de l'installation. Voir /var/log/nvidia-installer.log"
        return 1
    }

    rm -f "${run_file}"
    info "NVIDIA driver ${NVIDIA_BLACKWELL_VERSION} installé."
}

# Service oneshot : installe le driver au boot suivant (après nouveau déchargé)
create_nvidia_install_service() {
    cat > /etc/systemd/system/anklume-nvidia-install.service << 'UNIT'
[Unit]
Description=Installation du driver NVIDIA Blackwell (post-boot)
After=network-online.target
Wants=network-online.target
ConditionPathExists=!/usr/bin/nvidia-smi

[Service]
Type=oneshot
ExecStart=/usr/local/bin/anklume-nvidia-postboot
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
UNIT

    cat > /usr/local/bin/anklume-nvidia-postboot << SCRIPT
#!/usr/bin/env bash
set -euo pipefail
NVIDIA_VERSION="${NVIDIA_BLACKWELL_VERSION}"
NVIDIA_URL="${NVIDIA_BLACKWELL_RUN}"
apt-get install -y -qq "linux-headers-\$(uname -r)" build-essential dkms pkg-config > /dev/null 2>&1
run_file="/tmp/NVIDIA-Linux-x86_64-\${NVIDIA_VERSION}.run"
curl -L -o "\${run_file}" "\${NVIDIA_URL}"
chmod +x "\${run_file}"
"\${run_file}" --dkms --open --silent
rm -f "\${run_file}"
systemctl disable anklume-nvidia-install.service
rm -f /etc/systemd/system/anklume-nvidia-install.service
rm -f /usr/local/bin/anklume-nvidia-postboot
SCRIPT
    chmod +x /usr/local/bin/anklume-nvidia-postboot
    systemctl enable anklume-nvidia-install.service
    info "Service d'installation NVIDIA programmé au prochain boot."
}

# ---------------------------------------------------------------------------
# Incus
# ---------------------------------------------------------------------------

setup_incus() {
    if command -v incus &> /dev/null; then
        info "Incus déjà installé."
    else
        apt-get install -y -qq incus > /dev/null
        info "Incus installé."
    fi

    systemctl enable --now incus.socket incus.service 2>/dev/null || true

    local retries=10
    while ! incus info &> /dev/null && (( retries-- > 0 )); do
        sleep 1
    done

    if incus info &> /dev/null; then
        if ! incus profile show default &> /dev/null 2>&1; then
            incus admin init --minimal
        fi
        info "Incus opérationnel."
    else
        warn "Incus ne démarre pas (normal en live si pas assez de ressources)."
    fi
}

# ---------------------------------------------------------------------------
# AnKLuMe (uv + anklume + alias ank)
# ---------------------------------------------------------------------------

setup_anklume() {
    # Identifier l'utilisateur (peut être root en live)
    local main_user
    main_user=$(logname 2>/dev/null || echo "${SUDO_USER:-root}")
    local user_home
    user_home=$(getent passwd "${main_user}" | cut -d: -f6 || echo "/root")

    # uv
    if [[ ! -x "${user_home}/.local/bin/uv" ]] && ! command -v uv &> /dev/null; then
        if [[ "${main_user}" != "root" ]]; then
            su - "${main_user}" -c 'curl -LsSf https://astral.sh/uv/install.sh | sh' 2>/dev/null || true
        else
            curl -LsSf https://astral.sh/uv/install.sh | sh 2>/dev/null || true
            export PATH="/root/.local/bin:${PATH}"
        fi
        info "uv installé."
    fi

    # anklume
    local uv_bin="${user_home}/.local/bin/uv"
    [[ ! -x "${uv_bin}" ]] && uv_bin=$(command -v uv 2>/dev/null || true)

    if [[ -n "${uv_bin}" ]]; then
        if [[ "${main_user}" != "root" ]]; then
            su - "${main_user}" -c "${uv_bin} tool install anklume" 2>/dev/null || \
                warn "anklume pas encore sur PyPI."
        else
            "${uv_bin}" tool install anklume 2>/dev/null || \
                warn "anklume pas encore sur PyPI."
        fi
    fi

    # Alias ank dans bash
    local bashrc="${user_home}/.bashrc"
    if [[ -f "${bashrc}" ]] && ! grep -q "alias ank=" "${bashrc}" 2>/dev/null; then
        cat >> "${bashrc}" << 'BLOCK'

# AnKLuMe — PATH + alias
export PATH="${HOME}/.local/bin:${PATH}"
command -v anklume &> /dev/null && alias ank='anklume'
BLOCK
    fi

    # Fixer les droits
    if [[ "${main_user}" != "root" ]]; then
        local uid gid
        uid=$(id -u "${main_user}")
        gid=$(id -g "${main_user}")
        [[ -f "${bashrc}" ]] && chown "${uid}:${gid}" "${bashrc}"
    fi

    info "AnKLuMe configuré."
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo "=== AnKLuMe — Post-installation FAI.me ==="
    echo ""

    setup_nvidia
    setup_incus
    setup_anklume

    echo ""
    info "Post-installation terminée."
    echo ""
    echo "  anklume init mon-infra && cd mon-infra"
    echo "  anklume tui"
    echo "  anklume apply all"
    echo ""
}

main
