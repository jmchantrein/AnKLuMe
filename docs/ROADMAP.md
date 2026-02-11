# ROADMAP.md — Implementation Phases

Each phase produces a testable deliverable. Do not start phase N+1
before phase N is complete and validated.

---

## Phase 1: PSOT Generator ✅ COMPLETE

**Goal**: `infra.yml` → complete Ansible file tree

**Deliverables**:
- `scripts/generate.py` — the PSOT generator
- `infra.yml` — PSOT file with 4 domains (admin, pro, perso, homelab)
- Generated inventory in `inventory/`
- Generated group_vars and host_vars with managed sections
- Constraint validation (unique names, unique subnets, valid IPs)
- Orphan detection
- `make sync` and `make sync-dry`

**Validation criteria**:
- [x] `make sync` idempotent (re-running changes nothing)
- [x] Add a domain in infra.yml + `make sync` → files created
- [x] Remove a domain → orphans detected and listed
- [x] Managed sections preserved, user content kept
- [x] Validation constraints: clear error on duplicate name/subnet/IP

---

## Phase 2: Infrastructure Roles (Incus Reconciliation) ✅ COMPLETE

**Goal**: `make apply --tags infra` creates all Incus infrastructure

**Deliverables**:
- `roles/incus_networks/` — bridges
- `roles/incus_projects/` — projects + default profile (root + eth0)
- `roles/incus_profiles/` — extra profiles (GPU, nesting)
- `roles/incus_instances/` — LXC containers (device override, static IP)
- `site.yml` — master playbook at project root (ADR-016)

**Validation criteria**:
- [x] `ansible-lint` 0 violations, production profile
- [x] Idempotent (0 changed on second run)
- [x] All 4 domains created with correct static IPs
- [x] `--tags networks` works standalone
- [x] `--limit homelab` works standalone

**Lessons learned (ADR-015, ADR-016)**:
- `run_once: true` incompatible with hosts:all + connection:local pattern
- Connection variables in group_vars override playbook `connection:`
- Playbook must be at project root for group_vars/host_vars resolution
- Incus `device set` fails on profile-inherited device → use `device override`
- Ansible 2.19 requires `when:` conditionals to evaluate to strict bool

---

## Phase 2b: Post-Deployment Hardening ✦ PRIORITY

**Goal**: Fix issues discovered during Phase 2 deployment

**Deliverables**:
- Commit manual hotfixes (failed_when images remote)
- Systemd service for admin-ansible proxy socket (ADR-019)
- ADR-017, ADR-018, ADR-019 documented in ARCHITECTURE.md
- Molecule tests updated for fixes

**Validation criteria**:
- [ ] admin-ansible restarts without manual intervention
- [ ] `ansible-playbook site.yml` idempotent after fixes
- [ ] `make lint` passes
- [ ] ADR-017 to ADR-019 present in ARCHITECTURE.md

---

## Phase 3: Instance Provisioning ✅ COMPLETE

**Goal**: `make apply --tags provision` installs packages and services

**Deliverables**:
- `roles/base_system/` — base packages, locale, timezone
- `roles/admin_bootstrap/` — admin-specific provisioning (ansible, git)
- `site.yml` — provisioning phase added
- Connection plugin `community.general.incus` configured

**Validation criteria**:
- [x] Instance created + provisioned in a single `make apply`
- [x] Re-provisioning idempotent
- [x] Installed packages verifiable

---

## Phase 4: Snapshots ✅ COMPLETE

**Goal**: `make snapshot` / `make restore`

**Deliverables**:
- `roles/incus_snapshots/` — Ansible role for snapshot management
- `snapshot.yml` — standalone playbook
- Individual, per-domain, and global snapshot support
- Restore + delete with idempotency

**Validation criteria**:
- [x] Snapshot + restore round-trip functional
- [x] Per-domain snapshot only touches that domain

---

## Phase 5: GPU + LLM ✅ COMPLETE

**Goal**: Ollama container with GPU + Open WebUI

**Deliverables**:
- `roles/ollama_server/` — Ollama installation with GPU detection
- `roles/open_webui/` — Open WebUI frontend via pip
- `instance_devices` support in PSOT generator and incus_instances role
- Conditional provisioning in site.yml (instance_roles-based)
- `make apply-llm` target

**Validation criteria**:
- [x] GPU device correctly added to target instance
- [x] `nvidia-smi` works inside the GPU container
- [x] Ollama service running and responding on port 11434
- [x] Idempotent on second run

