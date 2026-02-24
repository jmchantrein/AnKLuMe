# Overnight Autonomous Execution Plan

Master plan for implementing all remaining ROADMAP phases with
maximum parallelism. Claude works overnight, user reviews
`DECISIONS.md` the next morning.

## Dependency graph

```
VAGUE 1 (running now — no blockers):
  Phase 20g  ──┐
  Phase 32  ───┤─── all independent, 4 parallel agents
  Phase 35  ───┤
  Phase 36  ──┘

VAGUE 2 (after vague 1 merge):
  Phase 37  ←── blocked by 36
  Phase 30  ←── no blocker (code framework only)

VAGUE 3 (after vague 2 merge):
  Phase 38  ←── blocked by 37
  Phase 39  ←── blocked by 37
  Phase 33  ←── blocked by 30 + 32

VAGUE 4 (after vague 3 merge):
  Phase 40  ←── blocked by 38 + 39

INDEPENDENT (hardware-dependent, not automatable):
  Phase 27  ←── GPU + audio hardware
  Phase 31  ←── physical boot media (already in progress)
```

## Vague 1 — COMPLETE

| Agent | Phase | Branch | Status |
|-------|-------|--------|--------|
| a094b57f | 20g Persistent data | feat/persistent-data | Merged ✓ |
| a11d4e14 | 32 Makefile UX | feat/makefile-ux | Merged ✓ |
| a984299c | 35 Dev workflow | feat/dev-workflow-simplify | Merged ✓ |
| a61669d1 | 36 Naming convention | feat/naming-convention | Merged ✓ |

**Result**: All 4 branches merged into main. 3343 tests passing,
linters clean. DECISIONS.md consolidated. Worktrees cleaned up.

## Vague 2 — Running now

### Phase 37: Per-Domain OpenClaw
**Branch**: `feat/openclaw-per-domain`
**Scope** (code-only, no running Incus needed):
- Extend `roles/openclaw_server/` for multi-instance support
- Parameterize ADR-036 templates per domain
- Add `openclaw: true` domain-level directive in infra.yml
- Generator: validate `openclaw` field, generate per-domain config
- Update examples/ (retire centralized ai-openclaw)
- Tests: multi-instance configuration
- Doc: update SPEC.md, ARCHITECTURE.md

**Cannot do** (needs infra): actual deployment test with 2 running
OpenClaw instances, Telegram integration, network isolation verify.

### Phase 30: Educational Platform (framework only)
**Branch**: `feat/educational-labs`
**Scope** (code-only):
- Create `labs/` directory structure
- Create lab framework: `lab.yml` format, step validation format
- Write 3 example labs (01-first-deploy, 02-network-isolation,
  03-snapshots) — infra.yml + steps + solutions
- Makefile targets: lab-list, lab-start, lab-check, lab-hint,
  lab-reset, lab-solution
- Scripts: `scripts/lab-runner.sh` (~150 lines)
- Tests: lab format validation, step parsing

**Cannot do** (needs infra): Incus-in-Incus sandbox execution,
teacher mode N-student deployment, actual lab running.

## Vague 3 — After vague 2 merge

### Phase 38: OpenClaw Heartbeat (templates + skills)
**Branch**: `feat/openclaw-heartbeat`
**Scope**:
- HEARTBEAT.md Jinja2 template per domain
- Custom skills: `anklume-health`, `anklume-network-diff`
- Cron configuration templates
- Alert escalation logic (Telegram config)
- Role extension: heartbeat tasks in openclaw_server
- Tests: template rendering, skill syntax

### Phase 39: LLM Sanitization Proxy (generator + docs)
**Branch**: `feat/llm-sanitizer`
**Scope**:
- Evaluate candidates (LLM Sentinel, LLM Guard, Privacy Proxy)
  → document recommendation in DECISIONS.md
- Generator: validate `ai_provider`, `ai_sanitize` fields
- IaC detection patterns (regex for 10.1xx IPs, Incus names, etc.)
- Role skeleton: `roles/llm_sanitizer/` (tasks, defaults, templates)
- Network policy: auto-generate sanitizer routing rules
- Doc: SPEC.md, ARCHITECTURE.md, docs/llm-sanitizer.md

### Phase 33: Student Mode and i18n
**Branch**: `feat/student-mode`
**Scope**:
- CLI profiles: mode-student, mode-user, mode-dev in Makefile
- `~/.anklume/mode` persistence
- `i18n/fr.yml` translation file for all user-facing targets
- Bilingual help in student mode
- Transparent mode wrapper (Makefile-based, not callback plugin)
- Tests: mode switching, i18n output

## Vague 4 — After vague 3 merge

### Phase 40: Network Inspection (code framework)
**Branch**: `feat/network-inspection`
**Scope**:
- Custom skills: `anklume-network-triage`, `anklume-inventory-diff`,
  `anklume-pcap-summary`
- nmap scan diff scripts
- Cloud escalation pipeline code
- Network-specific anonymization patterns
- Alerting pipeline integration
- Doc: SPEC.md section, docs/network-inspection.md

## Phases NOT implementable autonomously

### Phase 27: Streaming STT
**Reason**: Needs GPU container with STT service + audio hardware
for testing real-time latency. Cannot validate < 500ms requirement
without physical audio input.
**What can be prepared**: evaluation document comparing backends
(whisper-streaming, faster-whisper, Vosk, Moonshine).

### Phase 31: Live OS
**Reason**: Already in progress. Needs physical hardware or VM for
boot testing, UEFI, encrypted ZFS/BTRFS pool creation.
**Status**: Arch Linux base support checked, 11 of 12 criteria remaining.

## DECISIONS.md strategy

Each vague produces a consolidated `DECISIONS.md` at the repo root:
- Accumulates decisions from all agents in that vague
- Previous vague's decisions are archived to `docs/decisions/vague-N.md`
- User reviews the root DECISIONS.md each morning

## Merge strategy

1. Review DECISIONS.md from each agent
2. Run `make lint && make test` on each worktree
3. Merge in dependency order (smallest first for conflict safety)
4. Run full test suite after each merge
5. If merge conflict: resolve, re-test, continue

## Estimated timeline

- Vague 1: ~30-60 min (already running)
- Merge 1: ~10 min
- Vague 2: ~45 min (2 parallel agents)
- Merge 2: ~10 min
- Vague 3: ~45 min (3 parallel agents)
- Merge 3: ~10 min
- Vague 4: ~30 min (1 agent)
- Merge 4: ~10 min
- Total: ~3-4 hours
