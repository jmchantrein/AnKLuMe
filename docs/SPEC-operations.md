# SPEC-operations.md — AnKLuMe Operational Reference

This file contains implementation and operational details extracted from
SPEC.md. For the core specification (vision, concepts, PSOT model,
infra.yml format), see [SPEC.md](SPEC.md).

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
