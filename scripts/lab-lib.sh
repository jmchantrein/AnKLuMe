#!/usr/bin/env bash
# lab-lib.sh — Shared helpers for the lab runner
# Sourced by lab-runner.sh. Not executed directly.

# ── ANSI Colors (used by lab-runner.sh which sources this file) ──
# shellcheck disable=SC2034
RED='\033[0;31m'
# shellcheck disable=SC2034
GREEN='\033[0;32m'
# shellcheck disable=SC2034
YELLOW='\033[1;33m'
# shellcheck disable=SC2034
CYAN='\033[0;36m'
# shellcheck disable=SC2034
BOLD='\033[1m'
# shellcheck disable=SC2034
DIM='\033[2m'
# shellcheck disable=SC2034
RESET='\033[0m'

die() { echo -e "${RED}ERROR:${RESET} $*" >&2; exit 1; }
info() { echo -e "${CYAN}INFO:${RESET} $*"; }

# ── Lab discovery ────────────────────────────────────────

find_lab_dir() {
    local num="$1"
    local pattern="${num}-*"
    local match
    match=$(find "$LABS_DIR" -maxdepth 1 -type d -name "$pattern" | head -1)
    if [[ -z "$match" ]]; then
        die "Lab $num not found. Run 'lab-list' to see available labs."
    fi
    echo "$match"
}

# ── YAML field readers (via inline Python) ───────────────

read_lab_field() {
    local lab_yml="$1"
    local field="$2"
    python3 - "$lab_yml" "$field" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
print(data.get(sys.argv[2], ""))
PYEOF
}

get_step_count() {
    local lab_yml="$1"
    python3 - "$lab_yml" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
print(len(data.get("steps", [])))
PYEOF
}

get_step_field() {
    local lab_yml="$1"
    local step_idx="$2"
    local field="$3"
    python3 - "$lab_yml" "$step_idx" "$field" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
steps = data.get("steps", [])
idx = int(sys.argv[2])
if idx < len(steps):
    print(steps[idx].get(sys.argv[3], ""))
PYEOF
}

# ── Progress tracking ────────────────────────────────────

ensure_state_dir() {
    local lab_id="$1"
    mkdir -p "$STATE_DIR/$lab_id"
}

get_current_step() {
    local lab_id="$1"
    local progress="$STATE_DIR/$lab_id/progress.yml"
    if [[ -f "$progress" ]]; then
        python3 - "$progress" <<'PYEOF'
import sys, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f) or {}
print(data.get("current_step", 0))
PYEOF
    else
        echo "0"
    fi
}

save_progress() {
    local lab_id="$1"
    local step="$2"
    local assisted="${3:-false}"
    ensure_state_dir "$lab_id"
    local progress="$STATE_DIR/$lab_id/progress.yml"
    python3 - "$progress" "$step" "$assisted" <<'PYEOF'
import sys, yaml
from datetime import datetime, timezone
path, step, assisted = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
except FileNotFoundError:
    data = {}
data["current_step"] = step
if "started_at" not in data:
    data["started_at"] = datetime.now(timezone.utc).isoformat()
if assisted == "true":
    data["assisted"] = True
completed = data.get("completed_steps", [])
step_id = f"{step + 1:02d}"
if step_id not in completed:
    completed.append(step_id)
data["completed_steps"] = completed
with open(path, "w") as f:
    yaml.dump(data, f, default_flow_style=False)
PYEOF
}
