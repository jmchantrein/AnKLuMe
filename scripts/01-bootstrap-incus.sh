#!/usr/bin/env bash
# 01-bootstrap-incus.sh — Initialize Incus for AnKLuMe (headless)
#
# Configures Incus with a preseed matching the AnKLuMe architecture:
#   - No cluster
#   - dir storage backend (simple, works everywhere)
#   - Managed bridge (incusbr0) with IPv4, no IPv6
#   - Default profile: root disk + NIC
#   - No remote HTTPS access (local unix socket only)
#
# Run as root on the HOST machine, after 00-prerequisites-debian13.sh.
#
# Usage: sudo bash scripts/01-bootstrap-incus.sh
set -euo pipefail

# ── Colors ───────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Checks ───────────────────────────────────────────────────
[[ $EUID -eq 0 ]] || { error "This script must be run as root."; exit 1; }
command -v incus >/dev/null 2>&1 || { error "incus not found. Run 00-prerequisites-debian13.sh first."; exit 1; }

# Check if already initialized
if incus list >/dev/null 2>&1; then
    warn "Incus appears to be already initialized."
    read -rp "Re-initialize? This may conflict with existing config. [y/N] " answer
    [[ "$answer" =~ ^[Yy]$ ]] || { info "Aborted."; exit 0; }
fi

# ── Preseed ──────────────────────────────────────────────────
info "Initializing Incus with AnKLuMe preseed..."

incus admin init --preseed <<'PRESEED'
# AnKLuMe — Incus preseed configuration
# No cluster, no remote access, local socket only.

config:
  images.auto_update_interval: "6"

# Storage: dir backend (simple, no extra setup)
# For production, consider zfs or btrfs for faster snapshots.
storage_pools:
- name: default
  driver: dir

# Network: managed bridge
# Domain-specific bridges (net-admin, net-work, ...) will be
# created by Ansible roles, not here.
networks:
- name: incusbr0
  type: bridge
  config:
    ipv4.address: auto
    ipv6.address: none

# Default profile: root disk + NIC on the managed bridge.
# Domain-specific profiles (GPU, nesting, ...) will be
# created by Ansible roles.
profiles:
- name: default
  devices:
    root:
      path: /
      pool: default
      type: disk
    eth0:
      name: eth0
      nictype: bridged
      parent: incusbr0
      type: nic
PRESEED

# ── Verify ───────────────────────────────────────────────────
info "Verifying initialization..."

echo ""
echo "Storage pools:"
incus storage list

echo ""
echo "Networks:"
incus network list

echo ""
echo "Default profile:"
incus profile show default

# ── Subuid/subgid (for unprivileged containers) ─────────────
for file in /etc/subuid /etc/subgid; do
    if ! grep -q "root:1000000:1000000000" "$file" 2>/dev/null; then
        info "Configuring ${file} for unprivileged containers..."
        echo "root:1000000:1000000000" >> "$file"
    fi
done

# ── Done ─────────────────────────────────────────────────────
info "Incus initialized for AnKLuMe."
info ""
info "Next steps:"
info "  1. Copy infra.yml.example to infra.yml and edit it"
info "  2. make sync     — generate Ansible files"
info "  3. make apply    — create the infrastructure"
info ""
info "To verify: incus list"
