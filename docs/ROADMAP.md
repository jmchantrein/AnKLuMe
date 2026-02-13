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

## Phase 8: nftables Inter-Bridge Isolation ✅ COMPLETE

**Goal**: Block traffic between domains at the network level

**Context**: By default, Incus creates nftables chains per bridge but
does not forbid forwarding between different bridges. A container in one
domain can communicate with containers in other domains, breaking
network isolation.

**Deliverables**:
- `roles/incus_nftables/` — inter-bridge isolation rules
- Rules: DROP all inter-bridge traffic (admin included — D-034)
- Admin communicates via Incus socket, not the network
- Integration in site.yml (tag `nftables`)
- `scripts/deploy-nftables.sh` — host-side deployment script
- Documentation `docs/network-isolation.md`

**Validation criteria**:
- [x] All inter-bridge traffic blocked (e.g., perso ↛ pro, admin ↛ pro)
- [x] Admin manages instances via Incus socket (not network — D-034)
- [x] NAT to Internet functional from all bridges
- [x] Idempotent (nftables rules applied only once)

**Design decisions**:
- nftables priority -1 (before Incus chains at priority 0)
- Two-step workflow: generate in admin container, deploy on host
- Same-bridge accept rules for br_netfilter compatibility
- Atomic table replacement (delete + recreate)
- ADR-004 exception: deploy script runs on host, not via Ansible

**Notes**:
- nftables rules are on the HOST, not in containers
- This is an exception to "Ansible does not modify the host" (ADR-004)
- Alternative: manage via Incus ACLs if the version supports it

---

## Phase 9: VM Support (KVM Instances) ✅ COMPLETE

**Goal**: Allow declaring `type: vm` in infra.yml

**Context**: Some workloads require stronger isolation than LXC
(untrusted workloads, GPU vfio-pci, custom kernel, non-Linux guests).

**Deliverables**:
- `incus_instances`: separate wait timeouts for VM (120s) vs LXC (60s)
- `incus-agent` wait task: polls `incus exec <vm> -- true` before provisioning
- PSOT validation: `type` must be `lxc` or `vm` (error on invalid values)
- VM resource config via `config:` keys (limits.cpu, limits.memory, etc.)
- Example: sandbox-isolation updated with VM + LXC coexistence
- Guide `docs/vm-support.md`

**Validation criteria**:
- [x] `type: vm` in infra.yml → KVM VM created with `--vm` flag
- [x] Provisioning via `community.general.incus` works (agent wait ensures readiness)
- [x] VM and LXC coexist in the same domain (validated by tests + example)
- [x] `make apply` idempotent with LXC + VM mix

**Design decisions**:
- Separate wait timeouts: LXC 30×2s=60s, VM 60×2s=120s (configurable)
- incus-agent wait: `incus exec <vm> -- true` with failed_when: false
- No minimum resource enforcement (KISS — Incus defaults work, docs recommend)
- VM profiles managed via `config:` and domain profiles, not role-internal logic

---

## Phase 10: Advanced GPU Management ✅ COMPLETE

**Goal**: GPU passthrough for LXC and VM with security policy

**Deliverables**:
- `gpu_policy: exclusive|shared` validation in PSOT generator (ADR-018)
- GPU instance detection via `gpu: true` flag AND profile device scanning
- `get_warnings()` function for non-fatal shared GPU warnings
- `nvidia-compute` profile pattern for LXC (documented)
- `gpu-passthrough` profile pattern for VM/vfio-pci (documented)
- Guide `docs/gpu-advanced.md`

**Validation criteria**:
- [x] LXC with GPU: nvidia-compute profile pattern documented + existing role
- [x] VM with GPU: vfio-pci profile pattern documented
- [x] Exclusive mode: PSOT error if 2 instances declare GPU
- [x] Shared mode: PSOT warning, 2 LXC share the GPU
- [x] GPU container restart: device persistence via Incus profiles

**Design decisions**:
- GPU detection: direct (`gpu: true`) + indirect (profile device scan)
- `get_warnings()` separate from `validate()` for backward compat
- VM GPU documented but IOMMU check not enforced (ADR-004 boundary)

