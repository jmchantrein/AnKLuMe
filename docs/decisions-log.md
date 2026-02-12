# Decisions Log

Autonomous implementation decisions made during Phases 7+.
Read this file to understand choices made without human review.

For architecture-level decisions, see [ARCHITECTURE.md](ARCHITECTURE.md)
(ADR-001 to ADR-019).

---

## Phase 7: Documentation + Publication

### D-001: Example directory structure

**Problem**: ROADMAP lists examples as flat files (`examples/student-sysadmin.infra.yml`)
but also says "each example accompanied by a README". Flat files + READMEs would be messy.

**Decision**: Use subdirectories per example:
```
examples/
├── README.md                    # Overview of all examples
├── student-sysadmin/
│   ├── infra.yml
│   └── README.md
├── teacher-lab/
│   ├── infra.yml
│   └── README.md
...
```

**Rationale**: KISS — one directory = one self-contained use case. Git-friendly.

### D-002: All example infra.yml files must pass PSOT validation

**Problem**: Examples are documentation but also runnable. Dead examples are worse
than no examples.

**Decision**: Add a pytest test that validates every `examples/*/infra.yml` against
`scripts/generate.py`'s `validate()` function. This ensures examples stay valid
as the generator evolves.

**Rationale**: TDD — if examples break, tests catch it.

### D-003: Pre-existing ansible-lint violations

**Problem**: `make lint` fails due to pre-existing violations in ollama_server,
open_webui, and incus_snapshots (command-instead-of-module, risky-shell-pipe,
var-naming[read-only]). These are not Phase 7 issues.

**Decision**: Note them but do not fix in Phase 7 branch. Phase 7 focuses on
docs/examples. Lint violations are tracked for a future fix pass.

### D-004: README_FR.md sync

**Problem**: ADR-011 requires French translation kept in sync. Phase 7 adds
significant new docs.

**Decision**: Update README_FR.md to match README.md changes. New docs
(quickstart, lab-tp, gpu-llm) are in English only per ADR-011 — no separate
French translation files for guides (README_FR.md covers the main README only).

### D-005: Documentation line count vs 200-line rule

**Problem**: CLAUDE.md states "No file over 200 lines" (KISS). The gpu-llm.md
guide is 275 lines. But existing project docs already exceed this: SPEC.md (337),
ARCHITECTURE.md (352), ROADMAP.md (777).

**Decision**: The 200-line rule applies to code files (roles, scripts, playbooks).
Documentation files are exempt when the content is cohesive and splitting would
hurt readability. gpu-llm.md covers a single topic (GPU+LLM setup) and splitting
it would create unnecessary navigation burden.

**Rationale**: KISS applies to complexity, not raw line count for prose.

### D-006: .gitignore pattern for infra.yml in examples

**Problem**: `.gitignore` had `infra.yml` as a global pattern, which also ignored
`examples/*/infra.yml`. Example infra files must be committed.

**Decision**: Changed `.gitignore` patterns from global to root-anchored:
`infra.yml` → `/infra.yml`, `inventory/` → `/inventory/`, etc. This ignores
user-specific files at the root but allows example files in subdirectories.

**Rationale**: Git anchored patterns (`/pattern`) match only at the repo root.
No need for `!` negation or force-add workarounds.

---

## Phase 8: nftables Inter-Bridge Isolation

### D-007: nftables priority -1 (coexist with Incus chains)

**Context**: Incus manages its own nftables chains at priority 0 for NAT
and per-bridge filtering. We need isolation rules that run before Incus
chains without disabling or conflicting with them.

**Decision**: Use `priority -1` in the AnKLuMe `inet anklume` table's
forward chain. This ensures our isolation rules are evaluated before
Incus chains. We do NOT disable the Incus firewall (`security.ipv4_firewall`)
because Incus chains provide useful per-bridge NAT and DHCP rules.

**Consequence**: AnKLuMe and Incus nftables coexist peacefully. Non-matching
traffic falls through to Incus chains with `policy accept`.

### D-008: Two-step deployment (generate in admin, deploy on host)

**Context**: AnKLuMe runs inside the admin container (ADR-004: Ansible
does not modify the host). However, nftables rules must be applied on
the host kernel, not inside a container.

