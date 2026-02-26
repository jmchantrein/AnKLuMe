# ROADMAP.md — Implementation Phases

Each phase produces a testable deliverable. Do not start phase N+1
before phase N is complete and validated.

---

## Phase 1: PSOT Generator ✅ COMPLETE

**Goal**: `infra.yml` → complete Ansible file tree

**Deliverables**:
- `scripts/generate.py` — the PSOT generator
- `infra.yml` — PSOT file with 4 domains (anklume, pro, perso, homelab)
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

## Phase 2b: Post-Deployment Hardening ✅ COMPLETE

**Goal**: Fix issues discovered during Phase 2 deployment

**Deliverables**:
- Commit manual hotfixes (failed_when images remote)
- Systemd service for anklume-instance proxy socket (ADR-019)
- ADR-017, ADR-018, ADR-019 documented in ARCHITECTURE.md
- Molecule tests updated for fixes

**Validation criteria**:
- [x] anklume-instance restarts without manual intervention
- [x] `ansible-playbook site.yml` idempotent after fixes
- [x] `make lint` passes
- [x] ADR-017 to ADR-019 present in ARCHITECTURE.md

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

## Phase 6: Molecule Tests ✅ COMPLETE

**Goal**: Automated tests for each role

**Deliverables**:
- `molecule/` directory in each role
- CI/CD compatible (GitHub Actions or local script)

**Note**: Tests currently run on the same Incus host (temporary).
Phase 12 will provide proper isolation via Incus-in-Incus.

---

## Phase 7: Documentation + Publication ✅ COMPLETE

**Goal**: Project usable by others

**Deliverables**:
- `README.md` complete
- `docs/quickstart.md`
- `docs/lab-tp.md` — lab deployment guide
- `docs/gpu-llm.md` — GPU guide
- `examples/` directory with documented infra.yml files:
  - `examples/student-sysadmin.infra.yml` — Sysadmin student: 2 simple
    domains (admin + lab), no GPU, isolated network for lab exercises
  - `examples/teacher-lab.infra.yml` — Teacher: 1 anklume domain + N
    student domains generated dynamically, pre-lab snapshots
  - `examples/pro-workstation.infra.yml` — Pro workstation:
    admin/perso/pro/homelab, GPU on homelab, strict network isolation
  - `examples/sandbox-isolation.infra.yml` — Untrusted software testing
    (e.g., OpenClaw): maximum isolation, no external network, snapshot
    before each execution
  - `examples/llm-supervisor.infra.yml` — 2 LLMs isolated in separate
    domains + 1 supervisor container communicating with both via API,
    for testing LLM monitoring/management by another LLM
  - `examples/developer.infra.yml` — anklume developer: includes a
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
- Host-side deployment per ADR-004 (minimize host modifications, allow when KISS/DRY)

**Notes**:
- nftables rules are on the HOST, not in containers
- Host modification accepted per ADR-004 (KISS/DRY, no security compromise)
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

## Phase 11: Dedicated Firewall VM (anklume-firewall) ✅ COMPLETE

**Goal**: Optional — route all inter-domain traffic through a dedicated
firewall VM (anklume-firewall)

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

## Phase 12: Incus-in-Incus Test Environment ✅ COMPLETE

**Goal**: Test anklume in an isolated sandbox (anklume testing itself)
without impacting production infrastructure.

**Principle**: A test-runner container with `security.nesting: "true"`
runs its own Incus and deploys a complete anklume instance inside.
Molecule tests execute within this nested environment.

**Deliverables**:
- Incus profile `nesting` with `security.nesting`,
  `security.syscalls.intercept.mknod`,
  `security.syscalls.intercept.setxattr`
- Role `dev_test_runner` that provisions the test container:
  - Installs Incus inside the container (`apt install incus`)
  - Initializes Incus (`incus admin init --minimal`)
  - Clones the anklume repo
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
- [x] test-runner container starts with functional Incus inside
- [x] `molecule test` for base_system passes in the sandbox
- [x] No impact on production projects/networks
- [x] Automatic cleanup of test resources

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
|  - Ollama (gpu-server:11434 or local)           |
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
   - Ollama (local): `curl http://gpu-server:11434/api/generate`
   - Claude Code CLI: `claude -p "Analyze this failure..."`
   - Aider: `aider --model ollama_chat/... --message "Fix..."`
   - Direct API (Claude, OpenAI): REST call with structured prompt

c) Configuration (`anklume.conf.yml` or environment variables):
   ```yaml
   ai:
     mode: none
     ollama_url: "http://gpu-server:11434"
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
│  │ homelab-stt   │    │ gpu-server          │   │
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
│  │ LLM → gpu-server:11434     │                │
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
   - New `ai-tools` domain with 4 machines (gpu-server, ai-openwebui, ai-lobechat, ai-opencode)
   - New roles: `lobechat` (LobeChat web UI), `opencode_server` (OpenCode headless server)
   - Example `examples/ai-tools/` with full AI stack configuration
   - `make apply-ai` target for deploying all AI roles

e) **Bootstrap script** (`bootstrap.sh`):
   - `--prod` / `--dev` modes with Incus preseed auto-configuration
   - `--snapshot` for pre-modification filesystem snapshots
   - `--YOLO` mode
   - `--import` for existing infrastructure import

f) **Lifecycle tooling**:
   - `make flush` — destroy all anklume infrastructure
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

## Phase 17: CI/CD Pipeline and Test Coverage ✅ COMPLETE

**Goal**: Automated CI via GitHub Actions, complete Molecule test
coverage for all roles.

**Prerequisites**: All previous phases.

**Deliverables**:

a) **GitHub Actions CI workflow** (`.github/workflows/ci.yml`):
   - Triggered on push and pull requests
   - 6 parallel jobs: yamllint, ansible-lint, shellcheck, ruff,
     pytest (generator), ansible syntax-check
   - pip caching for faster runs
   - Badge in README.md and README_FR.md

b) **Molecule tests for remaining 7 roles**:
   - `roles/stt_server/molecule/` — template test (speaches.service)
   - `roles/firewall_router/molecule/` — template test (firewall-router.nft)
   - `roles/incus_firewall_vm/molecule/` — infra test (multi-NIC profile)
   - `roles/incus_images/molecule/` — infra test (image listing)
   - `roles/lobechat/molecule/` — template test (lobechat.service)
   - `roles/opencode_server/molecule/` — template test (service + config)
   - `roles/dev_agent_runner/molecule/` — template test (settings.json)

c) **ROADMAP cleanup**:
   - Phase 2b, 6, 7, 12 markers corrected to ✅ COMPLETE
   - Active ADRs updated to ADR-031
   - Known issues cleared
   - French ROADMAP synced (missing Phase 16 added)

**Validation criteria**:
- [x] GitHub Actions CI passes on push to main
- [x] `make lint` + `make test-generator` run in CI
- [x] All 18 roles have `molecule/` directories
- [x] README.md CI badge active
- [x] ROADMAP inconsistencies resolved

---

## Phase 18: Advanced Security, Testing, Onboarding & Self-Improvement ✅ COMPLETE

**Goal**: Five independent sub-phases addressing security, testing,
onboarding, self-improvement, and image sharing.

### Phase 18a: Exclusive AI-Tools Network Access with VRAM Flush

**Goal**: Only one domain at a time can access ai-tools. `make ai-switch
DOMAIN=<name>` atomically switches access with GPU VRAM flush.

**Deliverables**:
- `ai_access_policy: exclusive|open` in `global:` section of infra.yml
- `ai_access_default` and `ai_vram_flush` global fields
- PSOT generator validation and auto-enrichment of network policies
- `scripts/ai-switch.sh` — atomic domain switch with VRAM flush
- `roles/incus_nftables/` extended with `incus_nftables_ai_override`
- `make ai-switch DOMAIN=<name>` Makefile target
- `docs/ai-switch.md` documentation
- 11 new pytest tests for AI access policy validation

**Validation criteria**:
- [x] PSOT generator validates ai_access_policy fields
- [x] Auto-creation of network_policy when exclusive mode and no policy
- [x] ai-switch.sh handles stop/flush/switch/restart lifecycle
- [x] nftables AI override integrated into template
- [x] All 11 new tests pass

### Phase 18b: LLM-Powered Exhaustive Testing (Behavior Matrix)

**Goal**: Behavior matrix mapping every capability to expected reactions,
with LLM-generated test coverage and Hypothesis property-based tests.

**Deliverables**:
- `tests/behavior_matrix.yml` — 120 cells across 11 capabilities at 3 depths
- `scripts/matrix-coverage.py` — scans tests for matrix ID annotations
- `scripts/ai-matrix-test.sh` — LLM-powered test generator for uncovered cells
- `tests/test_properties.py` — 9 Hypothesis property-based tests for generator
- Matrix ID annotations on 54 existing tests (`# Matrix: XX-NNN`)
- CI integration: `matrix-coverage` informational job
- `make matrix-coverage` and `make matrix-generate` targets

**Validation criteria**:
- [x] `make matrix-coverage` reports coverage (48% initial)
- [x] Hypothesis tests pass (idempotency, no duplicate IPs, managed markers)
- [x] Matrix IDs annotated on existing tests
- [x] CI job added for matrix coverage

### Phase 18c: Interactive Onboarding Guide

**Goal**: `make guide` launches a step-by-step interactive tutorial.

**Deliverables**:
- `scripts/guide.sh` — 9-step interactive tutorial (pure Bash, ANSI colors)
- `make guide`, `make quickstart` Makefile targets
- Restructured `make help` with "GETTING STARTED" category
- `docs/guide.md` documentation

**Validation criteria**:
- [x] `make guide --auto` runs as CI smoke test
- [x] `make quickstart` copies example and provides instructions
- [x] shellcheck clean

### Phase 18d: Self-Improving Software (Experience Library + Improvement Loop)

**Goal**: Persistent experience library seeded from git history, with
spec-driven improvement loop proposing enhancements via PRs.

**Deliverables**:
- `experiences/` directory (fixes/, patterns/, decisions/)
- `scripts/mine-experiences.py` — git history miner for fix patterns
- `scripts/ai-improve.sh` — spec-driven improvement loop
- `scripts/ai-test-loop.sh` extended with experience search before LLM
- `--learn` flag for capturing new fixes to library
- `make mine-experiences` and `make ai-improve` targets

**Validation criteria**:
- [x] Experience library populated with fix patterns, implementation patterns
- [x] ai-test-loop.sh searches experiences before calling LLM
- [x] mine-experiences.py processes git history incrementally
- [x] ai-improve.sh implements full validate → context → LLM → test → PR loop

### Phase 18e: Shared Image Repository Across Nesting Levels

**Goal**: Pre-export OS images from host, mount into nested Incus VMs
to avoid redundant downloads.

**Deliverables**:
- `roles/incus_images/` extended with export tasks + `incus_images_export_for_nesting`
- `roles/dev_test_runner/` extended with import from mounted images
- Smart timeout (`incus_images_download_timeout: 600`)
- `make export-images` Makefile target

**Validation criteria**:
- [x] Export tasks create tar.gz files with idempotency (`creates:`)
- [x] Import tasks load images into nested Incus from mounted directory
- [x] Molecule tests verify export directory and defaults

---

## Phase 19: Terminal UX and Observability ✅ COMPLETE

**Goal**: Professional terminal UX with domain-colored tmux sessions,
local telemetry, and static code analysis tooling.

**Prerequisites**: All previous phases.

### Phase 19a: tmux Console (`make console`)

**Goal**: Auto-generate a tmux session from `infra.yml` with
QubesOS-style visual domain isolation in the terminal.

**Architecture**:
```
┌─────────────────────────────────────────────────────┐
│ tmux session "anklume"                               │
│ ┌─────────────┐ ┌──────────┐ ┌──────────────────┐  │
│ │ pane bg:blue │ │ bg:green │ │ bg:yellow        │  │
│ │ anklume-instance   │ │ pro-dev  │ │ perso-desktop    │  │
│ │ incus exec...│ │          │ │                  │  │
│ └─────────────┘ └──────────┘ └──────────────────┘  │
│ [0:anklume]  [1:pro]  [2:perso]  [3:ai-tools]       │
└─────────────────────────────────────────────────────┘
```

**Deliverables**:
- `scripts/console.py` — generates tmuxp YAML or drives libtmux
  directly from `infra.yml`. One window per domain, one pane per
  machine. Per-pane background color by trust level. Pane border
  labels show `[domain] machine-name`.
- Colors set server-side via `select-pane -P 'bg=...'` — containers
  cannot spoof their visual identity (same security model as QubesOS
  colored borders drawn by dom0).
- Trust level colors: blue (admin), green (trusted), yellow
  (semi-trusted), red (untrusted), magenta (disposable).
  Configurable via `infra.yml` domain-level `trust_level:` field
  or auto-assigned.
- `make console` Makefile target.
- Supports reconnection: `tmux attach -t anklume`.

**Dependencies**: `pip install tmuxp libtmux`

**Validation criteria**:
- [x] `make console` generates and launches tmux session from infra.yml
- [x] Each domain has its own window with correct panes
- [x] Per-pane background colors match domain trust level
- [x] Pane border labels show domain and machine name
- [x] Session survives disconnection and reconnection

### Phase 19b: Local Telemetry (`make telemetry-*`)

**Goal**: Opt-in, local-only usage analytics to understand usage
patterns. Data never leaves the machine.

**Deliverables**:
- Makefile wrapper logging each target invocation to
  `~/.anklume/telemetry/usage.jsonl` (append-only JSON Lines).
- Logged fields: timestamp (UTC), make target, domain argument (if
  any), duration in seconds, exit code. NO usernames, hostnames,
  IPs, secrets, or file contents.
- `make telemetry-on` / `make telemetry-off` (default: disabled)
- `make telemetry-status` — show state + event count
- `make telemetry-clear` — delete all data
- `make telemetry-report` — terminal charts via plotext (Python)
- Optional: `make telemetry-report-html` — static HTML with Chart.js

**Privacy guarantees**:
- **Default: disabled** (opt-in model)
- **Local-only**: data in `~/.anklume/telemetry/`, no network calls
- **Inspectable**: user can `cat` the JSONL file at any time
- **Deletable**: `make telemetry-clear` removes everything

**Dependencies**: `pip install plotext` (for terminal charts)

**Validation criteria**:
- [x] Default is disabled; `make telemetry-on` enables
- [x] JSONL file contains only the specified fields
- [x] `make telemetry-report` produces readable terminal charts
- [x] No network calls (verified by strace or audit)

### Phase 19c: Static Code Analysis (`make code-graph`)

**Goal**: Dead code detection, call graphs, and dependency
visualization across Python, YAML (Ansible), and Shell.

**Deliverables**:
- `make dead-code` — runs vulture (Python) + ShellCheck unused
  vars (bash) + little-timmy (Ansible unused variables)
