# SPEC.md — AnKLuMe Specification

## 1. Vision

AnKLuMe is a declarative infrastructure compartmentalization framework.
It provides QubesOS-like isolation using native Linux kernel features
(KVM/LXC), orchestrated by the user through Ansible and Incus.

The user describes their infrastructure in a single YAML file (`infra.yml`),
runs `make sync && make apply`, and gets isolated, reproducible, disposable
environments.

Designed for:
- Sysadmins who want to compartmentalize their workstation
- Teachers deploying networking labs for N students
- Power users who want QubesOS-like isolation without QubesOS constraints

## 2. Key concepts

### Domain
A domain = an isolated subnet + an Incus project + N instances.
Each domain becomes:
- An Ansible inventory group
- A network bridge (`net-<domain>`)
- An Incus project (namespace isolation)
- A `group_vars/<domain>.yml` file

Adding a domain = adding a section in `infra.yml` + `make sync`.

### Instance (machine)
An LXC container or KVM virtual machine. Defined within a domain in `infra.yml`.
Each instance becomes an Ansible host in its domain's group, with variables
in `host_vars/<instance>.yml`.

### Profile
A reusable Incus configuration (GPU, nesting, resource limits). Defined at the
domain level in `infra.yml`, applied to instances that reference it.

### Snapshot
A saved state of an instance. Supports: individual, batch (whole domain),
restore, delete.

## 3. Source of truth model (PSOT)

```
┌─────────────────────┐     make sync     ┌─────────────────────────┐
│     infra.yml       │ ────────────────▶ │  Ansible files          │
│  (Primary Source     │                   │  (Secondary Source       │
│   of Truth)         │                   │   of Truth)             │
│                     │                   │                         │
│  High-level infra   │                   │  inventory/<domain>.yml │
│  description:       │                   │  group_vars/<domain>.yml│
│  domains, machines, │                   │  host_vars/<host>.yml   │
│  networks, profiles │                   │                         │
│                     │                   │  Users may freely edit  │
│                     │                   │  outside managed sections│
└─────────────────────┘                   └────────────┬────────────┘
                                                       │
                                                  make apply
                                                       │
                                                       ▼
                                          ┌─────────────────────────┐
                                          │    Incus state          │
                                          │  (bridges, projects,    │
                                          │   profiles, instances)  │
                                          └─────────────────────────┘
```

**Rules**:
- `infra.yml` holds the structural truth (what domains, machines, IPs, profiles).
- Generated Ansible files hold the operational truth (custom variables, extra
  config, role parameters added by the user).
- Both must be committed to git.
- `make sync` only overwrites `=== MANAGED ===` sections; everything else
  is preserved.

## 4. Host architecture

```
┌─────────────────────────────────────────────────────────┐
│ Host (any Linux distro)                                 │
│  • Incus daemon + nftables + (optional) NVIDIA GPU      │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ net-aaa  │ │ net-bbb  │ │ net-ccc  │  ...           │
│  │ .X.0/24  │ │ .Y.0/24  │ │ .Z.0/24  │                │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘                │
│       │             │             │                      │
│  ┌────┴────┐  ┌─────┴────┐ ┌────┴──────┐               │
│  │ LXC/VM  │  │ LXC/VM   │ │ LXC/VM   │               │
│  └─────────┘  └──────────┘ └──────────┘                │
│                                                         │
│  nftables isolation: net-X ≠ net-Y (no forwarding)     │
└─────────────────────────────────────────────────────────┘
```

The anklume container:
- Has the host's Incus socket mounted read/write
- Contains Ansible, the git repo, and drives everything via `incus` CLI
- Never modifies the host directly

## 5. infra.yml format

