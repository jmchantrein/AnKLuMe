<<<<<<< HEAD
# DECISIONS.md — Autonomous Implementation Decisions

Decisions made during overnight autonomous implementation.
Review and approve/decline each section.

---

## Phase 36: Naming Convention Migration

### Name mapping

| Old name | New name | Context |
|----------|----------|---------|
| `sys-firewall` (auto-created) | `anklume-firewall` | Already done (prior commit) |
| `sys-print` (container) | `shared-print` | Container in `shared` domain |
| `print-service` (domain) | `shared` | Domain for user-facing services |
| `examples/sys-print/` | `examples/shared-services/` | Example directory |

### Script naming

The script `scripts/sys-print.sh` retains its filename. It is a tool
(like `snap.sh`), not a container. Its examples and usage messages now
reference `shared-print` as the default instance name.

### Decision: `shared` domain in canonical infra.yml

The `shared` domain is NOT added to the canonical `infra.yml.example`.
Rationale: the canonical infra.yml is intentionally minimal (anklume +
work domains). The `shared` domain is documented in SPEC.md and
demonstrated in `examples/shared-services/`. Users add it when needed.

### `sys-` references NOT changed and why

| File | Reference | Reason |
|------|-----------|--------|
| `scripts/generate.py:941` | `"sys-firewall"` | Backward compatibility check |
| `tests/test_generate.py:541` | `sys-firewall` | Tests backward compatibility |
| `tests/test_generate_internals.py:1903` | `sys-firewall` | Tests backward compatibility |
| `docs/SPEC.md:402` | `sys-firewall` | Documents backward compatibility |
| `docs/parallel-prompts.md` | Multiple refs | Historical documentation |
| `docs/vision-ai-integration.md` | `sys-firewall`, `sys-print` | Documents the migration |
| `scripts/sys-print.sh` (filename) | `sys-print.sh` | Tool name, not container name |
| `tests/test_sys_print.py` (filename) | `test_sys_print.py` | Tests the tool |

### Questions for review

1. Should `scripts/sys-print.sh` be renamed to `scripts/shared-print.sh`?
2. Should the `shared` domain be added to `infra.yml.example` as commented-out?
3. Should `docs/sys-print.md` / `docs/sys-print_FR.md` be renamed?

---

## Phase 20g: Persistent Data & Flush Protection

### ADR numbering
- ADR-040 was already taken (credits/attribution). Used ADR-041 for
  persistent_data and ADR-042 for flush protection.

### persistent_data device prefix: `pd-`
- Chose `pd-` prefix to avoid collisions with `sv-` (shared volumes)
  and user-declared devices. Consistent with the `sv-` pattern from
  ADR-039.

### persistent_data source path convention
- Source: `<persistent_data_base>/<machine_name>/<volume_name>`
- Machine name in the path ensures isolation between instances.
- Default base: `/srv/anklume/data` (parallel to `/srv/anklume/shares`).

### shift: true by default on persistent_data
- Mirrored the shared_volumes default. Unprivileged containers need
  idmap shifting to access host-owned directories.

### Flush protection uses FORCE env var (not --force flag)
- The `--force` flag was already used for production safety (absolute_level
  check). The `FORCE` env var is a separate concept: bypass delete
  protection. The Makefile passes `FORCE=true` via env when the user
  specifies it.

### Step 5 project skip when instances remain
- Instead of attempting project delete and catching the error, the new
  flush.sh preemptively checks if instances remain after step 1.

### Test file exceeds 200 lines
- test_persistent_data.py is ~415 lines. Existing test files set
  precedent (test_spec_features.py: 1245L, test_flush.py: 493L).
  The 200-line rule applies to implementation files, not tests.

### Path collision detection between pd and sv
- persistent_data paths are checked against shared_volumes mount paths
  on the same machine, preventing two devices mounting to the same path.

### Questions for review

1. Should `persistent_data` support a `shift` option like shared_volumes?
   Currently hardcoded to `shift=true`.
2. Should `instance-remove.sh` also clean up host data directory at
   `/srv/anklume/data/<machine>/` when removing an instance?
3. The flush script's `FORCE` env var doubles as "bypass production
   safety" and "bypass delete protection". Should these be separate?

---

## Phase 32: Makefile UX and Robustness

### Target-to-category mapping