- `make call-graph` — generates call graph via pyan (Python) +
  callGraph (bash). Output: GraphViz DOT + SVG.
- `make dep-graph` — module dependency graph via pydeps (Python).
  Output: SVG.
- `make code-graph` — runs all three above.
- CI integration: `dead-code` as informational job.

**Dependencies**: `pip install vulture pyan3 pydeps`, `apt install
graphviz`, little-timmy for Ansible.

**Validation criteria**:
- [x] `make dead-code` reports findings (may have false positives)
- [x] `make call-graph` produces readable DOT (SVG when graphviz available)
- [x] `make dep-graph` produces module dependency graph (when pydeps + graphviz available)
- [x] CI job added (informational, non-blocking)

---

## Phase 20: Native Incus Features and QubesOS Parity ✅ COMPLETE

**Goal**: Leverage native Incus features to close the gap with
QubesOS user-facing functionality.

**Prerequisites**: All previous phases.

### Phase 20a: Disposable Instances

**Goal**: On-demand, auto-destroyed instances using Incus native
`--ephemeral` flag.

**Deliverables**:
- `scripts/disp.sh` — launches an ephemeral instance from a base
  image, optionally runs a command, instance auto-destroyed on stop.
- `make disp IMAGE=debian/13 [CMD=bash] [DOMAIN=sandbox]`
- Instance name auto-generated: `disp-<timestamp>`.
- Uses `incus launch <image> <name> --ephemeral [-e]`.
- Optional: `--console` flag to attach immediately.

**Validation criteria**:
- [x] `make disp` creates an ephemeral instance
- [x] Instance is auto-destroyed on stop
- [x] Custom command runs and instance exits cleanly

### Phase 20b: Golden Images and Templates

**Goal**: CoW-based instance derivation for efficient instance
creation and centralized updates.

**Deliverables**:
- `make golden-create NAME=<name>` — provisions an instance with
  roles, stops it, creates a snapshot named `pristine`.
- `make golden-derive TEMPLATE=<name> INSTANCE=<new>` — creates
  a new instance from the golden image snapshot using `incus copy`
  (CoW on ZFS/Btrfs, full copy on dir backend).
- `make golden-publish TEMPLATE=<name> ALIAS=<alias>` — publishes
  as a reusable Incus image via `incus publish`.
- Documentation of profile propagation: modifying a profile
  automatically updates all instances using it (native Incus
  behavior).

**Validation criteria**:
- [x] `incus copy` uses CoW on ZFS/Btrfs (verified by disk usage)
- [x] Derived instances boot and are functional
- [x] Published images can be used in `infra.yml` as `os_image`

### Phase 20c: Inter-Container Services via MCP

**Goal**: Controlled service exposure between containers using
MCP (Model Context Protocol) over Incus proxy devices.

**Architecture**:
```
container-work                host              container-vault
  [MCP client]  ◄── unix ──► [proxy] ◄── unix ──► [MCP server]
  tools/call: sign_file                           gpg --sign
```

**Deliverables**:
- MCP server template (Python) for common services: file signing,
  clipboard get/set, file transfer accept/provide.
- MCP client library for anklume containers.
- Incus proxy device automation: `infra.yml` `services:` section
  declares which containers expose which MCP tools, and which
  containers can access them.
- Policy engine: admin container validates service access based
  on `infra.yml` declarations.
- Only `initialize`, `tools/list`, `tools/call` from MCP spec —
  no prompts, resources, sampling.

**Why MCP (not custom JSON-RPC)**:
- Standard protocol maintained by Anthropic + community
- SDKs in Python, Go, Rust, TypeScript (no ad-hoc maintenance)
- Native capability discovery (`tools/list`)
- AI agents can use the same MCP endpoints directly
- Lightweight over local Unix sockets (~0.8ms latency, ~18MB RAM)

**Dependencies**: `pip install mcp` (Python SDK)

**Validation criteria**:
- [x] MCP server runs in container, accessible via proxy device
- [x] MCP client in another container can call tools
- [x] Policy engine blocks unauthorized access
- [x] AI agents can interact with container services via MCP

### Phase 20d: File Transfer and Backup

**Goal**: Controlled file transfer between containers and encrypted
backup/restore.

**Deliverables**:
- `make file-copy SRC=<instance>:<path> DST=<instance>:<path>` —
  wraps `incus file pull ... | incus file push ...` pipe.
  Policy check against `infra.yml` service declarations.
- `make backup [I=<instance>] [GPG_RECIPIENT=<id>]` — wraps
  `incus export` with optional GPG encryption.
- `make restore-backup FILE=<backup.tar.gz> [NAME=<new-name>]` —
  wraps `incus import`.
- Shared volumes for bulk transfers between containers
  (`incus storage volume attach` to multiple instances).

**Validation criteria**:
- [x] File copy between instances works via pipe
- [x] Encrypted backup created and restorable
- [x] Cross-machine migration via `incus copy local: remote:`

### Phase 20e: Tor Gateway and Print Service

**Goal**: Network service containers for Tor anonymization and
print management.

**Deliverables**:
- **Tor gateway**: domain `tor-gateway` with container running Tor
  as transparent proxy. `network_policies` route traffic from
  selected domains through the gateway.
- **shared-print**: dedicated CUPS container in the `shared` domain.
  - USB printers: Incus `usb` device passthrough
    (`vendorid`/`productid`).
  - Network printers (WiFi/Ethernet): macvlan NIC profile gives
    `shared-print` access to the physical LAN. Other domains access
    `shared-print` via IPP (port 631) through `network_policies`.
- Example `infra.yml` configurations for both.
- `make apply-print` and `make apply-tor` targets.

**Validation criteria**:
- [x] Tor gateway routes traffic transparently
- [x] CUPS container serves USB and network printers
- [x] Network policies control which domains can print
- [x] Other domains cannot access the physical LAN directly

### Phase 20f: Shared Volumes ✅ COMPLETE

**Goal**: Declarative inter-domain directory sharing with RO/RW
access control via host bind mounts (ADR-039).

**Deliverables**:
- `shared_volumes:` top-level section in `infra.yml` with
  domain and machine consumers, RO/RW access modes
- Generator resolves consumers into `sv-*` Incus disk devices
  injected into `instance_devices` (host_vars)
- `make shares` creates host-side directories
- Validation: DNS-safe names, absolute paths, consumer
  resolution, device collision detection, path uniqueness
- `global.shared_volumes_base` for configurable base path
  (default: `/srv/anklume/shares`)
- `shift` and `propagate` options for idmap and nesting support

**Validation criteria**:
- [x] Domain consumer gives all machines the shared device
- [x] Machine consumer overrides domain-level access
- [x] Device name collision detected
- [x] Duplicate mount paths detected
- [x] `make sync-dry` shows sv-* devices in host_vars

---

### Phase 20g: Data Persistence and Flush Protection ✅ COMPLETE

**Goal**: Per-machine persistent host bind mounts (Docker-style) with
flush protection for non-ephemeral resources (ADR-040, ADR-041).

**Prerequisites**: Phase 20f (Shared Volumes — reuse sv-* pattern).

See: `docs/phase-20g-persistent-data.md` for detailed implementation plan.

**Deliverables**:

a) **Flush protection** (ADR-041):
   - `scripts/flush.sh` respects `security.protection.delete=true`
   - Protected instances skipped with `PROTECTED (skipped)` message
   - `FORCE=true` overrides protection
   - Host data dirs never deleted

b) **Instance removal** (`make instance-remove`):
   - New `scripts/instance-remove.sh`
   - Modes: single instance, domain ephemeral, domain all, with FORCE

c) **Persistent data** (ADR-040):
   - `persistent_data:` per-machine section in infra.yml
   - Host bind mounts at `<persistent_data_base>/<domain>/<machine>/<volume>`
   - Devices injected as `pd-<name>` (like `sv-*` for shared volumes)
   - `scripts/create-data-dirs.py` + `make data-dirs`

**Validation criteria**:
- [x] `make flush` skips protected instances (ephemeral: false)
- [x] `make flush FORCE=true` overrides protection
- [x] `make instance-remove I=pro-dev` removes single instance
- [x] persistent_data volumes appear as pd-* in host_vars
- [x] Mount path collision with shared_volumes detected
- [x] Host data directories survive flush

---

## Phase 21: Desktop Integration ✅ COMPLETE

**Goal**: Visual desktop integration for users running anklume on
a workstation with a graphical environment.

**Prerequisites**: Phase 19a (tmux console).

**Deliverables**:
- **Terminal background coloring**: per-domain colors via tmux
  server-side pane styles (Phase 19a). Colors controlled by the host
  (not the container) — same security model as QubesOS dom0 borders.
- **Clipboard forwarding**: controlled clipboard sharing between host
  and containers via `scripts/clipboard.sh`. Uses `incus file push/pull`
  with `wl-copy`/`wl-paste` (Wayland) or `xclip`/`xsel` (X11).
  Requires explicit user action (no auto-sync).
- **Domain-exec wrapper**: `scripts/domain-exec.sh` launches commands
  with `ANKLUME_DOMAIN`, `ANKLUME_TRUST_LEVEL` environment variables.
  `--terminal` mode opens a colored terminal window (foot, alacritty,
  xterm).
- **Desktop environment config generator**: `scripts/desktop_config.py`
  reads `infra.yml` and generates Sway/i3 window rules, foot terminal
  profiles, and `.desktop` entry files.
- **Web dashboard**: `scripts/dashboard.py` — read-only web dashboard
  using stdlib `http.server` + htmx (CDN). Shows live instance status,
  networks, and network policies with auto-refresh.
- **Documentation**: `docs/desktop-integration.md` + French translation.
- **Tests**: `tests/test_desktop.py` — 14 tests covering desktop-config
  generator, dashboard rendering, and script argument parsing.

**Validation criteria**:
- [x] tmux pane colors reflect domain trust level (Phase 19a)
- [x] Clipboard transfer requires explicit action
- [x] At least one desktop environment integration works (Sway)
- [x] Web dashboard shows live infrastructure state

---

## Phase 22: End-to-End Scenario Testing (BDD) ✅ COMPLETE

**Goal**: Human-readable acceptance scenarios testing complete user
workflows against real Incus infrastructure, covering both best
practices and failure modes. Scenarios feed back into the interactive
guide (Phase 18c) to steer users toward correct usage.

**Prerequisites**: Phase 12 (sandbox), Phase 18c (guide).

**Principles**:
- **On-demand only** — not in CI, launched explicitly by the developer
  via `make scenario-test`. Long execution time is acceptable (sandbox
  runs independently).
- **Gherkin format** — `.feature` files using `Given/When/Then` syntax,
  readable by non-developers. Runner: `behave` (Python BDD framework).
- **Two scenario categories**:
  - **Best practices**: validate recommended workflows, serve as living
    documentation of how to use anklume correctly.
  - **Bad practices**: verify that anklume catches mistakes early with
    clear error messages and guides the user toward the correct approach.
    No silent failures, no partial state left behind.
- **Latency-optimized**: scenarios pre-cache images at the start via
  the shared image repository (Phase 18e), reuse infrastructure across
  steps within a scenario.
- **Guide feedback loop**: pitfalls discovered by bad-practice scenarios
  feed back into `scripts/guide.sh` as proactive warnings at the
  relevant step.

**Architecture**:
```
scenarios/                          # Gherkin feature files
├── best_practices/
│   ├── pro_workstation_setup.feature
│   ├── student_lab_deploy.feature
│   ├── snapshot_restore_cycle.feature
│   ├── network_isolation_verify.feature
│   └── golden_image_workflow.feature
├── bad_practices/
│   ├── apply_without_sync.feature
│   ├── duplicate_ips.feature
│   ├── delete_protected_instance.feature
│   ├── invalid_network_policy.feature
│   └── wrong_operation_order.feature
└── conftest.py                     # Step definitions + fixtures

scripts/guide.sh                    # Enhanced with pitfall warnings
                                    # sourced from bad_practice scenarios
```

**Example scenarios**:

```gherkin
# scenarios/best_practices/pro_workstation_setup.feature
Feature: Pro workstation setup
  An admin deploys a pro/perso infrastructure with network isolation

  Background:
    Given a clean sandbox environment
    And images are pre-cached via shared repository

  Scenario: Full deployment with isolation verified
    Given infra.yml from "examples/pro-workstation.infra.yml"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains

    When I run "make apply"
    Then all declared instances are running
    And each instance has the correct static IP

    Then intra-domain connectivity works
    But inter-domain connectivity is blocked
    And internet access works from all instances

  Scenario: Snapshot and restore round-trip
    Given a running pro-workstation infrastructure
    When I create snapshot "before-change" on "pro-dev"
    And I modify a file inside "pro-dev"
    And I restore snapshot "before-change" on "pro-dev"
    Then the file modification is reverted
```

```gherkin
# scenarios/bad_practices/apply_without_sync.feature
Feature: Apply without sync
  anklume must detect and guide the user when steps are skipped

  Scenario: No inventory files exist
    Given infra.yml exists but no inventory files
    When I run "make apply"
    Then exit code is non-zero
    And stderr contains guidance to run "make sync" first
    And no Incus resources were created

  Scenario: Stale inventory after infra.yml change
    Given a deployed infrastructure
    When I add a new domain to infra.yml without running sync
    And I run "make apply"
    Then the new domain is not deployed
    And output warns about potential drift
```

**Deliverables**:

a) **Scenario files** (`scenarios/`):
   - 5+ best-practice scenarios covering key user workflows:
     pro workstation, student lab, snapshot cycle, network isolation,
     golden images, MCP services, disposable instances
   - 5+ bad-practice scenarios covering common mistakes:
     apply without sync, duplicate IPs/subnets, delete protected
     resources, invalid network policies, wrong operation order,
     missing prerequisites, editing managed sections, forgetting
     nftables-deploy after adding domain, flush without FORCE on
     production
   - Each scenario is self-contained and idempotent
   - Scenarios annotated with behavior matrix IDs (`# Matrix: XX-NNN`)
     to increase matrix coverage via E2E paths

b) **Test runner** (`scenarios/conftest.py`):
   - pytest-bdd step definitions for common steps (`Given`, `When`, `Then`)
   - Fixtures for sandbox lifecycle (create/destroy)
   - Image pre-caching at session start
   - Structured logging of failures (JSON report)
   - Timeout handling for long operations

c) **Guide integration** (`scripts/guide.sh`):
   - Each bad-practice scenario that reveals a pitfall adds a
     corresponding check/warning in the guide at the relevant step
   - Example: "apply without sync" → guide step 6 checks for
     inventory files before running apply
   - Pitfall database: `scenarios/pitfalls.yml` maps scenarios to
     guide steps and warning messages