```yaml
# infra.yml — Primary Source of Truth
# Describes the infrastructure. Run `make sync` after editing.

project_name: my-infra

global:
  addressing:                         # Zone-based IP addressing (ADR-038)
    base_octet: 10                    # First octet, always 10 (RFC 1918)
    zone_base: 100                    # Starting second octet (default: 100)
    zone_step: 10                     # Gap between zones (default: 10)
  default_os_image: "images:debian/13"
  default_connection: community.general.incus
  default_user: root
  ai_access_policy: open            # "exclusive" or "open" (default: open)
  ai_access_default: pro            # Domain with initial access (required if exclusive)
  ai_vram_flush: true               # Flush GPU VRAM on domain switch (default: true)
  nesting_prefix: true              # Prefix Incus names with nesting level (default: true)
  resource_policy:                  # Optional: auto-allocate CPU/memory
    host_reserve:
      cpu: "20%"                    # Reserved for host (default: 20%)
      memory: "20%"                 # Reserved for host (default: 20%)
    mode: proportional              # proportional | equal (default: proportional)
    cpu_mode: allowance             # allowance (%) | count (vCPU) (default: allowance)
    memory_enforce: soft            # soft (ballooning) | hard (default: soft)
    overcommit: false               # Allow total > available (default: false)

domains:
  <domain-name>:
    description: "What this domain is for"
    enabled: true                     # Optional (default: true). false skips generation.
    subnet_id: <0-254>               # Optional: auto-assigned alphabetically within zone
    ephemeral: false                  # Optional (default: false). See below.
    trust_level: semi-trusted         # Determines IP zone (default: semi-trusted)
    profiles:                         # Optional: extra Incus profiles
      <profile-name>:
        devices: { ... }
        config: { ... }
    machines:
      <machine-name>:                # Must be globally unique
        description: "What this machine does"
        type: lxc                     # "lxc" or "vm"
        ip: "<bo>.<zone>.<seq>.<host>"  # Optional (auto-assigned if omitted)
        ephemeral: false              # Optional (default: inherit from domain)
        gpu: false                    # true to enable GPU passthrough
        profiles: [default]           # List of Incus profiles
        weight: 1                     # Resource allocation weight (default: 1)
        boot_autostart: false         # Optional: start on host boot (default: false)
        boot_priority: 0              # Optional: boot order 0-100 (default: 0)
        snapshots_schedule: "0 2 * * *"  # Optional: cron schedule for auto-snapshots
        snapshots_expiry: "30d"       # Optional: retention duration (e.g., 30d, 24h)
        config: { ... }              # Incus instance config overrides
        storage_volumes: { ... }     # Optional: dedicated volumes
        roles: [base_system]         # Ansible roles for provisioning
```

### Addressing convention (ADR-038)

IP addresses encode trust zones in the second octet:

```
10.<zone_base + zone_offset>.<domain_seq>.<host>/24
```

| trust_level    | zone_offset | Default second octet |
|----------------|-------------|----------------------|
| admin          | 0           | 100                  |
| trusted        | 10          | 110                  |
| semi-trusted   | 20          | 120                  |
| untrusted      | 40          | 140                  |
| disposable     | 50          | 150                  |

`domain_seq` (third octet) is auto-assigned alphabetically within each
zone, or explicitly overridden via `subnet_id` on the domain.

IP reservation per /24 subnet:
- `.1-.99`: static assignment (machines in infra.yml, auto-assigned)
- `.100-.199`: DHCP range
- `.250`: monitoring (reserved)
- `.251-.253`: infrastructure services
- `.254`: gateway (immutable convention)

### Gateway convention

Each domain network uses `<base_octet>.<zone>.<seq>.254` as its gateway
address. This is set automatically by the generator and cannot be overridden.

### Enabled directive

The optional `enabled` boolean on a domain controls whether the generator
produces files for it. Defaults to `true`. When `false`, no inventory,
group_vars, or host_vars files are generated for that domain. Disabled
domains still participate in addressing computation (their IP ranges are
reserved) and are not flagged as orphans.

### Ephemeral directive

The `ephemeral` boolean controls whether a domain or machine is protected
from accidental deletion:

