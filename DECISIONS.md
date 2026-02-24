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