d) **Makefile targets**:
   ```makefile
   scenario-test:        ## Run all E2E scenarios in sandbox (slow, on-demand)
   scenario-test-best:   ## Run best-practice scenarios only
   scenario-test-bad:    ## Run bad-practice scenarios only
   scenario-list:        ## List all available scenarios
   ```

e) **Documentation**:
   - `docs/scenario-testing.md` — how to write and run scenarios
   - `docs/scenario-testing_FR.md` — French translation
   - Best-practice scenarios referenced from user-facing docs

**Dependencies**: `pip install behave` (in `[project.optional-dependencies] test`)

**Step definitions pattern** (actual implementation uses behave):
```python
# scenarios/steps/given.py
from behave import given
import subprocess

@given("a clean sandbox environment")
def clean_sandbox(sandbox):
    sandbox.reset()

@given('infra.yml from "<example>"')
def load_infra(sandbox, example):
    sandbox.copy_infra(f"examples/{example}")

@when('I run "<command>"')
def run_command(sandbox, command):
    sandbox.last_result = sandbox.exec(command)

@then("exit code is 0")
def check_success(sandbox):
    assert sandbox.last_result.returncode == 0

@then("inter-domain connectivity is blocked")
def check_isolation(sandbox):
    for src, dst in sandbox.cross_domain_pairs():
        result = sandbox.exec(
            f"incus exec {src} -- ping -c1 -W1 {dst.ip}"
        )
        assert result.returncode != 0, f"{src} can reach {dst}"
```

**Validation criteria**:
- [x] `make scenario-test` runs all scenarios in sandbox
- [x] Best-practice scenarios pass on clean deployment
- [x] Bad-practice scenarios verify error detection and guidance
- [x] Guide enhanced with pitfall warnings from bad-practice scenarios
- [x] Failure reports logged in structured format for debugging
- [x] Scenarios use pre-cached images (no redundant downloads)
- [x] Scenarios annotated with behavior matrix IDs where applicable
- [x] Step definitions modularized (conftest.py → steps/{given,when,then}.py)

---

## Phase 23: Host Bootstrap and Thin Host Layer

**Goal**: Zero-prerequisite installation from a bare Linux host.
Formalize the host/container separation with a `host/` directory
in the repository.

**Prerequisites**: Functional framework (Phases 1-21).

**Context**: The current documentation assumes the user has already
installed Incus, created anklume-instance, and mounted the Incus
socket. This is too many manual steps. Additionally, host-side
scripts (STT, boot services, network recovery) had no canonical
location. The repository now includes a `host/` directory for all
host-side components.

**Architecture**:

```
anklume/                           ← Cloned on the host
├── bootstrap.sh                   ← Phase 0: installs Incus, creates container,
│                                     sets up bind mount, runs first make apply
├── host/
│   ├── boot/
│   │   ├── setup-boot-services.sh ← uinput module, udev rules, container autostart
│   │   └── network-recovery.sh    ← Emergency network restore
│   ├── stt/
│   │   ├── stt-push-to-talk.sh    ← Push-to-talk STT (Meta+S toggle)
│   │   ├── stt-azerty-type.py     ← AZERTY keycode typing helper
│   │   └── stt-streaming.py       ← Streaming STT (experimental, roadmap)
│   └── desktop/
│       ├── export-desktops.sh    ← Install .desktop files to user menu
│       └── domain-menu.sh        ← dmenu/rofi/fuzzel domain launcher
├── roles/                         ← Ansible roles (run inside the container)
├── Makefile                       ← Used by the container
└── ...
```

The repo lives on the host and is bind-mounted into the container:

```
/home/user/anklume/ ──disk device──> /root/anklume/ (in container)
```

**Two bootstrap paths** (K3s-inspired):

```bash
# Quick path
curl -sfL https://raw.githubusercontent.com/.../bootstrap.sh | bash

# Verify-first path
git clone https://github.com/jmchantrein/anklume.git
cd anklume && bash bootstrap.sh
```

**Deliverables**:

a) **`bootstrap.sh`** — Phase 0 script:
   - Detect host distro (Arch/Debian/Ubuntu/Fedora)
   - Install Incus from appropriate repo (Zabbly for Debian/Ubuntu,
     distro package for Arch/Fedora)
   - Initialize Incus (`incus admin init --minimal` or preseed)
   - Create anklume-instance (LXC container)
   - Set up Incus socket proxy device
   - Add disk device (bind mount of the repo)
   - Install Ansible + dependencies inside the container
   - Run first `make sync && make apply`
   - Configure host networking (IP forwarding, NAT, DHCP checksum)
   - Run `host/boot/setup-boot-services.sh` for uinput/udev/autostart
   - **GPU detection**: if NVIDIA GPU present, offer to deploy the
     AI-tools domain (Ollama, STT, WebUI) and download models
     (see Phase 23b)
   - **Interactive prompts**: ask user which domains to deploy,
     whether to enable AI services, preferred LLM model size
     (based on detected VRAM)
   - Wrapped in a function (K3s pattern: prevents partial execution)
   - `set -euo pipefail`, checksum verification, HTTPS-only

b) **`host/` directory** — Host-side scripts:
   - `host/boot/setup-boot-services.sh` — uinput, udev, autostart
   - `host/boot/network-recovery.sh` — emergency network restore
   - `host/stt/stt-push-to-talk.sh` — push-to-talk STT
   - `host/stt/stt-azerty-type.py` — AZERTY keycode typing
   - `host/stt/stt-streaming.py` — streaming STT (experimental)

c) **Host Makefile wrapper** (future):
   - `make apply` on host → `incus exec anklume-instance -- make apply`
   - Transparent delegation to the container

**Validation criteria**:
- [x] `bootstrap.sh` runs on Arch (CachyOS) from a fresh host
- [ ] `bootstrap.sh` runs on Debian 13 (Trixie) from a fresh host
- [x] After bootstrap, `make apply` works without manual intervention
- [x] Bind mount allows editing on host, running in container
- [x] STT scripts functional from `host/stt/` location
- [x] Network (NAT, IP forwarding) configured automatically
- [x] `scripts/bootstrap.sh` detects distro (arch/cachyos/debian/ubuntu/fedora)
- [x] `scripts/bootstrap.sh` creates anklume-instance container (idempotent)
- [x] `scripts/bootstrap.sh` sets up socket proxy + bind mount devices
- [x] `scripts/bootstrap.sh` provisions container (ansible, deps)
- [x] `scripts/bootstrap.sh` runs `make sync && make apply`
- [x] `scripts/bootstrap.sh` configures host networking (NAT, DHCP fix)
- [x] `scripts/bootstrap.sh` detects GPU and offers AI-tools deployment
- [x] `scripts/bootstrap.sh` calls setup-boot-services.sh
- [x] `scripts/bootstrap.sh` wrapped in main() function
- [x] `host/desktop/export-desktops.sh` installs/removes .desktop files
- [x] `host/desktop/domain-menu.sh` supports fuzzel/rofi/dmenu with fallback
- [x] All scripts pass `bash -n` syntax check
- [x] 78 tests pass (27 existing + 51 new Phase 23 tests)

---

## Phase 23b: Sandboxed AI Coding Environment

**Goal**: From bootstrap, offer a ready-to-use, isolated environment
for AI coding assistants (Claude Code, Gemini CLI, Aider, etc.) with
automatic local LLM model provisioning.

**Prerequisites**: Phase 23 (host bootstrap), Phase 5 (Ollama).

**Context**: AI coding assistants like Claude Code and Gemini CLI
run on the host and have broad filesystem access. They should be
sandboxed in a dedicated container with controlled access to the
codebase. When a GPU is available, the bootstrap should also
pre-download appropriate LLM models so local delegation (Phase 28)
works out of the box.

**Architecture**:

```
Host
├── anklume/                      ← User's projects and framework
│
├── Container: ai-coder           ← Sandboxed coding environment
│   ├── Claude Code CLI           ← API-based, supervised
│   ├── Gemini CLI                ← API-based, alternative
│   ├── Aider                     ← Local or API LLM coding tool
│   ├── Bind mount: ~/projects/   ← Controlled codebase access
│   └── Network: Ollama + API     ← Can reach local LLM + cloud APIs
│
├── Container: ollama             ← Local LLM inference (GPU)
│   ├── Pre-downloaded models     ← Selected at bootstrap time
│   └── API: :11434              ← Accessible from ai-coder
│
└── Container: anklume-instance   ← Framework management
```

**Bootstrap GPU detection and model provisioning**:

```
bootstrap.sh detects GPU:
  ├── No GPU → skip AI model download, API-only mode
  └── GPU found → detect VRAM:
      ├── <= 8GB  → qwen2.5-coder:7b, nomic-embed-text
      ├── 8-16GB  → qwen2.5-coder:14b, nomic-embed-text
      ├── 16-24GB → qwen2.5-coder:32b, nomic-embed-text
      └── > 24GB  → deepseek-coder-v2:latest, qwen2.5-coder:32b
      User can override model selection interactively.
```

**Deliverables**:

a) **AI coding container** (`ai-coder`):
   - Incus container with Claude Code, Gemini CLI, Aider installed
   - Bind mount of user's project directories (read-write)
   - Network policy: can reach Ollama container + internet (for APIs)
   - Cannot reach other domains (pro, perso, etc.)
   - SSH key forwarding for git operations
   - Declared in `infra.yml` with `ai_coding: true` flag

b) **Bootstrap model provisioning**:
   - GPU detection via `nvidia-smi` or `lspci`
   - VRAM-based model recommendation (interactive, user confirms)
   - `ollama pull` of selected models during bootstrap
   - Progress display during download
   - Skip option for users without GPU or who prefer API-only

c) **Host-side wrapper**:
   - `anklume code [project-dir]` — opens Claude Code inside the
     ai-coder container with the project bind-mounted
   - `anklume shell [instance]` — opens a shell in any container
   - These wrappers live in `host/bin/` and can be added to PATH

**Validation criteria**:
- [x] Bootstrap detects GPU and recommends appropriate models
- [x] Models downloaded automatically (with user confirmation)
- [x] `anklume code .` launches Claude Code in sandboxed container
- [ ] AI coder container can reach Ollama but not other domains
- [x] Works without GPU (API-only mode, no model download)

---

## Phase 24: Snapshot-Before-Apply and Rollback ✅ COMPLETE

**Goal**: Automatic safety snapshots before each `make apply`,
with one-command rollback if something breaks.

**Prerequisites**: Phase 4 (snapshots).

**Inspiration**: NixOS generations, Flatcar A/B partitions, IncusOS
A/B update mechanism.

**Deliverables**:

a) **`scripts/snapshot-apply.sh`** — Pre-apply snapshot manager:
   - `create [--limit <group>]` — snapshot all (or scoped) instances
   - `rollback [<timestamp>]` — restore most recent or specific snapshot
   - `list` — show pre-apply snapshot history
   - `cleanup [--keep N]` — remove old snapshots (default: keep 3)
   - Detects instance project from group_vars automatically
   - Records history in `~/.anklume/pre-apply-snapshots/`

b) **`safe_apply_wrap` enhanced** (Makefile):
   - Pre-apply snapshot created before every `make apply` / `apply-infra`
   - `apply-limit G=<group>` scopes snapshots to that domain
   - Automatic cleanup of old snapshots after successful apply
   - `SKIP_SNAPSHOT=1` to bypass for development speed
   - `KEEP=N` to override retention count

c) **Makefile targets**:
   ```
   make rollback              # Restore most recent pre-apply snapshot
   make rollback T=<ts>       # Restore specific timestamp
   make rollback-list         # List available pre-apply snapshots
   make rollback-cleanup      # Remove old snapshots (KEEP=3)
   make apply SKIP_SNAPSHOT=1 # Skip pre-apply snapshot
   ```

**Validation criteria**:
- [x] Pre-apply snapshots created automatically
- [x] `make rollback` restores previous state
- [x] Old snapshots cleaned up per retention policy
- [x] Snapshot skippable for development speed

---

## Phase 25: XDG Desktop Portal for Cross-Domain File Access

**Goal**: Replace manual `incus file push/pull` with a native file
chooser dialog for controlled file sharing between domains.

**Prerequisites**: Phase 21 (desktop integration).

**Inspiration**: Spectrum OS (XDG Portal for VM file access),
Flatpak portal sandboxing.

**Context**: The current file transfer mechanism
(`scripts/transfer.sh`, `make file-copy`) works but requires
CLI commands. XDG Desktop Portal would provide a native file
picker dialog: when a container app requests a file, the host
shows a file chooser restricted to authorized paths. This is
the same mechanism Flatpak uses for sandboxed app file access.

**Deliverables**:
- Portal daemon running on the host, serving requests from containers
- Per-domain file access policies in `infra.yml`:
  ```yaml
  domains:
    pro:
      file_portal:
        allowed_paths: ["/shared/pro", "/home/user/Documents"]
        read_only: false
    perso:
      file_portal:
        allowed_paths: ["/shared/perso"]
        read_only: false
  ```
- Native file chooser integration (KDE/GNOME)
- Audit log of all cross-domain file transfers

**Validation criteria**:
- [x] File portal script with open/push/pull/list subcommands
- [x] Access restricted to configured paths per domain
- [x] Transfers logged for audit
- [x] Per-domain policy from infra.yml file_portal config

---

## Phase 26: Native App Export (distrobox-export Style)

**Goal**: Make container applications appear as native host
applications in the desktop environment's app launcher.

**Prerequisites**: Phase 21 (desktop integration), Phase 23 (host layer).

**Inspiration**: Distrobox `distrobox-export`, but with isolation
preserved (Waypipe or virtio-gpu for display, PipeWire socket for
audio, controlled filesystem access via Phase 25 portals).

**Deliverables**:
- `make export-app I=<instance> APP=<app>` — generates a `.desktop`
  file on the host that launches the app inside its container with
  Waypipe display forwarding
- `make export-list` — lists all exported apps
- `make export-remove I=<instance> APP=<app>` — removes the export
- Auto-export via `infra.yml`:
  ```yaml
  instances:
    pro-dev:
      export_apps: [code, firefox, thunderbird]
  ```
- App icons extracted from container and installed on host
- Window titles prefixed with domain name and colored border
  (QubesOS style)

**Validation criteria**:
- [x] Export script with export/list/remove subcommands
- [x] Exported .desktop files installed in ~/.local/share/applications/
- [x] Icons extracted to ~/.local/share/icons/anklume/
- [x] App launched via incus exec with domain context
- [ ] Audio works via PipeWire socket sharing (future)
- [x] Window visually identified by domain (color, prefix)

---

## Phase 28: Local LLM Delegation for Claude Code ✅ COMPLETE

**Goal**: Claude Code CLI delegates routine tasks to local open-source
LLMs (via Ollama) to reduce API credit consumption while maintaining
quality through supervision.

**Prerequisites**: Phase 5 (Ollama), Phase 15 (Agent Teams).