- **Domain level**: `ephemeral: false` (default) protects the entire domain.
- **Machine level**: overrides the domain value for that specific machine.
- **Inheritance**: if not specified on a machine, it inherits from its domain.
  If not specified on a domain, it defaults to `false` (protected).

**Semantics**:
- `ephemeral: false` (protected): any delete operation (machine, network,
  domain) that would destroy this resource is refused by tooling.
  `detect_orphans()` reports protected resources but `--clean-orphans`
  skips them.
- `ephemeral: true`: the resource can be freely created and destroyed.

The `incus_instances` role propagates the ephemeral flag to Incus natively:
`ephemeral: false` sets `security.protection.delete=true` on the instance,
preventing deletion via `incus delete`. `ephemeral: true` sets it to `false`.

### Boot autostart

The optional `boot_autostart` and `boot_priority` fields control instance
behavior when the Incus host boots:

- `boot_autostart: true` sets `boot.autostart=true` on the instance,
  causing Incus to automatically start it when the daemon starts.
- `boot_priority` (0-100) controls the start order. Higher values start
  first. Default: 0.

The `incus_instances` role applies these via `incus config set`.

### Automatic snapshots

The optional `snapshots_schedule` and `snapshots_expiry` fields enable
Incus-native automatic snapshots:

- `snapshots_schedule` is a cron expression (5 fields, e.g., `"0 2 * * *"`
  for daily at 2am). Incus creates snapshots automatically on this schedule.
- `snapshots_expiry` is a retention duration (e.g., `"30d"`, `"24h"`,
  `"60m"`). Incus deletes snapshots older than this automatically.

Both are optional and independent. The `incus_instances` role applies
these via `incus config set snapshots.schedule` and `snapshots.expiry`.

### Nesting prefix

The optional `nesting_prefix` boolean in `global:` enables prefixing
all Incus resource names with the nesting level. This prevents name
collisions when running AnKLuMe nested inside another AnKLuMe instance.

```yaml
global:
  nesting_prefix: false   # Opt-out (default: true)
```

When enabled, the generator reads `/etc/anklume/absolute_level` (created
by the parent instance). If the file is absent (physical host, no nesting),
no prefix is applied regardless of the setting. The prefix format is
`{level:03d}-`:

| Resource | Without prefix | With prefix (level 1) |
|----------|---------------|----------------------|
| Incus project | `pro` | `001-pro` |
| Bridge name | `net-pro` | `001-net-pro` |
| Instance name | `pro-dev` | `001-pro-dev` |

Ansible file paths and group names remain unprefixed (`inventory/pro.yml`,
`group_vars/pro.yml`, `host_vars/pro-dev.yml`). The prefix only affects
Incus-facing names stored in variables (`incus_project`, `incus_network.name`,
`instance_name`). Ansible roles consume these variables transparently.

When `nesting_prefix: false`, no prefix is applied. This is useful when
running AnKLuMe directly on a physical host with no nesting.

### Trust levels

The optional `trust_level` field indicates the security posture and
isolation requirements of a domain. This is primarily used by the
console generator (Phase 19a) for visual domain identification via
color-coding (QubesOS-style), but may also inform future access
control and policy decisions.

Valid values:
- **`admin`**: Administrative domain with full system access (blue)
- **`trusted`**: Production workloads, personal data (green)
- **`semi-trusted`**: Development, testing, low-risk browsing (yellow)
- **`untrusted`**: Untrusted software, risky browsing (red)
- **`disposable`**: Ephemeral sandboxes, one-time tasks (magenta)

If omitted, no trust level is assigned and the domain has no specific
color coding in the console.

The generator propagates `trust_level` to `domain_trust_level` in
`group_vars/<domain>.yml`. Roles and tools can read this variable to
adapt behavior based on domain trust posture.

### Validation constraints

- Domain names: unique, alphanumeric + hyphen
- Machine names: globally unique (not just within their domain)
- `enabled`: must be a boolean if present (default: true)
- `subnet_id`: optional with `addressing:` (auto-assigned); unique within
  same trust zone, range 0-254
