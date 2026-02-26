# Step 04: Verify Cross-Domain Isolation

## Goal

Confirm that traffic between domains is blocked.

## Instructions

1. Get the DMZ web server IP:

   ```bash
   incus list --project lab-dmz --format csv -c n4
   ```

2. From `office-pc`, try to ping the DMZ server:

   ```bash
   incus exec office-pc --project lab-office -- \
     ping -c 3 -W 2 <dmz-web-ip>
   ```

   This should **fail** (timeout or unreachable). The containers
   are on different bridges and nftables blocks inter-bridge traffic.

3. Generate and deploy nftables rules to make isolation explicit:

   ```bash
   anklume network rules
   ```

   Examine the generated rules to see the drop policy.

4. Even without explicit nftables rules, containers on different
   bridges cannot communicate because there is no routing between
   `net-lab-office` and `net-lab-dmz`.

## Key concept

anklume enforces network isolation at two levels:
- **Bridge level**: each domain has its own bridge, no default routing
- **nftables level**: explicit drop rules prevent forwarding between
  bridges, even if a route were added

This is the same isolation model used by QubesOS, implemented with
standard Linux networking.

## Clean up

When done, restore your original infrastructure:

```bash
anklume flush --force
cp infra.yml.bak infra.yml 2>/dev/null || true
anklume sync
```
