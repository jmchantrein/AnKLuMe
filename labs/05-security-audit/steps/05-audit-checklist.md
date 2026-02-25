# Step 05: Audit Checklist

## Goal

Perform a systematic security audit of the infrastructure using
anklume's conventions and tools. This checklist mirrors what a
sysadmin would verify on a production deployment.

## Instructions

### Audit 1: IP addressing zones

Verify that IP addresses match their declared trust levels:

```bash
echo "=== IP Zone Audit ==="
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  echo "--- $proj ---"
  incus list --project "$proj" --format csv -c n4
done
```

Cross-reference with the expected zones:

| Trust Level | Expected Second Octet | Domain |
|-------------|----------------------|--------|
| trusted | 110 | corp-office |
| semi-trusted | 120 | corp-dev |
| untrusted | 140 | corp-dmz |
| disposable | 150 | corp-sandbox |

Any IP address outside its expected zone indicates a misconfiguration.

### Audit 2: Ephemeral and protection flags

Check which instances are protected from deletion:

```bash
echo "=== Protection Audit ==="
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  echo "--- $proj ---"
  for inst in $(incus list --project "$proj" --format csv -c n); do
    prot=$(incus config get "$inst" --project "$proj" \
      security.protection.delete 2>/dev/null)
    echo "  $inst: protection.delete=$prot"
  done
done
```

Expected results based on infra.yml:
- `office-fileserver`: `true` (explicit `ephemeral: false`)
- `office-workstation`: `true` (domain default: non-ephemeral)
- `dev-server`: `true` (default: non-ephemeral)
- `dmz-web`: `false` (explicit `ephemeral: true`)
- `sandbox-test`: `false` (inherits domain `ephemeral: true`)

### Audit 3: Network isolation verification

Run a systematic cross-domain ping sweep:

```bash
echo "=== Isolation Audit ==="
# Collect all IPs
declare -A IPS
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  for inst in $(incus list --project "$proj" --format csv -c n); do
    ip=$(incus list --project "$proj" --format csv -c 4 "$inst" \
      | cut -d' ' -f1)
    IPS["$proj/$inst"]="$ip"
  done
done

# Test cross-domain (should all fail)
incus exec office-workstation --project corp-office -- \
  ping -c 1 -W 1 "${IPS[corp-dmz/dmz-web]}" > /dev/null 2>&1 \
  && echo "FAIL: office->dmz reachable" \
  || echo "OK: office->dmz blocked"

incus exec sandbox-test --project corp-sandbox -- \
  ping -c 1 -W 1 "${IPS[corp-office/office-workstation]}" > /dev/null 2>&1 \
  && echo "FAIL: sandbox->office reachable" \
  || echo "OK: sandbox->office blocked"
```

### Audit 4: Network policies review

List all declared network policies and verify they match
business requirements:

```bash
echo "=== Network Policy Audit ==="
grep -A 5 "network_policies" infra.yml
```

For each policy, verify:
- The source (`from`) and destination (`to`) are correct
- Ports are restricted to what is actually needed
- Unidirectional unless `bidirectional: true` is justified
- A clear description explains the business need

### Audit 5: Infrastructure doctor

If the `doctor.sh` script is available, run a health check:

```bash
scripts/doctor.sh 2>/dev/null || echo "doctor.sh not available"
```

Otherwise, run manual checks:

```bash
echo "=== Manual Health Check ==="
# All containers running?
for proj in corp-office corp-dev corp-dmz corp-sandbox; do
  stopped=$(incus list --project "$proj" --format csv -c s \
    | grep -c STOPPED || true)
  if [ "$stopped" -gt 0 ]; then
    echo "WARNING: $proj has $stopped stopped containers"
  else
    echo "OK: $proj - all running"
  fi
done

# Bridges exist?
for bridge in net-corp-office net-corp-dev net-corp-dmz net-corp-sandbox; do
  incus network show "$bridge" > /dev/null 2>&1 \
    && echo "OK: $bridge exists" \
    || echo "FAIL: $bridge missing"
done
```

## Clean up

When finished, remove all lab resources:

```bash
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
```

## What you learned

- How trust levels encode security posture in IP addresses
- How to verify network isolation systematically
- How nftables rules enforce default-deny between domains
- How network policies create selective, auditable exceptions
- How ephemeral flags control deletion protection
- A repeatable audit methodology for anklume infrastructure

## Audit summary template

Use this template to document your audit findings:

```
Infrastructure Audit — [date]
---
Domains: 4 (trusted, semi-trusted, untrusted, disposable)
Instances: 5 total
IP zones: [PASS/FAIL] — all IPs match expected zones
Isolation: [PASS/FAIL] — cross-domain traffic blocked
Policies: [N] active — [reviewed/not reviewed]
Protection: [PASS/FAIL] — ephemeral flags correctly set
Health: [PASS/FAIL] — all instances running
```
