#!/usr/bin/env bash
# Lab 02 — Reference solution commands

set -euo pipefail

echo "=== Step 01: Create two domains ==="
cp infra.yml infra.yml.bak 2>/dev/null || true
cp labs/02-network-isolation/infra.yml infra.yml
anklume sync

echo "=== Step 02: Deploy ==="
anklume domain apply
incus list --project lab-office
incus list --project lab-dmz

echo "=== Step 03: Intra-domain connectivity ==="
SERVER_IP=$(incus list --project lab-office --format csv -c 4 office-server | cut -d' ' -f1)
incus exec office-pc --project lab-office -- ping -c 3 "$SERVER_IP"
echo "PASS: Intra-domain ping succeeded"

echo "=== Step 04: Cross-domain isolation ==="
DMZ_IP=$(incus list --project lab-dmz --format csv -c 4 dmz-web | cut -d' ' -f1)
if incus exec office-pc --project lab-office -- ping -c 2 -W 2 "$DMZ_IP" 2>/dev/null; then
    echo "FAIL: Cross-domain ping should not succeed"
    exit 1
else
    echo "PASS: Cross-domain ping blocked (expected)"
fi

echo "=== Cleanup ==="
anklume flush --force
cp infra.yml.bak infra.yml 2>/dev/null || true
anklume sync

echo "Lab 02 complete."