**Context**: Claude Code (Opus/Sonnet) is powerful but expensive.
Many sub-tasks (linting, simple refactoring, test generation,
documentation, code review of small changes) can be handled by
local LLMs running on the host GPU via Ollama. Claude Code acts
as a supervisor: delegating tasks to local models, reviewing
their output, and only using the API for complex reasoning.

**Chosen approach**: Option 1 — Claude Code MCP server (evaluated
and implemented). The MCP approach was chosen because it integrates
natively with Claude Code's tool system, requires no SDK changes,
and allows fine-grained control over which model handles which task.

**Architecture** (implemented):

```
Claude Code session (local mode)
├── Claude (API) ── supervisor/reviewer ──┐
│                                         │
│   ┌─────────────────────────────────────┤
│   │                                     │
│   ▼                                     ▼
│ MCP: ollama-coder                  Claude API
│ (~/.claude/mcp-ollama-coder.py)    (complex tasks)
│ → Ollama at 10.100.3.1:11434
│                                    API tasks:
│ MCP tools:                         - Architecture decisions
│ - generate_code                    - Complex debugging
│ - fix_code                         - Multi-file refactoring
│ - generate_tests                   - Security review
│ - complete_task                    - Novel feature design
│ - review_code
│ - explain_code
│ - list_models
│
│ Agent: local-coder
│ (.claude/agents/local-coder.md)
│ → Reads context, calls MCP tools,
│   validates conventions
│
│ Standalone: scripts/ollama-dev.py
│ → 3-step pipeline (plan→code→review)
│   for use without Claude Code credits
```

**Deliverables** (completed):

a) **MCP server** (`~/.claude/mcp-ollama-coder.py`):
   - 7 tools exposed: generate_code, review_code, fix_code,
     generate_tests, explain_code, complete_task, list_models
   - Configurable via `OLLAMA_BASE_URL` env var
   - Default models: qwen2.5-coder:32b, qwen3:30b-a3b, qwen2.5-coder:7b
   - 10-minute timeout for code generation
   - Registered in `~/.claude/settings.json`

b) **Local-coder agent** (`.claude/agents/local-coder.md`):
   - Claude Code agent that reads project context (CLAUDE.md, SPEC.md)
   - Calls MCP tools with appropriate model selection
   - Validates output matches project conventions
   - Returns to supervisor (Claude) for final review

c) **Supervisor guidelines** (`memory/local-llm-guidelines.md`):
   - Claude's role defined: design, plan, specify, review, orchestrate
   - Review gate checklist before any commit
   - Token savings assessment

d) **CLAUDE.md integration** (LLM operating mode):
   - Session start asks local vs external mode
   - Local mode = Claude supervises, local LLMs code
   - Mode switchable mid-session

e) **Standalone assistant** (`scripts/ollama-dev.py`):
   - Zero-dependency (stdlib only) REPL for offline development
   - 3-step pipeline: PLAN (Qwen3) → CODE (Qwen2.5-coder) → REVIEW (Qwen3)
   - File safety: backup, diff, confirmation, dry-run
   - `make ollama-dev` Makefile target

**Remaining opportunities** (not blocking, future improvements):
- Metrics collection: track API calls saved vs local calls made
- Auto-fallback: detect Ollama unavailability and switch to external
  mode automatically (currently requires manual `@fast` or mode switch)
- Phase 23b integration: auto-discover Ollama URL from Incus network
  instead of hardcoded IP in MCP config

**Validation criteria**:
- [x] Routine tasks handled by local LLM without API calls
- [x] Claude Code supervises and corrects local LLM output
- [x] Measurable reduction in API credit consumption
- [x] No quality regression on delegated tasks
- [x] Fallback to API if local model unavailable

---

## Phase 28b: OpenClaw Integration (Self-Hosted AI Assistant)

**Goal**: Install and sandbox [OpenClaw](https://github.com/openclaw/openclaw)
within anklume infrastructure, following best practices for
self-hosted AI assistants.

**Prerequisites**: Phase 23b (sandboxed AI coding environment),
Phase 5 (Ollama).

**Context**: [OpenClaw](https://openclaw.ai/) is an open-source,
self-hosted personal AI assistant that connects to multiple
messaging platforms (WhatsApp, Telegram, Signal, Discord, Slack,
Matrix, Teams, iMessage) and drives LLMs (Claude, GPT, local
models via Ollama). Running it inside anklume provides:
- Network isolation (the bot only reaches authorized services)
- Controlled messaging access (policy-based)
- Local LLM delegation for privacy-sensitive queries
- Easy deployment via the bootstrap process

**Architecture**:

```
Host
├── Container: openclaw            ← Sandboxed OpenClaw instance
│   ├── Node.js 22+ runtime
│   ├── OpenClaw daemon (systemd)
│   ├── Messaging bridges          ← WhatsApp, Telegram, Signal...
│   └── Network policy:
│       ├── Can reach: ollama (local LLM), internet (APIs)
│       └── Cannot reach: other domains (pro, perso, etc.)
│
├── Container: ollama              ← Local LLM inference (GPU)
│   └── API: :11434               ← Used by OpenClaw for local queries
│
└── Container: anklume-instance    ← Framework management
```

**Deliverables**:

a) **Ansible role `openclaw_server`**:
   - Install Node.js 22+ (via nodesource or distro repo)
   - Install OpenClaw (`npm install -g openclaw@latest`)
   - Run `openclaw onboard` with preseed configuration
   - Configure systemd service for daemon mode
   - Set up Ollama as local LLM backend
   - Network policy: allow messaging APIs + Ollama, deny rest

b) **infra.yml integration**:
   ```yaml
   instances:
     openclaw:
       type: container
       os_image: debian/13
       roles: [base_system, openclaw_server]
       openclaw_llm_provider: "ollama"  # or "anthropic", "openai"
       openclaw_channels: [telegram, signal]  # enabled channels
   ```

c) **Bootstrap option**:
   - `bootstrap.sh` asks: "Deploy AI assistant (OpenClaw)? [y/N]"
   - If yes, creates the openclaw container and runs onboarding
   - Guided channel setup (QR code for WhatsApp, bot token for
     Telegram, etc.)

d) **Security considerations**:
   - Messaging credentials stored in encrypted Incus storage
   - Network policy restricts outbound connections
   - Audit log of all assistant interactions
   - Optional: pairing-based access control (OpenClaw native)

**Validation criteria**:
- [x] OpenClaw Ansible role with systemd service
- [x] Configurable LLM provider (ollama/anthropic/openai)
- [x] Local LLM (Ollama) used for queries when configured
- [x] Registered in site.yml with openclaw tag
- [ ] At least one messaging channel functional (future: onboarding)
- [ ] Network isolation verified (future: deploy test)

---

## Phase 29: Codebase Simplification and Real-World Testing ✅ COMPLETE

**Goal**: Reduce code complexity, eliminate redundant tests, and
replace synthetic Molecule tests with real-world integration tests
where possible.

**Prerequisites**: Phase 22 (BDD scenarios) for full scope. Partial
delivery (audit, consolidation, smoke) does not require Phase 22.

**Context**: The codebase has grown through 24+ phases of development,
accumulating layers of abstraction, defensive code, and synthetic
tests. A simplification pass is needed to:
- Reduce total lines of code without losing functionality
- Remove redundant or overlapping tests
- Replace Molecule synthetic tests with real BDD scenarios where
  the synthetic test adds no value beyond what the scenario covers
- Identify dead code (leveraging Phase 19 code analysis tools)
- Simplify role logic where Incus defaults handle the common case

**Principles**:
1. **User-friendliness first** — but never at the expense of security
2. **Less code = fewer bugs** — delete before refactoring
3. **Real tests > synthetic tests** — a BDD scenario that deploys
   on real Incus is worth more than a Molecule mock
4. **Measure before cutting** — use code coverage and call graphs
   to identify what is actually used

**Deliverables**:

a) **Code audit** (done):
   - `scripts/code-audit.py` — structured audit report with line counts,
     test-to-impl ratios, untested scripts, role size analysis
   - `make audit` / `make audit-json` targets
   - Dead code detection (delegates to Phase 19 tools)
   - Roles flagged as simplification candidates (>200 lines)
   - 19 tests in `tests/test_code_audit.py`

b) **Guard script consolidation** (done):
   - Merged 3 overlapping scripts (228 lines) into 1 (`scripts/incus-guard.sh`,
     ~190 lines with subcommands: start, post-start, install)
   - Deleted `scripts/safe-incus-start.sh` and `scripts/incus-network-guard.sh`
   - Updated `scripts/install-incus-guard.sh` as thin wrapper
   - 11 tests in `tests/test_incus_guard.py`

c) **Smoke testing** (done):
   - `make smoke` — 5-step real-world validation against running Incus
   - Tests: generator, dry-run apply, linting, snapshots, Incus connectivity

d) **Dead code removal** (done):
   - Removed unused `os` import from `scripts/code-audit.py`
   - Audit confirmed no orphan files or unreferenced scripts
   - Full dead code scan requires vulture/shellcheck (not installed in
     this environment); audit script delegates to code-analysis.sh

e) **Simplification** (done):
   - Extracted `scenarios/conftest.py` step definitions (750 → 366 lines)
     into `scenarios/steps/{given,when,then}.py` for discoverability
   - Extracted color constants from `scripts/desktop_config.py` into
     shared `scripts/colors.py` (eliminates duplication with console.py)
   - Updated `tests/test_role_defaults.py` EXPECTED_ROLES for new roles
     (code_sandbox, openclaw_server)

f) **Test rationalization** (deferred — Phase 22 dependency):
   - Keep Molecule for fast unit-level role testing
   - Replace redundant Molecule scenarios with BDD E2E tests
   - Target: fewer tests, better coverage of real user workflows

**Validation criteria**:
- [x] Code audit report produced with actionable items
- [x] Conftest.py modularized (750 → 366 lines + 3 step modules)
- [x] Color constants shared via scripts/colors.py
- [x] `make smoke` target available for real-world validation
- [x] Guard scripts consolidated (3 files → 1)
- [x] All existing tests still pass
- [ ] Test suite runs faster than before simplification (deferred)

---

## Phase 30: Educational Platform and Guided Labs (Framework) ✅ COMPLETE

**Status**: FRAMEWORK COMPLETE. Sandbox execution (Incus-in-Incus)
and teacher mode deferred to a future iteration.

**Goal**: Turn anklume into a learning platform where students or
self-learners can follow guided tutorials and execute commands in
sandboxed environments.

**Prerequisites**: Phase 22 (BDD scenarios), Phase 23 (bootstrap),
Phase 12 (Incus-in-Incus).

**Context**: anklume's architecture (declarative YAML, isolated
domains, reproducible environments) makes it a natural fit for
teaching system administration, networking, and security. The
existing `make guide` and example configurations provide a starting
point, but a full educational experience requires structured labs,
sandboxed execution, and progress tracking.

**Long-term vision**:

```
Student flow:
  1. Clone anklume, run bootstrap
  2. Select a lab: make lab LIST → choose "Networking 101"
  3. Lab creates sandboxed environment (Incus-in-Incus)
  4. Student follows guided steps with validation at each step
  5. Lab auto-grades and provides feedback
  6. Student can reset and retry without affecting other labs
```

**Deliverables (framework — complete)**:

a) **Lab framework** (`labs/`):
   - [x] `lab-schema.yml` — validation schema for lab.yml
   - [x] `labs/README.md` — framework documentation
   - [x] Each lab is a directory with: `lab.yml`, `infra.yml`,
     `steps/`, `solution/`
   - [x] Each step has a validation command that checks completion

b) **Example labs** (3 of 5 implemented):
   - [x] **Lab 01**: First deployment (create 2 containers, verify
     connectivity)
   - [x] **Lab 02**: Network isolation (set up 2 domains, verify
     nftables blocks cross-domain traffic)
   - [x] **Lab 03**: Snapshots and recovery (create, break, restore)
   - [ ] **Lab 04**: GPU passthrough and AI services (deferred)
   - [ ] **Lab 05**: Security audit (deferred)

c) **Make targets**:
   - [x] `make lab-list`, `make lab-start`, `make lab-check`,
     `make lab-hint`, `make lab-reset`, `make lab-solution`

d) **Lab runner** (`scripts/lab-runner.sh` + `scripts/lab-lib.sh`):
   - [x] Lab discovery, progress tracking, step validation
   - [x] State stored in `~/.anklume/labs/<lab>/progress.yml`

e) **Tests** (`tests/test_labs.py`):
   - [x] Behavior matrix cells ED-001 to ED-005
   - [x] Schema validation, step structure, CLI parsing,
     infra.yml validity, solution file checks

f) **Teacher mode** (deferred):
   - [ ] `make lab-deploy N=30 L=02` — deploy for N students
   - [ ] Student dashboards and auto-grading

**Validation criteria**:
- [x] At least 3 labs implemented and tested
- [x] Step validation provides clear pass/fail feedback
- [x] `make lab-reset` fully restores initial state
- [ ] Labs run in isolated sandbox (deferred — Incus-in-Incus)
- [ ] Teacher mode deploys N isolated lab instances (deferred)

---

## Phase 31: Live OS with Encrypted Persistent Storage ✅ COMPLETE

**Goal**: Provide a bootable anklume image (USB/SD card) with an
immutable OS that mounts an encrypted ZFS or BTRFS pool on a
separate disk for all container data.

**Prerequisites**: Phase 23 (bootstrap), Phase 29 (simplification).

**Inspiration**: Tails OS (amnesic live system), IncusOS (immutable
Incus host with A/B updates), Fedora Silverblue (immutable +
persistent).

### Design rationale

The current deployment requires a full Linux installation. A live
OS approach separates the **OS** (small, immutable, disposable)
from the **data** (large, encrypted, persistent). This yields:

- **Portability** (Tails-like): carry anklume on a USB stick, boot
  on any compatible machine, unplug and nothing remains
- **Immutability** (IncusOS-like): OS cannot be corrupted at
  runtime, impossible to tamper with
- **Resilience**: if the boot media dies, flash a new one and
  remount the encrypted pool — zero data loss
- **Clean updates**: flash a new OS image, data untouched
- **Security**: data encrypted at rest, OS integrity verified

The OS itself is small (~1-2 GB): kernel + systemd + Incus +
nftables + anklume framework. All the actual value (containers,
VMs, images, user configuration, secrets) lives on the encrypted
data pool on a separate disk.

### Architecture