| Category            | Targets |
|---------------------|---------|
| Getting Started     | guide, quickstart, init |
| Core Workflow       | sync, sync-dry, apply, apply-limit, check, nftables, doctor |
| Snapshots           | snapshot, restore, rollback, rollback-list |
| AI / LLM            | apply-ai, llm-switch, llm-status, llm-bench, llm-dev, ai-switch, claude-host |
| Console             | console, dashboard |
| Instance Management | disp, backup, file-copy |
| Lifecycle           | upgrade, flush, import-infra |
| Development         | lint, test, smoke |

### Backward compatibility approach

- **ollama-dev**: Added as a Make alias target that depends on `llm-dev`.
  The old name still works but delegates to the new one.

### llm-bench.sh robustness fixes

- Numeric guards on integer comparisons to prevent crash on non-numeric values.
- Fallback `|| echo "0 0 0"` on bench_endpoint calls.
- Default values `${var:-0}` for empty variables in result rows.

### upgrade.sh improvements

- Conflicts moved to `/tmp/anklume-upgrade-backup-<timestamp>/` instead
  of `.local-backup` alongside originals.
- Preserves directory structure. Clear restore instructions.

### Questions for review

1. Should `ollama-dev` alias emit a deprecation warning?
2. Should any targets be promoted from internal to user-facing?

---

## Phase 35: Development Workflow Simplification

### What was archived (moved to scripts/archive/)

| File | Original location | Reason |
|------|-------------------|--------|
| `mcp-anklume-dev.py` | `scripts/` | MCP proxy retired per Phase 35 roadmap |
| `mcp-anklume-dev.service` | `scripts/` | Systemd unit for the retired proxy |
| `sync-claude-credentials.sh` | `host/boot/` | Credential sync timer no longer needed |

### What was NOT extracted as a new MCP server

All 21+ tools in the proxy were analyzed. None justify extraction because
Claude Code provides native equivalents (Bash for git/make/incus, Read for
files, WebSearch/WebFetch for web). `mcp-ollama-coder` covers local LLM
delegation (code gen, review, fix, tests, explain).

### Credential references

The credential **bind-mount device** in OpenClaw's Incus profile was NOT
removed (still needed by OpenClaw, Phase 37 scope). Only the **sync timer**
was archived because the bind-mount makes it redundant.

### Makefile changes

The four `mcp-dev-*` targets replaced with deprecation notice.

### Test changes

`tests/test_proxy.py`: removed 8 test classes (90+ tests) for proxy
internals. Added `TestProxyArchive` verifying archive structure.
Kept `TestOpenClawDocumentation` and `TestOpenClawTemplates`.

### Risks and manual verification needed

1. If `mcp-anklume-dev.service` is active in `anklume-instance`, stop it
2. If OpenClaw connects to proxy at `anklume-instance:9090`, it will fail
   (expected — reconfiguration is Phase 37 scope)
3. If `anklume-sync-creds.timer` was installed on host, manually disable it

### Questions for review

1. Should `docs/openclaw.md` be updated for proxy retirement now or Phase 37?
2. Should OpenClaw templates referencing proxy IP/port be updated now or Phase 37?
3. Should `scripts/mcp-client.py` (proxy debugging tool) also be archived?

---
=======
# DECISIONS.md -- Phase 35: Development Workflow Simplification

Decisions made during this implementation, pending human review.

## What was archived (moved to scripts/archive/)

| File | Original location | Reason |
|------|-------------------|--------|
| `mcp-anklume-dev.py` | `scripts/` | MCP proxy retired per Phase 35 roadmap |
| `mcp-anklume-dev.service` | `scripts/` | Systemd unit for the retired proxy |
| `sync-claude-credentials.sh` | `host/boot/` | Credential sync timer no longer needed |

## What was NOT extracted as a new MCP server

After thorough analysis of all 21+ tools in `mcp-anklume-dev.py`, none
justify extraction into a standalone MCP server because:

- **git_status, git_log, git_diff**: Claude Code has native Bash tool
  with `git` commands.
- **make_target, run_tests, lint**: Claude Code can run `make` and
  `pytest` via Bash natively.
- **incus_list, incus_exec**: Claude Code can run `incus` commands via
  Bash natively.
