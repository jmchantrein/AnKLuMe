# SPEC.md — anklume Specification

## 1. Vision

anklume is a declarative infrastructure compartmentalization
framework. It provides QubesOS-like isolation using native
Linux kernel features (KVM/LXC), with optional integrated AI
capabilities.

The user describes their infrastructure in a single YAML file
(`infra.yml`), runs `make sync && make apply`, and gets
isolated, reproducible, disposable environments. anklume
abstracts away the complexity of the underlying technologies
(Incus, Ansible, nftables) behind a high-level declarative
format — mastering these tools is beneficial but not required.

**Design principle: minimize UX friction.** Every interaction
with the framework — from first bootstrap to daily operations —
should require the fewest possible steps, decisions, and
prerequisites. Sensible defaults eliminate configuration when
the user has no opinion. Error messages explain what to do, not
just what went wrong. Formats are chosen for maximum
compatibility (e.g., hybrid ISO for live images, standard
Ansible layout for generated files).

The framework ships with sensible defaults following
enterprise conventions:
- Trust-level-aware IP addressing (`10.<zone>.<seq>.<host>`)
  encoding security posture directly in IP addresses
- Domain naming conventions aligned with professional
  network segmentation practices
- All defaults are configurable for custom environments

Optionally, anklume integrates AI assistants into the
compartmentalized infrastructure:
- Per-domain AI assistants respecting network boundaries
- Local-first LLM inference (GPU) with optional cloud
  fallback
- Automatic anonymization of sensitive data leaving the
  local perimeter

Designed for:
- **Sysadmins** compartmentalizing their workstation
- **Students** learning system administration in a safe,
  reproducible environment that mirrors enterprise
  conventions (IP classes, naming, network segmentation)
- **Teachers** deploying networking labs for N students
- **Power users** wanting QubesOS-like isolation without
  QubesOS constraints
- **Privacy-conscious users** needing to bypass internet
  restrictions or route traffic through isolated gateways
  (Tor, VPN)
- Anyone wanting AI tools that respect domain boundaries
  and data confidentiality

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

The anklume container (`anklume-instance`):
- Has the host's Incus socket mounted read/write
- Contains Ansible, the git repo, and drives everything via `incus` CLI
- Avoids modifying the host as much as possible; when necessary
  (nftables, software prerequisites), changes are made directly
  if it is more KISS/DRY and does not compromise security (ADR-004)

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
    openclaw: false                   # Optional: deploy per-domain OpenClaw AI assistant
    ai_provider: local               # "local" | "cloud" | "local-first" (default: local)
    ai_sanitize: false               # true | false | "always" (default: auto, see below)
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
        persistent_data:             # Optional: host-persisted data
          <volume-name>:
            path: "/absolute/path"   # Required: mount path inside container
            readonly: false          # Optional (default: false)
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
collisions when running anklume nested inside another anklume instance.

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
running anklume directly on a physical host with no nesting.

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

### AI provider and sanitization (Phase 39)

The optional `ai_provider` and `ai_sanitize` fields on a domain
control how LLM requests are routed and whether they pass through
the sanitization proxy (ADR-044).

**`ai_provider`** — where LLM inference runs for this domain:
- **`local`** (default): All requests stay on the local network
  (e.g., Ollama in `ai-tools` domain). No sanitization needed.
- **`cloud`**: Requests are sent to external cloud APIs. The
  sanitization proxy is enabled by default.
- **`local-first`**: Prefers local inference, falls back to cloud
  when local capacity is insufficient. Sanitization enabled by
  default for the cloud fallback path.

**`ai_sanitize`** — sanitization behavior:
- **`false`** (default for `local`): No sanitization.
- **`true`** (default for `cloud` and `local-first`): Sanitize
  cloud-bound requests using the `llm_sanitizer` role patterns.
- **`"always"`**: Sanitize all requests, including local ones.
  Useful for audit/compliance or when local infrastructure is
  shared with untrusted parties.

**Default logic**: If `ai_sanitize` is not set:
- `ai_provider: local` -> `ai_sanitize: false`
- `ai_provider: cloud` -> `ai_sanitize: true`
- `ai_provider: local-first` -> `ai_sanitize: true`