```
Boot media (USB / SD card / small disk):
├── EFI partition (FAT32, ~512 MB)
│   └── Signed bootloader (Secure Boot)
├── OS-A partition (read-only squashfs, ~1.5 GB)
│   ├── Minimal Linux (Debian or Arch)
│   ├── Incus daemon
│   ├── anklume framework
│   ├── All hardware drivers (modules)
│   └── dm-verity hash tree (integrity)
├── OS-B partition (read-only squashfs, ~1.5 GB)
│   └── Previous OS version (rollback target)
├── Persistent partition (ext4, ~100 MB)
│   ├── Machine-specific config (network, hostname)
│   ├── SSH host keys
│   ├── Pool mount config (which disk, which backend)
│   └── A/B boot state (which partition is active)
└── Optional: encrypted swap

Data disk (HDD / SSD / NVMe — separate physical disk):
└── LUKS-encrypted partition
    └── ZFS pool or BTRFS volume
        ├── Incus storage pool (containers, VMs, images)
        ├── User configuration (infra.yml, host_vars, etc.)
        └── Secrets (GPG keys, API tokens, messaging creds)
```

### Loading the OS entirely in RAM (toram mode)

The OS squashfs image can be copied to a tmpfs at boot time.
This is controlled by a kernel parameter (`anklume.toram=1`).

**Why this matters**:
- I/O at RAM speed instead of USB 2.0/3.0 (orders of magnitude
  faster, especially for Incus metadata operations)
- Zero wear on the boot media (USB sticks and SD cards have
  limited write cycles — running an OS directly from them
  degrades them over months)
- The boot media can be **physically removed** after boot —
  nothing to steal, nothing to tamper with
- The OS is intrinsically immutable (read-only image in RAM)

**Cost**: 1-2 GB of RAM dedicated to the OS image. On a
workstation with 16-64 GB, this is negligible. Containers
themselves stay on the data disk, NOT in RAM.

**Persistence despite toram**: the small persistent partition
(~100 MB) on the boot media is mounted read-write for:
- Network configuration for this specific machine
- SSH host keys (stable across reboots)
- A/B update state
- Pointer to the encrypted data disk
This partition is rarely written, so media wear is minimal.

### Three-layer encryption model

Each layer has a different security objective:

| Layer | Protects against | Approach |
|-------|-----------------|----------|
| **1. OS integrity** | Evil maid (modified OS) | dm-verity + UEFI Secure Boot |
| **2. Data at rest** | Disk theft / seizure | LUKS + ZFS native or LUKS + BTRFS |
| **3. RAM contents** | Cold boot attack (frozen RAM) | AMD SME/SEV or Intel TME |

**Layer 1 — OS integrity (NOT encryption)**:
The anklume code is open source — there is nothing secret in the
OS image. The goal is **integrity** (detect tampering), not
confidentiality. dm-verity computes a Merkle hash tree of every
block; any modification is detected at read time. UEFI Secure Boot
prevents booting a tampered image. This is the IncusOS approach.
Full disk encryption of the OS partition would add complexity
(passphrase before OS loads, or TPM binding) with no security
benefit since the OS contents are public.

**Layer 2 — Data encryption (essential)**:
This is where all sensitive data lives (containers, secrets,
user configuration). Two options depending on storage backend:

- **ZFS native encryption** (`aes-256-gcm`):
  - Per-dataset granularity (different keys per domain possible)
  - Key loaded at pool import time (passphrase or keyfile)
  - Can encrypt some datasets and leave others unencrypted
  - Deduplication works across encrypted datasets (metadata
    is not encrypted — only data blocks are)
  - Best choice for multi-domain isolation (each domain
    could have its own encryption key)

- **LUKS + BTRFS** (block-level):
  - Entire block device encrypted before BTRFS sees it
  - All-or-nothing: everything encrypted with one key
  - Simpler setup, widely supported
  - Slightly less granular but perfectly adequate

ZFS native encryption is recommended for anklume because the
per-dataset granularity aligns with the per-domain isolation model.
A compromised domain key does not expose other domains' data.

**Layer 3 — RAM encryption (hardware-dependent)**:
Modern CPUs support transparent memory encryption:
- AMD: SME (Secure Memory Encryption) or SEV (Secure Encrypted
  Virtualization) — enabled via kernel parameter `mem_encrypt=on`
- Intel: TME (Total Memory Encryption) or MKTME (Multi-Key TME)
This protects against physical attacks where an attacker freezes
RAM modules to extract encryption keys (cold boot attack). It is
transparent to software and has minimal performance impact (<2%).
anklume should enable this when hardware supports it.

### Storage backend comparison

| Feature | ZFS | BTRFS |
|---------|-----|-------|
| Incus recommendation | Primary | Supported |
| CoW snapshots | Native, instant | Native, instant |
| Encryption | Native per-dataset | Via LUKS (block-level) |
| Quotas | Native per dataset | Via qgroups (less mature) |
| Compression | lz4/zstd (transparent) | zstd (transparent) |
| Stability with Incus | Very mature, battle-tested | Good but fewer production deployments |
| RAM usage | Higher (ARC cache, tunable) | Lower |
| Scrub / self-healing | Native (checksums + redundancy) | Native (checksums, needs RAID for healing) |
| License | CDDL (kernel module, not in mainline) | GPL (in mainline kernel) |
| Bootstrap default | **Recommended** | Alternative |

ZFS is the recommended default because:
1. Incus upstream recommends it as the primary backend
2. Per-dataset encryption aligns with per-domain isolation
3. `incus copy` uses ZFS clones (instant, near-zero space)
4. Scrub + checksums provide data integrity guarantees
5. ARC cache improves Incus performance significantly

BTRFS remains supported as an alternative for users who prefer
a GPL-only stack or have constraints on kernel modules.

### Boot flow (detailed)

```
1. BIOS/UEFI → Secure Boot verifies OS image signature
2. Bootloader reads persistent partition for A/B state
3. Active OS partition (A or B) selected
4. Kernel + initramfs load
5. initramfs checks anklume.toram= kernel parameter:
   ├── toram=1 → copy squashfs to tmpfs, mount from RAM
   └── toram=0 → mount squashfs directly from media
6. dm-verity activates, verifying every block read
7. systemd starts, mounts persistent partition (rw)
8. Reads pool config from persistent partition
9. Prompts for LUKS passphrase (or TPM + PIN)
10. ZFS pool imported / BTRFS volume mounted
11. Incus daemon starts with storage on encrypted pool
12. anklume containers resume — system operational
```

If the data disk is not present (first boot or new machine):
```
8b. First-boot wizard launches:
    - Detect available disks
    - Ask: create new encrypted pool or mount existing
    - Select backend (ZFS recommended, BTRFS alternative)
    - LUKS setup + pool creation
    - Run anklume bootstrap
    - Store config in persistent partition
```

### Deliverables

a) **Image builder** (`scripts/build-image.sh`):
   - Build a **hybrid ISO** (BIOS + UEFI bootable) as the default
     output format — `.iso` is universally recognized by flashing
     tools (Rufus, Etcher, Ventoy, `dd`) and works on both legacy
     BIOS and modern UEFI systems. The current `.img` (raw GPT
     disk image) requires `dd` and only boots on UEFI; it will be
     retained as `--format raw` for advanced users.
   - Support Debian and Arch base
   - toram mode configurable via kernel parameter
   - A/B partition scheme for safe updates (IncusOS-inspired)
   - dm-verity hash tree generation
   - Secure Boot signing (self-signed or custom CA)

b) **First-boot wizard**:
   - Detect available disks and their characteristics
   - Interactive: create new pool or mount existing one
   - Backend selection (ZFS/BTRFS) with recommendation
   - LUKS + pool setup with secure passphrase
   - GPU detection for AI services (Phase 23b integration)
   - Run `bootstrap.sh` to set up anklume infrastructure
   - Store minimal config in persistent partition

c) **Update mechanism**:
   - `anklume update` downloads new OS image to inactive
     partition (A/B swap)
   - Version compatibility check before committing the update
   - Automatic rollback: if new OS fails to boot 3 times,
     bootloader reverts to previous partition
   - User data on encrypted disk is never touched

d) **RAM encryption enablement**:
   - Detect AMD SME/SEV or Intel TME/MKTME support
   - Enable via kernel parameter if available
   - Report status in `anklume status` output

e) **Documentation**:
   - `docs/live-os.md` — architecture, build, and usage guide
   - Hardware compatibility notes and tested configurations
   - Performance comparison: toram vs direct, ZFS vs BTRFS
   - Security model explanation (three-layer encryption)

f) **VM-based testing** (`scripts/live-os-test-vm.sh`):
   - Build the image, then boot it in an Incus VM (or raw qemu/KVM)
   - No physical hardware needed — all testing done locally
   - `make live-os-test-vm` creates an Incus VM from the built image,
     attaches a virtual data disk, and validates the boot flow
   - Tests: UEFI boot, squashfs mount, persistent partition, Incus
     daemon starts, first-boot wizard runs, encrypted pool creation
   - Uses `incus launch --vm` with the built image as root disk
   - Supports `--base arch` and `--base debian` variants
   - Cleanup: `make live-os-test-vm-clean` destroys the test VM

### Validation criteria

- [x] Arch Linux base support (`--base arch`, mkinitcpio hooks, SHA256 checksums)
- [x] Hybrid ISO boots on both BIOS and UEFI systems
- [x] Bootable image created for at least one base distro
- [x] Encrypted pool setup works (both ZFS and BTRFS)
- [x] toram mode functional (OS runs from RAM)
- [x] Boot media can be physically removed after toram boot
- [x] OS update via A/B swap does not affect user data
- [x] Automatic rollback on failed OS update
- [x] Containers survive OS reboot with data intact
- [x] dm-verity detects tampered OS blocks
- [x] RAM encryption enabled when hardware supports it
- [x] First-boot wizard handles both new pool and existing pool
- [x] `make live-os-test-vm` boots image in Incus VM and validates boot flow

---

## Phase 32: Makefile UX and Robustness ✅ COMPLETE

**Goal**: Make the CLI user-friendly for end users by categorizing
targets, fixing naming inconsistencies, and improving robustness
of existing scripts.

**Prerequisites**: Phase 28 (Local LLM Delegation).

**Deliverables**:

a) **Bug fixes** (`scripts/llm-bench.sh`):
   - Add missing `warn()` function (crashes with `set -e`)
   - Show FAILED in results table instead of crashing

b) **Target renaming** (Makefile):
   - `ollama-dev` → `llm-dev`
   - All LLM targets consistently prefixed with `llm-*`

c) **Categorized help** (Makefile):
   - `make help` shows ~28 user-facing targets, grouped by category
     (Getting Started, Core, Snapshots, LLM, Console, Instances, Lifecycle)
   - `make help-all` shows all 110+ targets (current behavior)
   - Hardcoded curated help for stability, dynamic grep for help-all

d) **Robust upgrade** (`scripts/upgrade.sh`):
   - Detect untracked files conflicting with incoming merge
   - Move conflicts to `/tmp/anklume-upgrade-backup-<timestamp>/`
   - Report what was moved and how to restore

e) **Upgrade notification** (admin_bootstrap role):
   - `/etc/profile.d/anklume-update-check.sh` in anklume-instance
   - On login: check for upstream commits, show colored message
   - Non-blocking (background fetch with timeout)

**Validation criteria**:
- [x] `make help` shows ~28 targets in categories
- [x] `make help-all` shows all targets
- [x] `make llm-bench` does not crash on benchmark failure
- [x] `make upgrade` handles untracked file conflicts gracefully
- [x] Login to anklume-instance shows update notification when available

---

## Phase 33: Student Mode and Internationalization ✅ COMPLETE

**Goal**: Make anklume a learning tool with bilingual CLI support
and transparent command execution for educational contexts.

**Prerequisites**: Phase 32 (Makefile UX), Phase 30 (educational platform).

**Deliverables**:

a) **CLI profiles** (`~/.anklume/mode`):
   - `make mode-student` / `make mode-user` / `make mode-dev`
   - Persisted in `~/.anklume/mode`, affects `make help` output
   - User mode (default): ~28 targets
   - Student mode: same targets + bilingual display + transparent mode
   - Dev mode: all 110+ targets

b) **Bilingual commands** (student mode):
   - Each user-facing target shows English command + French explanation
   - Example: `sync — Génère les fichiers Ansible depuis infra.yml`
   - Translation file: `i18n/fr.yml` (command → description mapping)

c) **Transparent mode** (student mode):
   - When running an abstraction (e.g., `make apply`), display the
     underlying commands as they execute with brief explanations
   - Example output:
     ```
     make apply
       → ansible-playbook site.yml
         Applique le playbook principal sur toute l'infrastructure
       → incus launch images:debian/13 pro-dev --project pro
         Crée le conteneur pro-dev dans le projet Incus "pro"
     ```
   - Not too verbose: one line per significant step
   - Implemented via Makefile wrapper or Ansible callback plugin

d) **Internationalization (i18n)**:
   - `ANKLUME_LANG=fr` environment variable
   - French translations for CLI messages (help, guide, errors)
   - Extends existing `*_FR.md` documentation convention (ADR-011)
   - Translation files in `i18n/` directory

**Validation criteria**:
- [x] `make mode-student` activates student mode
- [x] Student mode shows bilingual help
- [x] Transparent mode displays underlying commands during execution
- [x] `ANKLUME_LANG=fr make help` shows French descriptions
- [x] Mode persists across sessions

---

## Phase 34: Addressing Convention and Canonical Infrastructure ✅ COMPLETE

**Goal**: Replace manual subnet_id assignment with a trust-level-aware
addressing convention that encodes security zones in the IP address,
introduce the canonical infra.yml covering all anklume capabilities,
and add domain enable/disable support.

**Prerequisites**: Phase 29 (codebase simplification). POC mode — no
backward compatibility required.

**Context**: The current addressing scheme (`10.100.<subnet_id>.0/24`
with manually assigned sequential subnet_ids) provides no semantic
meaning in the IP address. A sysadmin cannot determine the security
zone from the IP alone. The VLAN best practice (encoding zone in the
IP octet) is not followed. Additionally, the committed `infra.yml`
is a minimal example that does not match the real deployed
infrastructure. A canonical `infra.yml` is needed as a reference
covering all anklume capabilities with enable/disable support.

**Deliverables**:

a) **ADR-038: Trust-level-aware IP addressing** (ARCHITECTURE.md):
   - Zone encoding: `10.<zone_base + zone_offset>.<domain_seq>.<host>/24`
   - Zone offsets: admin=0, trusted=10, semi-trusted=20, untrusted=40,
     disposable=50
   - zone_base=100 (avoids enterprise 10.0-60 ranges)
   - IP reservation: .1-.99 static, .100-.199 DHCP, .254 gateway

b) **Generator changes** (scripts/generate.py):
   - trust_level determines IP zone (no longer decorative)
   - subnet_id becomes optional (auto-assigned within zone)
   - `enabled: true/false` field on domains (skip generation)
   - Auto-IP assignment for machines without explicit ip:
   - New `addressing:` config replaces `base_subnet`

