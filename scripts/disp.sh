#!/usr/bin/env bash
# Launch disposable (ephemeral) instances using Incus --ephemeral flag.
# Instance is auto-destroyed when stopped.
# See docs/disposable.md and ROADMAP.md Phase 20a.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${ANKLUME_PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"

# Defaults
IMAGE=""
DOMAIN=""
CMD=""
CONSOLE=false
NO_ATTACH=false
VM=false
FORCE=false

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

# ── Read default image from infra.yml if available ─────────
get_default_image() {
    local infra_src
    if [[ -f "$PROJECT_DIR/infra.yml" ]]; then
        infra_src="$PROJECT_DIR/infra.yml"
    elif [[ -d "$PROJECT_DIR/infra" && -f "$PROJECT_DIR/infra/base.yml" ]]; then
        infra_src="$PROJECT_DIR/infra/base.yml"
    else
        echo "images:debian/13"
        return
    fi
    python3 - "$infra_src" <<'PYEOF' 2>/dev/null || echo "images:debian/13"
import sys, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
img = (data.get("global") or {}).get("default_os_image", "")
print(img if img else "images:debian/13")
PYEOF
}

# ── Generate unique instance name ──────────────────────────
generate_name() {
    echo "disp-$(date +%Y%m%d-%H%M%S)"
}

# ── Pre-flight: verify Incus daemon is accessible ─────────
check_incus() {
    if ! incus project list --format csv >/dev/null 2>&1; then
        die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
    fi
}

# ── Find disposable domain from infra.yml ─────────────────
find_disposable_domain() {
    local infra_src
    if [[ -f "$PROJECT_DIR/infra.yml" ]]; then
        infra_src="$PROJECT_DIR/infra.yml"
    elif [[ -d "$PROJECT_DIR/infra" && -f "$PROJECT_DIR/infra/base.yml" ]]; then
        infra_src="$PROJECT_DIR/infra"
    else
        return 1
    fi
    python3 - "$infra_src" <<'PYEOF' 2>/dev/null
import sys, yaml
from pathlib import Path
p = Path(sys.argv[1])
if p.is_dir():
    data = yaml.safe_load((p / "base.yml").read_text()) or {}
    dd = p / "domains"
    if dd.is_dir():
        data.setdefault("domains", {})
        for f in sorted(dd.glob("*.yml")):
            data["domains"].update(yaml.safe_load(f.read_text()) or {})
else:
    data = yaml.safe_load(p.read_text()) or {}
for dname, dcfg in (data.get("domains") or {}).items():
    if dcfg.get("trust_level") == "disposable":
        print(dname)
        sys.exit(0)
sys.exit(1)
PYEOF
}

# ── Resolve domain to Incus project ───────────────────────
resolve_project() {
    local domain="$1"
    if [[ -z "$domain" ]]; then
        # Try to find a disposable domain in infra.yml
        local disp_domain
        if disp_domain=$(find_disposable_domain); then
            info "Using disposable domain: ${disp_domain}" >&2
            echo "$disp_domain"
            return
        fi
        # No disposable domain found — refuse default project unless --force
        if [[ "$FORCE" != "true" ]]; then
            die "No --domain specified and no disposable domain found in infra.yml.
  Either create a domain with trust_level: disposable in infra.yml,
  or use --domain <name> to specify a project,
  or use --force to launch in the default project."
        fi
        echo "default"
        return
    fi
    # Check if the project exists
    if incus project list --format csv 2>/dev/null | cut -d, -f1 | grep -qx "$domain"; then
        echo "$domain"
    else
        die "Incus project '${domain}' not found. Available projects: $(incus project list --format csv 2>/dev/null | cut -d, -f1 | tr '\n' ' ')"
    fi
}

# ── Launch ephemeral instance ─────────────────────────────
launch() {
    local image="$1"
    local name="$2"
    local project="$3"
    local vm_flag=""

    if [[ "$VM" == "true" ]]; then
        vm_flag="--vm"
    fi

    info "Launching ephemeral instance '${name}' (image: ${image}, project: ${project})..."
    # shellcheck disable=SC2086
    incus launch "$image" "$name" --ephemeral --project "$project" $vm_flag
    info "Instance '${name}' is running (ephemeral — auto-destroyed on stop)."
}

# ── Main logic ─────────────────────────────────────────────
run() {
    check_incus

    local image="${IMAGE:-$(get_default_image)}"
    local name
    name="$(generate_name)"
    local project
    project="$(resolve_project "$DOMAIN")"

    launch "$image" "$name" "$project"

    if [[ -n "$CMD" ]]; then
        info "Running command: ${CMD}"
        # Run the command, then stop (auto-destroys)
        incus exec "$name" --project "$project" -- sh -c "$CMD" || true
        info "Command finished. Stopping instance (will be auto-destroyed)..."
        incus stop "$name" --project "$project" 2>/dev/null || true
    elif [[ "$CONSOLE" == "true" ]]; then
        info "Attaching console (Ctrl+a q to detach)..."
        incus console "$name" --project "$project"
    elif [[ "$NO_ATTACH" == "false" ]]; then
        info "Attaching shell..."
        incus exec "$name" --project "$project" -- bash || \
            incus exec "$name" --project "$project" -- sh || true
        info "Shell exited. Stopping instance (will be auto-destroyed)..."
        incus stop "$name" --project "$project" 2>/dev/null || true
    else
        info "Instance is running. Connect with: incus exec ${name} --project ${project} -- bash"
        info "Stop to destroy: incus stop ${name} --project ${project}"
    fi
}

# ── Usage ──────────────────────────────────────────────────
usage() {
    cat <<'EOF'
Usage: disp.sh [OPTIONS]

Launch a disposable (ephemeral) Incus instance. The instance is
auto-destroyed when stopped.

Options:
  --image IMAGE      OS image (default: from infra.yml or images:debian/13)
  --domain DOMAIN    Incus project/domain (default: default)
  --cmd CMD          Run CMD then stop (auto-destroys)
  --console          Attach console instead of shell
  --no-attach        Launch without attaching (background)
  --vm               Launch as VM instead of container
  --force            Allow launching in the default project
  -h, --help         Show this help

Instance name is auto-generated: disp-YYYYMMDD-HHMMSS

Examples:
  disp.sh                                    # Launch + attach shell
  disp.sh --image images:alpine/3.20         # Different image
  disp.sh --domain sandbox                   # In specific project
  disp.sh --cmd "apt update && apt upgrade"  # Run command then destroy
  disp.sh --console                          # Attach console
  disp.sh --no-attach                        # Background instance
  disp.sh --vm                               # Launch a VM
EOF
}

# ── Parse arguments ────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --image)
            [[ -n "${2:-}" ]] || die "--image requires a value"
            IMAGE="$2"; shift 2 ;;
        --domain)
            [[ -n "${2:-}" ]] || die "--domain requires a value"
            DOMAIN="$2"; shift 2 ;;
        --cmd)
            [[ -n "${2:-}" ]] || die "--cmd requires a value"
            CMD="$2"; shift 2 ;;
        --console)
            CONSOLE=true; shift ;;
        --no-attach)
            NO_ATTACH=true; shift ;;
        --vm)
            VM=true; shift ;;
        --force)
            FORCE=true; shift ;;
        -h|--help)
            usage; exit 0 ;;
        *)
            die "Unknown option: $1. Run 'disp.sh --help' for usage." ;;
    esac
done

run
