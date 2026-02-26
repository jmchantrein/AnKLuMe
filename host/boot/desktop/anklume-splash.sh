#!/bin/sh
# anklume-splash.sh — Display ASCII art header + random quote
# Called from bash_profile on every desktop boot

QUOTES_FILE="/opt/anklume/host/boot/desktop/quotes.txt"

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

printf '\n\033[0;36m  Run \033[1manklume guide\033[0;36m to start the setup wizard\033[0m\n\n'
