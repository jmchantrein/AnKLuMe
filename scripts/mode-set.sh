#!/usr/bin/env bash
# mode-set.sh — Set the anklume CLI mode (student/user/dev)
#
# Persists the mode to ~/.anklume/mode.
# Called by: make mode-student, make mode-user, make mode-dev
set -euo pipefail

VALID_MODES="student user dev"
MODE_DIR="${HOME}/.anklume"
MODE_FILE="${MODE_DIR}/mode"

usage() {
    echo "Usage: $0 <student|user|dev>"
    echo ""
    echo "Modes:"
    echo "  student  — Bilingual help (French descriptions), educational focus"
    echo "  user     — Standard help (default)"
    echo "  dev      — All targets visible in help"
    exit 1
}

# ── Argument validation ──────────────────────────────────
if [[ $# -ne 1 ]]; then
    usage
fi

mode="$1"

valid=false
for m in $VALID_MODES; do
    if [[ "$mode" == "$m" ]]; then
        valid=true
        break
    fi
done

if [[ "$valid" != "true" ]]; then
    echo "ERROR: Invalid mode '$mode'. Must be one of: $VALID_MODES" >&2
    exit 1
fi

# ── Persist mode ─────────────────────────────────────────
mkdir -p "$MODE_DIR"
echo "$mode" > "$MODE_FILE"

echo "anklume mode set to: $mode"
case "$mode" in
    student)
        echo "  Help will show French descriptions alongside targets."
        echo "  Run 'make help' to see the bilingual output."
        ;;
    user)
        echo "  Standard help mode (default)."
        ;;
    dev)
        echo "  All targets visible in help output."
        ;;
esac
