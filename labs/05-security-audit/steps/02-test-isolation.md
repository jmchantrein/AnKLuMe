# Step 02: Test Isolation

## Goal

Verify that containers in different domains cannot communicate
with each other. By default, anklume drops all inter-domain
traffic at the network level.

## Instructions

1. Get the IP addresses for testing. Pick one container from each
   domain:

   ```bash
   OFFICE_IP=$(incus list --project corp-office --format csv -c 4 \
     office-workstation | cut -d' ' -f1)
   DEV_IP=$(incus list --project corp-dev --format csv -c 4 \
     dev-server | cut -d' ' -f1)
   DMZ_IP=$(incus list --project corp-dmz --format csv -c 4 \
     dmz-web | cut -d' ' -f1)
   SANDBOX_IP=$(incus list --project corp-sandbox --format csv -c 4 \
     sandbox-test | cut -d' ' -f1)

   echo "Office: $OFFICE_IP"
   echo "Dev:    $DEV_IP"
   echo "DMZ:    $DMZ_IP"
   echo "Sandbox: $SANDBOX_IP"
   ```

2. Test intra-domain connectivity (should succeed):

   ```bash
   incus exec office-workstation --project corp-office -- \
     ping -c 2 -W 2 "$OFFICE_IP"
   ```

   Containers on the same bridge can reach each other.

3. Test cross-domain connectivity (should fail):

   Try from the trusted office to the untrusted DMZ:

   ```bash
   incus exec office-workstation --project corp-office -- \
     ping -c 2 -W 2 "$DMZ_IP"
   ```

   This should time out or return "Destination Host Unreachable".
   The separate bridges have no routing between them.

4. Test additional cross-domain paths. Each should fail:

   ```bash
   # Dev to Office
   incus exec dev-server --project corp-dev -- \
     ping -c 2 -W 2 "$OFFICE_IP"

   # Sandbox to Dev
   incus exec sandbox-test --project corp-sandbox -- \
     ping -c 2 -W 2 "$DEV_IP"

   # DMZ to Office
   incus exec dmz-web --project corp-dmz -- \
     ping -c 2 -W 2 "$OFFICE_IP"
   ```

5. Understand why isolation works:

   - Each domain has its own bridge (Layer 2 boundary)
   - No IP routing exists between bridges by default
   - When nftables rules are deployed, they add an explicit DROP
     for any forwarded traffic between anklume bridges as a
     defense-in-depth measure

## What to look for

- Intra-domain ping succeeds (same bridge)
- Cross-domain ping fails in every direction (no routing)
- No trust level has special privileges over another by default
- Isolation is symmetric: A cannot reach B, and B cannot reach A

## Security principle

**Default deny**: anklume follows the principle of least privilege.
No domain can communicate with any other domain unless explicitly
permitted by a network policy. This is enforced at multiple layers
(bridge isolation + nftables rules).