- **read_file**: Claude Code has a dedicated Read tool.
- **claude_chat, claude_sessions, claude_session_clear, claude_code**:
  These managed Claude Code sessions for OpenClaw. No longer needed
  since Claude Code runs standalone.
- **switch_brain, usage**: OpenClaw brain management. Phase 37 scope.
- **web_search, web_fetch**: Claude Code has native WebSearch/WebFetch
  tools.
- **self_upgrade**: OpenClaw-specific workflow.
- **propose_refactoring, review_code_local**: Already covered by
  `mcp-ollama-coder` tools (generate_code, review_code, fix_code,
  generate_tests, explain_code).
- **run_full_report, get_test_progress, get_test_report**: Test
  delegation. The underlying `scripts/test-runner-report.sh` can be
  called directly via Bash.

Conclusion: `mcp-ollama-coder` (already configured as an MCP server)
provides all local LLM delegation tools needed. No new MCP server was
created.

## Credential references found

| Location | What | Action |
|----------|------|--------|
| `host/boot/sync-claude-credentials.sh` | Systemd timer syncing OAuth credentials from host to anklume-instance | Archived to `scripts/archive/` |
| `scripts/mcp-anklume-dev.py` | Auth error detection, credential path constants | Archived with the proxy |
| `docs/openclaw.md` / `docs/openclaw_FR.md` | Documents credential bind-mount mechanism | NOT modified (still relevant for OpenClaw Phase 37) |
| `roles/openclaw_server/tasks/main.yml` | Git credential helper setup | NOT modified (still needed for OpenClaw git operations) |
| `scripts/agent-develop.sh`, `scripts/agent-fix.sh` | `ANTHROPIC_API_KEY` checks | NOT modified (Agent Teams scripts, independent of proxy) |
| `scripts/ai-config.sh` and AI scripts | `ANTHROPIC_API_KEY` usage | NOT modified (AI testing scripts, independent of proxy) |

Key decision: The credential **bind-mount device** in OpenClaw's Incus
profile was NOT removed. It is still needed by OpenClaw (Phase 37 scope).
Only the **sync timer** (which periodically copied credentials from host
to container) was archived, because the bind-mount makes it redundant.

## Makefile changes

The four `mcp-dev-*` targets (`mcp-dev-start`, `mcp-dev-stop`,
`mcp-dev-status`, `mcp-dev-logs`) were replaced with a single
deprecation notice pointing to the archive.

## Test changes

`tests/test_proxy.py` was rewritten:
- Removed: 8 test classes (90+ tests) that tested proxy internals
  (brain modes, proxy tag, tool registry, safety filters, usage
  tracking, session management, OpenAI compatibility)
- Added: `TestProxyArchive` class verifying archive structure
- Kept: `TestOpenClawDocumentation` and `TestOpenClawTemplates` classes
  (still testing active OpenClaw role and docs)

## Documentation changes

| File | Change |
|------|--------|
| `docs/claude-code-workflow.md` | Added Architecture section documenting new workflow |
| `CLAUDE.md` | Added `claude-code-workflow.md` to context files list |
| `scripts/archive/README.md` | Created, explains archive contents |

## Risks and manual verification needed

1. **Running anklume-instance**: If the `mcp-anklume-dev.service` is
   currently active in `anklume-instance`, it will continue running
   until stopped. Run `make mcp-dev-stop` or manually:
   `incus exec anklume-instance -- systemctl disable --now mcp-anklume-dev.service`

2. **OpenClaw configuration**: If OpenClaw is configured to connect to
   the proxy at `anklume-instance:9090`, it will fail. This is expected
   -- OpenClaw reconfiguration is Phase 37 scope.

3. **Systemd timer**: If `anklume-sync-creds.timer` was installed on
   the host via `sync-claude-credentials.sh --install`, it should be
   manually disabled:
   `sudo systemctl disable --now anklume-sync-creds.timer`

## Questions for human review

1. Should `docs/openclaw.md` and `docs/openclaw_FR.md` be updated to
   note the proxy retirement, or is that Phase 37 scope?

2. The OpenClaw role templates (`AGENTS.md.j2`, `TOOLS.md.j2`) reference
   the proxy IP and port. Should these be updated now or in Phase 37?

3. Should `scripts/mcp-client.py` (an MCP test client) also be archived?
   It appears to be a debugging tool for the proxy.
>>>>>>> feat/dev-workflow-simplify