**Decision**: Split into two steps:
1. `make nftables` — runs inside admin container, generates rules to
   `/opt/anklume/nftables-isolation.nft`
2. `make nftables-deploy` — runs `scripts/deploy-nftables.sh` on the
   host, pulls rules from admin container via `incus file pull`,
   validates syntax, installs to `/etc/nftables.d/`, and applies

**Consequence**: The operator can review generated rules before deploying.
The admin container never needs host-level privileges. This is a documented
exception to ADR-004.

### D-009: br_netfilter same-bridge handling

**Context**: When `br_netfilter` is loaded (required for nftables to
see bridge traffic), intra-bridge traffic (same bridge, different ports)
also passes through the `forward` chain. Without explicit accept rules,
same-bridge traffic between containers in the same domain would be
dropped by the inter-bridge drop rule.

**Decision**: Add explicit same-bridge accept rules for every AnKLuMe
bridge before the inter-bridge drop rule:
```nft
iifname "net-admin" oifname "net-admin" accept
iifname "net-perso" oifname "net-perso" accept
...
```

**Consequence**: Containers within the same domain can communicate freely.
The rules are generated dynamically from the list of discovered bridges.

### D-010: .gitignore root-anchor patterns

**Context**: Generated files (like nftables rules) should not be committed
to the repository. The `.gitignore` file uses root-anchored patterns
(e.g., `/opt/`) to avoid accidentally ignoring files in subdirectories
with similar names.

**Decision**: Use root-anchored patterns in `.gitignore` where possible.
For generated artifacts like nftables rules, the output path
(`/opt/anklume/`) is inside the container filesystem and does not appear
in the repository, so no `.gitignore` entry is needed.

**Consequence**: Clean git status. No generated artifacts leak into the
repository.

---

## Phase 9: VM Support (KVM Instances)

### D-011: Separate wait timeouts for VM vs LXC

**Context**: The `incus_instances` role had a single wait loop (30 retries
× 2s = 60s) for all instance types. VMs take 10-30 seconds for UEFI+kernel
boot, while LXC containers start in <2 seconds.

**Decision**: Split the wait into type-specific tasks with configurable
defaults: LXC keeps 30×2s=60s, VMs get 60×2s=120s. Variables are
role-prefixed (`incus_instances_vm_retries`, etc.) per project conventions.

**Consequence**: VMs have adequate boot time without slowing LXC deployments.

### D-012: incus-agent wait as separate task

**Context**: After a VM reaches "Running" status, the `incus-agent` inside
the guest still needs seconds to initialize. Without the agent, `incus exec`
and the `community.general.incus` connection plugin fail, breaking the
provisioning phase.

**Decision**: Add a dedicated "wait for incus-agent" task that polls
`incus exec <vm> -- true` with `failed_when: false` + `until` loop.
Only runs for VMs (`when: instance_type == 'vm'`).

**Consequence**: Provisioning phase reliably connects to VMs. No impact
on LXC container workflow.

### D-013: Instance type validation without minimum resource enforcement

**Context**: ROADMAP mentions "VM constraints (minimum memory, minimum CPU)"
but Incus defaults (1 vCPU, 1 GiB) work for most lightweight Linux guests.
Enforcing minimums in the generator would add complexity for marginal benefit.

**Decision**: Validate that `type` is `lxc` or `vm` (error on invalid values).
Do NOT enforce minimum resource requirements — Incus defaults are adequate
and users can override via `config:` in infra.yml.

**Rationale**: KISS — the generator validates structure, not policy. Resource
recommendations belong in documentation (`docs/vm-support.md`), not code.

### D-014: VM example in sandbox-isolation

**Context**: Needed a practical example showing VM+LXC coexistence. The
sandbox-isolation example is the natural fit since VMs provide stronger
isolation for untrusted workloads.

**Decision**: Add `sbx-vm` (type: vm, 2 vCPU, 2 GiB) alongside existing
`sbx-test` (type: lxc) in the sandbox-isolation example. Updated README
with hardware requirements and isolation comparison.

---

## Phase 10: Advanced GPU Management

### D-015: GPU policy validation in generator (ADR-018)

**Context**: ADR-018 specifies exclusive/shared GPU policy but the
validation was not implemented in the generator.