- IPs: globally unique, must be within the correct subnet (auto-assigned
  in `.1-.99` range when omitted with `addressing:` mode)
- `addressing.base_octet`: must be 10 (RFC 1918)
- `addressing.zone_base`: must be 0-245 (default: 100)
- `addressing.zone_step`: must be a positive integer (default: 10)
- Profiles referenced by a machine must exist in its domain
- `ephemeral`: must be a boolean if present (at both domain and machine level)
- `trust_level`: must be one of `admin`, `trusted`, `semi-trusted`, `untrusted`, `disposable` (if present)
- `weight`: must be a positive integer if present (default: 1)
- `boot_autostart`: must be a boolean if present
- `boot_priority`: must be an integer 0-100 if present (default: 0)
- `snapshots_schedule`: must be a valid cron expression (5 fields) if present
- `snapshots_expiry`: must be a duration string (e.g., `30d`, `24h`, `60m`) if present
- `ai_access_policy`: must be `exclusive` or `open`
- `resource_policy.mode`: must be `proportional` or `equal` (if present)
- `resource_policy.cpu_mode`: must be `allowance` or `count` (if present)
- `resource_policy.memory_enforce`: must be `soft` or `hard` (if present)
- `nesting_prefix`: must be a boolean if present (default: true)
- `resource_policy.overcommit`: must be a boolean (if present)
- `resource_policy.host_reserve.cpu` and `.memory`: must be `"N%"` or a
  positive number (if present)
- When `ai_access_policy: exclusive`:
  - `ai_access_default` is required and must reference a known domain
  - `ai_access_default` cannot be `ai-tools` itself
  - An `ai-tools` domain must exist
  - At most one `network_policy` can target `ai-tools` as destination

### Auto-creation of sys-firewall (firewall_mode: vm)

When `global.firewall_mode` is set to `vm`, the generator automatically
creates a `sys-firewall` machine in the anklume domain if one is not already
declared. This enrichment step (`enrich_infra()`) runs after validation but
before file generation. The auto-created machine uses:
- type: `vm`, ip: `<base_subnet>.<anklume_subnet_id>.253`
- config: `limits.cpu: "2"`, `limits.memory: "2GiB"`
- roles: `[base_system, firewall_router]`
- ephemeral: `false`

If the user declares `sys-firewall` explicitly (in any domain), their
definition takes precedence and no auto-creation occurs. If `firewall_mode`
is `vm` but no `anklume` domain exists, the generator exits with an error.

### Security policy (privileged containers)

The generator enforces a security policy based on nesting context:

- **`security.privileged: true`** is forbidden on LXC containers when
  `vm_nested` is `false` (i.e., no VM exists in the chain above the
  current AnKLuMe instance). Only VMs provide sufficient hardware
  isolation for privileged workloads.
- The `vm_nested` flag is auto-detected at bootstrap via
  `systemd-detect-virt` and propagated to all child instances.
- A `--YOLO` flag bypasses this restriction (warnings instead of errors).

Nesting context is stored in `/etc/anklume/` as individual files:
- `absolute_level` — nesting depth from the real physical host
- `relative_level` — nesting depth from the nearest VM boundary (resets to 0 at each VM)
- `vm_nested` — `true` if a VM exists anywhere in the parent chain
- `yolo` — `true` if YOLO mode is enabled

These files are created by the **parent** when it instantiates children,
not by the child's own bootstrap.

### Network policies

By default, all inter-domain traffic is dropped. The `network_policies`
section declares selective exceptions:

```yaml
network_policies:
  - description: "Pro domain accesses AI services"
    from: pro                    # Source: domain name or machine name
    to: ai-tools                 # Destination: domain name or machine name
    ports: [3000, 8080]          # TCP/UDP ports
    protocol: tcp                # tcp or udp

  - description: "Host accesses Ollama"
    from: host                   # Special keyword: the physical host
    to: gpu-server               # Specific machine
    ports: [11434]
    protocol: tcp

  - description: "Full connectivity between dev and staging"
    from: dev
    to: staging
    ports: all                   # All ports, all protocols
    bidirectional: true          # Rules in both directions
```

