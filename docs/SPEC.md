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
  base_subnet: "10.100"             # Domains use <base_subnet>.<subnet_id>.0/24
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
    subnet_id: <0-254>               # Must be unique across all domains
    ephemeral: false                  # Optional (default: false). See below.
    trust_level: admin                # Optional: admin|trusted|semi-trusted|untrusted|disposable
    profiles:                         # Optional: extra Incus profiles
      <profile-name>:
        devices: { ... }
        config: { ... }
    machines:
      <machine-name>:                # Must be globally unique
        description: "What this machine does"
        type: lxc                     # "lxc" or "vm"
        ip: "<base_subnet>.<subnet_id>.<host>"  # Optional (DHCP if omitted)
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

### Gateway convention

Each domain network uses `<base_subnet>.<subnet_id>.254` as its gateway
address. This is set automatically by the generator and cannot be overridden.

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
by the parent instance). If the file is absent, level defaults to 1.
The prefix format is `{level:03d}-`:

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
- `subnet_id`: unique per domain, range 0-254
- IPs: globally unique, must be within the correct subnet
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

## 6. Generator (scripts/generate.py)

Reads `infra.yml` and generates/updates the Ansible file tree.

### Generated files

```
inventory/<domain>.yml      # Hosts for this domain
group_vars/all.yml          # Global variables
group_vars/<domain>.yml     # Domain-level variables
host_vars/<machine>.yml     # Machine-specific variables
```

### Managed sections pattern

```yaml
# === MANAGED BY infra.yml ===
# Do not edit this section — it will be overwritten by `make sync`
incus_network:
  name: net-example
  subnet: 10.100.0.0/24
  gateway: 10.100.0.254
# === END MANAGED ===

# Your custom variables below:
```

### Generator behavior

1. **Missing file** → created with managed section + helpful comments
2. **Existing file** → only the managed section is rewritten, rest preserved
3. **Orphans** → listed in a report, interactive deletion proposed
4. **Validation** → all constraints checked before writing any file

### Input formats

The generator accepts two input formats:

- **Single file**: `scripts/generate.py infra.yml` — traditional mode
- **Directory**: `scripts/generate.py infra/` — merges files automatically

When using directory mode, the generator:
1. Loads `infra/base.yml` (required: project_name, global)
2. Merges all `infra/domains/*.yml` files (sorted alphabetically)
3. Merges `infra/policies.yml` if present
4. Validates the merged structure identically to single-file mode
5. Error messages include the source filename for debugging

### Connection variables

`default_connection` and `default_user` from `infra.yml`'s `global:` section
are stored in `group_vars/all.yml` as `psot_default_connection` and
`psot_default_user` (informational only). Playbooks may reference these
values if needed.

