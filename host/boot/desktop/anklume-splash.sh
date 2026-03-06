#!/bin/bash
# anklume-splash.sh — Display ASCII art header + random quote + anklume gui hint
# Called from bash_profile on login (terminal-first mode)
# Bilingual: auto-detects French from $LANG

QUOTES_DIR="/opt/anklume/host/boot/desktop"

# Detect language
case "${LANG:-}" in
    fr*) SPLASH_LANG="fr" ;;
    *)   SPLASH_LANG="en" ;;
esac

# Select quotes file (localized, fallback to English)
if [ "$SPLASH_LANG" = "fr" ] && [ -f "$QUOTES_DIR/quotes.fr.txt" ]; then
    QUOTES_FILE="$QUOTES_DIR/quotes.fr.txt"
else
    QUOTES_FILE="$QUOTES_DIR/quotes.txt"
fi

# ASCII art header
printf '\033[1;35m'
cat << 'BANNER'

     _    _  _ _  ___    _   _ __  __ ___
    / \  | \| | |/ / |  | | | |  \/  | __|
   / _ \ | .` | ' <| |__| |_| | |\/| | _|
  /_/ \_\|_|\_|_|\_\____|\___/|_|  |_|___|

BANNER
printf '\033[0m'

# Random quote
if [ -f "$QUOTES_FILE" ]; then
    total=$(wc -l < "$QUOTES_FILE")
    if [ "$total" -gt 0 ]; then
        # POSIX-compatible random line selection
        if [ -r /dev/urandom ]; then
            line=$(( $(od -An -tu4 -N4 /dev/urandom | tr -d ' ') % total + 1 ))
        else
            line=$(( $(date +%s) % total + 1 ))
        fi
        quote=$(sed -n "${line}p" "$QUOTES_FILE")
        printf '\033[3;37m  %s\033[0m\n' "$quote"
    fi
fi

# Bilingual hints
if [ "$SPLASH_LANG" = "fr" ]; then
    printf '\n\033[0;36m  Tapez \033[1manklume --help\033[0;36m pour la liste des commandes\033[0m\n'
    printf '\033[0;36m  Tapez \033[1manklume learn start\033[0;36m pour les labs en web\033[0m\n'
    printf '\033[0;36m  Tapez \033[1manklume console\033[0;36m pour la console par domaine\033[0m\n\n'
else
    printf '\n\033[0;36m  Type \033[1manklume --help\033[0;36m for all commands\033[0m\n'
    printf '\033[0;36m  Type \033[1manklume learn start\033[0;36m for web-rendered labs\033[0m\n'
    printf '\033[0;36m  Type \033[1manklume console\033[0;36m for the domain console\033[0m\n\n'
fi
