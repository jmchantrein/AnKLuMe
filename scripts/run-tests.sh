#!/usr/bin/env bash
# Sandboxed Molecule test runner using Incus-in-Incus (Phase 12).
# Creates a container with nested Incus, runs Molecule tests inside,
# and optionally destroys the container afterward.
# See docs/SPEC.md Phase 12 and docs/ARCHITECTURE.md.
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Configuration (overridable via environment) ───────────────────

RUNNER_NAME="${ANKLUME_RUNNER_NAME:-anklume}"
RUNNER_IMAGE="${ANKLUME_RUNNER_IMAGE:-images:debian/13}"
RUNNER_PROJECT="${ANKLUME_RUNNER_PROJECT:-default}"
REPO_URL="${ANKLUME_RUNNER_REPO_URL:-https://github.com/jmchantrein/anklume.git}"
REPO_BRANCH="${ANKLUME_RUNNER_REPO_BRANCH:-main}"
REPO_DIR="/root/anklume"
MAX_WAIT=120

# ── Pre-flight check ──────────────────────────────────────────────

check_incus_connectivity() {
    if ! incus project list --format csv >/dev/null 2>&1; then
        die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
    fi
}

# ── Helper functions ──────────────────────────────────────────────

ensure_nesting_profile() {
    if incus profile show nesting &>/dev/null; then
        return 0
    fi
    echo "Creating nesting profile..."
    incus profile create nesting
    incus profile set nesting security.nesting=true
    incus profile set nesting security.syscalls.intercept.mknod=true
    incus profile set nesting security.syscalls.intercept.setxattr=true
}

wait_for_network() {
    echo "Waiting for network connectivity..."
    local _
    for _ in $(seq 1 "$MAX_WAIT"); do
        if incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- \
            ping -c1 -W1 deb.debian.org &>/dev/null; then
            echo "Network ready."
            return 0
        fi
        sleep 1
    done
    die "Network timeout after ${MAX_WAIT}s"
}

provision_runner() {
    echo "=== Provisioning runner ==="
    incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- bash -c "
        export DEBIAN_FRONTEND=noninteractive

        # Install Incus and base packages
        apt-get update -qq
        apt-get install -y -qq incus incus-client \
            python3 python3-pip python3-venv git make

        # Initialize nested Incus if not already done
        if ! incus storage list --format json 2>/dev/null | python3 -c \
            'import json,sys; sys.exit(0 if json.load(sys.stdin) else 1)' 2>/dev/null; then
            cat <<'PRESEED' | incus admin init --preseed
networks:
- config:
    ipv4.address: 10.250.0.1/24
    ipv4.nat: \"true\"
    ipv6.address: none
  name: incusbr0
  type: bridge
storage_pools:
- config: {}
  name: default
  driver: dir
profiles:
- config: {}
  devices:
    eth0:
      name: eth0
      network: incusbr0
      type: nic
    root:
      path: /
      pool: default
      type: disk
  name: default
PRESEED
        fi

        # Ensure images remote exists
        incus remote add images https://images.linuxcontainers.org \
            --protocol simplestreams --public 2>/dev/null || true

        # Install test tools
        pip3 install molecule molecule-plugins ansible-lint yamllint \
            --break-system-packages -q
        ansible-galaxy collection install community.general -q

        # Configure git
        git config --global user.name 'anklume Runner'
        git config --global user.email 'runner@anklume.local'

        # Clone or update repo
        if [ -d ${REPO_DIR} ]; then
            cd ${REPO_DIR} && git fetch origin && git checkout ${REPO_BRANCH} \
                && git pull origin ${REPO_BRANCH} || true
        else
            git clone -q -b ${REPO_BRANCH} ${REPO_URL} ${REPO_DIR}
        fi

        echo '=== Runner provisioned ==='
    "
}

# ── Commands ──────────────────────────────────────────────────────

