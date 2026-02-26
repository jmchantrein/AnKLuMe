# Overnight Autonomous Execution Plan

Master plan for implementing all remaining ROADMAP phases with
maximum parallelism. Claude works overnight, user reviews
`DECISIONS.md` the next morning.

## Dependency graph

```
VAGUE 1 (COMPLETE):
  Phase 20g  ──┐
  Phase 32  ───┤─── all independent, 4 parallel agents
  Phase 35  ───┤
  Phase 36  ──┘

VAGUE 2 (COMPLETE):
  Phase 37  ←── blocked by 36
  Phase 30  ←── no blocker (code framework only)

VAGUE 3 (COMPLETE):
  Phase 38  ←── blocked by 37
  Phase 39  ←── blocked by 37
  Phase 33  ←── blocked by 30 + 32

VAGUE 4 (RUNNING):
  Phase 40  ←── blocked by 38 + 39

INDEPENDENT (requires specific environment):
  Phase 31  ←── VM testing via Incus/KVM (in progress)
```

## Vague 1 — COMPLETE

| Agent | Phase | Branch | Status |
|-------|-------|--------|--------|
| a094b57f | 20g Persistent data | feat/persistent-data | Merged |
| a11d4e14 | 32 Makefile UX | feat/makefile-ux | Merged |
| a984299c | 35 Dev workflow | feat/dev-workflow-simplify | Merged |
| a61669d1 | 36 Naming convention | feat/naming-convention | Merged |

**Result**: All 4 branches merged into main. 3343 tests passing,
linters clean. DECISIONS.md consolidated. Worktrees cleaned up.

## Vague 2 — COMPLETE

| Agent | Phase | Branch | Status |
|-------|-------|--------|--------|
| af143511 | 37 Per-domain OpenClaw | worktree-agent-af143511 | Merged |
| ac2e3feb | 30 Educational labs | worktree-agent-ac2e3feb | Merged |

**Result**: Both branches merged into main. 3422 tests passing.
DECISIONS.md consolidated. Worktrees cleaned up.

## Vague 3 — COMPLETE

| Agent | Phase | Branch | Status |
|-------|-------|--------|--------|
| a406ee2e | 38 Heartbeat | worktree-agent-a406ee2e | Merged |
| a6b01915 | 39 LLM sanitizer | worktree-agent-a6b01915 | Merged |
| a23ea2c5 | 33 Student mode | worktree-agent-a23ea2c5 | Merged |

**Result**: All 3 branches merged into main. 3558 tests passing.
Conflict resolution: merged openclaw_server defaults (Phase 37 domain
awareness + Phase 38 heartbeat variables), generator (openclaw + sanitizer
validation), SPEC (both field sets), ARCHITECTURE (ADR-043 + ADR-044).
Post-merge fixes: llm_sanitizer meta/molecule, SAN->LS prefix rename.

## Vague 4 — RUNNING

| Agent | Phase | Branch | Status |
|-------|-------|--------|--------|
| afb53c8f | 40 Network inspection | worktree-agent-afb53c8f | Running |

**Scope**:
- Custom skills: `anklume-network-triage`, `anklume-inventory-diff`,
  `anklume-pcap-summary`
- nmap scan diff script
- Network-specific anonymization patterns
- Doc: docs/network-inspection.md
- Tests: NI-001 to NI-005

## Phases requiring specific environment

### Phase 31: Live OS
**Reason**: Needs Incus/KVM VM for boot testing, UEFI, encrypted
ZFS/BTRFS pool creation. Testable locally via `anklume live test`.
**Status**: Arch Linux base support checked, 11 of 12 criteria remaining.

## Final summary

| Vague | Phases | Tests added | Total tests |
|-------|--------|-------------|-------------|
| 1 | 20g, 32, 35, 36 | ~200 | 3343 |
| 2 | 37, 30 | ~80 | 3422 |
| 3 | 38, 39, 33 | ~136 | 3558 |
| 4 | 40 | ~TBD | ~3600+ |
