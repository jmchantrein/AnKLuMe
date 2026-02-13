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

---

## ADR-020: Privileged LXC forbidden at first nesting level

**Context**: LXC containers with `security.privileged: true` share the
host kernel with elevated capabilities. This expands the attack surface
significantly. AnKLuMe must distinguish between its primary purpose
(infrastructure compartmentalization) and development tooling
(Incus-in-Incus testing).

**Decision**: At the first nesting level (directly under the physical
host or under an unprivileged LXC), `security.privileged=true` is
forbidden for LXC containers. Only VMs provide sufficient hardware
isolation (separate kernel, IOMMU) for privileged workloads.

The enforcement uses a `vm_nested` flag with automatic detection and
propagation:

1. At bootstrap, detect virtualization type via `systemd-detect-virt`
2. Compute: `vm_nested = parent_vm_nested OR (local_type == kvm)`
3. Store in `/etc/anklume/vm_nested` (created by parent, not child)
4. Propagate to ALL child instances unconditionally
5. Generator validates: if `vm_nested == false` and machine has
   `security.privileged: true` on `type: lxc` → error

Additional context files in `/etc/anklume/`:
- `absolute_level` = parent + 1 (depth from real host)
- `relative_level` = 0 if VM (reset), else parent + 1
- `yolo` = bypass flag (warnings instead of errors)

**Consequence**: Safe by default. Privileged containers only allowed
inside a VM isolation boundary. The `--YOLO` flag bypasses this for
lab/training contexts. The nesting context files enable future
decision-making based on position in the hierarchy.

---

## ADR-021: Network policies — declarative cross-domain communication

**Context**: Phase 8 drops all inter-domain traffic. There is no
mechanism to selectively allow specific services to be accessed
cross-domain. Use cases like AI services accessible from multiple
domains require a policy system.

**Decision**: Add `network_policies:` section to infra.yml. Syntax is
a flat list of allow rules (inspired by Consul Intentions):

```yaml
network_policies:
  - description: "..."
    from: <domain|machine|host>
    to: <domain|machine>
    ports: [port1, port2] | all
    protocol: tcp | udp
    bidirectional: true | false
```

Default: all inter-domain traffic is DROP. Each rule adds an `accept`
before the `drop`. The generator validates that `from`/`to` references
known domains, machines, or the `host` keyword.

**Consequence**: Enables cross-domain service access while maintaining
isolation by default. Rules are generated into both host nftables
(Phase 8) and firewall VM nftables (Phase 11). Auditable: each rule's
description appears as an nftables comment.

---

## ADR-022: nftables priority -1 — coexist with Incus chains

**Context**: Incus manages its own nftables chains at priority 0 for NAT
and per-bridge filtering. AnKLuMe needs isolation rules that run before
Incus chains without disabling or conflicting with them.

**Decision**: Use `priority -1` in the AnKLuMe `inet anklume` table's
forward chain. AnKLuMe and Incus nftables coexist peacefully in separate
tables. Non-matching traffic falls through to Incus chains with
`policy accept`.

**Consequence**: No interference with Incus NAT, DHCP, or per-bridge
rules. AnKLuMe isolation is evaluated first.

---

## ADR-023: Two-step nftables deployment (admin → host)

**Context**: AnKLuMe runs inside the admin container (ADR-004) but
nftables rules must be applied on the host kernel.

**Decision**: Split into two steps:
1. `make nftables` — runs inside admin container, generates rules
2. `make nftables-deploy` — runs on the host, pulls rules from admin,
   validates, and applies

**Consequence**: The operator reviews rules before deploying. The admin
container never needs host-level privileges. Documented exception to
ADR-004.

---

## ADR-024: Firewall VM — two-role architecture

**Context**: The firewall VM needs infrastructure setup (multi-NIC
profile on the host) and provisioning (nftables inside the VM). These
run in different playbook phases with different connection types.

**Decision**: Split into two roles:
- `incus_firewall_vm`: Infrastructure role (connection: local). Creates
  multi-NIC profile.
- `firewall_router`: Provisioning role (connection: incus). Configures
  IP forwarding + nftables inside the VM.

**Consequence**: Matches the two-phase architecture (ADR-006).

---

## ADR-025: Defense in depth — host + firewall VM modes coexist

