#!/usr/bin/env bash
# stt-push-to-talk.sh — Push-to-talk STT via Speaches API
#
# Meta+S (toggle) : 1er appui = enregistre, 2e appui = transcrit + colle
#
# Dépendances : pw-record, curl, jq, ydotool (+ ydotoold), wl-copy, wl-paste,
#               notify-send, gdbus
#
# Configuration (variables d'environnement ou éditer ci-dessous) :
#   STT_API_URL    — URL de l'API Speaches (défaut: http://localhost:8000)
#   STT_MODEL      — Modèle Whisper (défaut: mobiuslabsgmbh/faster-whisper-large-v3-turbo)
#   STT_LANGUAGE   — Langue (défaut: fr)

set -uo pipefail

# ── Configuration ───────────────────────────────────────────
STT_API_URL="${STT_API_URL:-http://localhost:8000}"
STT_MODEL="${STT_MODEL:-mobiuslabsgmbh/faster-whisper-large-v3-turbo}"
STT_LANGUAGE="${STT_LANGUAGE:-fr}"

# ── Chemins internes ────────────────────────────────────────
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
PID_FILE="$RUNTIME_DIR/stt-push-to-talk.pid"
AUDIO_FILE="$RUNTIME_DIR/stt-recording.wav"
NOTIF_ID_FILE="$RUNTIME_DIR/stt-notif-id"
WCLASS_FILE="$RUNTIME_DIR/stt-window-class"
KWIN_SCRIPT="$RUNTIME_DIR/stt-kwin-detect.js"
CLIP_BACKUP="$RUNTIME_DIR/stt-clip-backup"

# Terminaux connus (resourceClass KWin) — Ctrl+Shift+V pour coller
TERMINALS="org.kde.konsole|konsole|kitty|Alacritty|alacritty|foot|wezterm|org.wezfurlong.wezterm|xterm|urxvt|gnome-terminal-server|xfce4-terminal|tilix|terminator|st|sakura|lxterminal|mate-terminal"

# ── Notifications ───────────────────────────────────────────
notify() {
    local title="$1"
    local body="${2:-}"
    local timeout="${3:-5000}"
    local replace_id
    replace_id=$(cat "$NOTIF_ID_FILE" 2>/dev/null || echo "0")
    local nid
    if [[ "$replace_id" != "0" ]] && [[ -n "$replace_id" ]]; then
        nid=$(notify-send -a "STT" -i audio-input-microphone \
            -t "$timeout" -p -r "$replace_id" \
            "$title" "$body" 2>/dev/null) || true
    else
        nid=$(notify-send -a "STT" -i audio-input-microphone \
            -t "$timeout" -p \
            "$title" "$body" 2>/dev/null) || true
    fi
    if [[ -n "$nid" ]]; then
        echo "$nid" > "$NOTIF_ID_FILE"
    fi
}

notify_close() {
    local nid
    nid=$(cat "$NOTIF_ID_FILE" 2>/dev/null)
    if [[ -n "$nid" ]] && [[ "$nid" != "0" ]]; then
        gdbus call --session --dest org.freedesktop.Notifications \
            --object-path /org/freedesktop/Notifications \
            --method org.freedesktop.Notifications.CloseNotification \
            "$nid" &>/dev/null || true
        echo "0" > "$NOTIF_ID_FILE"
    fi
}

# ── Détection fenêtre active (terminal vs GUI) ────────────────
detect_active_window_class() {
    if [[ ! -f "$KWIN_SCRIPT" ]]; then
        echo 'console.log("STT_WCLASS:" + (workspace.activeWindow ? workspace.activeWindow.resourceClass : "unknown"));' \
            > "$KWIN_SCRIPT"
    fi

    gdbus call --session --dest org.kde.KWin --object-path /Scripting \
        --method org.kde.kwin.Scripting.unloadScript "stt-detect" &>/dev/null || true

    gdbus call --session --dest org.kde.KWin --object-path /Scripting \
        --method org.kde.kwin.Scripting.loadScript "$KWIN_SCRIPT" "stt-detect" &>/dev/null || return 1
    gdbus call --session --dest org.kde.KWin --object-path /Scripting \
        --method org.kde.kwin.Scripting.start &>/dev/null || return 1

    sleep 0.15

    local wclass
    wclass=$(journalctl --user --since "3 seconds ago" --no-pager -o cat 2>/dev/null \
        | grep "STT_WCLASS:" | tail -1 | sed 's/.*STT_WCLASS://')

    gdbus call --session --dest org.kde.KWin --object-path /Scripting \
        --method org.kde.kwin.Scripting.unloadScript "stt-detect" &>/dev/null || true

    echo "$wclass"
}

