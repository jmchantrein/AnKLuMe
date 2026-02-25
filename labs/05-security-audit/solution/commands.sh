#!/usr/bin/env bash
# Lab 05 — Reference solution commands
# These commands complete each step of the lab.

set -euo pipefail

echo "=== Step 01: Inspect the topology ==="
cp infra.yml infra.yml.bak 2>/dev/null || true
cp labs/05-security-audit/infra.yml infra.yml
make sync && make apply

incus project list
incus network list

for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  echo "--- $proj ---"
  incus list --project "$proj" -c n4s
done

grep trust_level group_vars/corp-*.yml

echo "=== Step 02: Test isolation ==="
OFFICE_IP=$(incus list --project corp-office --format csv -c 4 \
  office-workstation | cut -d' ' -f1)
DEV_IP=$(incus list --project corp-dev --format csv -c 4 \
  dev-server | cut -d' ' -f1)
DMZ_IP=$(incus list --project corp-dmz --format csv -c 4 \
  dmz-web | cut -d' ' -f1)
SANDBOX_IP=$(incus list --project corp-sandbox --format csv -c 4 \
  sandbox-test | cut -d' ' -f1)

echo "Office: $OFFICE_IP, Dev: $DEV_IP, DMZ: $DMZ_IP, Sandbox: $SANDBOX_IP"

# Cross-domain ping (should fail)
incus exec office-workstation --project corp-office -- \
  ping -c 2 -W 2 "$DMZ_IP" || echo "Expected: cross-domain blocked"
incus exec dev-server --project corp-dev -- \
  ping -c 2 -W 2 "$OFFICE_IP" || echo "Expected: cross-domain blocked"

echo "=== Step 03: Examine nftables rules ==="
make nftables
cat /tmp/anklume-nftables.conf
grep -c "drop" /tmp/anklume-nftables.conf

echo "=== Step 04: Add a network policy ==="
# Append network_policies to infra.yml
cat >> infra.yml << 'POLICY'

network_policies:
  - description: "Dev team accesses DMZ web server"
    from: corp-dev
    to: dmz-web
    ports: [80, 443]
    protocol: tcp
POLICY

make sync
make nftables
grep "accept" /tmp/anklume-nftables.conf
# Verify no reverse rule
grep "net-corp-dmz.*net-corp-dev.*accept" /tmp/anklume-nftables.conf || \
  echo "OK: no reverse accept rule (unidirectional)"

echo "=== Step 05: Audit checklist ==="
# IP zone audit
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  echo "--- $proj ---"
  incus list --project "$proj" --format csv -c n4
done

# Protection audit
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  for inst in $(incus list --project "$proj" --format csv -c n); do
    prot=$(incus config get "$inst" --project "$proj" \
      security.protection.delete 2>/dev/null)
    echo "$inst: protection.delete=$prot"
  done
done

# Health check
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  stopped=$(incus list --project "$proj" --format csv -c s \
    | grep -c STOPPED || true)
  if [ "$stopped" -gt 0 ]; then
    echo "WARNING: $proj has $stopped stopped containers"
  else
    echo "OK: $proj - all running"
  fi
done

echo "=== Cleanup ==="
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  for inst in $(incus list --project "$proj" --format csv -c n); do
    incus config set "$inst" --project "$proj" \
      security.protection.delete=false 2>/dev/null || true
    incus delete "$inst" --project "$proj" --force
  done
done
for bridge in net-corp-office net-corp-dev net-corp-dmz net-corp-sandbox; do
  incus network delete "$bridge" 2>/dev/null || true
done
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  incus project delete "$proj" 2>/dev/null || true
done
cp infra.yml.bak infra.yml 2>/dev/null || true
make sync

echo "Lab 05 complete."
