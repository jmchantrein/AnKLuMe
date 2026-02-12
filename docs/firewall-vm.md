# Dedicated Firewall VM (sys-firewall)

AnKLuMe supports two firewall modes for inter-domain isolation:

- **`host` mode** (default): nftables rules on the host kernel (Phase 8)
- **`vm` mode**: traffic routed through a dedicated firewall VM

The `vm` mode provides stronger isolation: the firewall runs in its own
kernel, with centralized logging and full nftables control inside the VM.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│ Host                                                      │
│                                                           │
│  net-admin    net-perso    net-pro    net-homelab         │
│    │              │           │           │                │
│    └──────┬───────┴───────┬──┘           │                │
│           │               │              │                │
│    ┌──────┴───────────────┴──────────────┴──────┐        │
│    │         sys-firewall (KVM VM)               │        │
│    │  eth0=admin  eth1=perso  eth2=pro  eth3=hl  │        │
│    │                                              │        │
│    │  nftables: admin→all allowed                 │        │
│    │            non-admin→non-admin dropped        │        │
│    │            centralized logging                │        │
│    └──────────────────────────────────────────────┘        │
└──────────────────────────────────────────────────────────┘
```

The firewall VM has one NIC per domain bridge. It acts as a Layer 3
router between domains, applying nftables rules on forwarded traffic.

## Configuration

### 1. Set firewall mode in infra.yml

```yaml
global:
  base_subnet: "10.100"
  firewall_mode: vm  # Enable firewall VM mode
```

### 2. Declare the firewall VM

Add `sys-firewall` to the admin domain with the `firewall_router` role:

```yaml
domains:
  admin:
    subnet_id: 0
    machines:
      admin-ansible:
        type: lxc
        ip: "10.100.0.10"
        roles: [base_system]
      sys-firewall:
        description: "Centralized firewall VM"
        type: vm
        ip: "10.100.0.253"
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
        roles:
          - base_system
          - firewall_router
```

### 3. Deploy

```bash
make sync          # Generate Ansible files
make apply         # Create infrastructure + provision
```

The `incus_firewall_vm` role automatically:
1. Discovers all AnKLuMe bridges
2. Creates a `firewall-multi-nic` profile with one NIC per bridge
3. Attaches the profile to the sys-firewall VM

The `firewall_router` role provisions the VM:
1. Enables IP forwarding (`net.ipv4.ip_forward = 1`)
2. Installs nftables
3. Deploys isolation rules with logging

## Firewall rules

The generated nftables rules inside the VM enforce:

| Source | Destination | Action |
|--------|------------|--------|
| admin | any domain | ACCEPT (logged) |
| any domain | admin | ACCEPT (established only) |
| non-admin | non-admin | DROP (logged) |
| any | any (ICMP) | ACCEPT |

All decisions are logged with prefixes:
- `FW-ADMIN-FWD`: admin → other domain
- `FW-DENY-<DOMAIN>`: blocked inter-domain traffic
- `FW-INVALID`: invalid packet state
- `FW-DROP`: default drop
- `FW-INPUT-DROP`: connection attempt to the firewall VM itself

### Viewing logs

```bash
incus exec sys-firewall --project admin -- journalctl -kf | grep "FW-"
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
          - 10.100.1.10/24
        routes:
          - to: 10.100.0.0/16
            via: 10.100.1.253
          - to: default
            via: 10.100.1.254
```

### Via Ansible provisioning

Add a route configuration task in the `base_system` role or a custom role:

```yaml
- name: Add route to firewall VM for inter-domain traffic
  ansible.builtin.command:
    cmd: ip route add 10.100.0.0/16 via {{ firewall_vm_ip }}
  when: firewall_mode == 'vm'
```

## Customization

### Role defaults

| Variable | Default | Description |
|----------|---------|-------------|
| `firewall_router_admin_bridge` | `net-admin` | Admin bridge name |
| `firewall_router_logging` | `true` | Enable nftables logging |
| `firewall_router_log_prefix` | `FW` | Log message prefix |
| `incus_firewall_vm_bridge_pattern` | `net-` | Bridge discovery pattern |
| `incus_firewall_vm_profile` | `firewall-multi-nic` | Profile name |

### Adding custom rules

Edit the firewall rules inside the VM:

```bash
incus exec sys-firewall --project admin -- \
  vi /etc/nftables.d/anklume-firewall.nft

# Reload
incus exec sys-firewall --project admin -- \
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
incus profile show firewall-multi-nic --project admin
```

### Traffic not flowing through firewall VM

1. Verify IP forwarding: `incus exec sys-firewall -- sysctl net.ipv4.ip_forward`
2. Check nftables rules: `incus exec sys-firewall -- nft list ruleset`
3. Verify instance routes: `incus exec <instance> -- ip route show`

### Firewall VM not starting

VMs need more resources than containers. Ensure at least 2 vCPU and
2 GiB memory in the config.