---

## Phase 6: Molecule Tests

**Goal**: Automated tests for each role

**Deliverables**:
- `molecule/` directory in each role
- CI/CD compatible (GitHub Actions or local script)

**Note**: Tests currently run on the same Incus host (temporary).
Phase 12 will provide proper isolation via Incus-in-Incus.

---

## Phase 7: Documentation + Publication

**Goal**: Project usable by others

**Deliverables**:
- `README.md` complete
- `docs/quickstart.md`
- `docs/lab-tp.md` — lab deployment guide
- `docs/gpu-llm.md` — GPU guide
- `examples/` directory with documented infra.yml files:
  - `examples/student-sysadmin.infra.yml` — Sysadmin student: 2 simple
    domains (admin + lab), no GPU, isolated network for lab exercises
  - `examples/teacher-lab.infra.yml` — Teacher: 1 admin domain + N
    student domains generated dynamically, pre-lab snapshots
  - `examples/pro-workstation.infra.yml` — Pro workstation:
    admin/perso/pro/homelab, GPU on homelab, strict network isolation
  - `examples/sandbox-isolation.infra.yml` — Untrusted software testing
    (e.g., OpenClaw): maximum isolation, no external network, snapshot
    before each execution
  - `examples/llm-supervisor.infra.yml` — 2 LLMs isolated in separate
    domains + 1 supervisor container communicating with both via API,
    for testing LLM monitoring/management by another LLM
  - `examples/developer.infra.yml` — AnKLuMe developer: includes a
    dev-test domain with Incus-in-Incus (Phase 12)
  - Each example accompanied by a README explaining the use case,
    hardware requirements, and how to get started

---

## Phase 8: nftables Inter-Bridge Isolation

**Goal**: Block traffic between domains at the network level

**Context**: By default, Incus creates nftables chains per bridge but
does not forbid forwarding between different bridges. A container in one
domain can communicate with containers in other domains, breaking
network isolation.

**Deliverables**:
- `roles/incus_nftables/` — inter-bridge isolation rules
- Rules: DROP all traffic between net-X and net-Y by default
- Exception: admin → all (for Ansible and monitoring)
- Integration in site.yml (tag `nftables`)
- Documentation `docs/network-isolation.md`

**Validation criteria**:
- [ ] Traffic between non-admin domains blocked (e.g., perso ↛ pro)
- [ ] Traffic from admin to all domains allowed (Ansible, monitoring)
- [ ] NAT to Internet functional from all bridges
- [ ] Idempotent (nftables rules applied only once)

**Notes**:
- nftables rules are on the HOST, not in containers
- This is an exception to "Ansible does not modify the host" (ADR-004)
- Alternative: manage via Incus ACLs if the version supports it

---

## Phase 9: VM Support (KVM Instances)

**Goal**: Allow declaring `type: vm` in infra.yml

**Context**: Some workloads require stronger isolation than LXC
(untrusted workloads, GPU vfio-pci, custom kernel, non-Linux guests).

**Deliverables**:
- `incus_instances`: branch on `instance_type` to pass `--vm`
- VM-specific profiles (network agent, resources, secure boot)
- `incus-agent` support for Ansible connection to VMs
- PSOT validation: VM constraints (minimum memory, minimum CPU)
- Guide `docs/vm-support.md`

**Validation criteria**:
- [ ] `type: vm` in infra.yml → KVM VM created and reachable
- [ ] Provisioning via `community.general.incus` works in the VM
- [ ] VM and LXC coexist in the same domain
- [ ] `make apply` idempotent with LXC + VM mix

**Notes**:
- VMs are slower to start (~30s vs ~2s for LXC)
- `wait_for_running` will need a longer timeout for VMs
- VMs use `incus-agent` instead of direct `incus exec`

---

## Phase 10: Advanced GPU Management

**Goal**: GPU passthrough for LXC and VM with security policy

**Deliverables**:
- Implementation of `gpu_policy: exclusive|shared` in PSOT (ADR-018)
- `nvidia-compute` profile for LXC (gpu device + nvidia.runtime)
- `gpu-passthrough` profile for VM (vfio-pci + IOMMU)
- PSOT validation: one GPU per instance in exclusive mode
- GPU device management at startup (availability check)
- Guide `docs/gpu-advanced.md`