cmd_create() {
    echo "=== Creating runner container: ${RUNNER_NAME} ==="

    check_incus_connectivity
    ensure_nesting_profile

    # Launch or reuse container
    if incus info "$RUNNER_NAME" --project "$RUNNER_PROJECT" &>/dev/null; then
        echo "Container ${RUNNER_NAME} already exists, reusing."
        incus start "$RUNNER_NAME" --project "$RUNNER_PROJECT" 2>/dev/null || true
    else
        incus launch "$RUNNER_IMAGE" "$RUNNER_NAME" \
            --project "$RUNNER_PROJECT" \
            --profile default \
            --profile nesting
    fi

    wait_for_network
    provision_runner

    echo "=== Runner ${RUNNER_NAME} ready ==="
}

cmd_test() {
    local role="${1:-all}"

    check_incus_connectivity

    # Verify runner exists
    incus info "$RUNNER_NAME" --project "$RUNNER_PROJECT" &>/dev/null \
        || die "Runner ${RUNNER_NAME} not found. Run '$0 create' first."

    echo "=== Running Molecule tests in ${RUNNER_NAME} (role: ${role}) ==="

    if [ "$role" = "all" ]; then
        incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- bash -c "
            cd ${REPO_DIR}
            passed=0
            failed=0
            failed_roles=''

            for role_dir in roles/*/molecule; do
                role=\$(basename \$(dirname \"\$role_dir\"))
                echo ''
                echo \"===== Testing: \$role =====\"
                cd ${REPO_DIR}/roles/\$role
                if molecule test 2>&1; then
                    echo \"PASS: \$role\"
                    passed=\$((passed + 1))
                else
                    echo \"FAIL: \$role\"
                    failed=\$((failed + 1))
                    failed_roles=\"\$failed_roles \$role\"
                fi
            done

            echo ''
            echo '===== Results ====='
            echo \"Passed: \$passed\"
            echo \"Failed: \$failed\"
            [ -n \"\$failed_roles\" ] && echo \"Failed roles:\$failed_roles\"
            [ \$failed -eq 0 ] || exit 1
        "
    else
        [ -d "roles/${role}/molecule" ] \
            || die "Role '${role}' has no molecule directory"

        incus exec "$RUNNER_NAME" --project "$RUNNER_PROJECT" -- bash -c "
            cd ${REPO_DIR}/roles/${role}
            molecule test
        "
    fi
}

cmd_destroy() {
    echo "=== Destroying runner: ${RUNNER_NAME} ==="
    check_incus_connectivity
    incus delete "$RUNNER_NAME" --project "$RUNNER_PROJECT" --force 2>/dev/null \
        || echo "Container ${RUNNER_NAME} not found or already removed."
}

# ── Entry point ───────────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: run-tests.sh <command> [args]

Commands:
  create        Create and provision the runner container
  test [role]   Run Molecule tests (all roles or specific role)
  destroy       Destroy the runner container
  full [role]   Create, test, destroy (full cycle)
  help          Show this help

Environment:
  ANKLUME_RUNNER_NAME     Container name (default: anklume)
  ANKLUME_RUNNER_IMAGE    Base image (default: images:debian/13)
  ANKLUME_RUNNER_PROJECT  Incus project (default: default)
  ANKLUME_RUNNER_REPO_URL Git repository URL
  ANKLUME_RUNNER_REPO_BRANCH Git branch (default: main)

Examples:
  run-tests.sh create                  # Create and provision runner
  run-tests.sh test                    # Run all Molecule tests
  run-tests.sh test base_system        # Test one role
  run-tests.sh full                    # Full cycle: create, test, destroy
  run-tests.sh full base_system        # Full cycle for one role
  run-tests.sh destroy                 # Remove runner container
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 0; }

case "$1" in
    create)  cmd_create ;;
    test)    shift; cmd_test "${1:-all}" ;;
    destroy) cmd_destroy ;;
    full)    shift; cmd_create; cmd_test "${1:-all}"; cmd_destroy ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: $1. Run 'run-tests.sh help' for usage." ;;
esac
