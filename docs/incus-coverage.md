# Incus Native Feature Coverage

anklume is a declarative high-level interface to Incus. It manages Incus
resources (projects, networks, profiles, instances) via the CLI, leveraging
native Incus features wherever possible and adding custom logic only where
Incus does not provide the needed functionality.

## Positioning

anklume does not replace Incus. It provides:
- A single YAML file (`infra.yml`) describing the entire infrastructure
- Automatic generation of Ansible inventory and variables
- Reconciliation-based idempotent management of Incus resources
- Inter-domain network isolation via nftables
- Lifecycle tooling (snapshots, flush, import, upgrade)

All Incus features remain accessible via the CLI alongside anklume.

## Coverage matrix

| Incus feature | Coverage | How |
|---------------|----------|-----|
| **Projects** | Full | `incus_projects` role creates per-domain projects |
| **Bridges (managed)** | Full | `incus_networks` role creates `net-*` bridges |
| **Profiles** | Full | `incus_profiles` role + domain-level `profiles:` in infra.yml |
| **LXC instances** | Full | `incus_instances` role, `type: lxc` |
| **KVM VMs** | Full | `incus_instances` role, `type: vm` with `--vm` flag |
| **Static IPs** | Full | Device override on `eth0` in default profile |
| **GPU passthrough (LXC)** | Full | `nvidia-compute` profile pattern |
| **GPU passthrough (VM)** | Documented | `gpu-passthrough` profile with PCI address |
| **Instance config** | Full | `config:` in infra.yml propagated to `incus config set` |
| **Storage volumes** | Full | `storage_volumes:` in infra.yml, created and attached |
| **Ephemeral instances** | Full | `--ephemeral` flag on `incus launch` |
| **boot.autostart** | Full | `boot_autostart:` in infra.yml |
| **boot.autostart.priority** | Full | `boot_priority:` in infra.yml (0-100) |
| **security.protection.delete** | Full | Derived from `ephemeral: false` |
| **snapshots.schedule** | Full | `snapshots_schedule:` cron expression in infra.yml |
| **snapshots.expiry** | Full | `snapshots_expiry:` duration in infra.yml |
| **Manual snapshots** | Full | `scripts/snap.sh` wraps `incus snapshot` |
| **Image caching** | Full | `incus_images` role pre-downloads images |
| **Image export/import** | Full | Shared image repository across nesting levels |
| **Nesting** | Full | `security.nesting` via profile config + nesting context files |
| **Proxy devices** | Full | Used for Incus socket forwarding to anklume container |
| **Cloud-init** | Partial | Supported via `config:` keys, no dedicated abstraction |
| **Limits (CPU/memory)** | Full | `config:` keys + `resource_policy` auto-allocation |
| **Network ACLs** | Not used | See explanation below |
| **Network zones** | Not used | See explanation below |
| **OVN networking** | Not used | See explanation below |
| **Clustering** | Out of scope | anklume targets single-host deployments |
| **OCI containers** | Out of scope | anklume manages LXC and KVM only |
| **SR-IOV** | Out of scope | Requires enterprise hardware |
| **Confidential VMs (SEV/TDX)** | Out of scope | Requires specific CPU features |
| **OIDC authentication** | Out of scope | anklume uses the local Unix socket |
| **Remote servers** | Out of scope | All operations are local |
| **Instance migration** | Not covered | Could be added for multi-host setups |
| **pause/resume** | Not covered | Operational command, no declarative need |

## Features we use natively

anklume uses native Incus features for:

- **Project isolation**: Each domain is an Incus project with separate
  namespace for instances and profiles (`features.networks=false` for
  shared bridges).
- **Profile inheritance**: Domain-level profiles (GPU, nesting, resources)
  are applied via `incus profile assign`.
- **Boot management**: `boot.autostart` and `boot.autostart.priority`
  control startup order natively.
- **Delete protection**: `security.protection.delete` prevents accidental
  deletion of non-ephemeral instances.
- **Automatic snapshots**: `snapshots.schedule` and `snapshots.expiry`
  delegate snapshot lifecycle to Incus.
- **Storage volumes**: Created via `incus storage volume create` and
  attached as disk devices.
- **Image management**: `incus image copy` pre-caches images, export/import
  for nesting.

## Custom logic (why nftables, not Network ACLs)

### Network ACLs

Incus Network ACLs operate **within a single bridge** (intra-network
filtering). They control traffic between instances on the same bridge.

anklume's isolation requirement is **cross-bridge**: block forwarding
between `net-pro` and `net-perso`. Network ACLs cannot enforce this
because they do not see traffic crossing bridge boundaries at the host
kernel level.

The `incus_nftables` role generates host-level nftables rules in a
separate table (`inet anklume`) at priority -1, which runs before
Incus-managed chains and drops inter-bridge forwarded traffic.

Network ACLs could complement nftables as defense-in-depth (intra-bridge
filtering on top of cross-bridge isolation), but this is not currently
implemented.

### Network zones

Incus Network Zones provide auto-generated DNS records for instances.
This is complementary to anklume's IP management but does not replace
it. anklume uses static IPs assigned via device overrides, not DNS
resolution. Network Zones could be integrated in a future phase to
provide DNS-based service discovery.

### OVN networking

OVN (Open Virtual Network) provides software-defined networking with
distributed routers and ACLs. It is designed for multi-host clusters
and adds significant complexity. anklume targets single-host
deployments where Linux bridges + nftables provide sufficient isolation
with lower overhead.

## Roadmap for future integration

| Feature | Benefit | Priority |
|---------|---------|----------|
| Network Zones (DNS) | Auto-generated DNS for instances | Medium |
| Network ACLs (defense-in-depth) | Intra-bridge filtering | Low |
| Instance migration | Multi-host deployments | Low |
| Project resource limits | Per-domain resource caps | Medium |
| pause/resume | Suspend/resume instances on demand | Low |
