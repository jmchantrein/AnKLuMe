#!/bin/bash
# anklume-splash.sh — Display ASCII art header + random quote + startde hint
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
    printf '\n\033[0;36m  Lancez \033[1manklume guide\033[0;36m pour commencer\033[0m\n'
    printf '\033[0;33m  Tapez \033[1mstartde\033[0;33m pour lancer le bureau graphique\033[0m\n\n'
else
    printf '\n\033[0;36m  Run \033[1manklume guide\033[0;36m to start the setup wizard\033[0m\n'
    printf '\033[0;33m  Type \033[1mstartde\033[0;33m to launch the desktop environment\033[0m\n\n'
fi