The generator propagates these to `domain_ai_provider` and
`domain_ai_sanitize` in `group_vars/<domain>.yml`. The
`llm_sanitizer` role reads these variables to decide whether
to activate.

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
- GPU policy (`gpu_policy: exclusive` default): at most one instance
  with `gpu: true` or a GPU profile device. If count > 1 and policy
  != `shared` → error. If count > 1 and policy == `shared` → warning.
  VM instances with GPU require IOMMU (Phase 9+)
- `ephemeral`: must be a boolean if present (at both domain and machine level)
- `trust_level`: must be one of `admin`, `trusted`, `semi-trusted`, `untrusted`, `disposable` (if present)
- `openclaw`: must be a boolean if present (default: false)
- `ai_provider`: must be `local`, `cloud`, or `local-first` (if present, default: `local`)
- `ai_sanitize`: must be `true`, `false`, or `"always"` (if present; default:
  `true` when `ai_provider` is `cloud` or `local-first`, `false` otherwise)
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
- `shared_volumes_base`: must be an absolute path if present
  (default: `/srv/anklume/shares`)
- `shared_volumes` volume names: DNS-safe
  (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)
- `shared_volumes.*.source` and `.path`: must be absolute paths
- `shared_volumes.*.shift`: must be a boolean if present (default: true)
- `shared_volumes.*.propagate`: must be a boolean if present
  (default: false)
- `shared_volumes.*.consumers`: must be a non-empty mapping; keys must
  be known domain or machine names; values must be `"ro"` or `"rw"`
- Device name collision: `sv-<name>` must not collide with user-declared
  devices on any consumer
- Path uniqueness: two volumes cannot mount at the same `path` on the
  same consumer machine
- `persistent_data_base`: must be an absolute path if present
  (default: `/srv/anklume/data`)
- `persistent_data` volume names: DNS-safe
  (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)
- `persistent_data.*.path`: required, must be an absolute path
- `persistent_data.*.readonly`: must be a boolean if present
  (default: false)
- Device name collision: `pd-<name>` must not collide with
  user-declared devices or `sv-*` shared volume devices
- Path uniqueness: persistent_data paths must not collide with
  shared_volume paths on the same machine
- When `ai_access_policy: exclusive`:
  - `ai_access_default` is required and must reference a known domain
  - `ai_access_default` cannot be `ai-tools` itself
  - An `ai-tools` domain must exist
  - At most one `network_policy` can target `ai-tools` as destination

### Naming conventions

Machine names follow the `<domain>-<role>` pattern. Two domains have
special naming significance:

**`anklume` domain** (infrastructure/admin):
- Trust level: `admin`
- Machines use the `anklume-` prefix
- Purpose: framework infrastructure (orchestration, firewall)
- Examples: `anklume-instance` (Ansible controller),
  `anklume-firewall` (auto-created firewall VM)

**`shared` domain** (user-facing shared services):
- Trust level: `semi-trusted` (services are shared, not admin)
- Machines use the `shared-` prefix
- Purpose: user-facing services accessible from multiple domains
  via `network_policies` (print, DNS, VPN)
- Examples: `shared-print` (CUPS server), `shared-dns` (local
  resolver), `shared-vpn` (VPN gateway)
- Distinct from `anklume`: the `anklume` domain is for framework
  infrastructure that users do not interact with directly; the
  `shared` domain is for services that users consume from other
  domains

**Other domains** follow the standard `<domain>-<role>` pattern:
- `pro-dev`, `perso-desktop`, `ai-gpu`, `torgw-proxy`

