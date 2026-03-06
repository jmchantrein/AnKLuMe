#!/bin/bash
# start-desktop.sh — Launch KDE Plasma Wayland
# Called automatically from bash_profile or via `anklume gui`

set -euo pipefail

# Keyboard layout for Wayland (auto-detect from vconsole.conf)
if [ -z "${XKB_DEFAULT_LAYOUT:-}" ]; then
    if grep -q '^KEYMAP=fr' /etc/vconsole.conf 2>/dev/null; then
        export XKB_DEFAULT_LAYOUT=fr
    fi
fi

# NVIDIA: configure Wayland for proprietary driver
if lsmod | grep -q '^nvidia '; then
    export GBM_BACKEND=nvidia-drm
    export __GLX_VENDOR_LIBRARY_NAME=nvidia
fi

export XDG_SESSION_TYPE=wayland
exec startplasma-wayland 2>/dev/null