---

## Phase 11: Dedicated Firewall VM (sys-firewall Style) ✅ COMPLETE

**Goal**: Optional — route all inter-domain traffic through a dedicated
firewall VM, QubesOS sys-firewall style

**Context**: In Phase 8, isolation is done via nftables on the host.
This phase adds an option to route all traffic through a dedicated
firewall VM, offering stronger isolation (the firewall has its own
kernel, unlike LXC containers that share the host kernel).

**Deliverables**:
- `global.firewall_mode: host|vm` validation in PSOT generator
- `roles/incus_firewall_vm/`: infrastructure role — multi-NIC profile creation
- `roles/firewall_router/`: provisioning role — IP forwarding + nftables inside VM
- nftables template (`firewall-router.nft.j2`) with admin/non-admin policy + logging
- `site.yml` updated with both roles (infra + provisioning phases)
- `docs/firewall-vm.md` — architecture, configuration, troubleshooting guide
- 4 firewall mode tests in test_generate.py

**Validation criteria**:
- [x] `host` mode: Phase 8 behavior (nftables on host)
- [x] `vm` mode: firewall VM with multi-NIC profile + nftables routing
- [x] PSOT generator validates firewall_mode values
- [x] Defense in depth: host + VM modes can coexist

**Design decisions**:
- Two-role architecture: infra (multi-NIC profile) + provisioning (nftables inside VM)
- Admin bridge always eth0, other bridges sorted alphabetically
- Generator validates firewall_mode but not deployment topology (KISS)
- Host + VM modes can coexist for layered security

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

## Phase 13: LLM-Assisted Testing and Development ✅ COMPLETE

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
- [x] `make ai-test AI_MODE=none` = standard Molecule tests (no regression)
- [x] `make ai-test AI_MODE=local` = tests + failure analysis by local Ollama
- [x] `make ai-test AI_MODE=claude-code` = tests + fix proposed by Claude Code
- [x] `make ai-test AI_MODE=aider` = tests + fix via Aider
- [x] dry_run prevents any automatic modification by default
- [x] Auto-created PRs are clearly labeled (ai-generated)
- [x] Full session log for every execution

---

## Phase 14: Speech-to-Text (STT) Service ✅ COMPLETE

**Goal**: Provide local, GPU-accelerated speech-to-text as a service
accessible by Open WebUI and other containers.

**Context**: Voice interaction with LLMs requires transcribing audio
to text before sending it to Ollama. Running STT locally preserves
privacy (no audio sent to cloud) and fits the compartmentalization
philosophy. Open WebUI already supports custom STT endpoints natively.

**Architecture**:

```
┌─────────────────────────────────────────────────┐
│ homelab domain (net-homelab, 10.100.3.0/24)     │
│                                                   │
│  ┌──────────────┐    ┌──────────────────────┐   │
│  │ homelab-stt   │    │ homelab-llm          │   │
│  │ GPU (shared)  │    │ GPU (shared)         │   │
│  │               │    │                      │   │
│  │ faster-whisper│    │ Ollama               │   │
│  │ + Speaches    │    │ :11434               │   │
│  │ :8000         │    │                      │   │
│  └──────┬───────┘    └──────────────────────┘   │
│         │                      ▲                  │
│         │    /v1/audio/        │  /api/generate   │
│         │    transcriptions    │                  │
│         ▼                      │                  │
│  ┌──────────────────────────────┐                │
│  │ homelab-webui                │                │
│  │ Open WebUI :3000             │                │
│  │ STT → homelab-stt:8000      │                │
│  │ LLM → homelab-llm:11434     │                │
│  └──────────────────────────────┘                │
└─────────────────────────────────────────────────┘
```

**Engine choice**: **faster-whisper** with **Whisper Large V3 Turbo**
model. faster-whisper uses CTranslate2 for up to 4x speedup over
vanilla Whisper on NVIDIA GPUs, with lower memory usage. Whisper
Large V3 Turbo provides the best accuracy/speed trade-off for
multilingual workloads (French + English).

