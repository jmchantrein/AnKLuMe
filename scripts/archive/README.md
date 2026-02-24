# scripts/archive/

Deprecated scripts kept for reference. These are no longer part of the
active development workflow but may contain useful patterns.

## Contents

### mcp-anklume-dev.py (archived in Phase 35)

MCP proxy server (~2000 lines) that ran in `anklume-instance` to route
OpenClaw requests through Claude Code CLI, manage sessions, switch
brains, handle credentials, and execute tools.

**Replaced by**: Claude Code (direct) + `mcp-ollama-coder` (local LLM
delegation) + `claude-code-router` (optional background routing).

See `docs/vision-ai-integration.md` for the rationale.

### mcp-anklume-dev.service (archived in Phase 35)

Systemd unit file for the MCP proxy. No longer needed since the proxy
is retired.
