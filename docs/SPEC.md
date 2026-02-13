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

domains:
  <domain-name>:
    description: "What this domain is for"
    subnet_id: <0-254>               # Must be unique across all domains
    ephemeral: false                  # Optional (default: false). See below.
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

### Validation constraints

- Domain names: unique, alphanumeric + hyphen
- Machine names: globally unique (not just within their domain)
- `subnet_id`: unique per domain, range 0-254
- IPs: globally unique, must be within the correct subnet
- Profiles referenced by a machine must exist in its domain
- `ephemeral`: must be a boolean if present (at both domain and machine level)

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
| `incus_storage` | Create dedicated storage volumes | `storage`, `infra` |
| `incus_instances` | Create/manage LXC + VM instances | `instances`, `infra` |

### Phase 2: Provisioning (connection: community.general.incus)

| Role | Responsibility | Tags |
|------|---------------|------|
| `base_system` | Base packages, locale, timezone, user | `provision`, `base` |
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

## 12. Out of scope

Managed manually or by host bootstrap scripts:
- NVIDIA driver installation/configuration
- Kernel / mkinitcpio configuration
- Incus daemon installation
- Host nftables configuration (inter-bridge isolation, NAT)
- Sway/Wayland configuration for GUI forwarding

The AnKLuMe framework DOES NOT modify the host. It drives Incus via the socket.
