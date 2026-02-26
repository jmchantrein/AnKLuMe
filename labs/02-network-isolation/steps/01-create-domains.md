# Step 01: Create Two Domains

## Goal

Generate Ansible files for a two-domain infrastructure.

## Instructions

1. Examine the lab infrastructure:

   ```bash
   cat labs/02-network-isolation/infra.yml
   ```

   Notice:
   - `lab-office` is `trusted` (subnet `10.110.x.x`)
   - `lab-dmz` is `untrusted` (subnet `10.140.x.x`)
   - Different trust levels get different IP zones (ADR-038)

2. Back up and copy:

   ```bash
   cp infra.yml infra.yml.bak 2>/dev/null || true
   cp labs/02-network-isolation/infra.yml infra.yml
   ```

3. Generate files:

   ```bash
   anklume sync
   ```

4. Compare the two domains:

   ```bash
   cat group_vars/lab-office.yml
   cat group_vars/lab-dmz.yml
   ```

## What to look for

- Each domain has its own bridge (`net-lab-office`, `net-lab-dmz`)
- IP subnets differ by trust zone: `10.110.0.x` vs `10.140.0.x`
- Each domain maps to a separate Incus project

## Validation

Both inventory files must exist.
