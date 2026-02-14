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

The admin container:
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
- `ai_access_policy`: must be `exclusive` or `open`
- When `ai_access_policy: exclusive`:
  - `ai_access_default` is required and must reference a known domain
  - `ai_access_default` cannot be `ai-tools` itself
  - An `ai-tools` domain must exist
  - At most one `network_policy` can target `ai-tools` as destination

### Auto-creation of sys-firewall (firewall_mode: vm)

When `global.firewall_mode` is set to `vm`, the generator automatically
creates a `sys-firewall` machine in the admin domain if one is not already
declared. This enrichment step (`enrich_infra()`) runs after validation but
before file generation. The auto-created machine uses:
- type: `vm`, ip: `<base_subnet>.<admin_subnet_id>.253`
- config: `limits.cpu: "2"`, `limits.memory: "2GiB"`
- roles: `[base_system, firewall_router]`
- ephemeral: `false`

If the user declares `sys-firewall` explicitly (in any domain), their
definition takes precedence and no auto-creation occurs. If `firewall_mode`
is `vm` but no `admin` domain exists, the generator exits with an error.

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
    to: ai-ollama                # Specific machine
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

### infra.yml as a directory

For large deployments, `infra.yml` can be replaced by an `infra/`
directory:

```
infra/
├── base.yml                 # project_name + global settings
├── domains/
│   ├── admin.yml            # One file per domain
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
Works from any instance with access to the Incus socket (typically the admin
container). Fails with a clear error if the hostname is not found.

### Self-restore safety

Restoring the instance you are running inside kills your session. The script
warns and asks for confirmation (`Type 'yes' to confirm`). Use `--force` to
skip the prompt (for scripted use).

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