Special keywords:
- Domain name → entire subnet of that domain
- Machine name → single IP of that machine
- `host` → the physical host machine
- `ports: all` → all ports and protocols
- `bidirectional: true` → creates rules in both directions

The generator validates that every `from` and `to` references a known
domain name, machine name, or the keyword `host`. Each rule maps to an
nftables `accept` rule before the blanket `drop`.

### Resource allocation policy

The optional `resource_policy` section in `global:` enables automatic
CPU and memory allocation to instances based on detected host resources.

```yaml
global:
  resource_policy:              # absent = no auto-allocation
    host_reserve:
      cpu: "20%"                # Reserved for host (default: 20%)
      memory: "20%"             # Reserved for host (default: 20%)
    mode: proportional          # proportional | equal (default: proportional)
    cpu_mode: allowance         # allowance (%) | count (vCPU) (default: allowance)
    memory_enforce: soft        # soft (ballooning) | hard (default: soft)
    overcommit: false           # Allow total > available (default: false)
```

Setting `resource_policy: {}` or `resource_policy: true` activates
allocation with all defaults: 20% host reserve, proportional
distribution, CPU allowance mode, soft memory enforcement.

**Host reserve**: A fixed percentage (or absolute value) of host
resources reserved for the operating system and Incus daemon. Instances
cannot use this reserve.

**Distribution modes**:
- `proportional`: Each machine gets resources proportional to its
  `weight` (default weight: 1). A machine with `weight: 3` gets three
  times the resources of a machine with `weight: 1`.
- `equal`: All machines get the same share regardless of weight.

**CPU modes**:
- `allowance`: Sets `limits.cpu.allowance` as a percentage. Allows
  flexible CPU sharing via CFS scheduler.
- `count`: Sets `limits.cpu` as a fixed vCPU count. Dedicates cores
  to instances.

**Memory enforcement**:
- `soft`: Adds `limits.memory.enforce: "soft"` (cgroups v2 memory
  ballooning). Instances can temporarily exceed their limit when
  host memory is available. VMs use virtio-balloon natively.
- `hard`: Default Incus behavior — strict memory limit.

**Overcommit**: When `false` (default), the generator errors if the
sum of all allocated resources (auto + explicit) exceeds the available
pool. When `true`, a warning is emitted instead.

**Machine weight**:

```yaml
machines:
  heavy-worker:
    weight: 3               # Gets 3x the share of default-weight machines
    type: lxc
  light-worker:
    type: lxc               # Default weight: 1
```

Machines with explicit `limits.cpu`, `limits.cpu.allowance`, or
`limits.memory` in their `config:` are excluded from auto-allocation
for that resource but counted towards the overcommit total. The
generator never overwrites explicit configuration.

**Detection**: Host resources are detected via `incus info --resources`
(preferred) or `/proc/cpuinfo` + `/proc/meminfo` (fallback). If
detection fails, resource allocation is skipped with a warning.

### infra.yml as a directory

For large deployments, `infra.yml` can be replaced by an `infra/`
directory:

```
infra/
├── base.yml                 # project_name + global settings
├── domains/
│   ├── anklume.yml          # One file per domain
│   ├── ai-tools.yml
│   ├── pro.yml
│   └── perso.yml
└── policies.yml             # network_policies
```

The generator auto-detects the format:
- If `infra.yml` exists → single-file mode (backward compatible)
- If `infra/` exists → merges `base.yml` + `domains/*.yml` (sorted
  alphabetically) + `policies.yml`

Both formats produce identical output after merging.

---

For operational details (generator, roles, snapshots, validators,
development workflow, tech stack, bootstrap, and testing), see
[SPEC-operations.md](SPEC-operations.md).
