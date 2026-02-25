#!/usr/bin/env bash
# detect.sh — Detect if Sway (or compatible i3/Hyprland) is running
# Returns: 0 if active, 1 otherwise
# Stdout: version string (optional)

set -euo pipefail

# Check if Sway is running
if [ -n "${SWAYSOCK:-}" ] && command -v swaymsg &>/dev/null; then
    version=$(swaymsg -t get_version 2>/dev/null | grep -oP '"human_readable":\s*"\K[^"]+' || echo "unknown")
    echo "sway $version"
    exit 0
fi

# Check if i3 is running (compatible config format)
if [ -n "${I3SOCK:-}" ] && command -v i3-msg &>/dev/null; then
    version=$(i3-msg -t get_version 2>/dev/null | grep -oP '"human_readable":\s*"\K[^"]+' || echo "unknown")
    echo "i3 $version"
    exit 0
fi

# Not running
exit 1
