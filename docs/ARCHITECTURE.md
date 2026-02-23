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

## ADR-004: Minimize host modifications

**Context**: The host runs Incus but should remain as untouched as
possible. The original rule ("never modify the host") proved too strict
in practice: nftables rules must be applied on the host kernel, and
some software prerequisites must be installed directly.

**Decision**: The host is not in the Ansible inventory. Ansible runs
inside `anklume-instance` with the Incus socket mounted. Modifications
to the host should be avoided as much as possible. When necessary
(nftables, software prerequisites), they are made directly if doing so
is more KISS/DRY and does not compromise overall security.

**Consequence**: The host is not managed by Ansible but may receive
targeted manual or scripted changes when isolation constraints require
it (e.g., `make nftables-deploy`).

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

## ADR-008: Globally unique machine names

**Decision**: Machine names are globally unique, not just within their domain.
The generator validates this constraint.

---

## ADR-009: Documentation-driven, behavior-driven development

**Context**: Code written before specs and tests tends to drift from
intent. Tests written after code describe what the code does, not what
it should do. A behavior matrix (formerly ADR-033) and BDD-style tests
provide both coverage tracking and living documentation.

**Decision**: The development workflow follows a strict order:
1. Write/update documentation and spec
2. Write behavior tests (Given/When/Then style) describing expected
   behavior from the spec — not from existing code
3. Implement until tests pass (Molecule for roles, pytest for generator)
4. Validate (`make lint`)
5. Review (reviewer agent)
6. Commit only when everything passes

Behavior tests serve as living documentation. They are organized in a
behavior matrix (`tests/behavior_matrix.yml`) with three depth levels
per capability. Each cell has a unique ID (e.g., `DL-001`). Tests
reference their matrix cell via `# Matrix: DL-001` comments.

Property-based tests (Hypothesis, `tests/test_properties.py`) complement
behavior tests for generator invariants: idempotency, no duplicate IPs,
managed markers present, orphan detection consistency.

When catching up on existing code, tests must be written from the specs,
not reverse-engineered from the implementation.

**Consequence**: No code without a corresponding spec and test. Coverage
is measurable and auditable via the behavior matrix.

---

## ADR-010: Python generator — prefer standard library, allow quality dependencies

**Decision**: `scripts/generate.py` uses PyYAML and the Python standard
library as its foundation. If a well-maintained open-source/libre library
avoids reinventing the wheel, it may be added. No heavy frameworks or
external templating engines. The bar for adding a dependency: it must be
actively maintained, solve a real problem better than stdlib, and not
introduce transitive dependency bloat.

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

**Decision**: Every file type in the project has a mandatory validator.
`make lint` chains all validators. CI must pass all of them. No file
escapes validation. Zero violations tolerated.

See SPEC-operations.md Section 9 for the full validator table.

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
(`anklume-instance`) which has the Incus socket mounted. Other hosts in the
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

**Decision:** The codebase MUST be kept VM-aware from now on. The
`instance_type` variable (from infra.yml `type: lxc|vm`) drives
role behavior where LXC and VM differ. Do not add VM-specific roles,
profiles, or devices until there is a concrete use case — keep the
abstraction minimal.

See SPEC-operations.md Section 7 (`incus_instances` role) for
implementation details (--vm flag, profile differences, GPU passthrough).

**Consequence:** All new code in incus_instances MUST branch on
`instance_type` where behavior differs between LXC and VM.

---

## ADR-018: GPU access policy — exclusive by default, shared optional

**Context:** GPU passthrough in LXC containers exposes the host kernel's
GPU driver to the container, expanding the attack surface. Binding the
same GPU to multiple containers simultaneously introduces risks:
- No VRAM isolation on consumer GPUs (no SR-IOV)
- Shared driver state could cause crashes
- Any container with GPU access can potentially read GPU memory

**Decision:**
1. **Default policy: `gpu_policy: exclusive`** — at most one GPU instance.
2. **Optional override: `gpu_policy: shared`** — allows multiple instances
   to share the GPU with a warning.
3. **GPU in VMs:** vfio-pci passthrough provides hardware-level isolation.
   Exclusive policy still applies (one VM per PCI device without SR-IOV).

See SPEC.md Validation constraints for generator validation rules.

**Consequence:** Safe by default. Users who know what they're doing can
opt into shared GPU access explicitly.

---

## ADR-019: anklume-instance proxy socket resilience at boot

**Context:** The `anklume-instance` proxy device maps the host's Incus
socket to `/var/run/incus/unix.socket` inside the container. On restart,
`/var/run/` (tmpfs) is empty and the proxy bind fails.

**Decision:** A systemd oneshot service creates `/var/run/incus/` early
in the boot sequence, before the proxy device starts.

**Why not `raw.lxc`:** `lxc.hook.pre-start` runs on the HOST, not inside
the container — conflicts with ADR-004. A systemd service inside the
container is self-contained and portable.

See SPEC-operations.md Section 12 for the systemd unit file.

**Consequence:** `anklume-instance` survives restarts without manual
intervention. Applies only to `anklume-instance`.

---

## ADR-020: Privileged LXC forbidden at first nesting level + nesting context

**Context**: LXC containers with `security.privileged: true` share the
host kernel with elevated capabilities. Each nesting level also needs
to know its position in the hierarchy for decision-making.