# ── Collage au curseur (via ydotool) ─────────────────────────────
paste_at_cursor() {
    local wclass="${1:-}"

    if [[ -n "$wclass" ]] && echo "$wclass" | grep -qEi "^($TERMINALS)$"; then
        ydotool key 29:1 42:1 47:1 47:0 42:0 29:0 2>/dev/null || true
    else
        ydotool key 29:1 47:1 47:0 29:0 2>/dev/null || true
    fi
}

# ── Nettoyage des processus orphelins ───────────────────────
cleanup_stale() {
    if [[ -f "$PID_FILE" ]]; then
        local old_pid
        old_pid=$(cat "$PID_FILE" 2>/dev/null)
        if [[ -n "$old_pid" ]] && ! kill -0 "$old_pid" 2>/dev/null; then
            rm -f "$PID_FILE" "$MODE_FILE"
        fi
    fi
}

# ── Arrêter pw-record proprement ────────────────────────────
stop_recording() {
    local pid="$1"
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
        kill -INT "$pid" 2>/dev/null
        local i
        for i in $(seq 1 30); do
            kill -0 "$pid" 2>/dev/null || return 0
            sleep 0.1
        done
        kill -TERM "$pid" 2>/dev/null
        sleep 0.2
        kill -9 "$pid" 2>/dev/null || true
    fi
}

# ── Transcription et collage ─────────────────────────────────
transcribe_and_output() {
    local window_class="$1"

    if [[ ! -f "$AUDIO_FILE" ]] || [[ $(stat -c%s "$AUDIO_FILE" 2>/dev/null || echo 0) -lt 1000 ]]; then
        notify "STT" "Enregistrement trop court" 3000
        rm -f "$AUDIO_FILE"
        return 1
    fi

    notify "STT" "Transcription en cours..." 30000

    local response
    response=$(curl -s --max-time 120 \
        -X POST "$STT_API_URL/v1/audio/transcriptions" \
        -F "file=@$AUDIO_FILE" \
        -F "model=$STT_MODEL" \
        -F "language=$STT_LANGUAGE" \
        -F "response_format=json" \
        2>&1)

    rm -f "$AUDIO_FILE"

    local text
    text=$(echo "$response" | jq -r '.text // empty' 2>/dev/null)

    if [[ -z "$text" ]]; then
        notify "STT" "Pas de texte reconnu" 3000
        return 1
    fi

    echo -n "$text" | wl-copy 2>/dev/null
    sleep 0.2
    paste_at_cursor "$window_class"

    notify "STT" "$text" 5000
    echo "0" > "$NOTIF_ID_FILE"
}

# ── Sauvegarde / restauration du presse-papier ───────────────
save_clipboard() {
    wl-paste --list-types 2>/dev/null | head -1 > "$CLIP_BACKUP.mime" || true
    wl-paste --no-newline 2>/dev/null > "$CLIP_BACKUP" || true
}

restore_clipboard() {
    if [[ -f "$CLIP_BACKUP" ]]; then
        local mime
        mime=$(cat "$CLIP_BACKUP.mime" 2>/dev/null)
        mime="${mime:-text/plain}"
        wl-copy --type "$mime" < "$CLIP_BACKUP" 2>/dev/null || true
        rm -f "$CLIP_BACKUP" "$CLIP_BACKUP.mime"
    fi
}

# ══════════════════════════════════════════════════════════════
# ── Point d'entrée ───────────────────────────────────────────
# ══════════════════════════════════════════════════════════════

cleanup_stale

# ── Mode toggle : Meta+S → enregistre, Meta+S → transcrit + colle ──

if [[ -f "$PID_FILE" ]]; then
    # 2e appui : arrêter et transcrire
    PID=$(cat "$PID_FILE" 2>/dev/null)
    rm -f "$PID_FILE"

    WINDOW_CLASS=$(cat "$WCLASS_FILE" 2>/dev/null)
    rm -f "$WCLASS_FILE"

    notify_close
    stop_recording "$PID"

    transcribe_and_output "$WINDOW_CLASS"
else
    # 1er appui : démarrer l'enregistrement
    pkill -f "pw-record.*stt-recording" 2>/dev/null || true
    rm -f "$AUDIO_FILE"

    if ! curl -s --connect-timeout 2 "$STT_API_URL/health" | grep -q "OK" 2>/dev/null; then
        notify "STT" "API Speaches injoignable" 5000
        exit 1
    fi

    # Détecter la fenêtre active (coût zéro au 2e appui)
    detect_active_window_class > "$WCLASS_FILE" 2>/dev/null &

    pw-record --rate 16000 --channels 1 --format s16 "$AUDIO_FILE" &
    RECORD_PID=$!

    sleep 0.2
    if ! kill -0 "$RECORD_PID" 2>/dev/null; then
        notify "STT" "Échec capture audio" 3000
        exit 1
    fi

    echo "$RECORD_PID" > "$PID_FILE"

    notify "STT — Micro ouvert" "Meta+S pour transcrire" 0
fi
