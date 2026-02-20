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
| `~/.openclaw/agents/main/AGENTS.md` | API instructions and tool documentation |

## Credential management

The proxy on `anklume-instance` uses Claude Code CLI which requires
valid OAuth credentials. A systemd timer (`anklume-sync-creds.timer`)
syncs credentials from the host every 2 hours:

```bash
# Install the credential sync timer (on the host)
host/boot/sync-claude-credentials.sh --install

# Manual sync
host/boot/sync-claude-credentials.sh
```

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

OAuth token has expired. Run the sync script on the host:

```bash
host/boot/sync-claude-credentials.sh
```

Or start Claude Code interactively on the host to refresh the token:

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
