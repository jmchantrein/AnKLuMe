#!/usr/bin/env bash
# learn-setup.sh — Create/destroy the anklume-learn container and demo infra.
#
# Usage:
#   bash scripts/learn-setup.sh           # Create container + demo instances
#   bash scripts/learn-setup.sh teardown  # Destroy everything
#
# The container runs in the Incus 'learn' project with a TLS certificate
# restricted to that project only. It cannot see or modify production
# projects (pro, perso, anklume, etc.).
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEARN_PROJECT="learn"
LEARN_CONTAINER="anklume-learn"
LEARN_PORT=8890
IMAGE="images:debian/13"

# ── Helpers ─────────────────────────────────────────────────

log()  { printf '\033[1;34m==> %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m  ✓ %s\033[0m\n' "$*"; }
err()  { printf '\033[1;31m  ✗ %s\033[0m\n' "$*" >&2; }

check_incus() {
    if ! command -v incus >/dev/null 2>&1; then
        err "incus is required but not found"
        exit 1
    fi
}

project_exists() {
    incus project list --format csv -c n 2>/dev/null | grep -qx "$1"
}

container_exists() {
    incus list --project "$LEARN_PROJECT" --format csv -c n 2>/dev/null \
        | grep -qx "$1"
}

container_running() {
    incus list --project "$LEARN_PROJECT" --format csv -c ns 2>/dev/null \
        | grep -q "^${1},RUNNING"
}

# ── Teardown ────────────────────────────────────────────────

do_teardown() {
    log "Tearing down learn infrastructure..."

    if project_exists "$LEARN_PROJECT"; then
        # Stop and delete all instances in the project
        local instances
        instances=$(incus list --project "$LEARN_PROJECT" --format csv -c n 2>/dev/null || true)
        for inst in $instances; do
            log "Deleting $inst..."
            incus stop "$inst" --project "$LEARN_PROJECT" --force 2>/dev/null || true
            incus delete "$inst" --project "$LEARN_PROJECT" --force 2>/dev/null || true
        done

        # Delete project (must be empty)
        incus project delete "$LEARN_PROJECT" 2>/dev/null || true
        ok "Project $LEARN_PROJECT removed"
    else
        ok "Project $LEARN_PROJECT does not exist"
    fi
}

# ── Setup ───────────────────────────────────────────────────

do_setup() {
    check_incus

    # 1. Create project
    log "Creating project $LEARN_PROJECT..."
    if project_exists "$LEARN_PROJECT"; then
        ok "Project $LEARN_PROJECT already exists"
    else
        incus project create "$LEARN_PROJECT" \
            -c features.images=false \
            -c features.profiles=true \
            -c features.networks=false \
            -c features.storage.volumes=true
        ok "Project $LEARN_PROJECT created"
    fi

    # 2. Copy default profile to learn project
    if ! incus profile show default --project "$LEARN_PROJECT" >/dev/null 2>&1; then
        incus profile copy default default --target-project "$LEARN_PROJECT" 2>/dev/null || true
    fi

    # 3. Enable TLS on daemon (if not already)
    log "Ensuring TLS is enabled on Incus daemon..."
    local current_addr
    current_addr=$(incus config get core.https_address 2>/dev/null || true)
    if [ -z "$current_addr" ]; then
        incus config set core.https_address "[::]:8443"
        ok "TLS enabled on [::]:8443"
    else
        ok "TLS already on $current_addr"
    fi

    # 4. Create container
    log "Creating container $LEARN_CONTAINER..."
    if container_exists "$LEARN_CONTAINER"; then
        ok "Container $LEARN_CONTAINER already exists"
        if ! container_running "$LEARN_CONTAINER"; then
            incus start "$LEARN_CONTAINER" --project "$LEARN_PROJECT"
            ok "Container started"
        fi
    else
        incus launch "$IMAGE" "$LEARN_CONTAINER" --project "$LEARN_PROJECT"
        ok "Container $LEARN_CONTAINER created"
    fi

    # 5. Add devices (idempotent — ignore errors if already exist)
    log "Configuring devices..."
    incus config device add "$LEARN_CONTAINER" project disk \
        source="$PROJECT_ROOT" path=/opt/anklume readonly=true \
        --project "$LEARN_PROJECT" 2>/dev/null || true
    ok "Project git mounted read-only at /opt/anklume"

    incus config device add "$LEARN_CONTAINER" web proxy \
        "listen=tcp:0.0.0.0:${LEARN_PORT}" "connect=tcp:127.0.0.1:${LEARN_PORT}" \
        --project "$LEARN_PROJECT" 2>/dev/null || true
    ok "Port $LEARN_PORT proxied to host"

    # 6. Install dependencies inside container
    log "Installing dependencies..."
    incus exec "$LEARN_CONTAINER" --project "$LEARN_PROJECT" -- bash -c '
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq python3-pip python3-venv >/dev/null 2>&1
        pip3 install --break-system-packages -q fastapi uvicorn 2>/dev/null
    '
    ok "Python + FastAPI installed"

    # 7. Create demo instances for guide chapters
    log "Creating demo instances..."
    for demo in learn-web learn-db; do
        if container_exists "$demo"; then
            ok "$demo already exists"
        else
            incus launch "$IMAGE" "$demo" --project "$LEARN_PROJECT"
            ok "$demo created"
        fi
    done

    # ── Summary ──────────────────────────────────────────────
    echo ""
    log "Setup complete!"
    echo "  Start the platform:  anklume learn start"
    echo "  Open in browser:     http://localhost:$LEARN_PORT"
    echo "  Tear down:           anklume learn teardown"
}

# ── Main ────────────────────────────────────────────────────

case "${1:-setup}" in
    teardown) do_teardown ;;
    setup|*)  do_setup ;;
esac
