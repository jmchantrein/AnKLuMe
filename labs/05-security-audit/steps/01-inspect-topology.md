# Step 01: Inspect the Topology

## Goal

Deploy a multi-domain infrastructure with four different trust
levels and examine its network topology.

## Instructions

1. Examine the lab infrastructure file:

   ```bash
   cat labs/05-security-audit/infra.yml
   ```

   Notice the four domains with different trust levels:

   | Domain | Trust Level | Zone Offset | Expected Subnet |
   |--------|-------------|-------------|-----------------|
   | `corp-office` | trusted | +10 | `10.110.x.x/24` |
   | `corp-dev` | semi-trusted | +20 | `10.120.x.x/24` |
   | `corp-dmz` | untrusted | +40 | `10.140.x.x/24` |
   | `corp-sandbox` | disposable | +50 | `10.150.x.x/24` |

   The second octet encodes the trust zone: `zone_base (100) +
   zone_offset`. An administrator can immediately identify a
   domain's security posture from any IP address.

2. Deploy the infrastructure:

   ```bash
   cp infra.yml infra.yml.bak 2>/dev/null || true
   cp labs/05-security-audit/infra.yml infra.yml
   make sync && make apply
   ```

3. List all Incus projects:

   ```bash
   incus project list
   ```

   You should see four projects, one per domain.

4. List all network bridges:

   ```bash
   incus network list
   ```

   Each domain has its own bridge (`net-corp-office`, `net-corp-dev`,
   `net-corp-dmz`, `net-corp-sandbox`), providing Layer 2 isolation.

5. Inspect each domain's containers and their IPs:

   ```bash
   for proj in corp-office corp-dev corp-dmz corp-sandbox; do
     echo "--- $proj ---"
     incus list --project "$proj" -c n4s
   done
   ```

   Verify that each container's IP matches the expected zone range.

6. Examine the generated group_vars to see trust level propagation:

   ```bash
   grep trust_level group_vars/corp-*.yml
   ```

   Each domain's `domain_trust_level` variable reflects the value
   from `infra.yml`.

## What to look for

- Four separate Incus projects provide namespace isolation
- Four separate bridges provide Layer 2 network isolation
- IP addresses are zone-encoded (second octet reveals trust level)
- Trust levels propagate to Ansible group_vars for role consumption

## Validation

This step passes when the `corp-office` project has at least one
running container.