**Validation criteria**:
- [ ] LXC with GPU: `nvidia-smi` works
- [ ] VM with GPU: `nvidia-smi` works (vfio-pci)
- [ ] Exclusive mode: PSOT error if 2 instances declare GPU
- [ ] Shared mode: PSOT warning, 2 LXC share the GPU
- [ ] GPU container restart without losing access

---

## Phase 11: Dedicated Firewall VM (sys-firewall Style)

**Goal**: Optional — route all inter-domain traffic through a dedicated
firewall VM, QubesOS sys-firewall style

**Context**: In Phase 8, isolation is done via nftables on the host.
This phase adds an option to route all traffic through a dedicated
firewall VM, offering stronger isolation (the firewall has its own
kernel, unlike LXC containers that share the host kernel).

**Deliverables**:
- `infra.yml`: option `global.firewall_mode: host|vm`
- `sys-firewall` VM in the admin domain
- Routing configuration: all bridges go through sys-firewall
- nftables/iptables in the firewall VM
- Centralized monitoring and logging

**Validation criteria**:
- [ ] `host` mode: Phase 8 behavior (nftables on host)
- [ ] `vm` mode: all inter-bridge traffic goes through sys-firewall
- [ ] No excessive single point of failure (health check + auto restart)
- [ ] Performance: added latency < 1ms for inter-bridge traffic

**Notes**:
- High complexity — do not implement before Phase 8 is stable
- Security gain for LXC is marginal (same kernel as host)
- Security gain is significant for VM workloads
- Performance impact: double network hop (container → FW VM → container)

---

## Phase 12: Incus-in-Incus Test Environment

**Goal**: Test AnKLuMe in an isolated sandbox (AnKLuMe testing itself)
without impacting production infrastructure.

**Principle**: A test-runner container with `security.nesting: "true"`
runs its own Incus and deploys a complete AnKLuMe instance inside.
Molecule tests execute within this nested environment.

**Deliverables**:
- Incus profile `nesting` with `security.nesting`,
  `security.syscalls.intercept.mknod`,
  `security.syscalls.intercept.setxattr`
- Role `dev_test_runner` that provisions the test container:
  - Installs Incus inside the container (`apt install incus`)
  - Initializes Incus (`incus admin init --minimal`)
  - Clones the AnKLuMe repo
  - Installs Molecule + ansible-lint + dependencies
- Script `scripts/run-tests.sh` that:
  1. Creates the test-runner container (or reuses it)
  2. Runs `molecule test` for each role inside the container
  3. Collects results
  4. Optionally destroys the test-runner container
- `examples/developer.infra.yml` including the dev-test domain
- Makefile targets: `make test-sandboxed`, `make test-runner-create`,
  `make test-runner-destroy`

**References**:
- [Incus nesting documentation](https://linuxcontainers.org/incus/docs/main/faq/)
- [Incus container inside Incus](https://discuss.linuxcontainers.org/t/incus-container-inside-incus/23146)
- [Debusine worker Incus-in-Incus](https://freexian-team.pages.debian.net/debusine/howtos/set-up-incus.html)

**Validation criteria**:
- [ ] test-runner container starts with functional Incus inside
- [ ] `molecule test` for base_system passes in the sandbox
- [ ] No impact on production projects/networks
- [ ] Automatic cleanup of test resources

---

## Phase 13: LLM-Assisted Testing and Development

**Goal**: Allow an LLM (local or remote) to analyze test results, propose
fixes, and optionally submit PRs autonomously.

**Modes** (configurable via `ANKLUME_AI_MODE` environment variable):

| Mode | Value | Description |
|------|-------|-------------|
| None | `none` | Standard Molecule tests, no AI (default) |
| Local | `local` | Local LLM via Ollama (e.g., qwen2.5-coder:32b) |
| Remote | `remote` | Cloud API (Claude API, OpenAI API via key) |
| Claude Code | `claude-code` | Claude Code CLI in autonomous mode |
| Aider | `aider` | Aider CLI connected to Ollama or remote API |

**Architecture**:

```
+--------------------------------------------------+
| test-runner (Incus-in-Incus, Phase 12)           |
|                                                   |
|  1. molecule test -> logs                        |
|  2. if fail -> send logs to LLM                  |
|  3. LLM analyzes -> proposes patch               |
|  4. apply patch in branch fix/<issue>            |
|  5. molecule test again                          |
|  6. if pass -> git push + create PR              |
|  7. if fail again -> report + stop (max retries) |
|                                                   |
|  LLM backend (configurable):                    |
|  - Ollama (homelab-llm:11434 or local)           |
|  - Claude API (ANTHROPIC_API_KEY)                |
|  - Claude Code CLI (claude -p "...")              |
|  - Aider (aider --model ollama_chat/...)          |
+--------------------------------------------------+
```

**Deliverables**:

a) Script `scripts/ai-test-loop.sh` — main orchestrator:
   - Runs `molecule test` and captures logs
   - On failure: sends context (log + failing file + CLAUDE.md) to LLM
   - LLM proposes a diff/patch
   - Applies the patch, re-tests
   - Max retries configurable (default: 3)
   - On success: commit + push to branch + PR creation via `gh` CLI
   - Dry-run mode: displays the patch without applying it

b) LLM backend integrations (uniform pattern: send context, receive patch):
   - Ollama (local): `curl http://homelab-llm:11434/api/generate`
   - Claude Code CLI: `claude -p "Analyze this failure..."`
   - Aider: `aider --model ollama_chat/... --message "Fix..."`
   - Direct API (Claude, OpenAI): REST call with structured prompt

c) Configuration (`anklume.conf.yml` or environment variables):
   ```yaml
   ai:
     mode: none
     ollama_url: "http://homelab-llm:11434"
     ollama_model: "qwen2.5-coder:32b"
     anthropic_api_key: ""
     max_retries: 3
     auto_pr: false
     dry_run: true
   ```