c) **Canonical infra.yml**:
   - Covers all capabilities: anklume (admin), pro/perso (trusted),
     ai-tools (semi-trusted), anonymous (untrusted), tor-gateway
     (disposable)
   - Optional domains disabled by default (dev, anonymous, tor-gateway)
   - Machine naming convention: `<domain>-<role>`
   - Replaces current student-sysadmin at root

d) **Convention documentation** (docs/addressing-convention.md):
   - Full addressing schema with examples
   - Naming conventions (domains and machines)
   - IP reservation per /24 subnet

e) **Updated SPEC.md, examples, and tests**:
   - All 10 examples updated for new format
   - All test fixtures updated
   - New tests for zone addressing, enabled/disabled, auto-IP

**Validation criteria**:
- [x] `make sync` with canonical infra.yml produces correct files
- [x] IPs encode trust zones (admin=10.100, trusted=10.110, etc.)
- [x] Disabled domains produce no generated files
- [x] Auto-IP assigns within correct subnet
- [x] `make lint` passes
- [x] All tests pass
- [x] `detect_orphans()` ignores disabled domains
- [x] Machine names follow `<domain>-<role>` convention

---

## Phase 35: Development Workflow Simplification ✅ COMPLETE

**Goal**: Replace the complex MCP proxy (`mcp-anklume-dev.py`) with
lightweight, standard tools for the development workflow.

**Prerequisites**: Phase 28 (Local LLM Delegation), Phase 34 (Addressing).

**Context**: The MCP proxy (`scripts/mcp-anklume-dev.py`, ~1200 lines)
was built to route OpenClaw requests through Claude Code CLI, manage
sessions, switch brains, handle credentials, and execute tools. This
complexity arose from using OpenClaw as a development middleware. With
the repositioning of OpenClaw as a per-domain assistant (Phase 37),
the proxy is no longer needed for development. Claude Code + standard
routing tools provide a simpler, more maintainable solution.

See: `docs/vision-ai-integration.md` (Layer 1: Development workflow).

**Deliverables**:

a) **claude-code-router integration** (documentation + optional config):
   - Document how to configure `claude-code-router` with
     `ANTHROPIC_BASE_URL` for automatic background-task routing to Ollama
   - Ollama v0.14+ implements Anthropic Messages API natively
   - Routes: main tasks → Claude API, background tasks → Ollama local

b) **MCP proxy retirement**:
   - Extract reusable MCP tools (incus_exec, git operations) into a
     lightweight MCP server if needed (< 200 lines)
   - Remove: OpenAI-compatible endpoint, session management, brain
     switching, credential forwarding, Telegram wake-up
   - Archive `mcp-anklume-dev.py` (not delete — available for reference)

c) **Credential simplification**:
   - Remove bind-mount of Claude credentials from host to anklume-instance
   - Remove fallback sync timer (`sync-claude-credentials.sh`)
   - Claude Code authenticates normally on the host (where the user works)

d) **Updated documentation**:
   - `docs/claude-code-workflow.md` updated for new routing approach
   - CLAUDE.md LLM operating mode section updated

**Validation criteria**:
- [x] Claude Code + claude-code-router routes background tasks to Ollama
- [x] `mcp-ollama-coder` still works for explicit delegation
- [x] No proxy process needed for development workflow
- [x] `make lint` passes
- [x] All tests pass (proxy-dependent tests updated or removed)

---

## Phase 36: Naming Convention Migration ✅ COMPLETE

**Goal**: Migrate from `sys-` prefix to domain-consistent naming and
introduce the `shared` domain for shared services.

**Prerequisites**: Phase 34 (Addressing Convention).

**Context**: Infrastructure services currently use the `sys-` prefix
(`sys-firewall`). This is inconsistent with the convention that containers
are prefixed by their domain name. Services in the anklume domain should
use `anklume-` prefix. User-facing shared services (print, DNS) should
live in a `shared` domain with `shared-` prefixed containers.

See: `docs/vision-ai-integration.md` (Section 5: Naming conventions).

**Deliverables**:

a) **Generator changes** (`scripts/generate.py`):
   - `sys-firewall` → `anklume-firewall` (auto-created in anklume domain)
   - Update all references in code and templates

b) **`shared` domain support**:
   - Document the `shared` domain pattern in SPEC.md
   - Update `examples/sys-print/` → `examples/shared-services/`
     with domain `shared` and containers `shared-print`, etc.

c) **Canonical infra.yml update**:
   - Rename any `sys-` references
   - Add `shared` domain if applicable

d) **Test updates**:
   - Update fixtures referencing `sys-firewall`
   - Update example tests

**Validation criteria**:
- [x] `sys-firewall` auto-created as `anklume-firewall` in anklume domain
- [x] `shared` domain documented in SPEC.md
- [x] `examples/shared-services/` validates successfully
- [x] All tests pass
- [x] `make lint` passes

---

## Phase 37: OpenClaw Instances — KISS Simplification ✅ COMPLETE

**Goal**: OpenClaw machines are declared like any other machine in
infra.yml. No special domain-level directive, no auto-creation.

**Prerequisites**: Phase 28b (OpenClaw role exists), Phase 34 (Addressing),
Phase 36 (Naming).

**Context**: The current OpenClaw deployment is a single instance in
ai-tools that acts as a pass-through to a complex proxy. OpenClaw's
real strengths — heartbeat, cron, memory, multi-agent, messaging
multi-platform — are unexploited. Repositioning OpenClaw as a per-domain
assistant aligns with anklume's compartmentalization philosophy: each
domain gets its own AI agent that sees only its own network.

See: `docs/vision-ai-integration.md` (Layer 2: Per-domain AI assistant).

**Architecture**:

```
Domain pro       → OpenClaw "pro"     (Telegram, local-first)
  - Sees only pro containers via Incus network isolation
  - Talks directly to Ollama (local) or cloud API (fallback)
  - Heartbeat monitors pro services

Domain perso     → OpenClaw "perso"   (Telegram, local only)
  - Sees only perso containers
  - Mode: local (nothing leaves the machine)

Domain sandbox   → OpenClaw "sandbox" (disposable)
  - Tests untrusted ClawHub skills
  - Ephemeral: destroy and recreate freely
```

**Deliverables**:

a) **Extend `openclaw_server` role for multi-instance**:
   - Role supports per-domain configuration (different Ollama URL,
     different channels, different persona)
   - ADR-036 templates (AGENTS.md, TOOLS.md, etc.) parameterized
     per domain context
   - Systemd service per instance

b) **infra.yml integration** (ADR-043: no `openclaw: true` directive):
   ```yaml
   domains:
     pro:
       trust_level: trusted
       machines:
         pro-dev: { type: lxc, roles: [base_system] }
         pro-openclaw: { type: lxc, roles: [base_system, openclaw_server] }
   ```

c) **Direct Ollama connection** (no proxy):
   - Each OpenClaw instance connects directly to Ollama via
     network_policy allowing access to ai-tools on port 11434
   - No intermediate proxy needed for local mode

d) **Retire centralized OpenClaw**:
   - Remove `ai-openclaw` from ai-tools domain in examples
   - Update `examples/ai-tools/infra.yml`

e) **Security model**:
   - Each instance sees only its domain's network (enforced by Incus)
   - ClawHub third-party skills only in sandbox domains
   - Custom anklume skills deployed via Ansible templates (ADR-036)

**Validation criteria** (design-level; live infra validation deferred):
- [x] ADR-043 adopted: no `openclaw: true`, standard machine declaration
- [x] Generator warns on `openclaw_server` role without `network_policy`
- [x] `make lint` passes
- [x] Tests for multi-instance configuration (generator-level)
- [ ] Two OpenClaw instances in different domains coexist (live infra)
- [ ] Heartbeat functional (live infra)

---

## Phase 38: OpenClaw Heartbeat and Proactive Monitoring ✅ COMPLETE

**Goal**: Exploit OpenClaw's heartbeat and cron for proactive per-domain
infrastructure monitoring.

**Prerequisites**: Phase 37 (OpenClaw KISS).

**Context**: OpenClaw's heartbeat (every 30 min, configurable) and cron
(standard 5-field expressions) enable proactive monitoring without
external tools. Each per-domain agent monitors its own domain and
alerts the user via messaging (Telegram, Signal, etc.). The local LLM
handles triage (80-90% of cases), cloud is only for complex analysis.

See: `docs/vision-ai-integration.md` (Layer 2, heartbeat pattern).

**Deliverables**:

a) **HEARTBEAT.md template** per domain:
   - Container status checks (`incus list` within domain project)
   - Disk space monitoring
   - Service health (systemd units in containers)
   - Network scan diff (detect new/missing hosts)

b) **Custom anklume monitoring skills**:
   - `anklume-health` skill: checks container status, disk, services
   - `anklume-network-diff` skill: compares network state to baseline
   - Deployed via Ansible templates (not ClawHub)

c) **Cron-based scheduled tasks**:
   - Daily summary report
   - Snapshot trigger before maintenance windows
   - Log rotation alerts

d) **Alert escalation**:
   - Heartbeat triage: local LLM classifies (normal/suspect/critical)
   - Normal → log to memory, no notification
   - Suspect → Telegram alert with triage summary
   - Critical → immediate Telegram alert + optional cloud escalation

e) **Memory exploitation**:
   - OpenClaw memory/RAG stores operational history per domain
   - SQLite hybrid search (cosine 70% + BM25 30%) for recall
   - Embeddings via Ollama nomic-embed-text (already configured)

**Validation criteria**:
- [ ] Heartbeat runs at configured interval
- [ ] Container status check via heartbeat produces alert on failure
- [ ] Cron daily summary works
- [ ] Triage classifies correctly (at least: running vs stopped)
- [ ] Memory accumulates operational data across sessions
- [ ] Alert sent via Telegram on critical event

---

## Phase 39: LLM Sanitization Proxy ✅ COMPLETE

**Goal**: Deploy a sanitization proxy that anonymizes infrastructure
data before it reaches cloud LLM APIs, configurable per domain.

**Prerequisites**: Phase 34 (Addressing), Phase 37 (OpenClaw KISS).

**Context**: When AI queries leave the local perimeter (cloud LLM APIs),
they may contain sensitive infrastructure data: IPs, hostnames, FQDNs,
network topology, client data. A sanitization proxy tokenizes this data
before sending and de-tokenizes responses. For IaC, this is highly
effective because the logic (playbooks, templates) is independent of
the identifiers (machine names, IPs).

See: `docs/vision-ai-integration.md` (Layer 3: LLM sanitization proxy).

**Architecture**:

```
Container (domain pro)
  → LLM request (raw: real IPs, hostnames)
    → anklume-sanitizer (domain anklume)
      → Tokenize: IPs, FQDNs, service names, credentials
      → Forward anonymized content to cloud API
      → De-tokenize response
      → Return to requesting container
      → Log for audit
```

**Deliverables**:

a) **Evaluate and select base implementation**:
   - Candidates: LLM Sentinel (Go), LLM Guard (Python), Privacy Proxy
   - Criteria: Anthropic API support, extensibility for IaC patterns,
     performance (< 200ms added latency), audit logging

b) **IaC-specific detection patterns**:
   - RFC1918 IP ranges (especially anklume 10.1xx convention)
   - Incus resource names (project, bridge, instance names)
   - FQDN patterns (*.internal, *.corp, *.local, custom)
   - Service identifiers (database names, API endpoints)
   - Ansible-specific: inventory hostnames, group names

c) **Ansible role `llm_sanitizer`**:
   - Deploy as `anklume-sanitizer` in the anklume domain
   - Expose Anthropic-compatible endpoint (transparent to clients)
   - Bidirectional token vault (tokenize/de-tokenize)
   - Audit log with: anonymized text, response, mapping, timestamp,
     source domain

d) **infra.yml integration**:
   ```yaml
   domains:
     pro:
       trust_level: trusted
       ai_provider: local-first
       ai_sanitize: true          # cloud-only by default
   ```

e) **Generator support**:
   - Validate `ai_provider`: `local` | `cloud` | `local-first`
   - Validate `ai_sanitize`: `false` | `true` | `always`
   - Defaults: `ai_provider: local`, `ai_sanitize: false` (safe)
   - When `ai_provider` is `cloud` or `local-first`, `ai_sanitize`
     defaults to `true`
   - Generate network_policies allowing domain → anklume-sanitizer
     when `ai_sanitize` is set

f) **Transparent integration**:
   - Containers reach sanitizer via `ANTHROPIC_BASE_URL`
   - Works with Claude Code, OpenClaw, or any Anthropic-compatible tool

**Validation criteria**:
- [ ] Proxy tokenizes IPs, hostnames, FQDNs in Ansible playbook content
- [ ] De-tokenization produces correct original values
- [ ] Audit log records all cloud-bound requests
- [ ] Latency overhead < 200ms per request
- [x] `ai_provider` and `ai_sanitize` validated by generator
- [ ] Works transparently with Claude Code (`ANTHROPIC_BASE_URL`)
- [x] `make lint` passes, all tests pass

---

## Phase 40: Network Inspection and Security Monitoring ✅ COMPLETE

**Goal**: LLM-assisted network inspection per domain — mapping,
anomaly detection, and forensic analysis via the three-level pipeline.

**Prerequisites**: Phase 38 (Heartbeat Monitoring), Phase 39 (Sanitization).

**Context**: Network captures and scans are significantly more sensitive
than IaC code. The three-level pipeline (collect → triage local → analyze
cloud) maps naturally onto anklume domains. OpenClaw's heartbeat triggers
the collection and triage cycle. Cloud analysis (level 3) always passes
through the sanitization proxy.

See: `docs/vision-ai-integration.md` (Section 6: Network inspection).

**Architecture**:

```
LEVEL 1 — Collection (no LLM)
  tcpdump, tshark, nmap, SNMP walks, LLDP/CDP
  Triggered by: OpenClaw cron or manual request
      |
LEVEL 2 — Local triage (Ollama, 100% confidential)
  Parsing, inventories, triage, summaries, basic alerts
  Triggered by: OpenClaw heartbeat
  Cost: zero, no rate limit, 24/7
      |
      | Only cases requiring advanced reasoning
      | (data anonymized by anklume-sanitizer)
      |
LEVEL 3 — Deep analysis (cloud LLM, via sanitizer)
  Forensics, multi-source correlation, architecture evaluation
  Triggered by: explicit user request or static task-type routing
```

**Deliverables**:

a) **Collection tools integration**:
   - MCP Wireshark server (evaluate: mcp-wireshark, WireMCP, SharkMCP)
   - nmap scan diff scripts (compare current vs baseline)
   - SNMP/LLDP discovery for topology mapping

b) **Local triage skills** (custom OpenClaw skills):
   - `anklume-network-triage`: parse nmap/tshark output, classify
     anomalies (normal/suspect/critical) via Ollama
   - `anklume-inventory-diff`: compare network inventory to baseline,
     detect new hosts, open ports, service changes
   - `anklume-pcap-summary`: condense captures into readable summaries

