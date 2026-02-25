# Step 03: Examine nftables Rules

## Goal

Understand how anklume generates nftables rules for inter-domain
isolation and learn to read the rule structure.

## Instructions

1. Generate the nftables rules from your current infrastructure:

   ```bash
   make nftables
   ```

   This produces the rules file. Examine the output path shown
   by the command.

2. Read the generated rules:

   ```bash
   cat /tmp/anklume-nftables.conf
   ```

   If the file is at a different path, use the path shown by
   `make nftables`.

3. Understand the rule structure:

   The generated file contains an `inet anklume` table with a
   `forward` chain. Key elements:

   ```
   table inet anklume {
     chain forward {
       type filter hook forward priority -1; policy accept;

       # Accept rules for network_policies go here
       # (none yet — we will add one in the next step)

       # Drop rules between all anklume bridges
       iifname "net-corp-office" oifname "net-corp-dev" drop
       iifname "net-corp-office" oifname "net-corp-dmz" drop
       ...
     }
   }
   ```

   - **Priority -1**: Runs before Incus chains (priority 0), so
     anklume isolation is evaluated first (ADR-022)
   - **Policy accept**: Non-matching traffic falls through to Incus
     chains (which handle NAT, DHCP, etc.)
   - **Drop rules**: One pair per bridge combination (both directions)

4. Count the drop rules:

   ```bash
   grep -c "drop" /tmp/anklume-nftables.conf
   ```

   With 4 domains, there are 12 drop rules (4 bridges x 3 other
   bridges). Each pair is blocked in both directions.

5. Verify no accept rules exist yet:

   ```bash
   grep "accept" /tmp/anklume-nftables.conf
   ```

   Without network policies, there should be no accept rules in
   the anklume table (only drop rules).

6. If nftables rules are already deployed on the host, you can
   inspect the live rules:

   ```bash
   sudo nft list table inet anklume 2>/dev/null || echo "Table not deployed yet"
   ```

## What to look for

- The `inet anklume` table is separate from Incus tables (coexistence)
- Priority -1 ensures anklume rules are evaluated first
- Every bridge-to-bridge combination has a drop rule
- No accept rules exist until network policies are defined
- Rules are human-readable with bridge names as identifiers

## Security principle

**Defense in depth**: Even though bridges already provide Layer 2
isolation, nftables rules add an explicit Layer 3 drop. If a
misconfiguration or exploit bypasses bridge isolation, the nftables
rules still block the traffic.