d) Makefile targets:
   - `make ai-test` — run tests with AI-assisted fixing
   - `make ai-develop` — autonomous development session

e) Script `scripts/ai-develop.sh` — autonomous development:
   - Takes a task description as input (TASK)
   - Creates a feature branch
   - Uses the chosen LLM to implement the task
   - Runs tests, iterates if fail (max retries)
   - If tests pass → PR; full session log for human review

**Safety guardrails**:
- `dry_run: true` by default (LLM proposes, human applies)
- `auto_pr: false` by default (human creates the PR)
- Max retries to prevent infinite loops
- Every session is fully logged
- Incus-in-Incus sandbox (Phase 12) isolates all execution
- Never direct access to production from test-runner

**Design principles**:
- KISS: orchestrator is a simple shell script, not a complex framework
- DRY: single orchestration script with pluggable backends
- Security by default: dry_run + no auto_pr + sandbox isolation

**References**:
- [Claude Code CLI](https://code.claude.com/docs/en/overview)
- [Aider + Ollama](https://aider.chat/docs/llms/ollama.html)
- [Self-healing CI patterns](https://optimumpartners.com/insight/how-to-architect-self-healing-ci/cd-for-agentic-ai/)
- [claude-flow (multi-agent orchestration)](https://github.com/ruvnet/claude-flow)
- [Self-Evolving Agents cookbook](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining)

**Validation criteria**:
- [ ] `make ai-test AI_MODE=none` = standard Molecule tests (no regression)
- [ ] `make ai-test AI_MODE=local` = tests + failure analysis by local Ollama
- [ ] `make ai-test AI_MODE=claude-code` = tests + fix proposed by Claude Code
- [ ] `make ai-test AI_MODE=aider` = tests + fix via Aider
- [ ] dry_run prevents any automatic modification by default
- [ ] Auto-created PRs are clearly labeled (ai-generated)
- [ ] Full session log for every execution

---

## Current State

**Completed**:
- Phase 1: PSOT generator functional (make sync idempotent)
- Phase 2: Incus infrastructure deployed and idempotent
- Phase 3: Instance provisioning (base_system + admin_bootstrap)
- Phase 4: Snapshot management (role + playbook)
- Phase 5: GPU passthrough + Ollama + Open WebUI roles

**Deployed infrastructure**:

| Domain | Container | IP | Network | Status |
|--------|-----------|-----|---------|--------|
| admin | admin-ansible | 10.100.0.10 | net-admin | Running |
| perso | perso-desktop | 10.100.1.10 | net-perso | Running |
| pro | pro-dev | 10.100.2.10 | net-pro | Running |
| homelab | homelab-llm | 10.100.3.10 | net-homelab | Running |

**Active ADRs**: ADR-001 to ADR-019

**Known issues**:
- Inter-bridge traffic open (Phase 8)
- admin-ansible requires manual intervention at restart (Phase 2b)
- No effective VM support despite `type:` in infra.yml (Phase 9)