**API server**: **Speaches** (formerly faster-whisper-server). Exposes
an OpenAI-compatible `/v1/audio/transcriptions` endpoint that Open
WebUI can consume directly. Single container, no orchestration needed.

**Alternative engines** (for future consideration):
- **OWhisper**: "Ollama for STT" — unified CLI/server for multiple
  STT backends (whisper.cpp, Moonshine). Newer project (Aug 2025),
  promising UX but less mature.
- **NVIDIA Parakeet TDT 0.6B**: Blazing fast (RTFx 3386) but
  English-only. Ideal if multilingual is not required.
- **Vosk**: Lightweight, CPU-only. For instances without GPU access.

**Deliverables**:
- `roles/stt_server/` — Install faster-whisper + Speaches server
  (systemd service, GPU detection, model download)
- PSOT support: `homelab-stt` instance with GPU device + config
- Open WebUI integration: configure STT endpoint in admin settings
  (or via `open_webui_stt_url` variable)
- `make apply-stt` Makefile target
- `gpu_policy: shared` required if STT and Ollama share the same GPU
  (ADR-018). Document the trade-off: shared GPU means concurrent
  inference competes for VRAM.

**Optional TTS deliverable** (text-to-speech for full voice loop):
- **Piper TTS** as a lightweight, local text-to-speech engine
- Could run in the same `homelab-stt` container or a dedicated one
- Exposes an API endpoint for Open WebUI TTS configuration
- Deferred unless voice output is explicitly needed

**Variables (roles/stt_server/defaults/main.yml)**:
```yaml
stt_engine: "faster-whisper"
stt_model: "large-v3-turbo"
stt_host: "0.0.0.0:8000"
stt_quantization: "float16"    # float16, int8_float16, or int8
stt_language: ""               # Empty = auto-detect
```