They are **NOT** output as `ansible_connection` or `ansible_user` in any
generated file. Rationale: Ansible inventory variables override play-level
keywords ([variable precedence](https://docs.ansible.com/ansible/latest/reference_appendices/general_precedence.html)).
If `ansible_connection: community.general.incus` appeared in domain
group_vars, it would override `connection: local` in the playbook, causing
infrastructure roles to attempt connecting into containers that do not yet
exist. Connection is an operational concern of the playbook, not a
declarative property of the infrastructure.

## 7. Ansible roles

### Phase 1: Infrastructure (connection: local, target: localhost)

| Role | Responsibility | Tags |
|------|---------------|------|
| `incus_networks` | Create/reconcile bridges | `networks`, `infra` |
| `incus_projects` | Create/reconcile projects + default profile | `projects`, `infra` |
| `incus_profiles` | Create extra profiles (GPU, nesting) | `profiles`, `infra` |
| `incus_instances` | Create/manage LXC + VM instances | `instances`, `infra` |
| `incus_nftables` | Generate inter-bridge isolation rules | `nftables`, `infra` |
| `incus_firewall_vm` | Multi-NIC profile for firewall VM | `firewall`, `infra` |
| `incus_images` | Pre-download OS images to cache | `images`, `infra` |
| `incus_nesting` | Nesting context propagation | `nesting`, `infra` |

### Phase 2: Provisioning (connection: community.general.incus)

| Role | Responsibility | Tags |
|------|---------------|------|
| `base_system` | Base packages, locale, timezone, user | `provision`, `base` |
| `ollama_server` | Ollama LLM inference server | `provision`, `llm` |
| `open_webui` | Open WebUI chat frontend | `provision`, `webui` |
| `stt_server` | Speaches STT server (faster-whisper) | `provision`, `stt` |
| `lobechat` | LobeChat multi-provider web UI | `provision`, `lobechat` |
| `opencode_server` | OpenCode headless AI coding server | `provision`, `opencode` |
| `firewall_router` | nftables routing inside firewall VM | `provision`, `firewall` |
| `dev_test_runner` | Incus-in-Incus sandbox provisioning | `provision`, `test` |
| `dev_agent_runner` | Claude Code Agent Teams setup | `provision`, `agent-setup` |
| (user-defined) | Application-specific setup | `provision` |

### Reconciliation pattern (all infra roles)

Every infra role follows exactly this 6-step pattern:
1. **Read** current state: `incus <resource> list --format json`
2. **Parse** into a comparable structure
3. **Build** desired state from group_vars/host_vars
4. **Create** what is declared but missing
5. **Update** what exists but differs
6. **Detect orphans** — report, delete if `auto_cleanup: true`

## 8. Snapshots (scripts/snap.sh)

Imperative operations (not declarative reconciliation). Wraps `incus snapshot`.

### Interface

```bash
scripts/snap.sh create  <instance|self> [snap-name]    # Default name: snap-YYYYMMDD-HHMMSS
scripts/snap.sh restore <instance|self> <snap-name>
scripts/snap.sh list    [instance|self]                 # All instances if omitted
scripts/snap.sh delete  <instance|self> <snap-name>
```

### Makefile targets

```bash
make snap              I=<name|self> [S=<snap>]   # Create
make snap-restore      I=<name|self>  S=<snap>    # Restore
make snap-list        [I=<name|self>]              # List
make snap-delete       I=<name|self>  S=<snap>    # Delete
```

### Instance-to-project resolution

Queries `incus list --all-projects --format json` to find which Incus project
contains the instance. ADR-008 (globally unique names) guarantees unambiguous
resolution.

### "self" keyword

When `I=self`, the script uses `hostname` to detect the current instance name.
Works from any instance with access to the Incus socket (typically the anklume
container). Fails with a clear error if the hostname is not found.

### Self-restore safety

Restoring the instance you are running inside kills your session. The script
warns and asks for confirmation (`Type 'yes' to confirm`). Use `--force` to
skip the prompt (for scripted use).

## 8b. Pre-apply snapshots (scripts/snapshot-apply.sh)

Automatic snapshot safety net for `make apply`. Creates snapshots of all
affected instances before applying changes, with retention policy and
one-command rollback. This is an operational wrapper, not declarative.

### Interface

```bash
scripts/snapshot-apply.sh create [--limit <group>]    # Snapshot before apply
scripts/snapshot-apply.sh rollback [<timestamp>]      # Restore last pre-apply snapshot
scripts/snapshot-apply.sh list                        # List pre-apply snapshots
scripts/snapshot-apply.sh cleanup [--keep <N>]        # Remove old snapshots (default: keep 3)
```

### Makefile integration

The `safe_apply_wrap` Makefile function calls `snapshot-apply.sh create`
before every apply and `snapshot-apply.sh cleanup` after. Controlled by
`SKIP_SNAPSHOT=1` to bypass. Retention count configurable via `KEEP=N`.

```bash
make apply                      # Auto-snapshots all instances before apply
make apply-limit G=homelab      # Auto-snapshots only homelab instances
make rollback                   # Restore most recent pre-apply snapshot
make rollback T=20260219-143022 # Restore specific pre-apply snapshot
make rollback-list              # List available pre-apply snapshots
make rollback-cleanup KEEP=5    # Remove old snapshots, keep 5
```

### Snapshot naming

Snapshots are named `pre-apply-YYYYMMDD-HHMMSS`. The timestamp is
generated at create time. This prefix distinguishes pre-apply snapshots
from user-created snapshots (which use `snap-` prefix via `scripts/snap.sh`).

### Instance-to-project resolution

Uses Ansible inventory (`ansible-inventory -i inventory/ --list`) to
discover instances, then reads `group_vars/*/vars.yml` to find the
Incus project for each instance. Falls back to `default` project if
no project is found.

When `--limit <group>` is specified, only instances belonging to that
Ansible group are snapshotted.

### State tracking

Snapshot metadata is stored in `~/.anklume/pre-apply-snapshots/`:
- `latest` — timestamp of most recent snapshot
- `latest-scope` — group name or "all"
- `history` — ordered list of all snapshot names (one per line)

### Rollback behavior

- Without arguments: restores the most recent pre-apply snapshot
- With timestamp: restores the specific snapshot `pre-apply-<timestamp>`
- Skips instances that don't have the requested snapshot (reports count)
- Fails with error if no instances are restored

### Cleanup and retention

Default retention: 3 snapshots. The `cleanup` command removes the oldest
snapshots across all instances, keeping the most recent N. The `history`
file is trimmed to match.

### Error handling

- Missing instances (not found in Incus): warned and skipped during create
- Failed snapshots: warned, apply proceeds, rollback may be incomplete
- No inventory: warned, returns 0 (no-op)
- No snapshots to rollback: error with suggestion to run `make rollback-list`

## 9. Validators

Every file type has a dedicated validator. No file escapes validation.

| Validator | Target files | Checks |
|-----------|-------------|--------|
| `ansible-lint` | `roles/**/*.yml`, playbooks | Production profile, 0 violations |
| `yamllint` | All `*.yml` / `*.yaml` | Syntax, formatting, line length |
| `shellcheck` | `scripts/**/*.sh` | Shell best practices, portability |
| `ruff` | `scripts/**/*.py`, `tests/**/*.py` | Python linting + formatting |
| `markdownlint` | `**/*.md` (optional) | Markdown consistency |
| `ansible-playbook --syntax-check` | Playbooks | YAML/Jinja2 syntax |

`make lint` runs all validators in sequence. CI must pass all of them.

## 10. Development workflow

This project follows **spec-driven, test-driven development**:

1. **Spec first**: Update SPEC.md or ARCHITECTURE.md
2. **Test second**: Molecule (roles) or pytest (generator)
3. **Implement third**: Code until tests pass
4. **Validate**: `make lint`
5. **Review**: Run the reviewer agent
6. **Commit**: Only when everything passes

## 11. Tech stack

| Component | Version | Role |
|-----------|---------|------|
| Incus | ≥ 6.0 LTS | LXC containers + KVM VMs |
| Ansible | ≥ 2.16 | Orchestration, roles |
| community.general | ≥ 9.0 | `incus` connection plugin |
| Molecule | ≥ 24.0 | Role testing |
| pytest | ≥ 8.0 | Generator testing |
| Python | ≥ 3.11 | PSOT generator |
| nftables | — | Inter-bridge isolation |
| shellcheck | — | Shell script validation |
| ruff | — | Python linting |

## 12. Bootstrap and lifecycle

### Bootstrap script

`bootstrap.sh` initializes AnKLuMe on a new machine:

```bash
./bootstrap.sh --prod                    # Production: auto-detect FS, configure Incus
./bootstrap.sh --dev                     # Development: minimal config
./bootstrap.sh --prod --snapshot btrfs   # Snapshot FS before modifications
./bootstrap.sh --YOLO                    # Bypass security restrictions
./bootstrap.sh --import                  # Import existing Incus infrastructure
./bootstrap.sh --help                    # Usage
```

Production mode auto-detects the filesystem (btrfs, zfs, ext4) and
configures the Incus preseed with the optimal storage backend.

### Import existing infrastructure

`make import-infra` scans running Incus state and generates a matching
`infra.yml`. The user edits the result, then runs `make sync && make apply`
to converge idempotently.

### Flush (reset to zero)

`make flush` destroys all AnKLuMe infrastructure:
- All instances, profiles, projects, and `net-*` bridges
- Generated Ansible files (inventory/, group_vars/, host_vars/)
- Preserves: infra.yml, roles/, scripts/, docs/
- Requires `FORCE=true` on production (`absolute_level == 0`, `yolo != true`)

### Upgrade

`make upgrade` updates AnKLuMe framework files safely:
- Pulls upstream changes
- Detects locally modified framework files → creates `.bak`
- Regenerates managed sections via `make sync`
- Checks version compatibility

User files (`infra.yml`, `roles_custom/`, `anklume.conf.yml`) are never
touched during upgrade.

### User customization directories

- `roles_custom/` — user-created roles (gitignored, priority in roles_path)
- `anklume.conf.yml` — user configuration (gitignored, template provided)
- Generated files — user content outside `=== MANAGED ===` sections preserved

## 13. Out of scope (managed by bootstrap or host)

Managed by `bootstrap.sh` or manual host configuration:
- NVIDIA driver installation/configuration
- Kernel / mkinitcpio configuration
- Incus daemon installation and preseed (`bootstrap.sh --prod` assists)
- Host nftables configuration (`make nftables-deploy` assists)
- Sway/Wayland configuration for GUI forwarding
- Filesystem snapshots for rollback (`bootstrap.sh --snapshot` assists)

The AnKLuMe framework DOES NOT modify the host directly from Ansible.
It drives Incus via the socket. Host-level operations use dedicated
scripts run by the operator.

## 14. Behavior matrix testing

A YAML behavior matrix (`tests/behavior_matrix.yml`) maps every
capability to expected reactions at three depth levels:

- **Depth 1**: single-feature tests (e.g., create domain with valid subnet_id)
- **Depth 2**: pairwise interactions (e.g., domain ephemeral + machine override)
- **Depth 3**: three-way interactions (e.g., domain + VM + GPU + firewall_mode)

Each cell has a unique ID (e.g., `DL-001`). Tests reference cells via
`# Matrix: DL-001` comments. `scripts/matrix-coverage.py` scans tests and
reports coverage. `scripts/ai-matrix-test.sh` generates tests for uncovered
cells using an LLM backend.

Hypothesis property-based tests (`tests/test_properties.py`) complement
the matrix with randomized infra.yml structures testing generator invariants.

## 15. Image sharing across nesting levels

To avoid redundant image downloads in nested Incus environments:

1. Host exports images: `make export-images` (via `incus_images` role with
   `incus_images_export_for_nesting: true`)
2. Export directory mounted read-only into nested VMs as a disk device
3. Nested Incus imports from local files (`dev_test_runner` role)

No network access required for nested image imports. Read-only mount
preserves isolation.

## 16. Code audit (scripts/code-audit.py)

A Python script that produces a structured codebase audit report.

**Usage**:
```bash
make audit          # Terminal report
make audit-json     # JSON to reports/audit.json
scripts/code-audit.py --json --output FILE
```

**Report contents**:
- Line count per file type (Python impl, Python tests, Shell, YAML roles)
- Test-to-implementation ratio per module
- Scripts without test coverage identified
- Roles sorted by size with simplification candidates flagged (>200 lines)
- Dead code detection (delegates to `scripts/code-analysis.sh dead-code`)
- Overall summary (total impl lines, test lines, ratio)

**JSON output**: `--json` flag produces machine-readable output for CI
integration or trend tracking.

## 17. Incus network guard (scripts/incus-guard.sh)

Consolidated guard script that prevents Incus bridges from breaking host
network connectivity when bridge subnets conflict with the host's real
network.

**Subcommands**:
```bash
scripts/incus-guard.sh start       # Safe startup with bridge watcher
scripts/incus-guard.sh post-start  # Systemd ExecStartPost hook
scripts/incus-guard.sh install     # Install as systemd drop-in
```

**`start`**: Detects host network, runs a kernel-level bridge watcher
(deletes conflicting bridges every 100ms), starts Incus, cleans Incus
database, restores default route if lost, verifies gateway connectivity.

**`post-start`**: Runs after every Incus startup via systemd. Uses only
local kernel calls (`ip link`) — works even if network is broken. Scans
all bridges for subnet conflicts, removes conflicting ones, cleans Incus
database, restores default route.

**`install`**: Copies the guard script to `/opt/anklume/incus-guard.sh`,
creates a systemd drop-in for `incus.service` with
`ExecStartPost=/opt/anklume/incus-guard.sh post-start`, reloads systemd.

**Design principles**:
- Non-blocking: `post-start` exits 0 even on errors (never blocks Incus)
- Comprehensive: checks all bridges, not just `net-*` prefixed ones
- Defensive: saves host interface to `/run/incus-guard-host-dev` for
  recovery when default route is already lost
- Logs to `/var/log/incus-network-guard.log` with timestamps

## 18. Smoke testing

Minimal real-world deployment test that verifies core AnKLuMe
functionality on actual Incus infrastructure (not mocked).

**Usage**:
```bash
make smoke    # Requires running Incus daemon
```

**Test flow** (5 steps):
1. `make sync-dry` — verify generator works on real `infra.yml`
2. `make check` — dry-run apply (no actual changes)
3. `make lint` — all validators pass
4. `snapshot-list` — snapshot infrastructure responds
5. `incus list` — Incus daemon reachable

**Purpose**: Quick validation that the entire toolchain works end-to-end
on the host. Catches integration issues that unit tests cannot detect
(missing packages, broken Incus state, config drift).
