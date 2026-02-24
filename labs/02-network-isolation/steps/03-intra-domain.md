# Step 03: Test Intra-Domain Connectivity

## Goal

Verify that containers within the same domain can communicate.

## Instructions

1. Get the IP addresses:

   ```bash
   incus list --project lab-office --format csv -c n4
   ```

2. From `office-pc`, ping `office-server`:

   ```bash
   incus exec office-pc --project lab-office -- \
     ping -c 3 <office-server-ip>
   ```

   This should succeed. Both containers share the same bridge
   (`net-lab-office`) and the same subnet (`10.110.0.x/24`).

3. Verify from the other direction too:

   ```bash
   incus exec office-server --project lab-office -- \
     ping -c 3 <office-pc-ip>
   ```

## Key concept

Containers on the same bridge (same domain) can communicate freely.
This is the intra-domain trust boundary: machines within a domain
are assumed to trust each other at the network level.