**References**:
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Speaches (OpenAI-compatible server)](https://github.com/speaches-ai/speaches)
- [OWhisper](https://hyprnote.com/product/owhisper)
- [NVIDIA Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
- [Open WebUI STT features](https://docs.openwebui.com/features/)
- [Best open-source STT models 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)

**Validation criteria**:
- [x] `homelab-stt` container starts with GPU access
- [x] Speaches API responds on `/v1/audio/transcriptions`
- [x] Open WebUI voice input transcribes correctly (FR + EN)
- [x] Idempotent on second run
- [x] Concurrent GPU usage with Ollama stable (shared mode)
- [x] Transcription latency < 2s for 10s audio clip

---

## Phase 15: Claude Code Agent Teams — Autonomous Development and Testing ✅ COMPLETE

**Goal**: Enable fully autonomous development and testing cycles using
Claude Code Agent Teams (multi-agent orchestration) inside the
Incus-in-Incus sandbox, with human oversight at the PR merge level.

**Prerequisites**: Phase 12 (Incus-in-Incus), Phase 13 (AI-assisted
testing infrastructure), Claude Code CLI >= 1.0.34, Anthropic API key
or Max plan.

**Context**: Phase 13 provides pluggable LLM backends (Ollama, Claude
API, Aider, Claude Code CLI) for AI-assisted test fixing via a shell
script orchestrator. Phase 15 goes further: it uses Claude Code's native
Agent Teams feature (shipped with Opus 4.6, February 2026) to orchestrate
multiple Claude Code instances working in parallel inside the sandbox.
Phase 13 remains the lightweight, backend-agnostic option. Phase 15 is
the full-power option for users with Claude Code access.

**Architecture**:

```
+----------------------------------------------------------------+
| Container: test-runner (Incus-in-Incus, Phase 12)              |
| security.nesting: true                                         |
| CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1                         |
| --dangerously-skip-permissions (safe: isolated sandbox)        |
|                                                                |
| Claude Code Agent Teams (Opus 4.6)                             |
|                                                                |
|  Team Lead: orchestrator                                       |
|  +-- reads ROADMAP / task description                          |
|  +-- decomposes work into shared task list                     |
|  +-- assigns tasks to teammates                                |
|  +-- synthesizes results, creates PR                           |
|                                                                |
|  Teammate "Builder": feature implementation                    |
|  +-- implements Ansible roles, playbooks, configs              |
|  +-- follows CLAUDE.md conventions                             |
|  +-- commits to feature branch                                 |
|                                                                |
|  Teammate "Tester": continuous testing                         |
|  +-- runs molecule test for affected roles                     |
|  +-- reports failures to team via shared task list             |
|  +-- validates idempotence                                     |
|                                                                |
|  Teammate "Reviewer": code quality                             |
|  +-- runs ansible-lint, yamllint                               |
|  +-- checks ADR compliance                                     |
|  +-- verifies no regression on other roles                     |
|  +-- approves or rejects with feedback to Builder              |
|                                                                |
|  Nested Incus (Molecule test targets run here)                 |
+----------------------------------------------------------------+
```

**Operational modes**:

a) **Fix mode** (`make agent-fix`):
   - Lead runs `molecule test` across all roles
   - On failure: spawns Fixer teammate(s) per failing role
   - Fixers analyze logs + source, propose and apply patches
   - Tester re-runs affected tests after each fix
   - Loop until all tests pass or max retries reached
   - On success: Lead creates PR with summary of all fixes

b) **Develop mode** (`make agent-develop TASK="Implement Phase N"`):
   - Lead reads ROADMAP.md, CLAUDE.md, and task description
   - Decomposes the phase into parallel subtasks
   - Spawns Builder(s) for implementation, Tester for validation,
     Reviewer for quality
   - Teammates coordinate via shared task list and inter-agent messaging
   - Builder implements, Tester validates, Reviewer checks quality
   - Iterate until Tester + Reviewer both approve
   - Lead creates PR with full implementation + passing tests

**Deliverables**:

a) Role `dev_agent_runner` — extends `dev_test_runner` (Phase 12):
   - Installs Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
   - Installs Node.js >= 18 (Claude Code requirement)
   - Installs tmux (for Agent Teams split-pane mode)
   - Configures Claude Code settings:
     ```json
     {
       "env": {
         "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
       },
       "permissions": {
         "allow": [
           "Edit",
           "MultiEdit",
           "Bash(molecule *)",
           "Bash(ansible-lint *)",
           "Bash(yamllint *)",
           "Bash(git *)",
           "Bash(incus *)",
           "Bash(make *)"
         ],
         "deny": [
           "Bash(rm -rf /)",
           "Bash(curl * | bash)",
           "Bash(wget * | bash)"
         ]
       },
       "defaultMode": "bypassPermissions"
     }
     ```
   - Copies CLAUDE.md and project context into container
   - Configures git (user, email, remote, credentials)

b) Script `scripts/agent-fix.sh` — Fix mode orchestrator:
   - Creates/reuses test-runner container
   - Injects Anthropic API key (from env or `anklume.conf.yml`)
   - Launches Claude Code with prompt:
     ```
     Run molecule test for all roles. For each failure:
     1. Analyze the error log and the relevant source files
     2. Create a fix branch (fix/<role>-<issue>)
     3. Apply the fix
     4. Re-run the test
     5. If it passes, commit with a descriptive message
     If all tests pass, create a single PR summarizing all fixes.
     Use agent teams: spawn a Tester and a Fixer teammate.
     Max retries per role: 3.
     ```
   - Captures full session transcript for audit
   - Exits with summary: which roles fixed, which still failing

c) Script `scripts/agent-develop.sh` — Develop mode orchestrator:
   - Takes TASK description (free text or "Phase N" reference)
   - Creates feature branch (`feature/<task-slug>`)
   - Launches Claude Code with prompt:
     ```
     Read ROADMAP.md and CLAUDE.md. Your task: {TASK}
     Use agent teams to parallelize the work:
     - Builder teammate(s) for implementation
     - Tester teammate to run molecule tests continuously
     - Reviewer teammate to check code quality and ADR compliance
     Iterate until all tests pass and Reviewer approves.
     Then create a PR with a comprehensive description.
     ```
   - Full session transcript saved
   - Summary output: files changed, tests passed/failed, PR URL

