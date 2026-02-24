# Network Isolation with nftables

anklume uses nftables to enforce inter-bridge isolation on the host.
By default, Incus bridges allow forwarding between them, meaning a
container in one domain can reach containers in other domains. The
`incus_nftables` role generates rules that block all cross-domain
traffic.

## How domain isolation works

Each anklume domain has its own bridge (e.g., `net-anklume`, `net-pro`,
`net-perso`, `net-ai-tools`). Without isolation rules, the Linux kernel
forwards packets between these bridges freely.

The nftables rules enforce:

1. **Same-bridge traffic**: allowed (containers within a domain can
   communicate)
2. **All inter-bridge traffic**: dropped (e.g., `net-perso` cannot
   reach `net-pro`, and `net-anklume` cannot reach other domains either)
3. **Internet access**: unaffected (NAT rules from Incus are preserved)
4. **Return traffic**: stateful tracking allows response packets back
   through established connections

The anklume container does not need a network exception because it
communicates with all instances via the Incus socket (mounted
read/write inside the container), not via the network. Ansible uses
the `community.general.incus` connection plugin, which calls
`incus exec` over the socket. No IP traffic crosses bridges.

## nftables rule design

### Table and chain

The rules live in `table inet anklume` with a single chain `isolation`:

```nft
table inet anklume {
    chain isolation {
        type filter hook forward priority -1; policy accept;
        ...
    }
}
```

Key design choices:

- **`inet` family**: handles both IPv4 and IPv6 in a single table
- **`forward` hook**: filters traffic being routed between bridges
- **`priority -1`**: runs before Incus-managed chains (priority 0),
  ensuring isolation rules are evaluated first
- **`policy accept`**: default accept, with explicit drop rules for
  inter-bridge traffic. This avoids interfering with non-anklume traffic

### Atomic replacement

The ruleset uses `table inet anklume; delete table inet anklume;` followed
by the full table definition. This ensures rules are atomically replaced
without a gap where no rules are active.

### Coexistence with Incus

anklume rules use a separate table (`inet anklume`), priority -1 (before
Incus chains), and `policy accept`. Non-matching traffic falls through to
Incus-managed NAT and per-bridge chains without interference.

### Stateful tracking

`ct state established,related accept` allows return traffic from established
connections. Invalid packets are dropped.

## Two-step workflow

Generating and deploying nftables rules is a two-step process because
anklume runs inside the anklume container but nftables rules must be
applied on the host.

### Step 1: Generate rules (inside anklume container)

```bash
make nftables
```

This runs the `incus_nftables` Ansible role, which:

1. Queries `incus network list` to discover all bridges
2. Filters for anklume bridges (names starting with `net-`)
3. Templates the nftables rules to `/opt/anklume/nftables-isolation.nft`

The generated file is stored inside the anklume container and can be
reviewed before deployment.

### Step 2: Deploy rules (on the host)

```bash
make nftables-deploy
```

This runs `scripts/deploy-nftables.sh` **on the host** (not inside the
container). The script:

1. Pulls the rules file from the anklume container via `incus file pull`
2. Validates syntax with `nft -c -f` (dry-run)
3. Copies to `/etc/nftables.d/anklume-isolation.nft`
4. Applies the rules with `nft -f`

Use `--dry-run` to validate without installing:

```bash
scripts/deploy-nftables.sh --dry-run
```

### Why two steps?

anklume follows ADR-004: Ansible does not modify the host directly.
The anklume container drives Incus via the socket, but nftables must be
applied on the host kernel. Splitting generation (safe, inside container)
from deployment (requires host access) maintains this boundary while
giving the operator a chance to review the rules before applying them.

## Configuration

Variables in `roles/incus_nftables/defaults/main.yml`:

| Variable | Default | Description |
|----------|---------|-------------|
| `incus_nftables_bridge_pattern` | `net-` | Prefix used to identify anklume bridges |
| `incus_nftables_output_path` | `/opt/anklume/nftables-isolation.nft` | Where to write the generated rules |
| `incus_nftables_apply` | `false` | Apply rules immediately (use with caution) |

Setting `incus_nftables_apply: true` makes the role apply the rules directly.
This only works if the role runs on the host (not in a container).

## Verification

After deploying, verify the rules are active:

```bash
# List the anklume table
nft list table inet anklume

# Test isolation: from a non-anklume container, try to ping another domain
incus exec perso -- ping -c1 10.110.1.1    # Should fail (pro zone)
incus exec perso -- ping -c1 10.110.0.254  # Should work (own gateway)

# Test anklume isolation: anklume cannot reach other domains via network
incus exec anklume-instance -- ping -c1 10.110.1.1   # Should fail (dropped)

# Verify anklume can still manage instances via Incus socket
incus exec anklume-instance -- incus list             # Should work (socket, not network)

# Test internet: from any container
incus exec perso-desktop -- ping -c1 1.1.1.1       # Should work
```

## Troubleshooting

### Rules not taking effect

1. Verify the table exists: `nft list tables | grep anklume`
2. Check `br_netfilter` is loaded: `lsmod | grep br_netfilter`
3. If `br_netfilter` is not loaded, bridge traffic bypasses nftables
   entirely. Load it with: `modprobe br_netfilter`
4. Verify `net.bridge.bridge-nf-call-iptables = 1` in sysctl

### Internet access broken from containers

The anklume rules only affect `forward` chain traffic between bridges.
NAT (masquerade) rules managed by Incus use separate chains. If internet
is broken:

1. Check Incus NAT rules: `nft list ruleset | grep masquerade`
2. Verify the bridge has `ipv4.nat: "true"`: `incus network show net-<domain>`
3. The anklume `policy accept` should not block non-matching traffic

### Removing isolation rules

```bash
nft delete table inet anklume           # Remove active rules
rm /etc/nftables.d/anklume-isolation.nft  # Remove installed file
```

### Regenerating after adding a domain

```bash
make sync && make apply-infra    # Create new domain resources
make nftables                    # Regenerate rules (inside anklume)
make nftables-deploy             # Deploy updated rules (on host)
```
