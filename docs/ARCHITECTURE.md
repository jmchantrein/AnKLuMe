# ARCHITECTURE.md — Architecture Decision Records

Each decision is numbered and final unless explicitly superseded.
Claude Code must respect these decisions without questioning them.

---

## ADR-001: Ansible inventory reflects the real infrastructure

**Context**: An early iteration used a custom `domains/` folder with
`include_vars` + `find`. This was a reinvention of `group_vars`.

**Decision**: The Ansible inventory mirrors the real infrastructure.
Each domain = an Ansible group. Each container/VM = a host in its group.
Variables in `group_vars/<domain>.yml` and `host_vars/<machine>.yml`.

**Consequence**: Native Ansible mechanisms only. No custom dynamic loading.

---

## ADR-002: PSOT model — infra.yml is the Primary Source of Truth

**Context**: Manually editing inventory + group_vars + host_vars is tedious.

**Decision**: `infra.yml` is the Primary Source of Truth (PSOT). The generator
produces the Ansible file tree with managed sections. Generated files are the
Secondary Source of Truth — freely editable outside managed sections. Both
must be committed to git.

**Consequence**: To add a machine, edit `infra.yml` + `make sync`. To
customize further, edit generated files outside managed sections.

---

## ADR-003: Ansible tags for targeting, not extra-vars

**Context**: An early iteration used `-e target_domains=[...]`.

**Decision**: Use standard Ansible mechanisms: `--tags` for resource types,
`--limit` for domains. Combinable.

**Consequence**: No custom filtering logic in playbooks.

---

## ADR-004: No hypervisor in the inventory

**Context**: The host runs Incus but is not managed by Ansible.

**Decision**: Ansible runs inside an admin container with the Incus socket
mounted. Phase 1 targets `localhost`. Phase 2 targets instances via the
`community.general.incus` connection plugin.

**Consequence**: The host never appears in the inventory.

---

## ADR-005: Incus via CLI, no native Ansible modules

**Context**: `community.general.lxd_*` modules are broken with Incus.
No stable `incus_*` module exists.

**Decision**: Use `ansible.builtin.command` + `incus` CLI + `--format json`
+ manual idempotency checks.

**Consequence**: Each infra role implements its own idempotency. More verbose
but reliable.

---

## ADR-006: Two distinct execution phases

**Decision**:
- Phase 1 (Infra): `hosts: localhost`, `connection: local`, tag `infra`
- Phase 2 (Provisioning): `hosts: all:!localhost`,
  `connection: community.general.incus`, tag `provision`

**Consequence**: `--tags infra` and `--tags provision` work independently.

---

## ADR-007: NVIDIA GPU = LXC only, no VM

**Decision**: GPU instances are LXC containers with a GPU profile. LLM models
stored in separate storage volumes. No GPU for KVM VMs.

---

## ADR-008: Globally unique machine names

**Decision**: Machine names are globally unique, not just within their domain.
The generator validates this constraint.

---

## ADR-009: Spec-driven, test-driven development

**Decision**: The development workflow is:
1. Write/update the spec
2. Write tests (Molecule for roles, pytest for generator)
3. Implement until tests pass
4. Validate (`make lint`)
5. Review (reviewer agent)
6. Commit only when everything passes

**Consequence**: No code without a corresponding spec and test.

---

## ADR-010: Python generator with no external dependencies

**Decision**: `scripts/generate.py` uses only PyYAML and the standard library.
No framework, no external templating engine.

---

## ADR-011: All content in English, French translation maintained

**Decision**: All code, comments, documentation, prompts in English.
`README_FR.md` maintained as French translation of `README.md`, always in sync.

---

## ADR-012: Every file type has a dedicated validator

**Context**: Code quality must be enforced consistently across all file types.

**Decision**: Each file type has a mandatory validator:
- `*.yml` / `*.yaml` → `yamllint` + `ansible-lint` (for Ansible files)
- `*.sh` → `shellcheck`
- `*.py` → `ruff`
- `*.md` → `markdownlint` (optional but recommended)