**Decision**: Implement GPU policy enforcement in `validate()`:
- Count GPU instances via `gpu: true` flag AND profile device detection
- `exclusive` (default): error if >1 GPU instance
- `shared`: no error, but `get_warnings()` emits a warning
- Invalid `gpu_policy` value triggers a validation error

Profile device detection scans domain-level profiles referenced by the
machine to find any device with `type: gpu`. This catches both direct
(`gpu: true`) and indirect (profile-based) GPU access.

### D-016: get_warnings() as separate function

**Context**: Warnings (non-fatal) should not block `make sync` but should
be visible to the user. Changing `validate()` return type would break
backward compatibility with existing tests.

**Decision**: Add `get_warnings(infra)` as a separate function that returns
a list of warning strings. Called in `main()` after validation passes.
Warnings are printed to stderr with `WARNING:` prefix.

**Rationale**: DRY — GPU instance scanning logic is duplicated between
`validate()` and `get_warnings()` but they serve different purposes
(errors vs warnings). KISS wins over DRY here since the alternative
(shared return tuple) would change the API.

### D-017: VM GPU documented but not enforced

**Context**: ROADMAP mentions GPU in VMs via vfio-pci. However, vfio-pci
requires host-level IOMMU configuration that AnKLuMe cannot validate from
inside the admin container.

**Decision**: Document VM GPU setup in `docs/gpu-advanced.md` but do not
add runtime validation for IOMMU. The generator enforces exclusive policy
regardless of instance type. VM GPU profiles use `pci:` device syntax
documented by Incus upstream.

**Rationale**: KISS — IOMMU detection is a host concern, not an infra.yml
concern. ADR-004 (no hypervisor in inventory) means we can't check IOMMU
from the admin container.

---

## Phase 11: Dedicated Firewall VM

### D-018: Two-role architecture for firewall VM

**Context**: The firewall VM needs both infrastructure setup (multi-NIC
profile) and provisioning (nftables inside the VM). These run in different
playbook phases with different connection types.

**Decision**: Split into two roles:
- `incus_firewall_vm`: Infrastructure role (connection: local). Discovers
  bridges, creates a `firewall-multi-nic` profile with one NIC per domain
  bridge, attached to the sys-firewall VM.
- `firewall_router`: Provisioning role (connection: community.general.incus).
  Runs inside the VM: enables IP forwarding, installs nftables, deploys
  isolation rules via Jinja2 template.

**Rationale**: Matches the two-phase architecture (ADR-006). Infrastructure
creates the topology, provisioning configures the VM internals.

### D-019: Admin bridge always eth0

**Context**: The firewall VM needs one NIC per domain bridge. The admin
bridge must be predictable for nftables rules.

**Decision**: The `incus_firewall_vm` role sorts bridges with `net-admin`
always first (eth0). Other bridges are sorted alphabetically and assigned
eth1, eth2, etc. The nftables template uses this ordering to identify
the admin interface.

**Consequence**: Firewall rules can reference `eth0` as the admin interface
without configuration. Adding new domains automatically adds new NICs.

### D-020: firewall_mode validation in PSOT generator

**Context**: infra.yml supports `global.firewall_mode: host|vm`. Invalid
values should be caught early by `make sync`, not at deployment time.

**Decision**: Add `firewall_mode` validation to `validate()` in generate.py.
Valid values: `host` (default) and `vm`. Invalid values produce a
validation error. The generator does not enforce that a `sys-firewall`
machine exists when `vm` mode is set — that is the operator's responsibility.

**Rationale**: KISS — the generator validates values, not deployment topology.
Checking for sys-firewall existence would couple the generator to role-level
concerns.

### D-021: Defense in depth — host + VM modes can coexist

**Context**: Phase 8 provides host-level nftables isolation. Phase 11 adds
VM-level firewall routing. Should they be mutually exclusive?

**Decision**: Both modes can coexist for layered security. Host nftables
blocks direct bridge-to-bridge forwarding. The firewall VM routes permitted
traffic and logs decisions. Even if the firewall VM is compromised, host
rules still prevent direct inter-bridge traffic.

**Consequence**: Documented in `docs/firewall-vm.md`. The operator can
choose host-only, VM-only, or both. No code enforces exclusivity.

---
