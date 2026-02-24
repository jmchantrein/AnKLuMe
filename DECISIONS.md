# DECISIONS.md -- Phase 32: Makefile UX and Robustness

Decisions made during implementation, pending human review.

## Target-to-category mapping

### User-facing targets (shown in `make help`)

| Category            | Targets                                                                |
|---------------------|------------------------------------------------------------------------|
| Getting Started     | guide, quickstart, init                                                |
| Core Workflow       | sync, sync-dry, apply, apply-limit, check, nftables, doctor           |
| Snapshots           | snapshot, restore, rollback, rollback-list                             |
| AI / LLM            | apply-ai, llm-switch, llm-status, llm-bench, llm-dev, ai-switch, claude-host |
| Console             | console, dashboard                                                     |
| Instance Management | disp, backup, file-copy                                                |
| Lifecycle           | upgrade, flush, import-infra                                           |
| Development         | lint, test, smoke                                                      |

### Internal targets (shown only in `make help-all`)

All other targets (lint-yaml, lint-ansible, lint-shell, lint-python,
apply-infra, apply-provision, apply-base, apply-images, apply-llm,
apply-stt, apply-code-sandbox, apply-openclaw, test-generator,
test-roles, test-role, test-sandboxed, test-sandboxed-role,
runner-create, runner-destroy, scenario-test, scenario-test-best,
scenario-test-bad, scenario-list, matrix-coverage, matrix-generate,
test-report, ai-test, ai-test-role, ai-develop, agent-runner-setup,
agent-fix, agent-develop, file-copy, backup, restore-backup,
portal-open, portal-push, portal-pull, portal-list, dead-code,
call-graph, dep-graph, code-graph, audit, audit-json, golden-create,
golden-derive, golden-publish, golden-list, mcp-list, mcp-call,
apply-tor, apply-print, mcp-dev-start, mcp-dev-stop, mcp-dev-status,
mcp-dev-logs, mine-experiences, ai-improve, telemetry-on,
telemetry-off, telemetry-status, telemetry-clear, telemetry-report,
clipboard-to, clipboard-from, domain-exec, desktop-config,
export-app, export-list, export-remove, build-image, live-update,
live-status, nftables-deploy, snapshot-domain, restore-domain,
snapshot-delete, snapshot-list, rollback-cleanup, export-images,
install-update-notifier, claude-host-resume, claude-host-audit,
install-hooks, sync-clean, shares, syntax, check, smoke)

## Backward compatibility approach

- **ollama-dev**: Added as a Make alias target that depends on `llm-dev`.
  The old name still works but delegates to the new one. The alias is
  marked as deprecated in its `##` comment. It is included in `.PHONY`.

- No other `ollama-*` targets existed to rename. The LLM targets were
  already consistently named `llm-*` (llm-switch, llm-status, llm-bench,
  llm-dev).

## llm-bench.sh robustness fixes

- `warn()` was already present (added previously). No missing function.
- Added numeric guards (`[[ =~ ^[0-9]+$ ]]`) around integer comparisons
  in `bench_endpoint()` to prevent crash on non-numeric values from
  failed benchmarks.
- Added `|| echo "0 0 0"` fallback on `bench_endpoint` calls in
  `cmd_bench()` and `cmd_compare()` so individual model failures show
  FAILED instead of crashing the script.
- Added `|| true` on `scripts/llm-switch.sh` calls in `cmd_compare()`
  to survive backend switch failures.
- Added default values (`${var:-0}`) for results in `print_result_row`
  calls to handle empty variables.

## upgrade.sh improvements

- Moved conflicting untracked files to
  `/tmp/anklume-upgrade-backup-<timestamp>/` instead of creating
  `.local-backup` files alongside the originals.
- Preserves directory structure inside the backup directory.
- Backup directory only created when at least one conflict exists.
- Clear restore instructions printed after upgrade completes.

## Questions for human review

1. Should `ollama-dev` alias emit a deprecation warning when called?
   Currently it silently delegates. Adding a warning would require a
   recipe line, making it no longer a pure dependency.

2. The `make help` hardcoded list has 28 entries. Should any additional
   targets be promoted to user-facing (e.g., `apply-infra`, `backup`)?

3. `update-check.sh` and `install-update-notifier` target already exist.
   No changes were needed beyond verifying they work.