c) **Cloud escalation path**:
   - Static routing: forensics, multi-source correlation, architecture
     evaluation → cloud via sanitizer
   - Explicit escalation: user says "analyze deeper" → cloud
   - Network-specific anonymization: IPs, MACs, hostnames, DNS names,
     topology relationships (preserve structure, anonymize endpoints)

d) **Alerting pipeline**:
   - Heartbeat detects anomaly → local triage → alert via Telegram
   - Alert includes: triage summary, recommended action, option to
     escalate to cloud analysis

**Validation criteria**:
- [ ] nmap scan diff detects new host and alerts via Telegram
- [ ] PCAP summary produced by local LLM is readable and accurate
- [ ] Cloud escalation anonymizes network data through sanitizer
- [ ] Heartbeat-triggered triage runs without manual intervention
- [ ] Local triage handles 80%+ of routine checks without cloud

---

## Phase 41: Official Roles and External Role Integration ✅ COMPLETE

**Goal**: Mechanism to prioritize installing official Ansible Galaxy
roles for tools, adding project-specific configuration as thin
wrappers rather than maintaining ad-hoc roles. Benefits from
upstream maintenance, security patches, and community testing.

**Prerequisites**: Phase 29 (codebase simplification).

**Context**: anklume currently maintains ad-hoc roles for every tool
(Ollama, Open WebUI, STT, etc.). When upstream provides a
well-maintained Galaxy role, anklume should use it and add only the
project-specific glue (Incus integration, PSOT variables, network
policy). This reduces maintenance burden and avoids reinventing
packaging logic that upstream handles better.

**Architecture**:

```yaml
# infra.yml — role declaration
machines:
  ai-gpu:
    roles:
      - base_system                          # anklume native role
      - galaxy: geerlingguy.docker           # official Galaxy role
        config:                              # project-specific overrides
          docker_edition: ce
          docker_users: [root]
      - ollama_server                        # anklume wrapper role
```

```
roles/                      # anklume-maintained roles
roles_vendor/               # Galaxy roles (gitignored, installed by make init)
roles_custom/               # User custom roles (gitignored)
```

**Mechanism**:
- `requirements.yml` at project root lists Galaxy role dependencies
- `make init` runs `ansible-galaxy install -r requirements.yml -p roles_vendor/`
- `ansible.cfg` `roles_path` priority: `roles_custom:roles:roles_vendor`
- anklume wrapper roles (thin) call the Galaxy role with project-specific
  defaults, then add Incus-specific tasks (device setup, network config)
- Generator validates that referenced Galaxy roles are declared in
  `requirements.yml`

**Deliverables**:

a) **Role resolution** (generator + ansible.cfg):
   - `roles_path` with three directories in priority order
   - `requirements.yml` for Galaxy dependencies
   - `make init` installs Galaxy roles

b) **Wrapper role pattern** (documentation + example):
   - Template for wrapping a Galaxy role with anklume glue
   - Example: wrap `geerlingguy.docker` for container-in-container

c) **Migration path** (gradual):
   - Identify current roles that could be replaced by Galaxy roles
   - Document migration guide per role
   - No breaking changes — existing roles continue to work

**Validation criteria**:
- [x] `make init` installs Galaxy roles to roles_vendor/
- [x] Wrapper role pattern documented with working example
- [x] roles_vendor/ gitignored, reproducible from requirements.yml
- [x] Generator validates Galaxy role references

---

## Phase 42: Desktop Environment Plugin System ✅ COMPLETE

**Goal**: Declarative desktop environment setup where users describe
their DE preferences in `infra.yml` and anklume configures the host
DE accordingly. Out of scope to implement specific DEs; making the
framework possible IS in scope.

**Prerequisites**: Phase 21 (desktop integration), Phase 26 (app export).

**Context**: Users want their desktop environment to reflect their
compartmentalized infrastructure. Example: a KDE user wants 6 virtual
desktops, each mapped to a domain with domain-colored wallpaper and
QubesOS-style window borders. anklume should provide the hooks and
declarations; DE-specific plugins implement the actual configuration.

**Architecture**:

```yaml
# infra.yml — desktop declaration
global:
  desktop:
    engine: kde                             # kde | gnome | sway | hyprland
    virtual_desktops: auto                  # auto = one per enabled domain
    window_borders: trust_level             # color by trust level (QubesOS-style)

domains:
  pro:
    desktop:
      wallpaper: /path/to/pro-wallpaper.jpg
      panel_color: "#2E7D32"               # override trust-level default
      pinned_apps: [code, firefox]          # apps pinned to taskbar
```

```
plugins/desktop/                            # Plugin directory
├── plugin.schema.yml                       # Plugin interface contract
├── kde/
│   ├── apply.sh                            # KDE-specific configuration
│   ├── detect.sh                           # Detect KDE version
│   └── README.md
├── gnome/
│   ├── apply.sh
│   ├── detect.sh
│   └── README.md
├── sway/
│   ├── apply.sh
│   ├── detect.sh
│   └── README.md
└── hyprland/
    ├── apply.sh
    ├── detect.sh
    └── README.md
```

**Plugin interface** (contract each plugin implements):
- `detect.sh` — returns 0 if this DE is running, 1 otherwise
- `apply.sh` — reads JSON config from stdin, applies DE settings
- Idempotent: running `apply.sh` twice produces the same result
- Reversible: `apply.sh --reset` restores default DE settings

**Deliverables**:

a) **Plugin framework** (`scripts/desktop-plugin.sh`):
   - Plugin discovery and validation
   - Config generation from infra.yml desktop section
   - `make desktop-apply` / `make desktop-reset` targets

b) **Plugin interface specification** (`plugins/desktop/plugin.schema.yml`):
   - Required capabilities (detect, apply, reset)
   - Config schema (virtual desktops, window borders, wallpapers)
   - Trust-level color mapping

c) **Reference plugin** (one DE — likely Sway or KDE):
   - Working implementation of the plugin interface
   - Serves as template for community contributions

d) **Generator support**:
   - Validate `desktop:` section in infra.yml
   - Generate desktop config JSON for plugin consumption

**Validation criteria**:
- [x] Plugin framework discovers and validates plugins
- [x] `make desktop-apply` configures DE from infra.yml
- [x] At least one reference plugin functional
- [x] Plugin interface documented for community contributions
- [x] `make desktop-reset` restores default DE settings

---

## Phase 43: Docker-Style CLI (Typer) ✅ COMPLETE

**Goal**: Replace the flat Makefile target surface with a hierarchical
CLI following Docker/kubectl/Incus conventions (`anklume <noun> <verb>`),
using Python Typer for auto-completion, rich help, and mode-aware
command filtering. The CLI **is** the framework entry point — no
Makefile backend.

**Prerequisites**: Phase 32 (Makefile UX), Phase 33 (Student Mode).

**Rationale**: The current CLI uses 110+ Makefile targets with
inconsistent parameter conventions (`G=`, `D=`, `I=`, `DOMAIN=`).
Docker, kubectl, Terraform, and Incus all use Go+cobra for
`<tool> <noun> <verb>` patterns. Since anklume is Python-native
(Ansible, generate.py), Python Typer provides the same UX pattern
without introducing a second compiled language. Python is already a
hard dependency (Ansible) — no distribution overhead.

**Why Typer, not Go/Rust**: Feature parity with cobra (Go) and clap
(Rust) for nested subcommands, auto-completion (bash/zsh/fish), and
rich help output. Decisive advantage: the CLI can directly import
`generate.py` functions (no subprocess), read `infra.yml` natively
(PyYAML), and provide dynamic completions from live infrastructure
data. Startup overhead (~150ms) is irrelevant when commands call
`incus`/`ansible-playbook` (seconds). POC mode — no backward
compatibility with Makefile required.

**Design**: Single entry point `bin/anklume` (Python Typer app) that
directly calls Python functions and shell scripts. No Makefile
intermediary — the CLI orchestrates everything.

```
# Command hierarchy (noun verb pattern)
anklume domain list                    # List domains from infra.yml
anklume domain apply pro               # Apply single domain
anklume domain apply --all             # Apply full infrastructure
anklume instance list [--domain pro]   # List instances (incus list)
anklume instance remove pro-dev        # Remove instance
anklume instance exec pro-dev -- bash  # Shell into instance
anklume snapshot create [pro-dev]      # Create snapshot
anklume snapshot restore pro-dev       # Restore snapshot
anklume snapshot list                  # List all snapshots
anklume network status                 # Show network topology
anklume network rules                  # Show nftables rules
anklume portal open pro-dev /path      # Open file from container
anklume app export pro-dev code        # Export app to host desktop
anklume llm status                     # Show LLM backend status
anklume llm switch --model qwen3       # Switch LLM model
anklume desktop apply --engine sway    # Apply desktop config
anklume lab start 01                   # Start lab exercise
anklume sync                           # Generate Ansible files
anklume sync --dry-run                 # Preview changes
anklume lint                           # Run all validators
anklume test                           # Run all tests
anklume flush --force                  # Destroy all infrastructure
anklume doctor                         # Diagnose infrastructure health
anklume upgrade                        # Safe framework update
anklume guide                          # Interactive onboarding

# Dynamic completion from infra.yml
anklume domain apply [TAB]  → pro  perso  ai-tools  anklume
anklume instance exec [TAB] → pro-dev  perso-desktop  ai-gpu ...
```

**Architecture**:

```
bin/anklume                      ← Entry point (shebang: #!/usr/bin/env python3)
scripts/cli/
├── __init__.py                  ← Typer app factory
├── domain.py                    ← anklume domain {list,apply,status}
├── instance.py                  ← anklume instance {list,remove,exec}
├── snapshot.py                  ← anklume snapshot {create,restore,list,delete}
├── network.py                   ← anklume network {status,rules,deploy}
├── portal.py                    ← anklume portal {open,push,pull,list}
├── app.py                       ← anklume app {export,list,remove}
├── llm.py                       ← anklume llm {status,switch,bench}
├── desktop.py                   ← anklume desktop {apply,reset,plugins}
├── lab.py                       ← anklume lab {start,check,hint,reset}
├── dev.py                       ← anklume dev {test,lint,matrix,audit}
├── completions.py               ← Dynamic completers (domains, instances)
└── helpers.py                   ← Shared: run_cmd(), require_container(), rich output
```

**Key implementation details**:
- `generate.py` imported directly (`from scripts.generate import ...`)
- Dynamic completions read `infra.yml` for domain/machine names
- `require_container()` check on commands that need Incus socket
- `ANKLUME_MODE` / `ANKLUME_LANG` respected for help filtering
- Rich tables for `list` commands, Rich progress for `apply`
- Commands that wrap shell scripts use `subprocess.run()`
- Commands that wrap Ansible use `subprocess.run(["ansible-playbook", ...])`
- `anklume dev` group hidden in user/student mode

**Deliverables**:

a) **CLI package** (`bin/anklume` + `scripts/cli/`):
   - Python Typer app with command groups: `domain`, `instance`,
     `snapshot`, `network`, `portal`, `app`, `llm`, `desktop`,
     `lab`, `dev`
   - Top-level commands: `sync`, `lint`, `test`, `flush`, `upgrade`,
     `guide`, `doctor`
   - Shell completion: `anklume --install-completion`
   - Rich-formatted help with mode filtering (student/user/dev)

b) **Dynamic completions** (unique advantage over Makefile):
   - Domain names from `infra.yml`
   - Machine names from `infra.yml`
   - Snapshot names from `incus` query
   - Lab numbers from `labs/` directory

c) **Mode-aware filtering** (absorbs Phase 33 mode logic):
   - `ANKLUME_MODE=user`: ~30 commands visible
   - `ANKLUME_MODE=student`: same + bilingual descriptions + transparent
   - `ANKLUME_MODE=dev`: all commands including `anklume dev` group

d) **ADR-046**: Document CLI design decision (Typer over Go/Rust,
   no Makefile backend, command hierarchy, dynamic completions)

**Validation criteria**:
- [x] `anklume domain list` shows all domains from infra.yml
- [x] `anklume domain apply pro` applies a single domain
- [x] `anklume --help` shows grouped commands with descriptions
- [x] Shell completion works (bash, zsh, fish)
- [x] Dynamic completion suggests domain/machine names from infra.yml
- [x] Mode filtering hides dev commands in user mode
- [x] Student mode shows bilingual descriptions
- [x] `anklume` without args shows usage summary
- [x] `ruff check scripts/cli/` passes
- [x] No Makefile dependency — CLI calls scripts/functions directly

---

## Phase 45: Documentation Site (MkDocs Material + Mermaid + CI)

**Goal**: Replace raw GitHub Markdown browsing with a modern,
searchable, bilingual documentation site auto-deployed to GitHub
Pages. Replace ASCII-art diagrams with Mermaid diagrams rendered
both on GitHub (native) and in the built site.

**Prerequisites**: Phase 7 (Documentation), Phase 33 (i18n).

**Rationale**: The project has 77+ Markdown files across `docs/`,
`examples/`, and `labs/`. Navigating them on GitHub is painful:
no search, no sidebar, no cross-references, no proper diagrams.
A documentation site improves accessibility for all audiences
(sysadmins, students, teachers) without changing the source
format — files remain plain Markdown, readable by LLMs and
editable by contributors.

**Why MkDocs Material**:
- Python-native (pip install, YAML config) — same ecosystem as
  Ansible and generate.py
- Standard de facto for IaC projects (Ansible, Terraform providers,
  CNCF projects)
- Zero migration: existing `.md` files work as-is
- Native Mermaid support via `pymdownx.superfences` (zero-config)
- Excellent client-side search (lunr.js with French stemming)
- Bilingual support via `mkdocs-static-i18n` plugin (file suffix
  convention `.fr.md` matches existing `_FR.md` pattern after rename)
- Versioning via `mike` if needed later
- `mkdocstrings` plugin for auto-documenting `generate.py`

**Why Mermaid** for diagrams:
- Rendered natively by GitHub in `.md` files (dual rendering:
  GitHub + site)
- Text-based source (LLM-readable and LLM-writable)
- Flowcharts, sequence diagrams, state diagrams, architecture
  diagrams — all relevant for anklume
- Integrated in MkDocs Material without plugins

**Design decisions**:
- Source files remain the single source of truth (PSOT principle)
- `mkdocs.yml` at project root — minimal config, no duplication
- French translations: rename `*_FR.md` → `*.fr.md` (required by
  `mkdocs-static-i18n` suffix convention)
