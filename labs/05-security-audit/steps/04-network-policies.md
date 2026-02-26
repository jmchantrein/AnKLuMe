# Step 04: Add a Network Policy

## Goal

Create a selective network policy allowing the development domain
to access a specific service in the DMZ, while keeping all other
cross-domain traffic blocked.

## Instructions

1. The scenario: developers in `corp-dev` need to access the web
   server in `corp-dmz` on port 80 (HTTP) and port 443 (HTTPS).
   No other cross-domain access should be permitted.

2. Edit `infra.yml` to add a `network_policies` section at the
   top level (after `domains:`):

   ```yaml
   network_policies:
     - description: "Dev team accesses DMZ web server"
       from: corp-dev
       to: dmz-web
       ports: [80, 443]
       protocol: tcp
   ```

   Note: `from` is a domain name (entire subnet), `to` is a
   machine name (single IP). This follows the principle of least
   privilege: only the specific service is accessible, not the
   entire DMZ domain.

3. Regenerate Ansible files and nftables rules:

   ```bash
   anklume sync
   anklume network rules
   ```

4. Examine the updated nftables rules:

   ```bash
   cat /tmp/anklume-nftables.conf
   ```

   You should now see accept rules before the drop rules:

   ```
   # Dev team accesses DMZ web server
   iifname "net-corp-dev" oifname "net-corp-dmz" \
     ip daddr <dmz-web-ip> tcp dport { 80, 443 } accept
   ```

   The description from `infra.yml` appears as a comment for
   auditability.

5. Verify that the policy is unidirectional. The rules allow
   traffic FROM `corp-dev` TO `dmz-web`, but NOT the reverse.
   Check that no accept rule exists for `net-corp-dmz` to
   `net-corp-dev`:

   ```bash
   grep "net-corp-dmz.*net-corp-dev.*accept" /tmp/anklume-nftables.conf
   ```

   This should return no matches.

6. If you deploy the rules (`anklume network deploy` on the host),
   you can test the policy live:

   ```bash
   # Install curl in dev-server for testing
   incus exec dev-server --project corp-dev -- \
     apt-get update -qq && apt-get install -y -qq curl

   # This should work (port 80 allowed by policy)
   incus exec dev-server --project corp-dev -- \
     curl -s -o /dev/null -w "%{http_code}" http://<dmz-web-ip>

   # Ping should still fail (only TCP 80/443 allowed, not ICMP)
   incus exec dev-server --project corp-dev -- \
     ping -c 2 -W 2 <dmz-web-ip>
   ```

7. Verify other domains still cannot reach the DMZ:

   ```bash
   incus exec office-workstation --project corp-office -- \
     ping -c 2 -W 2 <dmz-web-ip>
   ```

   This should still fail. The policy only permits `corp-dev`.

## What to look for

- Accept rules appear before drop rules (order matters)
- Rules are scoped: specific source, destination, ports, protocol
- Descriptions become nftables comments for audit trails
- Unidirectional by default (use `bidirectional: true` for both ways)
- Other domains remain fully isolated

## Security principle

**Principle of least privilege**: Network policies grant the minimum
access needed. Instead of opening all traffic between domains, you
specify exact source, destination, ports, and protocol. Each policy
is documented with a description explaining the business need.
