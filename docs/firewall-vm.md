# Dedicated Firewall VM (anklume-firewall)

anklume supports two firewall modes for inter-domain isolation:

- **`host` mode** (default): nftables rules on the host kernel (Phase 8)
- **`vm` mode**: traffic routed through a dedicated firewall VM

The `vm` mode provides stronger isolation: the firewall runs in its own
kernel, with centralized logging and full nftables control inside the VM.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Host                                                      │
│                                                           │
│  net-anklume  net-perso    net-pro    net-ai-tools        │
│    │              │           │           │                │
│    └──────┬───────┴───────┬──┘           │                │
│           │               │              │                │
│    ┌──────┴───────────────┴──────────────┴──────┐        │
│    │       anklume-firewall (KVM VM)              │        │
│    │  eth0=anklume  eth1=perso  eth2=pro  eth3=ai │        │
│    │                                              │        │
│    │  nftables: all inter-domain dropped            │        │
│    │            anklume uses Incus socket (not net)  │        │
│    │            centralized logging                │        │
│    └──────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────┘
```

The firewall VM has one NIC per domain bridge. It acts as a Layer 3
router between domains, applying nftables rules on forwarded traffic.

## Quick start (auto-creation)

The simplest way to enable the firewall VM is to set `firewall_mode: vm`
in `infra.yml`. The PSOT generator automatically creates the `anklume-firewall`
machine in the anklume domain if you have not declared one yourself:

```yaml
# infra.yml — just add firewall_mode: vm
global:
  addressing:
    base_octet: 10
    zone_base: 100
  firewall_mode: vm

domains:
  anklume:
    trust_level: admin
    machines:
      anklume-instance:
        type: lxc
        roles: [base_system]
  # ... other domains ...
```

```bash
anklume sync    # Auto-creates anklume-firewall (.253) in anklume domain
anklume domain apply   # Creates infrastructure + provisions the firewall VM
```

The generator prints an informational message when auto-creating:

```
INFO: firewall_mode is 'vm' — auto-created anklume-firewall in anklume domain (ip: 10.100.0.253)
```

(IP depends on zone addressing; shown here for admin zone at zone_base=100.)

The auto-created `anklume-firewall` has: type `vm`, IP `.253` in the anklume
subnet, 2 vCPU, 2 GiB memory, roles `[base_system, firewall_router]`,
and `ephemeral: false`.

To customize the firewall VM (different IP, more resources, extra roles),
declare it explicitly in `infra.yml` and the generator will use your
definition instead. See the manual configuration section below.

## Configuration (manual)

### 1. Set firewall mode in infra.yml

```yaml
global:
  addressing:
    base_octet: 10
    zone_base: 100
  firewall_mode: vm  # Enable firewall VM mode
```

### 2. Declare the firewall VM (optional — auto-created if omitted)

To override the defaults, add `anklume-firewall` to the anklume domain:

```yaml
domains:
  anklume:
    trust_level: admin
    machines:
      anklume-instance:
        type: lxc
        roles: [base_system]
      anklume-firewall:
        description: "Centralized firewall VM"
        type: vm
        config:
          limits.cpu: "4"
          limits.memory: "4GiB"
        roles:
          - base_system
          - firewall_router
```

### 3. Deploy

```bash
anklume sync          # Generate Ansible files
anklume domain apply         # Create infrastructure + provision
```

The `incus_firewall_vm` role automatically:
1. Discovers all anklume bridges
2. Creates a `firewall-multi-nic` profile with one NIC per bridge
3. Attaches the profile to the anklume-firewall VM

The `firewall_router` role provisions the VM:
1. Enables IP forwarding (`net.ipv4.ip_forward = 1`)
2. Installs nftables
3. Deploys isolation rules with logging

## Firewall rules

The generated nftables rules inside the VM enforce:

| Source | Destination | Action |
|--------|------------|--------|
| any domain | different domain | DROP (logged) |
| any | any (ICMP) | ACCEPT |
| any | any (established) | ACCEPT |

The anklume domain is treated like any other domain. The anklume container
communicates with all instances via the Incus socket, not the network,
so it does not need a network-level exception.

All decisions are logged with prefixes:
- `FW-DENY-<DOMAIN>`: blocked inter-domain traffic
- `FW-INVALID`: invalid packet state
- `FW-DROP`: default drop
- `FW-INPUT-DROP`: connection attempt to the firewall VM itself

### Viewing logs

```bash
incus exec anklume-firewall --project anklume -- journalctl -kf | grep "FW-"
```

## Defense in depth

The `host` and `vm` modes can coexist for layered security:

1. **Host nftables** (Phase 8): blocks direct bridge-to-bridge forwarding
2. **Firewall VM** (Phase 11): routes permitted traffic + logs

Even if the firewall VM is compromised, host-level nftables rules
still prevent direct inter-bridge traffic.

## Instance routing

For instances to route inter-domain traffic through the firewall VM,
configure static routes. Two approaches:

### Via instance config (cloud-init)

```yaml
# In host_vars/<instance>.yml (manually, outside managed section)
instance_config:
  cloud-init.network-config: |
    version: 2
    ethernets:
      eth0:
        addresses:
          - 10.110.1.1/24      # Example: trusted zone
        routes:
          - to: 10.0.0.0/8     # All anklume zones via firewall
            via: 10.110.1.253
          - to: default
            via: 10.110.1.254
```

### Via Ansible provisioning

Add a route configuration task in the `base_system` role or a custom role:

```yaml
- name: Add route to firewall VM for inter-domain traffic
  ansible.builtin.command:
    cmd: ip route add 10.0.0.0/8 via {{ firewall_vm_ip }}
  when: firewall_mode == 'vm'
```

## Customization

### Role defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `firewall_router_logging` | `true` | Enable nftables logging |
| `firewall_router_log_prefix` | `FW` | Log message prefix |
| `incus_firewall_vm_bridge_pattern` | `net-` | Bridge discovery pattern |
| `incus_firewall_vm_profile` | `firewall-multi-nic` | Profile name |

### Adding custom rules

Edit the firewall rules inside the VM:

```bash
incus exec anklume-firewall --project anklume -- \
  vi /etc/nftables.d/anklume-firewall.nft

# Reload
incus exec anklume-firewall --project anklume -- \
  systemctl restart nftables
```

## Troubleshooting

### Firewall VM has only one NIC

The `incus_firewall_vm` role adds NICs dynamically based on discovered
bridges. Verify bridges exist:

```bash
incus network list | grep net-
```

Check the profile:

```bash
incus profile show firewall-multi-nic --project anklume
```

### Traffic not flowing through firewall VM

1. Verify IP forwarding: `incus exec anklume-firewall -- sysctl net.ipv4.ip_forward`
2. Check nftables rules: `incus exec anklume-firewall -- nft list ruleset`
3. Verify instance routes: `incus exec <instance> -- ip route show`

### Firewall VM not starting

VMs need more resources than containers. Ensure at least 2 vCPU and
2 GiB memory in the config.
