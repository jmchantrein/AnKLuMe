#!/usr/bin/env bash
# Lab 01 — Reference solution commands
# These commands complete each step of the lab.

set -euo pipefail

echo "=== Step 01: Create infrastructure ==="
cp infra.yml infra.yml.bak 2>/dev/null || true
cp labs/01-first-deploy/infra.yml infra.yml
make sync

echo "=== Step 02: Deploy and verify ==="
make apply
incus list --project lab-net
# Extract lab-db IP and ping from lab-web
LAB_DB_IP=$(incus list --project lab-net --format csv -c 4 lab-db | cut -d' ' -f1)
incus exec lab-web --project lab-net -- ping -c 3 "$LAB_DB_IP"

echo "=== Step 03: Clean up ==="
incus delete lab-web --project lab-net --force
incus delete lab-db --project lab-net --force
incus network delete net-lab-net
incus project delete lab-net
cp infra.yml.bak infra.yml 2>/dev/null || true
make sync

echo "Lab 01 complete."