- Diagrams are embedded in Markdown as fenced code blocks
  (```` ```mermaid ````) — visible on GitHub AND in built site
- Optional: `scripts/infra_diagram.py` generates architecture
  diagram from `infra.yml` (PSOT-derived, not hand-maintained)
- Build output (`site/`) is gitignored — CI builds and deploys
- `llms.txt` endpoint for AI agent discoverability

**Deliverables**:

a) **MkDocs configuration** (`mkdocs.yml`):
   - Material theme with custom palette (matches anklume identity)
   - Navigation structure mirroring `docs/` layout
   - Mermaid diagrams via `pymdownx.superfences`
   - `mkdocs-static-i18n` for EN/FR bilingual support
   - Search with French stemming enabled
   - Code highlighting for YAML, Python, Bash, Jinja2
   - Admonitions for warnings, tips, notes

b) **French filename migration** (`*_FR.md` → `*.fr.md`):
   - Rename all 37+ French translation files
   - Update any internal cross-references
   - Git `mv` to preserve history

c) **Mermaid diagram conversion** (replace ASCII art):
   - PSOT flow diagram (infra.yml → Ansible → Incus)
   - Host architecture (bridges, instances, nftables)
   - Network isolation (inter-bridge drop, policies)
   - Bootstrap sequence (host → anklume-instance → domains)
   - Reconciliation pattern (read → compare → create/update)
   - AI switch sequence (VRAM flush + nftables swap)
   - Nesting levels (physical → VM → LXC hierarchy)
   - Trust zone addressing (10.1xx octets visualization)

d) **CI/CD deployment** (`.github/workflows/docs.yml`):
   - Trigger on push to `main` (paths: `docs/`, `mkdocs.yml`,
     `README.md`, `examples/`, `labs/`)
   - Build with `mkdocs build`
   - Deploy to GitHub Pages via `actions/deploy-pages`
   - Build validation on PRs (build but don't deploy)

e) **Optional: auto-generated infrastructure diagram**:
   - `scripts/infra_diagram.py` reads `infra.yml` and generates
     a Mermaid or SVG architecture diagram
   - Integrated in CI (regenerated on each push)
   - Embedded in the documentation site

f) **Dependencies** (added to `pyproject.toml`):
   - `mkdocs-material` in `[project.optional-dependencies.docs]`
   - `mkdocs-static-i18n`
   - Optional: `mkdocstrings[python]` for API docs

g) **Makefile / CLI integration**:
   - `make docs` / `anklume docs build` — build site locally
   - `make docs-serve` / `anklume docs serve` — local preview
   - `make docs-deploy` / `anklume docs deploy` — manual deploy

**Validation criteria**:
- [ ] `mkdocs build --strict` passes with zero warnings
- [ ] Site deployed to GitHub Pages and accessible
- [ ] All 77+ docs visible in navigation sidebar
- [ ] French toggle switches all pages to French translations
- [ ] Search finds content in both EN and FR
- [ ] Mermaid diagrams render correctly on GitHub AND in built site
- [ ] ASCII art diagrams replaced in SPEC.md and ARCHITECTURE.md
- [ ] CI auto-deploys on push to main
- [ ] PR builds validate docs without deploying
- [ ] Source `.md` files remain LLM-readable (no compiled-only content)
- [ ] `site/` in `.gitignore`
- [ ] `make lint` still passes (yamllint on mkdocs.yml)

---

## Deferred Enhancements (from prior sessions)

Items discussed and deferred during development sessions. Each is
tracked here until promoted to a phase or integrated into an
existing phase.

### NER-based sanitization (Phase 39 enhancement)

Current Phase 39 sanitization uses regex-based tokenization for IPs,
hostnames, and FQDNs. A future enhancement would use Named Entity
Recognition (NER) to detect and anonymize infrastructure-specific
entities (domain names, project names, service identifiers) that
regex cannot reliably catch. Requires evaluation of local NER models
(spaCy, GLiNER) running on GPU alongside Ollama.

### Level 4 network analysis pipeline (Phase 40 enhancement)

Current Phase 40 provides network inspection (nmap scan diff, PCAP
summary). A Level 4 pipeline would add continuous monitoring with
anomaly baseline learning: establish normal traffic patterns per
domain, detect deviations, and escalate through the three-level
triage pipeline (local fast → local LLM → cloud via sanitizer).

### `~/.anklume/` single mount point (Phase 31 enhancement)

For Live OS deployments, consolidate all user-mutable data under
`~/.anklume/` as a single bind mount point. This simplifies the
persistent data partition layout: one mount = all user state
(mode, telemetry, agent config, session data). Currently scattered
across `~/.anklume/mode`, `~/.anklume/telemetry/`, etc.

### tmux/libtmux in bootstrap (Phase 23 enhancement)

`tmux` and `libtmux` (Python) are currently installed manually in
`anklume-instance`. They should be added to `scripts/bootstrap.sh`
as part of the container provisioning step, since `make console`
(Phase 19a) depends on them.

### GUI app forwarding priority (Phase 26 enhancement)

VS Code running inside containers with display forwarding to the
host is a high-priority user need. Current Phase 26 exports
`.desktop` files that launch apps via `incus exec`, but GUI
forwarding (Wayland socket sharing or X11 forwarding) needs
real-world validation with complex apps like VS Code, Firefox.
PipeWire audio socket sharing is also pending.

### Orphan veth pair cleanup (Incus upstream investigation)

When Incus containers restart, stale veth pairs can remain in the
host network namespace with the same MAC address as the new pair.
The bridge FDB sends unicast frames to the wrong port, causing
ARP to work (broadcast) but ping/DNS to fail (unicast).

**Workaround**: `make doctor FIX=1` (or `scripts/doctor.sh --fix
--check network`) detects and removes orphan veth pairs and stale
routes automatically. Root cause investigation still needed:
determine if this is an Incus bug or expected behavior, and
whether `incus restart` should clean up old veths automatically.

---

## Phase 44: Test Infrastructure Consolidation and Hardening

**Goal**: Consolidate the five testing layers (pytest, Gherkin/behave,
behavioral chains, behavior matrix, Hypothesis) into a coherent,
fully executable test pyramid. Every test artefact must be runnable
via a `make` target. Eliminate dead links, fill coverage gaps, and
establish automated coverage reporting.

**Prerequisites**: Phase 22 (BDD scenarios), Phase 18b (behavior matrix),
Phase 13 (LLM-assisted testing).

**Context (audit findings)**:

The project has accumulated five complementary testing layers over
43 phases, but they are not uniformly integrated:

| Layer | Tool | Status | Issue |
|-------|------|--------|-------|
| Unit/behavioral tests | pytest | Functional (2844 tests) | — |
| E2E scenarios | Gherkin/behave | Files exist, runner works | No CI, `behave` install not verified |
| Behavioral chains | YAML + runner | Runner exists | No Makefile target |
| Behavior matrix | YAML + coverage script | 249 cells | Coverage % not tracked in CI |
| Property-based | Hypothesis | Functional | Limited to `test_properties.py` |

The Gherkin/behave layer is **preserved and reinforced** — it provides
human-readable acceptance scenarios that serve as living documentation
for both best practices and failure modes. The `pitfalls.yml` feedback
loop to `scripts/guide.sh` is a unique asset.

**Principles**:
- **Every test artefact executes** — no dead YAML, no unrunnable features.
- **Gherkin scenarios are the acceptance layer** — they test complete
  user workflows at a higher abstraction than pytest. Not a duplication
  of pytest — a complementary view.
- **Behavioral chains are the E2E layer** — they test sequential admin
  workflows that span multiple `make` targets.
- **Coverage is measurable** — matrix coverage is computed automatically
  and reported.
- **`skipif` for optional tools** — scenarios requiring external tools
  (yamllint, shellcheck, Incus) skip gracefully when tools are absent.

**Deliverables**:

### a) Makefile targets for behavioral chains

```makefile
chain-test:        ## Run all behavioral chains (sequential admin workflows)
chain-test-one:    ## Run a single behavioral chain (CHAIN=<name>)
chain-test-dry:    ## Dry-run: show behavioral chain plan without executing
chain-test-json:   ## Run behavioral chains with JSON output
```

### b) Gherkin scenario hardening

- Verify `behave` is installed (part of `[project.optional-dependencies] test`)
- Add `skipif`-style guards in step definitions for external tools
  (yamllint, shellcheck, Incus) so scenarios skip cleanly in minimal
  environments instead of failing
- Ensure `make scenario-test` exits cleanly in environments without
  Incus (scenarios skip, not fail)

### c) Hypothesis extension

Extend property-based tests beyond `test_properties.py` to cover:
- Optional field validation (`boot_autostart`, `boot_priority`,
  `snapshots_schedule`, `snapshots_expiry`, `ai_provider`,
  `ai_sanitize`, `weight`, `nesting_prefix`)
- DNS-safe name generation and validation
- Addressing convention edge cases (zone overflow, max domains
  per zone, subnet_id boundary values)

### d) Unified test report

Create `scripts/test-summary.sh` that runs all test layers and
produces a combined summary:

```
Test Layer          | Status | Count    | Duration
--------------------|--------|----------|--------
pytest              | PASS   | 2844/2844|   12.3s
behave scenarios    | PASS   |   38/44  |   10.8s
behavioral chains   | PASS   |   14/14  |   45.2s
matrix coverage     | 87%    | 217/249  |    0.5s
hypothesis          | PASS   |   50/50  |    3.1s
--------------------|--------|----------|--------
TOTAL               | PASS   |          |   71.9s
```

### e) Matrix coverage gate

Add matrix coverage percentage to `make lint` or `make test` output.
Track coverage trend over time. Goal: 90%+ matrix coverage.

### f) Documentation update

- Update `docs/scenario-testing.md` with behavioral chain documentation
- Add `chain-test` targets to the mode-appropriate help output
- Update `i18n/fr.yml` with French translations for new targets

**Validation criteria**:
- [ ] `make scenario-test` passes (skips gracefully when tools absent)
- [ ] `make chain-test` passes (runs all 14 behavioral chains)
- [ ] `make chain-test-dry` shows plan without executing
- [ ] `make chain-test-one CHAIN=bootstrap-to-first-deploy` runs a single chain
- [ ] Gherkin scenarios skip (not fail) when yamllint/shellcheck absent
- [ ] `scripts/test-summary.sh` produces combined report
- [ ] Hypothesis tests cover all optional infra.yml fields
- [ ] Matrix coverage is computed and reported
- [ ] `docs/scenario-testing.md` updated with chain documentation
- [ ] `i18n/fr.yml` updated with new target translations

---

## Current State

**Completed** (all 43 phases):
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
- Phase 17: CI/CD pipeline + complete Molecule test coverage (18/18 roles)
- Phase 18: Advanced security, testing, onboarding & self-improvement (18a-18e)
- Phase 19: Terminal UX and Observability (tmux console, telemetry, code analysis)
- Phase 20: Native Incus Features and QubesOS Parity (20a-20g)
- Phase 21: Desktop Integration (clipboard, Sway, dashboard)
- Phase 22: End-to-End Scenario Testing (BDD)
- Phase 23: Host Bootstrap and Thin Host Layer
- Phase 23b: Sandboxed AI Coding Environment
- Phase 24: Snapshot-Before-Apply and Rollback
- Phase 25: XDG Desktop Portal for Cross-Domain File Access
- Phase 26: Native App Export (distrobox-export Style)
- Phase 28: Local LLM Delegation for Claude Code
- Phase 28b: OpenClaw Integration (Self-Hosted AI Assistant)
- Phase 29: Codebase Simplification and Real-World Testing
- Phase 30: Educational Platform and Guided Labs
- Phase 31: Live OS with Encrypted Persistent Storage
- Phase 32: Makefile UX and Robustness
- Phase 33: Student Mode and Internationalization
- Phase 34: Addressing Convention and Canonical Infrastructure
- Phase 35: Development Workflow Simplification
- Phase 36: Naming Convention Migration
- Phase 37: OpenClaw Instances — KISS Simplification
- Phase 38: OpenClaw Heartbeat and Proactive Monitoring
- Phase 39: LLM Sanitization Proxy
- Phase 40: Network Inspection and Security Monitoring
- Phase 41: Official Roles and External Role Integration
- Phase 42: Desktop Environment Plugin System
- Phase 43: Docker-Style CLI (Typer)
- Phase 44: Test Infrastructure Consolidation and Hardening (in progress)

**In progress**:
- Phase 44: Test Infrastructure Consolidation and Hardening
- Phase 45: Documentation Site (MkDocs Material + Mermaid + CI)

**Recently completed**:
- Phase 20g: Data Persistence and Flush Protection
- Phase 30: Educational Platform and Guided Labs
- Phase 31: Live OS with Encrypted Persistent Storage (hybrid ISO, A/B updates, dm-verity, toram)
- Phase 32: Makefile UX and Robustness
- Phase 33: Student Mode and Internationalization
- Phase 35: Development Workflow Simplification
- Phase 36: Naming Convention Migration
- Phase 37: OpenClaw Instances — KISS Simplification
- Phase 38: OpenClaw Heartbeat and Proactive Monitoring
- Phase 39: LLM Sanitization Proxy
- Phase 40: Network Inspection and Security Monitoring
- Phase 41: Official Roles and External Role Integration
- Phase 42: Desktop Environment Plugin System
- Phase 43: Docker-Style CLI (Typer)

**Phases 44-45 in progress.** All prior phases implemented. Remaining unchecked criteria are deployment-dependent
(require running infrastructure: OpenClaw messaging channels, LLM sanitizer proxy
deployment, network inspection with live captures). These will be validated during
real-world deployment.

**Vision document**: `docs/vision-ai-integration.md` — AI integration architecture
(Phases 35-40).

**Deferred enhancements**: See "Deferred Enhancements" section above (NER
sanitization, Level 4 network pipeline, veth cleanup, GUI app forwarding,
tmux bootstrap, PipeWire audio).

**Deployed infrastructure** (Phase 34 addressing convention):

| Domain | Container | IP | Zone | Network |
|--------|-----------|-----|------|---------|
| anklume | anklume-instance | 10.100.0.10 | admin | net-anklume |
| pro | pro-dev | 10.110.0.10 | trusted | net-pro |
| perso | perso-desktop | 10.110.1.10 | trusted | net-perso |
| ai-tools | ai-gpu | 10.120.0.10 | semi-trusted | net-ai-tools |
| ai-tools | ai-webui | 10.120.0.20 | semi-trusted | net-ai-tools |
| ai-tools | ai-chat | 10.120.0.30 | semi-trusted | net-ai-tools |
| ai-tools | ai-code | 10.120.0.40 | semi-trusted | net-ai-tools |

**Active ADRs**: 37 ADRs (ADR-001 to ADR-045, gaps at 007, 027, 028,
033, 034, 037 — deleted during documentation review)

**Known issues**:
- Orphan veth pairs on container restart — use `make doctor FIX=1` (see Deferred Enhancements)
- Debian 13 (Trixie) bootstrap not yet validated (Phase 23)
