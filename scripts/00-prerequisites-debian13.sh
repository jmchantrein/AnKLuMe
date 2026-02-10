#!/usr/bin/env bash
# 00-prerequisites-debian13.sh — Install AnKLuMe prerequisites on Debian 13 (Trixie)
#
# Run as root on the HOST machine (not inside a container).
# This is an EXAMPLE helper — adapt to your environment.
#
# Usage: sudo bash scripts/00-prerequisites-debian13.sh
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Checks ───────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || { error "This script must be run as root."; exit 1; }

# ── Enable backports + non-free ──────────────────────────────
BACKPORTS_LIST="/etc/apt/sources.list.d/backports.list"
if [[ ! -f "$BACKPORTS_LIST" ]]; then
    info "Enabling trixie-backports..."
    cat > "$BACKPORTS_LIST" <<'EOF'
deb http://deb.debian.org/debian trixie-backports main contrib non-free non-free-firmware
EOF
else
    info "Backports already configured."
fi

# Ensure contrib + non-free are enabled in main sources
info "Checking non-free components in sources..."
if ! grep -q 'non-free' /etc/apt/sources.list 2>/dev/null; then
    warn "Add 'contrib non-free non-free-firmware' to your /etc/apt/sources.list"
    warn "Example: deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware"
fi

info "Updating package lists..."
apt-get update -qq

# ── Incus ────────────────────────────────────────────────────
info "Installing Incus..."
apt-get install -y -t trixie-backports incus incus-client

# Add current user to incus-admin group (if not root-only usage)
if [[ -n "${SUDO_USER:-}" ]]; then
    info "Adding ${SUDO_USER} to incus-admin group..."
    usermod -aG incus-admin "$SUDO_USER"
    warn "Log out and back in for group change to take effect."
fi

# ── Ansible + tools ──────────────────────────────────────────
info "Installing Ansible and validation tools..."
apt-get install -y \
    ansible \
    ansible-lint \
    yamllint \
    shellcheck \
    python3-pip \
    python3-yaml \
    python3-pytest \
    git \
    jq

# Python tools not available as Debian packages
info "Installing Python tools (ruff, molecule)..."
pip install --break-system-packages ruff molecule 2>/dev/null \
    || pip install ruff molecule

# Ansible collection
info "Installing Ansible collections..."
ansible-galaxy collection install community.general

# ── NVIDIA GPU (optional) ───────────────────────────────────
cat <<'GPU_INFO'

════════════════════════════════════════════════════════════════
  NVIDIA GPU — Important notes
════════════════════════════════════════════════════════════════

  Debian 13 packages nvidia-driver 550.x (trixie-backports).
  This version does NOT support Blackwell GPUs (RTX 5090/5080/5070).

  RTX 5090 laptop (Blackwell) requires:
    - Driver >= 570.x (recommended: 575+ or 580+)
    - OPEN kernel modules (closed modules will NOT work)
    - Manual install from NVIDIA .run installer

  Steps for RTX 5090:
    1. Download driver from https://www.nvidia.com/Download/index.aspx
    2. Install kernel headers: apt install linux-headers-$(uname -r)
    3. Blacklist nouveau:      echo "blacklist nouveau" > /etc/modprobe.d/blacklist-nouveau.conf
    4. Update initramfs:       update-initramfs -u
    5. Reboot, then run:       bash NVIDIA-Linux-x86_64-5xx.xx.xx.run --open-kernel
                               (the --open-kernel flag is MANDATORY for Blackwell)

  For older GPUs (Ada, Ampere, Turing, Pascal):
    apt install -t trixie-backports nvidia-driver nvidia-kernel-dkms

════════════════════════════════════════════════════════════════

GPU_INFO

# ── Summary ──────────────────────────────────────────────────
info "Prerequisites installed. Next step:"
info "  sudo bash scripts/01-bootstrap-incus.sh"