d) Makefile targets:
   ```makefile
   agent-fix:          ## Autonomous test fixing with Claude Code Agent Teams
   agent-develop:      ## Autonomous feature development (TASK required)
   agent-runner-setup: ## Setup the agent-runner container with Claude Code
   ```

e) CLAUDE.md additions for Agent Teams context:
   - Section describing the project structure for agents
   - Role naming conventions, ADR index, test patterns
   - Instructions for Molecule test execution
   - Git workflow: feature branches, PR conventions, commit messages

f) PreToolUse hook (`scripts/agent-audit-hook.sh`):
   - Logs every tool invocation (tool name, args, timestamp)
   - Stored in `logs/agent-session-<timestamp>.jsonl`
   - Enables post-hoc audit of everything the agents did

**Permission model and human-in-the-loop**:

| Layer | Control |
|-------|---------|
| Sandbox | Incus-in-Incus = total isolation. No access to production projects/nets |
| Claude Code permissions | `bypassPermissions` (safe in sandbox) + PreToolUse audit hook logs everything |
| Git workflow | Agents work on feature/fix branches. Never commit to main. PR created automatically |
| Human gate | PR merge = human decision. Full session transcript available. `git diff` reviewable before merge |

The key principle: full autonomy inside the sandbox, human approval at
the production boundary (PR merge).

**Cost considerations**:
- Agent Teams consume significantly more tokens (3-5x a single session)
- Each teammate has its own context window
- Recommended: use `agent-fix` for targeted fixes (lower cost),
  `agent-develop` for full phase implementation (higher cost, higher value)
- Estimated costs per mode (Opus 4.6 at $5/$25 per MTok):
  - `agent-fix` (single role): ~$3-8
  - `agent-fix` (all roles): ~$15-40
  - `agent-develop` (small phase): ~$20-60
  - `agent-develop` (large phase): ~$50-150

**Design principles**:

*Defense in depth*:
- Incus-in-Incus sandbox = OS-level isolation
- Claude Code permissions = application-level control
- Git branch protection = workflow-level gate
- PR merge = human-level decision
- Audit logs = accountability

*Autonomous but auditable*:
- Agents have full freedom inside the sandbox
- Every action is logged (PreToolUse hook)
- Full session transcript saved
- PR description auto-generated with summary
- Human reviews before anything reaches production

*Progressive trust*:
- Start with `agent-fix` (lower risk, targeted scope)
- Graduate to `agent-develop` as confidence builds
- Phase 13 backends remain available for lighter-weight usage
- Can always fall back to manual development