**Context**: Phase 8 provides host-level nftables isolation. Phase 11
adds a firewall VM. Should they be mutually exclusive?

**Decision**: Both modes coexist for layered security. Host nftables
blocks direct bridge-to-bridge forwarding. The firewall VM routes
permitted traffic and logs decisions. Even if the firewall VM is
compromised, host rules still prevent direct inter-bridge traffic.

**Consequence**: Operator can choose host-only, VM-only, or both.

---

## ADR-026: Admin bridge — no exception in nftables rules

**Context**: The admin container communicates with all instances via
the Incus socket (ADR-004), not the network. Ansible uses
`community.general.incus` which calls `incus exec` over the socket.

**Decision**: The admin bridge has no special accept rule in nftables.
All domains (including admin) are treated equally for network isolation.
`ping` from admin to other domains fails (expected).

**Consequence**: Stronger isolation. Admin management traffic flows
through the Incus socket, which is the correct and intended path.

---

## ADR-027: Sandbox-first Agent Teams architecture

**Context**: Agent Teams with `bypassPermissions` give Claude Code
full system access. This is dangerous on production but safe inside
an Incus-in-Incus sandbox.

**Decision**: Agent Teams ONLY run inside the Phase 12 sandbox.
Defense in depth: OS-level isolation (Incus) + application-level
permissions (Claude Code) + workflow-level gates (PR merge) + audit
logging (PreToolUse hook).

**Consequence**: Full autonomy inside sandbox, human approval at the
production boundary (PR merge).

---

## ADR-028: Nesting context files in /etc/anklume/

**Context**: Each AnKLuMe level needs to know its position in the
nesting hierarchy for decision-making.

**Decision**: Store one file per context value in `/etc/anklume/`:
- `absolute_level` — depth from the real physical host
- `relative_level` — depth from the nearest VM boundary (resets at VMs)
- `vm_nested` — whether a VM exists in the parent chain
- `yolo` — whether YOLO mode is active

Files created by the **parent** at instance creation time. Propagation:
`absolute_level = parent + 1`, `relative_level = 0 if VM else parent + 1`,
`vm_nested = parent_vm_nested OR (type == kvm)`.

**Consequence**: Trivially readable from shell, Ansible, or Python.
No parsing dependency. Enables ADR-020 enforcement and future
nesting-aware decisions.

---

## ADR-029: dev_test_runner in VM (not LXC)

**Context**: Testing AnKLuMe inside AnKLuMe required privileged LXC
containers, conflicting with ADR-020. Triple nesting caused AppArmor
issues on Debian 13.

**Decision**: The test runner (`anklume-test`) is a VM. Inside the VM,
AnKLuMe bootstraps as on a fresh host. Tests run at level 1 and 2
within the VM's kernel — no AppArmor interference from the host.

**Consequence**: Slower boot (~30s) but hardware-isolated. Triple
nesting eliminated. Test environment matches production exactly.

---

## ADR-030: infra/ directory support alongside infra.yml

**Context**: A single `infra.yml` becomes unwieldy for large
deployments (20+ domains).

**Decision**: The generator accepts both formats with auto-detection:
- `infra.yml` → single-file mode (backward compatible)
- `infra/` → merges `base.yml` + `domains/*.yml` + `policies.yml`

**Consequence**: Scales to large deployments. Git-friendly. 100%
backward compatible.

---

## ADR-031: User data protection during upgrades

**Context**: AnKLuMe is distributed as a git repository. Framework
upgrades must not destroy user configuration, custom roles, or
generated file customizations.

**Decision**: Multi-layer protection:
1. Explicit file classification: framework (overwritten), user config
   (never touched), generated (managed sections), runtime (never touched)
2. `roles_custom/` directory (gitignored) with priority in `roles_path`
3. `make upgrade` with conflict detection and `.bak` creation
4. Version marker for compatibility checking

**Consequence**: Users never lose data during upgrades. Custom roles
and configurations survive framework updates.

---

## ADR-032: Exclusive AI-tools network access with VRAM flush

**Context**: Multiple domains could access ai-tools simultaneously,
creating a risk of cross-domain data leakage through GPU VRAM. Consumer
GPUs lack SR-IOV, so VRAM is shared across all processes using the GPU.

