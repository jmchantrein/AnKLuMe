#!/bin/bash
# start-desktop.sh — Launch the desktop environment
# Called via `startde` function from bash_profile
# Reads $ANKLUME_DE to determine which DE to launch

set -euo pipefail

DE="${ANKLUME_DE:-}"
if [ -z "$DE" ]; then
    echo "No desktop environment configured (ANKLUME_DE not set)"
    echo "Boot with anklume.desktop=kde|sway|labwc on the kernel cmdline"
    exit 1
fi

# Keyboard layout for Wayland (auto-detect from vconsole.conf)
if [ -z "${XKB_DEFAULT_LAYOUT:-}" ]; then
    if grep -q '^KEYMAP=fr' /etc/vconsole.conf 2>/dev/null; then
        export XKB_DEFAULT_LAYOUT=fr
    fi
fi

# NVIDIA: use Vulkan renderer for proprietary driver compatibility
if lsmod | grep -q '^nvidia '; then
    export WLR_RENDERER=vulkan
fi

export XDG_SESSION_TYPE=wayland

case "$DE" in
    sway|1)
        exec sway 2>/dev/null
        ;;
    labwc)
        exec labwc 2>/dev/null
        ;;
    kde)
        # KDE Plasma manages its own renderer
        unset WLR_RENDERER
        exec startplasma-wayland 2>/dev/null
        ;;
    *)
        echo "Unknown desktop environment: $DE"
        echo "Supported: sway, labwc, kde"
        exit 1
        ;;
esac
