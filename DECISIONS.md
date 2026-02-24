# DECISIONS.md — Parallel branch merge decisions

This file consolidates DECISIONS.md from all 5 merged branches.
Delete after review.

---

## Branch 1: boot_autostart & snapshots_config (20 tests)

BA-004/005/006, BA-2-001/002, BA-3-001, SN-004/005/006, SN-2-001, SN-3-001.
Open: `bool` subclass of `int` bug, BA-001/BA-004 tag mismatch.

## Branch 2: nesting_prefix & resource_policy (11 tests)

NX-004/005, NX-2-001/002, NX-3-001, RP-2-001/002, RP-3-001.
Coverage: 89% → 93%.

## Branch 3: make help categories (Phase 32)

32 user-facing targets, 8 categories, `help-all` for internals.
Fix: warn() in llm-bench.sh.

## Branch 4: sys-firewall → anklume-firewall (Phase 36)

Pure rename, 26 files. Backward compat preserved.

## Branch 5: French translations sync

Updated: SPEC_FR, ARCHITECTURE_FR (16 new ADRs), desktop_FR, sys-print_FR, scenario-testing_FR.
Translation conventions: technical terms kept in English per ADR-011.
Missing FR files: SPEC-operations, addressing-convention, live-os, parallel-prompts, tor-gateway, vm-support.