`make lint` chains all validators. CI must pass all of them. No file escapes
validation.

**Consequence**: Contributors must have all validators installed. `make init`
installs them.

---

## ADR-013: Snapshot MVP via shell script, not Ansible role

**Context**: Snapshot and restore are imperative, one-shot operations ("take a
snapshot now", "restore to this snapshot now"). They do not follow the
declarative reconciliation pattern (read/compare/create/update/orphans) that
all infra roles use. An Ansible playbook would be a glorified for-loop around
`incus snapshot` with unnecessary overhead.

**Decision**: The snapshot MVP is `scripts/snap.sh`, a standalone Bash script
wrapping `incus snapshot` CLI commands. It queries Incus directly
(`incus list --all-projects`) to resolve instance-to-project mappings.
Supports `self` keyword to auto-detect the current instance via `hostname`.

**Consequence**: Makefile snapshot targets invoke `scripts/snap.sh`. Validated
by `shellcheck`. A declarative Ansible role may supersede this in a future
phase if pre/post hooks or scheduling are needed.

---

## ADR-014: Networks live in the default Incus project

**Context**: Incus projects can control whether networks are project-specific
or shared. Our projects use `features.networks=false`, meaning networks are
managed globally in the default project.

**Decision**: All domain bridges are created in the default project. Each
project's default profile references the appropriate bridge by name.

**Justification**:
- Simpler management: one place for all networks
- nftables isolation happens at the host level, not at the Incus project level
- Consistent with Incus upstream recommendations for most deployments
- Reference: https://linuxcontainers.org/incus/docs/main/explanation/projects/

**Consequences**: Network-related Ansible tasks do not use the `--project`
flag. Profile tasks DO need `--project` to configure each project's profile.

---

## ADR-015: Playbook uses hosts:all with connection:local

**Context**: All Incus commands must run on the Ansible controller
(`admin-ansible`) which has the Incus socket mounted. Other hosts in the
inventory do not have access to Incus and do not exist yet when the
infrastructure roles run.

**Decision**: The `site.yml` playbook uses `hosts: all` with
`connection: local`. Each host provides its PSOT-generated variables
(domain, network config, instance config). All commands execute locally
on the controller via the Incus socket. No `run_once` is used — each
host runs the roles independently.

**Why not `run_once`**: With `run_once: true`, only one host per play
executes each task. Since each host has variables for its own domain,
this means only one domain's resources get created. Removing `run_once`
allows every host to create its domain's resources, with idempotence
guaranteed by the reconciliation pattern (check if exists → skip).

**Why not `delegate_to`**: Since ALL tasks run locally (not just some),
`connection: local` is cleaner than `delegate_to: localhost` on every
task. The Ansible documentation recommends `connection: local` when
the entire play targets a local API.

**Concurrency**: With `forks > 1`, two hosts from the same domain could
try to create the same project simultaneously. The reconciliation pattern
handles this gracefully (second host sees the resource already exists).
For strict sequential execution, `serial: 1` can be enabled.

---

## ADR-016: Standard Ansible directory layout with playbook at root

**Context**: Ansible's `host_group_vars` plugin loads variable files from
paths relative to the playbook file or the inventory source. With the
playbook in `playbooks/site.yml`, Ansible looked for `playbooks/group_vars/`
instead of the actual `group_vars/` at the project root, causing all
PSOT-generated variables to be undefined.

**Decision**: Adopt the standard Ansible directory layout with `site.yml`
at the project root, alongside `group_vars/`, `host_vars/`, `inventory/`,
and `roles/`.

**Reference**: https://docs.ansible.com/ansible/2.9/user_guide/playbooks_best_practices.html#directory-layout

**Consequence**: Variable resolution works correctly out of the box.
The layout matches what Ansible users expect from standard projects.