The `sys-` prefix is retired. Legacy `sys-firewall` declarations
are still accepted for backward compatibility (see "Auto-creation
of anklume-firewall" below).

### Per-domain OpenClaw (openclaw directive)

The optional `openclaw` boolean on a domain enables automatic deployment
of a per-domain OpenClaw AI assistant instance. When `openclaw: true`,
the generator auto-creates a `<domain>-openclaw` machine in that domain
if one is not already explicitly declared.

```yaml
domains:
  pro:
    trust_level: trusted
    openclaw: true          # Auto-creates pro-openclaw machine
    machines:
      pw-dev:
        type: lxc
```

The auto-created machine uses:
- type: `lxc`
- roles: `[base_system, openclaw_server]`
- ephemeral: `false`
- IP: auto-assigned within the domain's subnet

If the user declares `<domain>-openclaw` explicitly, their definition
takes precedence and no auto-creation occurs. The generator propagates
`domain_openclaw: true` to `group_vars/<domain>.yml` so roles and tools
can detect whether the domain has an OpenClaw instance.

Each per-domain OpenClaw instance sees only its own domain's network,
providing network-isolated AI assistance that respects domain boundaries.
Domain-specific variables (`openclaw_server_domain`,
`openclaw_server_instance_name`) allow templates to produce
domain-aware agent configurations.

### Auto-creation of anklume-firewall (firewall_mode: vm)

When `global.firewall_mode` is set to `vm`, the generator automatically
creates an `anklume-firewall` machine in the anklume domain if one is not
already declared. This enrichment step (`enrich_infra()`) runs after
validation but before file generation. The auto-created machine uses:
- type: `vm`, ip: `<base_octet>.<zone>.<anklume_seq>.253`
- config: `limits.cpu: "2"`, `limits.memory: "2GiB"`
- roles: `[base_system, firewall_router]`
- ephemeral: `false`

If the user declares `anklume-firewall` explicitly (in any domain), their
definition takes precedence and no auto-creation occurs. For backward
compatibility, a user-declared `sys-firewall` also prevents auto-creation.
If `firewall_mode` is `vm` but no `anklume` domain exists, the generator
exits with an error.

### Security policy (privileged containers)

The generator enforces a security policy based on nesting context:

- **`security.privileged: true`** is forbidden on LXC containers when
  `vm_nested` is `false` (i.e., no VM exists in the chain above the
  current anklume instance). Only VMs provide sufficient hardware
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

### Shared volumes

The optional top-level `shared_volumes:` section declares host
directories shared with consumers (machines or entire domains)
via Incus disk devices.

```yaml
global:
  shared_volumes_base: /mnt/anklume-data/shares  # Default: /srv/anklume/shares

shared_volumes:
  docs:
    source: /mnt/anklume-data/shares/docs  # Optional, default: <base>/<name>
    path: /shared/docs                      # Optional, default: /shared/<name>
    shift: true                             # Optional, default: true
    propagate: false                        # Optional, default: false
    consumers:
      pro: ro            # Domain -> all machines in domain get ro access
      pro-dev: rw        # Machine -> override with rw for this machine
      ai-tools: ro       # Another domain
```

**Fields**:
- `source`: absolute host path to the directory. Default:
  `<shared_volumes_base>/<volume_name>`.
- `path`: mount path inside consumers. Default: `/shared/<volume_name>`.
- `shift`: enable idmap shifting (`shift=true` on the Incus disk device).
  Default: `true`. Required for unprivileged containers to access
  host-owned files.
- `propagate`: if `true`, the volume is also mounted in instances that
  have `security.nesting=true` in their config, allowing nested anklume
  instances to re-declare the volume. Default: `false`.
- `consumers`: mapping of domain or machine names to access mode
  (`ro` or `rw`). Machine-level entries override domain-level entries
  for that specific machine.

**Mechanism**: The generator resolves `shared_volumes` into Incus disk
devices injected into `instance_devices` in each consumer's host_vars.
No new Ansible role is needed — the existing `incus_instances` role
handles arbitrary disk devices.

- Device naming: `sv-<volume_name>` (prefix `sv-` avoids collisions
  with user-declared devices).
- Consumer resolution: domain name expands to all machines in that
  domain; machine name targets that machine specifically; machine-level
  access overrides domain-level access for the same machine.
- Merge: `sv-*` devices are added alongside user-declared
  `instance_devices`. Validation prevents naming collisions.

**Cross-nesting**: `propagate: true` mounts the volume in
nesting-enabled instances. The child anklume can then re-declare the
volume with `source:` pointing to the propagated mount path. There is
no automatic recursive propagation — each nesting level must explicitly
declare its volumes.

**Host directories**: `make shares` creates the host-side directories
for all declared shared volumes. `global.shared_volumes_base` sets
the base path (default: `/srv/anklume/shares`).

### Persistent data volumes

The optional `persistent_data` field on a machine declares host
directories that persist across container rebuilds. Unlike shared
volumes (which share data between instances), persistent data is
tied to a specific machine.

```yaml
global:
  persistent_data_base: /srv/anklume/data   # Default

domains:
  pro:
    machines:
      pro-dev:
        type: lxc
        persistent_data:
          projects:
            path: /home/user/projects    # Required: mount path inside container
            readonly: false              # Optional, default: false
          config:
            path: /home/user/.config
```

**Fields**:
- `path`: absolute path inside the container where the volume is
  mounted. Required.
- `readonly`: boolean, default `false`. If `true`, the volume is
  mounted read-only.

**Mechanism**: The generator resolves `persistent_data` into Incus
disk devices injected into `instance_devices`. Device naming:
`pd-<volume_name>` (prefix `pd-` avoids collisions with user
devices and `sv-*` shared volume devices). Source directory:
`<persistent_data_base>/<machine_name>/<volume_name>`.

**Host directories**: `make data-dirs` creates the host-side
directories. `global.persistent_data_base` sets the base path
(default: `/srv/anklume/data`).

**Flush protection**: `make flush` never deletes
`/srv/anklume/data/` or `/srv/anklume/shares/`. Data persists
across infrastructure rebuilds. See ADR-042.

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

## 6. Educational Labs

anklume ships with guided labs for learning system administration,
networking, and security concepts in isolated environments.

### Lab directory structure

Each lab is a self-contained directory under `labs/`:

```
labs/
  lab-schema.yml              # Validation schema for lab.yml
  README.md                   # Framework documentation
  01-first-deploy/
    lab.yml                   # Metadata (title, difficulty, steps)
    infra.yml                 # Lab-specific infrastructure
    steps/                    # Ordered instruction files
      01-create-infra.md
      02-verify.md
    solution/
      commands.sh             # Reference commands
```

### lab.yml format

```yaml
title: "Lab title"
description: "What the student will learn"
difficulty: beginner          # beginner | intermediate | advanced
duration: "30m"               # Estimated time (e.g., 15m, 1h, 2h)
prerequisites: []             # List of prior lab IDs
objectives:
  - "Objective 1"
steps:
  - id: "01"
    title: "Step title"
    instruction_file: "steps/01-step-name.md"
    hint: "Optional hint text"
    validation: "shell command returning 0 on success"
```

Required fields: `title`, `description`, `difficulty`, `duration`,
`objectives`, `steps`. Each step requires `id`, `title`, and
`instruction_file`. The `hint` and `validation` fields are optional.

Step IDs must be two-digit strings (`01`, `02`, ...) in sequential
order. Instruction files must exist relative to the lab directory.

### Step validation

Each step may include a `validation` field containing a shell command.
The lab runner executes this command; exit code 0 means the step is
complete. On success, the runner advances to the next step and
displays its instructions.

### Make targets

```bash
make lab-list              # List all labs (number, title, difficulty)
make lab-start L=01        # Start lab 01, display first step
make lab-check L=01        # Validate current step
make lab-hint  L=01        # Show hint for current step
make lab-reset L=01        # Reset lab progress
make lab-solution L=01     # Show solution (marks as assisted)
```

### Progress tracking

Lab progress is stored in `~/.anklume/labs/<lab-id>/progress.yml`:

```yaml
current_step: 2
started_at: "2026-02-25T10:00:00+00:00"
assisted: false
completed_steps:
  - "01"
  - "02"
```

Viewing the solution marks the lab as `assisted: true`.

---

For operational details (generator, roles, snapshots, validators,
development workflow, tech stack, bootstrap, and testing), see
[SPEC-operations.md](SPEC-operations.md).