**Decision**: At the first nesting level (directly under the physical
host or under an unprivileged LXC), `security.privileged=true` is
forbidden for LXC containers. Only VMs provide sufficient hardware
isolation (separate kernel, IOMMU) for privileged workloads.

Nesting context is stored as individual files in `/etc/anklume/`
(created by the **parent**, not the child). Individual files rather
than a structured config because they are trivially readable from
shell, Ansible, or Python with no parsing dependency.

The `--YOLO` flag bypasses security restrictions (warnings instead
of errors) for lab/training contexts.

See SPEC.md "Security policy" section for the full file list,
propagation formulas, and validation rules.

**Consequence**: Safe by default. Privileged containers only allowed
inside a VM isolation boundary. Nesting context enables future
hierarchy-aware decisions. (Absorbs former ADR-028.)

---

## ADR-021: Network policies — declarative cross-domain communication

**Context**: Phase 8 drops all inter-domain traffic. There is no
mechanism to selectively allow specific services to be accessed
cross-domain (e.g., AI services from multiple domains).

**Decision**: Add `network_policies:` section to infra.yml — a flat
list of allow rules inspired by Consul Intentions. Default: all
inter-domain traffic is DROP. Each rule adds an `accept` before
the `drop`.

See SPEC.md "Network policies" for the full syntax and examples.

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

## ADR-023: Two-step nftables deployment (anklume → host)

**Context**: AnKLuMe runs inside the anklume container (ADR-004) but
nftables rules must be applied on the host kernel.

**Decision**: Split into two steps:
1. `make nftables` — runs inside anklume container, generates rules
2. `make nftables-deploy` — runs on the host, pulls rules from anklume,
   validates, and applies

**Consequence**: The operator reviews rules before deploying. The anklume
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

## ADR-026: Anklume bridge — no exception in nftables rules

**Context**: The anklume container communicates with all instances via
the Incus socket (ADR-004), not the network. Ansible uses
`community.general.incus` which calls `incus exec` over the socket.

**Decision**: The anklume bridge has no special accept rule in nftables.
All domains (including anklume) are treated equally for network isolation.
`ping` from `anklume-instance` to other domains fails (expected).

**Consequence**: Stronger isolation. Admin management traffic flows
through the Incus socket (`incus exec`), which is the correct and
intended path. `anklume-instance` does not need network access to
manage other instances.

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

**Decision**: The generator accepts both formats with auto-detection.
See SPEC.md "infra.yml as a directory" for the directory layout.

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
domains atomically flushes VRAM and updates nftables rules.

See SPEC.md Validation constraints for generator validation rules.
See docs/ai-switch.md for the operational switching procedure.

**Consequence**: VRAM isolation enforced at the operational level.
Cross-domain data leakage through GPU memory prevented by flushing
between domain switches.

---

## ADR-035: Shared image cache across nesting levels

**Context**: Each Incus daemon (host and nested) downloads OS images
independently from the internet. The dev_test_runner VM (Phase 12)
re-downloads all images, wasting bandwidth and time.

**Decision**: Pre-export images from the host, mount read-only into
nested VMs, import locally.

Why not mount host filesystem directly: breaks isolation.
Why not use host as Incus remote: requires network + TLS + auth setup.

See SPEC-operations.md Section 15 for the full flow.

**Consequence**: No internet access needed for nested Incus image
downloads. Faster sandbox bootstrap. Read-only mount preserves
isolation.

---

## ADR-036: Agent operational knowledge must be framework-reproducible

**Context**: OpenClaw agents run inside Incus containers. If the
container is destroyed, all operational knowledge is lost unless it
comes from the framework.

**Decision**: The AnKLuMe git repository is the **single source of
truth** for agent operational knowledge. All agent files are Jinja2
templates deployed with `force: true` on every `make apply`. Agents
MUST NOT modify their operational files directly — they follow the
standard development workflow (edit template, test, PR, merge, apply).

Exception: `SOUL.md` (personality) is agent-owned and `.gitignored`.

See SPEC-operations.md for the template file list and deploy rules.

**Consequence**: Any agent can be fully reproduced from the framework
alone (minus personality). Destroying and rebuilding a container
restores full operational capability.

---

## ADR-038: Trust-level-aware IP addressing convention

**Context**: The original addressing scheme (`10.100.<subnet_id>.0/24`
with manually assigned sequential subnet_ids) provides no semantic
information. An administrator cannot determine a domain's security
posture from its IP address alone. Manual allocation is error-prone
and does not follow network segmentation best practices.

**Decision**: Encode trust zones in the second IP octet:
`10.<zone_base + zone_offset>.<domain_seq>.<host>/24`. The
`base_subnet` field is superseded by `addressing`.

See SPEC.md "Addressing convention" for the full zone table, IP
reservations, configuration format, and validation rules.
See docs/addressing-convention.md for the complete documentation.

**Why not `11.x.x.x`**: `11.0.0.0/8` is public address space (US DoD).
DNS leaks, packet leaks — disqualifies the framework.

**Why zone_base=100**: avoids `10.0-60.x.x` used by enterprise VPNs,
home routers, and container orchestrators. `10.1xx` is a visual marker
for AnKLuMe traffic.

**Consequence**: IP addresses are human-readable. From `10.140.0.5`,
an admin immediately knows: zone 140 = 100+40 = untrusted.
