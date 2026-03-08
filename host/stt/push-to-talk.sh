#!/usr/bin/env bash
# push-to-talk.sh — Transcription vocale toggle Meta+S
# Enregistre via PipeWire, transcrit via Speaches, colle dans la fenêtre active.
set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────
STT_API_URL="${STT_API_URL:-http://10.100.3.1:8000}"
STT_LANGUAGE="${STT_LANGUAGE:-fr}"
STT_MODEL="${STT_MODEL:-base}"
AUDIO_FILE="/tmp/anklume-stt-$$.wav"
PID_FILE="/tmp/anklume-stt-recording.pid"

# ── Nettoyage ────────────────────────────────────────────────────────
cleanup() {
    rm -f "$AUDIO_FILE"
}
trap cleanup EXIT

# ── Fonctions utilitaires ────────────────────────────────────────────

is_recording() {
    [ -f "$PID_FILE" ] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

start_recording() {
    notify-send "STT" "Enregistrement…" -t 2000
    pw-record --target=0 "$AUDIO_FILE" &
    echo $! > "$PID_FILE"
}

stop_recording() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid="$(cat "$PID_FILE")"
        kill "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
}

detect_terminal() {
    local wclass
    wclass="$(kdotool getactivewindow getwindowclassname 2>/dev/null || echo "")"
    case "$wclass" in
        konsole|Alacritty|kitty|foot|wezterm|org.wezfurlong.wezterm)
            return 0 ;;
        *)
            return 1 ;;
    esac
}

paste_text() {
    if detect_terminal; then
        # Paste terminal : Ctrl+Shift+V
        wtype -M ctrl -M shift -k v
    else
        # Paste standard : Ctrl+V
        wtype -M ctrl -k v
    fi
}

transcribe() {
    local response text
    response="$(curl -s -X POST \
        "${STT_API_URL}/v1/audio/transcriptions" \
        -F "file=@${AUDIO_FILE}" \
        -F "model=${STT_MODEL}" \
        -F "language=${STT_LANGUAGE}" \
        -F "response_format=json")"

    text="$(echo "$response" | jq -r '.text // empty')"

    if [ -z "$text" ]; then
        notify-send "STT" "Aucun texte reconnu" -t 3000
        return 1
    fi

    echo "$text"
}

# ── Mode toggle ──────────────────────────────────────────────────────

if is_recording; then
    # 2e appui : arrêter et transcrire
    stop_recording

    text="$(transcribe)" || exit 1

    # Copier dans le presse-papiers et coller
    echo -n "$text" | wl-copy
    paste_text

    notify-send "STT" "$text" -t 5000
else
    # 1er appui : démarrer l'enregistrement
    start_recording
fi
