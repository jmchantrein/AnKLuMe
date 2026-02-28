#!/bin/bash
# anklume-splash.sh — Display ASCII art header + random quote
# Called from bash_profile on every desktop boot
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

# Bilingual guide message
if [ "$SPLASH_LANG" = "fr" ]; then
    printf '\n\033[0;36m  Lancez \033[1manklume guide\033[0;36m pour commencer\033[0m\n\n'
else
    printf '\n\033[0;36m  Run \033[1manklume guide\033[0;36m to start the setup wizard\033[0m\n\n'
fi

# Offer brief window to stay in console mode
if [ "$SPLASH_LANG" = "fr" ]; then
    printf '\033[0;33m  Appuyez sur [c] dans 5s pour rester en console...\033[0m\n'
else
    printf '\033[0;33m  Press [c] within 5s to stay in console mode...\033[0m\n'
fi

if read -r -t 5 -n 1 key 2>/dev/null && [ "$key" = "c" ]; then
    touch "$HOME/.anklume-console"
    if [ "$SPLASH_LANG" = "fr" ]; then
        printf '\n\033[0;32m  Mode console actif. Tapez "rm ~/.anklume-console" pour restaurer le bureau.\033[0m\n'
    else
        printf '\n\033[0;32m  Console mode active. Type "rm ~/.anklume-console" to restore desktop.\033[0m\n'
    fi
    exit 0
fi
