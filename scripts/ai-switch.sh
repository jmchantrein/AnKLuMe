#!/usr/bin/env bash
# Switch AI-tools network access between domains.
# Usage: scripts/ai-switch.sh --domain <name> [--no-flush] [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
DOMAIN=""
FLUSH_VRAM=true
DRY_RUN=false
STATE_FILE="/opt/anklume/ai-access-current"
LOG_DIR="/var/log/anklume"
LOG_FILE="$LOG_DIR/ai-switch.log"

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }
warn() { echo "WARNING: $*" >&2; }

usage() {
    cat <<'EOF'
Usage: ai-switch.sh --domain <name> [--no-flush] [--dry-run]

Switch exclusive AI-tools network access to a different domain.
Only one domain can access ai-tools at a time.

Options:
  --domain <name>  Target domain (required)
  --no-flush       Skip VRAM flush (faster, less secure)
  --dry-run        Show what would happen without making changes
  -h, --help       Show this help

Example:
  ai-switch.sh --domain pro          # Switch AI access to pro domain
  ai-switch.sh --domain perso --no-flush  # Switch without VRAM flush
EOF
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
    case "$1" in
        --domain)
            [[ -n "${2:-}" ]] || die "--domain requires a value"
            DOMAIN="$2"
            shift 2
            ;;
        --no-flush)
            FLUSH_VRAM=false
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            die "Unknown argument: $1"
            ;;
    esac
done

[[ -n "$DOMAIN" ]] || die "Missing required --domain argument. See --help."

# --- Resolve infra source ---
if [[ -d "$PROJECT_DIR/infra" ]]; then
    INFRA_SRC="$PROJECT_DIR/infra"
elif [[ -f "$PROJECT_DIR/infra.yml" ]]; then
    INFRA_SRC="$PROJECT_DIR/infra.yml"
else
    die "Neither infra.yml nor infra/ found in $PROJECT_DIR"
fi

# --- Validate domain exists (quick YAML check) ---
domain_exists() {
    python3 -c "
import sys, yaml
from pathlib import Path
p = Path('$INFRA_SRC')
if p.is_file():
    data = yaml.safe_load(p.read_text())
elif p.is_dir():
    base = yaml.safe_load((p / 'base.yml').read_text()) or {}
    data = base
    dd = p / 'domains'
    if dd.is_dir():
        data.setdefault('domains', {})
        for f in sorted(dd.glob('*.yml')):
            data['domains'].update(yaml.safe_load(f.read_text()) or {})
domains = (data.get('domains') or {}).keys()
sys.exit(0 if '$1' in domains else 1)
"
}

domain_exists "$DOMAIN" || die "Domain '$DOMAIN' not found in $INFRA_SRC"
[[ "$DOMAIN" != "ai-tools" ]] || die "Cannot switch AI access to 'ai-tools' itself"

# --- Read current state ---
CURRENT=""
if [[ -f "$STATE_FILE" ]]; then
    CURRENT="$(cat "$STATE_FILE")"
fi

if [[ "$CURRENT" == "$DOMAIN" ]]; then
    info "AI access is already set to '$DOMAIN'. Nothing to do."
    exit 0
fi

# --- Dry-run summary ---
PREFIX=""
if [[ "$DRY_RUN" == "true" ]]; then
    PREFIX="[DRY-RUN] "
fi

info "${PREFIX}Switching AI-tools access: '${CURRENT:-<none>}' -> '$DOMAIN'"
if [[ "$FLUSH_VRAM" == "true" ]]; then
    info "${PREFIX}VRAM flush: enabled"
else
    info "${PREFIX}VRAM flush: skipped"
fi

if [[ "$DRY_RUN" == "true" ]]; then
    info "Dry-run complete. No changes made."
    exit 0
fi

# --- Pre-flight: verify Incus daemon is accessible ---
if ! incus project list --format csv >/dev/null 2>&1; then
    die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
fi

# --- Step 1: Stop GPU services in ai-tools ---
info "Stopping GPU services in ai-tools domain..."
# Find the AI project (default to ai-tools)
AI_PROJECT="ai-tools"

# Try to stop services gracefully; don't fail if they don't exist
for service in ollama speaches; do
    incus exec ai-ollama --project "$AI_PROJECT" -- \
        systemctl stop "$service" 2>/dev/null || true
done

# --- Step 2: Flush VRAM (unless --no-flush) ---
if [[ "$FLUSH_VRAM" == "true" ]]; then
    info "Flushing VRAM..."
    # Kill remaining GPU processes via nvidia-smi
    incus exec ai-ollama --project "$AI_PROJECT" -- \
        bash -c 'nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null | xargs -r kill -9' 2>/dev/null || true
    # Attempt GPU reset (may fail on some hardware, non-fatal)
    incus exec ai-ollama --project "$AI_PROJECT" -- \
        nvidia-smi --gpu-reset 2>/dev/null || warn "GPU reset not supported (non-fatal)"
    info "VRAM flush complete."
fi

# --- Step 3: Update nftables rules ---
info "Updating nftables rules (AI access: $DOMAIN -> ai-tools)..."
cd "$PROJECT_DIR"
ansible-playbook site.yml --tags nftables \
    -e "incus_nftables_ai_override={\"from_bridge\":\"net-${DOMAIN}\",\"to_bridge\":\"net-ai-tools\",\"ports\":\"all\",\"protocol\":\"tcp\"}"

# --- Step 4: Restart GPU services ---
info "Restarting GPU services in ai-tools domain..."
for service in ollama speaches; do
    incus exec ai-ollama --project "$AI_PROJECT" -- \
        systemctl start "$service" 2>/dev/null || true
done

# --- Step 5: Record new state ---
mkdir -p "$(dirname "$STATE_FILE")"
echo "$DOMAIN" > "$STATE_FILE"

# --- Step 6: Log the switch ---
mkdir -p "$LOG_DIR"
echo "$(date -Is) switched ai-tools access: '${CURRENT:-<none>}' -> '$DOMAIN' flush=$FLUSH_VRAM" >> "$LOG_FILE"

info "AI-tools access switched to '$DOMAIN' successfully."
