#!/usr/bin/env bash
# anklume-cheatsheet.sh — Keybinding cheat sheet for sway/labwc
# Displayed on first boot; dismissed with any key press.

# Detect language
case "${LANG:-}" in
    fr*) L="fr" ;;
    *)   L="en" ;;
esac

# Colors
C='\033[1;36m'   # cyan bold
K='\033[1;33m'   # yellow bold
D='\033[0;37m'   # dim
R='\033[0m'      # reset
H='\033[1;35m'   # magenta bold

clear
printf '%b' "$H"
cat << 'BANNER'

     _    _  _ _  ___    _   _ __  __ ___
    / \  | \| | |/ / |  | | | |  \/  | __|
   / _ \ | .` | ' <| |__| |_| | |\/| | _|
  /_/ \_\|_|\_|_|\_\____|\___/|_|  |_|___|

BANNER
printf '%b' "$R"

if [ "$L" = "fr" ]; then
    printf '%b\n' "${C}  Raccourcis essentiels${R}"
else
    printf '%b\n' "${C}  Essential keybindings${R}"
fi
echo ""
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + Enter" "$R" "Open terminal"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + d" "$R" "Application launcher"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + Shift + q" "$R" "Close window"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + f" "$R" "Fullscreen"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + 1-9" "$R" "Switch workspace"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + Arrow keys" "$R" "Navigate windows"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + Shift + Arrows" "$R" "Move window"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + Shift + Space" "$R" "Toggle floating"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Super + Shift + e" "$R" "Exit sway"
printf '%b  %b%-25s%b %b\n' "$D" "$K" "Alt + Shift" "$R" "Toggle FR/US keyboard"
echo ""

if [ "$L" = "fr" ]; then
    printf '%b  Toutes les touches : %b/opt/anklume/host/boot/desktop/KEYBINDINGS.fr.txt%b\n\n' "$D" "$C" "$R"
    printf '%b  Appuyez sur une touche pour fermer...%b\n' "$D" "$R"
else
    printf '%b  All shortcuts: %b/opt/anklume/host/boot/desktop/KEYBINDINGS.txt%b\n\n' "$D" "$C" "$R"
    printf '%b  Press any key to dismiss...%b\n' "$D" "$R"
fi

# Wait for any keypress
read -r -n 1 -s _ 2>/dev/null || read -r _ 2>/dev/null
