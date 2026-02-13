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

## ADR-011: All content in English, French translations maintained

**Decision**: All code, comments, documentation, prompts in English.
French translations (`*_FR.md`) are maintained for all documentation files,
always in sync with their English counterparts. This includes `README_FR.md`
and all files in `docs/` (e.g., `quickstart_FR.md`, `SPEC_FR.md`,
`ARCHITECTURE_FR.md`, etc.). Each French file includes a header note
indicating that the English version is authoritative in case of divergence.

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

---

## ADR-017: Instance type abstraction — LXC now, VM-ready later

**Context:** All current instances are LXC containers. However, some use
cases require KVM VMs: stronger isolation (GPU with vfio-pci, untrusted
workloads), full kernel customization, or running non-Linux guests.

**Decision:** The `instance_type` variable (from infra.yml `type: lxc|vm`)
is present in host_vars but the `incus_instances` role currently treats all
instances as LXC containers. The codebase MUST be kept VM-aware from now on:

1. **infra.yml already supports `type: lxc|vm`** — no schema change needed
2. **incus_instances role:** the `incus launch` command must pass `--vm`
   when `instance_type == 'vm'`. This is the ONLY change needed for basic
   VM creation. All other reconciliation logic (device override, IP config,
   wait for running) works identically.
3. **Profiles:** VM instances may need different default profiles (e.g.,
   `agent.nic.enp5s0.mode` for network config inside VMs). This is a
   Phase 8+ concern.
4. **GPU in VMs:** Requires vfio-pci passthrough + IOMMU groups, which is
   significantly more complex than LXC GPU passthrough. Deferred to Phase 9+.
5. **Connection plugin:** VMs use `incus exec` just like LXC containers,
   so the `community.general.incus` connection plugin works for both.

**Consequence:** All new code in incus_instances MUST branch on
`instance_type` where behavior differs between LXC and VM. Today the
only difference is the `--vm` flag on `incus launch`. Future phases will
add VM-specific profiles, devices, and boot configuration.

**What NOT to do now:** Do not add VM-specific roles, profiles, or devices
until there is a concrete use case. Keep the abstraction minimal.

---

## ADR-018: GPU access policy — exclusive by default, shared optional

**Context:** GPU passthrough in LXC containers exposes the host kernel's
GPU driver to the container, expanding the attack surface. Binding the
same GPU to multiple containers simultaneously introduces risks:
- No VRAM isolation on consumer GPUs (no SR-IOV)
- Shared driver state could cause crashes
- Any container with GPU access can potentially read GPU memory

**Decision:**
1. **Default policy: `gpu_policy: exclusive`** — the PSOT generator
   validates that at most ONE instance across all domains has a GPU device.
   If multiple instances declare `gpu: true`, the generator errors with a
   clear message.
2. **Optional override: `gpu_policy: shared`** — set in `infra.yml`
   `global.gpu_policy: shared` to allow multiple instances to share the
   GPU. The generator emits a warning but does not error.
3. **GPU in VMs:** When `instance_type: vm` has GPU access, it uses
   vfio-pci passthrough which provides hardware-level isolation. The
   exclusive policy still applies by default (only one VM can own a
   PCI device), but `shared` mode is irrelevant for VMs (you can't
   share a PCI device between VMs without SR-IOV).

**Validation rules for the PSOT generator (scripts/generate.py):**
- Count instances with `gpu: true` or with a profile containing a `gpu` device
- If count > 1 and `global.gpu_policy` != `shared` → error
- If count > 1 and `global.gpu_policy` == `shared` → warning
- If a VM instance has `gpu: true` → validate host has IOMMU enabled (Phase 9+)

**Consequence:** Safe by default. Users who know what they're doing can
opt into shared GPU access explicitly.

---

## ADR-019: admin-ansible proxy socket resilience at boot

**Context:** The `admin-ansible` container has an Incus proxy device that
maps the host's Incus socket (`/var/lib/incus/unix.socket`) to
`/var/run/incus/unix.socket` inside the container. When the container is
restarted, the `/var/run/` directory is ephemeral (tmpfs) and the
`/var/run/incus/` subdirectory does not exist yet when the proxy device
tries to bind, causing the container to fail to start with:

```
Error: Failed to listen on /var/run/incus/unix.socket:
listen unix /var/run/incus/unix.socket: bind: no such file or directory
```

The workaround today is manual: remove the proxy device, start the
container, create the directory, re-add the proxy device. This must be
automated.

**Decision:** Add a systemd oneshot service in the `admin-ansible`
container that creates `/var/run/incus/` before the proxy device starts.
This service runs early in boot (`Before=network.target`,
`After=local-fs.target`).

Implementation in the `base_admin` role (or provisioning for admin-ansible):

```ini
# /etc/systemd/system/incus-socket-dir.service
[Unit]
Description=Create Incus socket directory for proxy device
DefaultDependencies=no
Before=network.target
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/mkdir -p /var/run/incus
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

**Why not `raw.lxc`:** The `lxc.hook.pre-start` hook runs on the HOST,
not inside the container. While it could create the directory in the
container's rootfs, it requires knowing the rootfs path and runs as root
on the host — which conflicts with our principle that Ansible does not
modify the host (ADR-004). A systemd service inside the container is
self-contained and portable.

**Scope:** This fix applies ONLY to `admin-ansible`. Other containers do
not have the proxy device and are not affected.

**Consequence:** `admin-ansible` survives restarts without manual
intervention. The systemd service is idempotent (mkdir -p).