**References**:
- [Claude Code Agent Teams docs](https://code.claude.com/docs/en/agent-teams)
- [Claude Code permissions](https://code.claude.com/docs/en/permissions)
- [Claude Code sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Opus 4.6 features](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-6)
- [Agent Teams setup guide](https://serenitiesai.com/articles/claude-code-agent-teams-documentation)
- [Addy Osmani on Claude Code swarms](https://addyosmani.com/blog/claude-code-agent-teams/)

**Validation criteria**:
- [x] `make agent-runner-setup` creates container with Claude Code + Agent Teams
- [x] `make agent-fix` runs test-fix cycle autonomously, creates PR
- [x] `make agent-develop TASK="..."` implements a task, tests it, creates PR
- [x] All agent actions logged in session transcript
- [x] Agents never touch production (sandbox isolation verified)
- [x] PR contains clear description of changes and test results
- [x] Human can review full session log before merging

---

## Phase 16: Security Policy, Cross-Domain Communication, and Bootstrap ✅ COMPLETE

**Goal**: Enforce nesting security policy, enable selective cross-domain
access, provide robust bootstrap/lifecycle tooling.

**Prerequisites**: All previous phases.

**Deliverables**:

a) **Security policy (ADR-020)**:
   - `vm_nested` flag auto-detection via `systemd-detect-virt`
   - Nesting context files (`/etc/anklume/{absolute_level,relative_level,vm_nested,yolo}`)
   - Generator validation: reject `security.privileged: true` on LXC when `vm_nested=false`
   - YOLO bypass mode
   - dev_test_runner migrated from LXC to VM

b) **Network policies (ADR-021)**:
   - `network_policies:` section in infra.yml (flat allow-list syntax)
   - Generator validation of from/to references
   - nftables rule generation (accept rules before drop)
   - Integration with both host nftables and firewall VM modes

c) **infra/ directory support**:
   - Generator accepts `infra/` directory (base.yml + domains/*.yml + policies.yml)
   - Auto-detection of single file vs directory
   - Backward compatible with infra.yml

d) **AI tools domain**:
   - New `ai-tools` domain with 4 machines (ai-ollama, ai-openwebui, ai-lobechat, ai-opencode)
   - New roles: `lobechat` (LobeChat web UI), `opencode_server` (OpenCode headless server)
   - Example `examples/ai-tools/` with full AI stack configuration
   - `make apply-ai` target for deploying all AI roles

e) **Bootstrap script** (`bootstrap.sh`):
   - `--prod` / `--dev` modes with Incus preseed auto-configuration
   - `--snapshot` for pre-modification filesystem snapshots
   - `--YOLO` mode
   - `--import` for existing infrastructure import

f) **Lifecycle tooling**:
   - `make flush` — destroy all AnKLuMe infrastructure
   - `make upgrade` — safe framework update with conflict detection
   - `make import-infra` — reverse-generate infra.yml from Incus state
   - `roles_custom/` directory for user role customization
   - Version marker for compatibility checking

**Validation criteria**:
- [x] `security.privileged: true` on LXC rejected when `vm_nested=false`
- [x] `security.privileged: true` on LXC accepted when `vm_nested=true`
- [x] `--YOLO` bypasses privileged restriction (warning instead of error)
- [x] Context files created correctly at each nesting level
- [x] `network_policies` rules generate correct nftables accept lines
- [x] `infra/` directory produces identical output to equivalent `infra.yml`
- [x] `bootstrap.sh --prod` configures Incus with detected FS backend
- [x] `make flush` destroys infrastructure, preserves user files
- [x] `make upgrade` preserves user files, detects conflicts
- [x] `make import-infra` generates valid infra.yml from running Incus
- [x] `lobechat` and `opencode_server` roles created and integrated
- [x] AI tools example validates with PSOT generator

---

## Current State

**Completed**:
- Phase 1: PSOT generator functional (make sync idempotent)
- Phase 2: Incus infrastructure deployed and idempotent
- Phase 2b: Post-deployment hardening (ADR-017 to ADR-019)
- Phase 3: Instance provisioning (base_system + admin_bootstrap)
- Phase 4: Snapshot management (role + playbook)
- Phase 5: GPU passthrough + Ollama + Open WebUI roles
- Phase 6: Molecule tests for each role
- Phase 7: Documentation + publication
- Phase 8: nftables inter-bridge isolation
- Phase 9: VM support (KVM instances)
- Phase 10: Advanced GPU management (gpu_policy validation)
- Phase 11: Dedicated firewall VM (host + VM modes)
- Phase 12: Incus-in-Incus test environment
- Phase 13: LLM-assisted testing (ai-test-loop + ai-develop)
- Phase 14: Speech-to-Text (STT) service (stt_server role)
- Phase 15: Claude Code Agent Teams (autonomous dev + testing)

- Phase 16: Security policy, network policies, bootstrap, AI tools domain

**Next**:
- Phase 17+ (to be defined)

**Deployed infrastructure**:

| Domain | Container | IP | Network | Status |
|--------|-----------|-----|---------|--------|
| admin | admin-ansible | 10.100.0.10 | net-admin | Running |
| perso | perso-desktop | 10.100.1.10 | net-perso | Running |
| pro | pro-dev | 10.100.2.10 | net-pro | Running |
| homelab | homelab-llm | 10.100.3.10 | net-homelab | Running |

**Active ADRs**: ADR-001 to ADR-019

**Known issues**:
- admin-ansible requires manual intervention at restart (Phase 2b)
