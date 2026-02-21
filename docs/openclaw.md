# OpenClaw — Self-Hosted AI Assistant

AnKLuMe integrates [OpenClaw](https://github.com/openclaw/openclaw), an
open-source, self-hosted AI assistant that connects to messaging platforms
(Telegram, WhatsApp, Signal, Discord, etc.) and drives multiple LLM backends.

Running OpenClaw inside AnKLuMe provides network isolation, controlled
messaging access, and local LLM delegation for privacy-sensitive queries.

## Architecture

```
Host
+-- Container: openclaw              (ai-tools project)
|   +-- OpenClaw daemon (Node.js)
|   +-- Messaging bridges (Telegram, etc.)
|   +-- Connected to proxy on anklume-instance
|
+-- Container: anklume-instance       (anklume project)
|   +-- OpenAI-compatible proxy (:9090)
|   +-- Claude Code CLI (brain for anklume/assistant modes)
|   +-- REST API for infrastructure tools
|
+-- Container: ollama                 (ai-tools project)
    +-- llama-server (:8081)
    +-- GPU-accelerated inference
    +-- qwen2.5-coder:32b (coding) / qwen3:30b-a3b (chat)
```

### Why Claude Code runs on anklume-instance, not in openclaw

A natural question: why doesn't Ada run commands directly inside her
`openclaw` container? Why go through `incus exec openclaw` from
`anklume-instance`?

The reason is **Claude Code CLI licensing**. Claude modes (anklume and
assistant) use Claude Code CLI, which requires a valid Anthropic
subscription (Max plan). Claude Code authenticates via OAuth tokens
stored in `~/.claude/`. These credentials live on `anklume-instance`
(synced from the host) because that container is the AnKLuMe control
plane — it has the Incus socket, the project repository, and Ansible.

Running Claude Code directly in `openclaw` would require duplicating
the OAuth credentials, the project context (CLAUDE.md, SPEC.md), and
the Incus socket into a second container. This would:
- Double the credential sync surface (two containers to keep in sync)
- Break the single-control-plane principle (ADR-004)
- Require `openclaw` to have the Incus socket (security risk for a
  container that also has internet access and messaging bridges)

Instead, the proxy on `anklume-instance` acts as a bridge: it receives
OpenAI-compatible requests from OpenClaw, translates them into Claude
Code CLI calls, and returns the responses. Claude Code runs with
`--allowedTools` that permit it to execute commands in `openclaw` via
`incus exec openclaw --project ai-tools`. This way:
- Credentials stay on `anklume-instance` only
- The Incus socket is not exposed to the internet-facing container
- Ada can still act as root in her `openclaw` container (install
  packages, edit files, run git) through the `incus exec` bridge

If a future version uses the Claude API directly (instead of Claude
Code CLI), OpenClaw's native tool execution could handle commands
inside `openclaw` without the `incus exec` indirection — but at the
cost of losing project context and Max plan credits.

## Brain modes

OpenClaw supports three switchable brain modes. The user can switch
at any time by messaging "passe en mode anklume", "switch to local", etc.

| Mode | Backend | Description |
|------|---------|-------------|
| **anklume** | Claude Code (Opus) | Expert AnKLuMe: infra, Ansible, Incus, networking |
| **assistant** | Claude Code (Opus) | General-purpose assistant (Ada persona) |
| **local** | qwen3:30b-a3b (MoE) | Free, fast local LLM via llama-server on GPU |

### How switching works

1. User sends "mode local" on Telegram
2. OpenClaw forwards the message to the proxy
3. The LLM includes a `[SWITCH:local]` marker in its response
4. The proxy detects the marker and:
   - Updates OpenClaw's config to use the new backend
   - Switches llama-server model if needed (coder vs chat)
   - Restarts OpenClaw
   - Sends a wake-up message on Telegram confirming the new mode

### llama-server model switching

Claude modes use `qwen2.5-coder:32b` (optimized for code tasks via MCP).
Local mode uses `qwen3:30b-a3b` (MoE with 3B active params, fast,
good at chat and personality). The two models run as mutually exclusive
systemd services (`llama-server.service` and `llama-server-chat.service`
with `Conflicts=` directives) since both require the full GPU VRAM.

## Usage tracking

The proxy tracks cumulative Claude Code usage (cost, tokens) per session.
When the user asks about consumption ("combien j'ai consomme?"), the
proxy injects the usage stats directly into the LLM context. The
assistant presents them naturally without needing to call any external API.

Stats include:
- Total cost in USD since proxy start
- Input/output token counts
- Cache token usage (read and creation)
- Per-session breakdown (openclaw-anklume vs openclaw-assistant)

Note: the global Max plan quota is not accessible via API. Only
per-proxy-session costs are tracked.

## Proxy API

The proxy on `anklume-instance:9090` exposes:

### OpenAI-compatible endpoint
- `POST /v1/chat/completions` — used by OpenClaw as its LLM backend
- Supports both streaming (SSE) and non-streaming responses
- Session persistence via Claude Code `--resume`

### Infrastructure tools (REST)
- `/api/git_status`, `/api/git_log`, `/api/git_diff`
- `/api/make_target`, `/api/run_tests`, `/api/lint`
- `/api/incus_list`, `/api/incus_exec`, `/api/read_file`
- `/api/claude_chat`, `/api/claude_sessions`, `/api/claude_code`
- `/api/switch_brain`, `/api/usage`

### Web tools (delegated to openclaw container)
- `/api/web_search` — Brave Search API (`{"query": "...", "count": 5}`)
- `/api/web_fetch` — Fetch and extract text from a URL (`{"url": "..."}`)

### Self-management
- `/api/self_upgrade` — Check/apply framework updates (`{"action": "check|upgrade|apply-openclaw"}`)

### Development workflow

Ada works directly in her `openclaw` container (where she is root) using
`/api/incus_exec` with `instance: openclaw`. The container has internet
access, Incus nesting (`security.nesting=true`), and a git clone of
AnKLuMe at `/root/AnKLuMe/`. This allows full development, testing, and
PR creation without creating additional containers.

## Self-improvement

Ada has two self-improvement loops, both operating autonomously from
her sandboxed container:

### Persona evolution

OpenClaw stores Ada's identity and knowledge in editable workspace
files (`~/.openclaw/workspace/`). Ada can modify these herself to
refine her behavior over sessions:

| File | What Ada can evolve |
|------|--------------------|
| `SOUL.md` | Personality, tone, values, opinions |
| `AGENTS.md` | Operating instructions, tool documentation |
| `TOOLS.md` | Local notes, API references, infrastructure map |
| `MEMORY.md` | Long-term curated knowledge |
| `memory/YYYY-MM-DD.md` | Daily session notes for continuity |

When Ada learns something useful during a conversation (a new pattern,
a user preference, a debugging insight), she can persist it in her
memory files. Over time, her persona and knowledge base evolve through
accumulated experience — without any manual intervention.

### Framework contribution

Ada can also improve the AnKLuMe framework itself. From her `openclaw`
container, she has full access to the git repository:

```
Ada on Telegram → understands a bug or improvement
  → creates a branch in /root/AnKLuMe/
  → implements the fix, runs tests (make lint, pytest)
  → pushes and creates a PR via gh CLI
  → jmc reviews and merges
```

This creates a recursive loop: the AI assistant improves the
infrastructure framework that hosts the AI assistant. Combined with
the experience library (Phase 18d) and Agent Teams (Phase 15), this
enables continuous, auditable self-improvement with human oversight
at the merge gate.

### What makes this safe

- **Sandbox isolation**: Ada runs in a dedicated LXC container with
  no access to other domains (pro, perso, etc.)
- **Git workflow**: all changes go through branches and PRs — Ada
  never commits to main directly
- **Human gate**: jmc reviews every PR before it reaches production
- **Persona files are local**: workspace changes only affect Ada's
  own behavior, not the framework or other users

## Value-add over native OpenClaw

The AnKLuMe proxy architecture extends OpenClaw with capabilities
that go beyond what OpenClaw provides natively. Here is a comparison
of what each layer brings:

### 1. Agentic coding brain (Claude Code CLI)

**Native OpenClaw**: calls any OpenAI-compatible API with simple
request/response. The LLM can only produce text.

**With proxy**: Claude Code CLI is an agentic coding assistant with
tool use (Read, Edit, Grep, Bash). It can read files, write code,
search codebases, and run commands — all autonomously within a single
turn. Ada doesn't just answer questions — she actively modifies code,
debugs issues, and manages infrastructure.

### 2. Cross-container orchestration

**Native OpenClaw**: can only run commands in its own container via
the built-in `exec` tool.

**With proxy**: the `incus_exec` tool lets Ada execute commands in
ANY Incus container across ALL projects (with safety filters). She
can inspect the Ollama container, check network state, manage other
instances — acting as an infrastructure-wide agent.

### 3. Multi-brain switching with GPU VRAM management

**Native OpenClaw**: supports one model at a time, configured in
`openclaw.json`. Switching requires manual config editing and restart.

**With proxy**: seamless switching between Claude (expensive, powerful)
and local LLMs (free, fast) via natural language ("passe en mode
local"). The proxy automatically swaps llama-server models, manages
GPU VRAM (mutually exclusive systemd services), restarts OpenClaw,
and sends a wake-up message on Telegram confirming the new mode.

### 4. Message attribution

**Native OpenClaw**: all messages appear from the same bot. No way to
distinguish between the LLM, OpenClaw itself, or an error handler.

**With proxy**: proxy-emitted messages are tagged with `⚙️ [proxy]`
so users can distinguish between Ada (the brain), the proxy
(middleware), and OpenClaw (the body). This aids debugging and helps
users understand the architecture.

### 5. Credential auto-sync via bind-mount

**Native OpenClaw**: does not manage OAuth credentials for external
CLIs.

**With proxy**: host Claude Code credentials are bind-mounted into the
container. Token freshness is automatic — no sync timers, no manual
intervention. When tokens expire, the proxy returns a clear error
message instead of an opaque failure.

### 6. Usage and cost tracking

**Native OpenClaw**: does not track LLM API costs.

**With proxy**: accumulates cost, token counts, and cache usage per
Claude Code session. When the user asks about consumption ("combien
j'ai consomme?"), the proxy injects stats directly into the LLM
context. The assistant presents them naturally.

### 7. Infrastructure REST API

**Native OpenClaw**: has exec and browser tools.

**With proxy**: typed, safety-filtered REST endpoints for git, make,
incus, lint, and tests — with blocklists for dangerous operations
(`flush`, `nftables-deploy`) and output truncation. The brain
interacts with infrastructure safely through well-defined tools.

### 8. Web search delegation across network boundaries

**Native OpenClaw**: has native Brave Search integration.

**With proxy**: delegates `web_search` and `web_fetch` to the
`openclaw` container (which has internet access), while
`anklume-instance` itself has no internet. This maintains network
isolation while still enabling web access through the bridge.

### 9. Self-upgrade capability

**Native OpenClaw**: `openclaw update` updates itself.

**With proxy**: the `self_upgrade` tool can check and apply AnKLuMe
framework updates, re-sync configuration (`make sync`), and
re-provision the openclaw container — all from a Telegram message.

### 10. Persistent multi-turn sessions

**Native OpenClaw**: each agent turn is a fresh API call. Context is
limited to what fits in a single request.

**With proxy**: maintains persistent Claude Code sessions via
`--resume`, enabling multi-turn conversations where the brain retains
full codebase context across messages. Stale sessions are
auto-cleaned after 1 hour of inactivity.

### Summary table

| Capability | Native OpenClaw | With AnKLuMe proxy |
|------------|-----------------|-------------------|
| LLM brain | API text completion | Agentic coding (tool use) |
| Command scope | Own container only | Any Incus container |
| Model switching | Manual config edit | Natural language + auto-restart |
| Message origin | Opaque | Tagged (`[proxy]`) |
| Credentials | Manual | Bind-mount (auto) |
| Cost tracking | No | Per-session stats |
| Infrastructure tools | exec only | git, make, incus, lint, tests |
| Web search | Native (same container) | Delegated (network isolation) |
| Self-update | OpenClaw only | Framework + container |
| Session memory | Per-turn | Persistent (--resume) |

## Deployment

### Prerequisites
- AnKLuMe deployed with the `ai-tools` domain
- Ollama or llama-server running with a model loaded
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))

### Ansible role

The `openclaw_server` role installs and configures OpenClaw:

```yaml
# In infra.yml
domains:
  ai-tools:
    subnet_id: 10
    machines:
      openclaw:
        type: lxc
        ip: "10.100.10.40"
        roles: [base_system, openclaw_server]
```

Role variables (`roles/openclaw_server/defaults/main.yml`):

| Variable | Default | Description |
|----------|---------|-------------|
| `openclaw_version` | `latest` | OpenClaw version to install |
| `openclaw_llm_provider` | `ollama` | LLM provider (ollama, anthropic, openai) |
| `openclaw_ollama_url` | `http://10.100.3.1:8081/v1` | Ollama/llama-server API URL |
| `openclaw_enabled` | `true` | Enable OpenClaw service |

### Manual setup (after role deployment)

```bash
# Inside the openclaw container
incus exec openclaw --project ai-tools -- bash

# Run onboarding (interactive)
cd ~/.openclaw && openclaw onboard

# Configure Telegram channel
# Follow the prompts to enter your bot token and user ID

# Start the daemon
openclaw start
```

## Configuration files

Inside the `openclaw` container:

| File | Purpose |
|------|---------|
| `~/.openclaw/openclaw.json` | Main config (model, provider, channels) |
| `~/.openclaw/agents/main/SOUL.md` | Persona definition (identity, tone, language) |
| `~/.openclaw/agents/main/AGENTS.md` | Operating manual with mode-specific sections |

### AGENTS.md structure

The `AGENTS.md` file uses mode markers (`[ALL MODES]`, `[ANKLUME MODE]`,
`[ASSISTANT MODE]`, `[LOCAL MODE]`) to organize content by brain mode.
OpenClaw sends the entire file to whatever LLM backend is active, and
the LLM follows only the sections relevant to its current mode:

| Section marker | Content |
|----------------|---------|
| `[ALL MODES]` | Architecture, OpenClaw internals, brain switching, web tools, limitations |
| `[ANKLUME MODE]` | Dev workflow, infrastructure REST API, incus_exec, self-upgrade, Claude Code sessions |
| `[ASSISTANT MODE]` | General assistant behavior, usage tracking |
| `[LOCAL MODE]` | OpenClaw native tools (exec, browser, cron), skills |

## Credential management

The proxy on `anklume-instance` uses Claude Code CLI which requires
valid OAuth credentials. Credentials are shared via an Incus bind-mount
from the host into the container:

```bash
# The bind-mount is configured as an Incus disk device:
incus config device add anklume-instance claude-creds disk \
  source=/home/user/.claude/.credentials.json \
  path=/root/.claude/.credentials.json \
  readonly=true shift=true
```

This means the container always reads the host's current credentials
file directly — no sync timer, no copy, no delay. When Claude Code
refreshes the OAuth token on the host, the container sees the new
token immediately.

**Requirement**: The host credentials file must be world-readable
(`chmod 644`) because Incus UID mapping maps the host user to
`nobody:nogroup` inside the container.

**Limitation**: OAuth tokens expire every ~12 hours. If Claude Code
is not used interactively on the host for more than 12 hours, the
token expires and Ada loses access to Claude modes. To recover, run
`claude` once on the host (the token refreshes automatically on
startup) — the bind-mount makes the fresh token available instantly.

When the token expires, the proxy returns a `⚙️ [proxy]` tagged
message explaining how to refresh it, rather than an opaque error.

## Troubleshooting

### Ada doesn't respond on Telegram

1. Check OpenClaw is running:
   ```bash
   incus exec openclaw --project ai-tools -- pgrep -f openclaw
   ```

2. Check proxy is running:
   ```bash
   incus exec anklume-instance --project anklume -- pgrep -f mcp-anklume-dev
   ```

3. Check proxy logs:
   ```bash
   incus exec anklume-instance --project anklume -- tail -20 /tmp/proxy.log
   ```

### Claude Code returns authentication error

OAuth token has expired. Start Claude Code interactively on the host
to refresh the token — the bind-mount makes the fresh token available
to the container immediately:

```bash
claude
# (token refreshes automatically, then exit)
```

### Local mode is slow

Check which llama-server service is active:

```bash
incus exec ollama --project ai-tools -- systemctl status llama-server-chat
```

The qwen3:30b-a3b MoE model should have fast inference (~3B active params).
If qwen2.5-coder:32b is loaded instead, the mode switch may have failed.

### Brain switch doesn't send wake-up message

Check that OpenClaw has restarted after the switch:

```bash
incus exec openclaw --project ai-tools -- pgrep -f openclaw
```

The wake-up message is sent via Telegram Bot API directly by the proxy,
with a delay (6s for Claude modes, 15s for local mode to allow model loading).