**Decision**: Add `ai_access_policy: exclusive` mode to infra.yml.
When enabled, only one domain at a time can access ai-tools. Switching
domains via `scripts/ai-switch.sh` atomically:
1. Stops GPU services (ollama, speaches)
2. Flushes VRAM (kills GPU processes, attempts nvidia-smi --gpu-reset)
3. Updates nftables rules (replaces source bridge in accept rule)
4. Restarts GPU services
5. Records state in `/opt/anklume/ai-access-current`

The PSOT generator validates:
- `ai_access_default` must reference a known domain (not ai-tools)
- An `ai-tools` domain must exist when exclusive mode is active
- At most one network_policy can target ai-tools as destination
- Auto-creates a network_policy from `ai_access_default` to ai-tools
  if none exists

The nftables role supports an `incus_nftables_ai_override` variable
for dynamic rule replacement without modifying infra.yml.

**Consequence**: VRAM isolation enforced at the operational level.
Cross-domain data leakage through GPU memory prevented by flushing
between domain switches.

---

## ADR-033: Behavior matrix for exhaustive testing

**Context**: Manual test coverage tracking is error-prone. The project
needs a systematic way to map capabilities to expected behaviors and
track which cells are covered by tests.

**Decision**: Maintain a YAML behavior matrix (`tests/behavior_matrix.yml`)
with three depth levels per capability:
- Depth 1: single-feature tests (e.g., "create domain with valid subnet_id")
- Depth 2: pairwise interactions (e.g., "domain ephemeral + machine override")
- Depth 3: three-way interactions (e.g., "domain + VM + GPU + firewall_mode")

Each cell has a unique ID (e.g., `DL-001`). Tests reference their matrix
cell via `# Matrix: DL-001` comments. `scripts/matrix-coverage.py` scans
test files and reports coverage per capability and depth level.

Complement the matrix with Hypothesis property-based tests
(`tests/test_properties.py`) for generator invariants: idempotency,
no duplicate IPs, managed markers present, orphan detection consistency.

**Consequence**: Coverage is measurable and auditable. LLM test
generators can target uncovered cells. Property-based tests discover
edge cases missed by manual tests.

---

## ADR-034: Experience library for self-improvement

**Context**: Fix patterns are lost after each debugging session.
The same errors are re-diagnosed from scratch each time they occur.

**Decision**: Maintain a persistent experience library (`experiences/`)
committed to git, with three categories:
- `fixes/` — error patterns and their solutions (extracted from git history)
- `patterns/` — reusable implementation patterns (reconciliation, role structure)
- `decisions/` — promoted architectural decisions with rationale

`scripts/mine-experiences.py` extracts fix patterns from git history
by scanning fix/lint/resolve commits and extracting file changes and
error patterns.

The AI test loop (`ai-test-loop.sh`) searches the experience library
before calling an LLM backend. If a matching fix pattern is found, it
is applied directly (faster, no LLM cost). New successful fixes are
added to the library via the `--learn` flag.

`scripts/ai-improve.sh` implements a spec-driven improvement loop:
validate → build context → LLM analysis → sandbox test → commit/discard.

**Consequence**: Institutional knowledge persists across sessions.
Repeated errors are fixed instantly from the library. The improvement
loop enables continuous spec-implementation convergence.

---

## ADR-035: Shared image cache across nesting levels

**Context**: Each Incus daemon (host and nested) downloads OS images
independently from the internet. The dev_test_runner VM (Phase 12)
re-downloads all images, wasting bandwidth and time.

**Decision**: Pre-export images from the host Incus to a shared
directory, mount it read-only into nested VMs, and import locally.

Flow:
1. Host: `incus image export <alias> /opt/anklume/images/` (via
   `incus_images` role with `incus_images_export_for_nesting: true`)
2. VM: disk device mounts `/opt/anklume/images` → `/mnt/host-images`
   (read-only)
3. Nested Incus: `incus image import /mnt/host-images/<file>.tar.gz`
   (via `dev_test_runner` role)

Why not mount host filesystem directly: breaks isolation.
Why not use host as Incus remote: requires network + TLS + auth setup.

**Consequence**: No internet access needed for nested Incus image
downloads. Faster sandbox bootstrap. Read-only mount preserves
isolation.
