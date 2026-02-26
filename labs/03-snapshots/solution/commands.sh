#!/usr/bin/env bash
# Lab 03 — Reference solution commands

set -euo pipefail

echo "=== Step 01: Setup ==="
cp infra.yml infra.yml.bak 2>/dev/null || true
cp labs/03-snapshots/infra.yml infra.yml
anklume sync
anklume domain apply

echo "=== Step 02: Create snapshot ==="
incus exec snap-server --project lab-snap -- \
    bash -c 'echo "Lab 03 baseline" > /root/marker.txt'
incus snapshot create snap-server baseline --project lab-snap
incus info snap-server --project lab-snap | grep baseline

echo "=== Step 03: Break container ==="
incus exec snap-server --project lab-snap -- rm -f /root/marker.txt
incus exec snap-server --project lab-snap -- rm -rf /etc/apt/sources.list.d/

echo "=== Step 04: Restore ==="
incus snapshot restore snap-server baseline --project lab-snap
sleep 2
incus exec snap-server --project lab-snap -- cat /root/marker.txt

echo "=== Step 05: Cleanup ==="
incus snapshot delete snap-server baseline --project lab-snap
anklume flush --force
cp infra.yml.bak infra.yml 2>/dev/null || true
anklume sync

echo "Lab 03 complete."
