#!/usr/bin/env bash
# Snapshots & Restore
# Save and restore instance state instantly.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../guide-lib.sh
source "$SCRIPT_DIR/../guide-lib.sh"

box_header 6 "$GUIDE_TOTAL_CHAPTERS" "Snapshots & Restore"

# ── Prerequisites ─────────────────────────────────────────────
check_prerequisite "incus"
check_incus_socket
check_deployed_domains

# ── Explain ───────────────────────────────────────────────────
section_title "How it works"
echo "  Snapshots save the complete state of an instance — filesystem,"
echo "  configuration, everything. Restore in seconds."
echo ""
echo "  Use cases:"
echo "    ${ARROW} Before risky changes: snapshot, try, restore if broken"
echo "    ${ARROW} Lab checkpoints: save progress, experiment freely"
echo "    ${ARROW} Auto-snapshots via cron (snapshots_schedule in infra.yml)"
echo ""
echo "  Snapshot commands:"
key_value "anklume snapshot create" "all instances"
key_value "anklume snapshot create NAME=pre-test" "named snapshot"
key_value "anklume snapshot restore NAME=pre-test" "restore"
key_value "anklume snapshot list" "list all"

# ── Demo ──────────────────────────────────────────────────────
section_title "Live demo"
echo "  Current instances and their snapshots:"
echo ""
run_demo "incus list --all-projects --format compact -c nsS"

if [[ "$GUIDE_AUTO" == "true" ]]; then
    check_info "Auto-mode: skipping snapshot creation"
else
    echo ""
    if guide_confirm "Create a demo snapshot (guide-demo)?"; then
        spinner_start "Creating snapshot..."
        (cd "$GUIDE_PROJECT_DIR" && make snapshot NAME=guide-demo 2>/dev/null) || true
        spinner_stop
        check_ok "Snapshot 'guide-demo' created"
        echo ""
        echo "  You can restore it anytime with:"
        check_info "anklume snapshot restore NAME=guide-demo"
    fi
fi

# ── Try it ────────────────────────────────────────────────────
section_title "Your turn"
echo "  Try the snapshot lifecycle:"
echo ""
check_info "1. anklume snapshot create NAME=test"
check_info "2. Make a change inside a container"
check_info "3. anklume snapshot restore NAME=test"
check_info "4. Verify the change is reverted"

# ── Recap ─────────────────────────────────────────────────────
chapter_recap "Snapshots provide instant rollback"
next_chapter
