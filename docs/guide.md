# Interactive Guide

anklume includes two interactive guides:

1. **Capability Tour** — discover what anklume can do (terminal + web)
2. **Setup Wizard** — initial infrastructure setup (terminal)

## Capability Tour (terminal)

```bash
anklume guide              # Interactive chapter menu
anklume guide CHAPTER=3    # Jump to chapter 3
anklume guide AUTO=1       # Non-interactive (CI)
anklume guide LANG=fr      # French
```

### Chapters

| # | Title | Demo | Prerequisite |
|---|-------|------|-------------|
| 1 | Domain Isolation | `incus list --all-projects` | Incus + domains |
| 2 | Tmux Console | `console.py --dry-run` | tmux |
| 3 | GUI App Forwarding | Wayland socket sharing | Wayland display |
| 4 | Clipboard Transfer | `clipboard.sh copy-to/from` | Incus |
| 5 | Network Isolation | nftables rules | Incus |
| 6 | Snapshots & Restore | Create, modify, restore | Incus |
| 7 | Web Dashboard | `dashboard.py` in browser | FastAPI |
| 8 | GPU & AI Services | `nvidia-smi`, Ollama | GPU (optional) |

Each chapter follows: **Explain**, **Live demo**, **Your turn**, **Recap**

Chapters with missing prerequisites are skipped gracefully (no error).

## Learning Platform (web)

The learning platform provides a Play-with-Docker-style split-pane
interface: guide content on the left, a live terminal on the right.
Clickable commands inject directly into the terminal.

```bash
anklume learn start          # Start on port 8890
anklume learn start --port 9000  # Custom port
```

### Architecture

The platform runs inside a dedicated `anklume-learn` container in
the Incus `learn` project. The container connects to Incus via a
TLS certificate restricted to the `learn` project only — it cannot
see or modify production projects (pro, perso, anklume, etc.).

```
Browser (host)  →  http://localhost:8890
                          │
              ┌───────────┘
              ↓
  anklume-learn (LXC, project: learn)
  ├── platform_server.py (FastAPI)
  │   ├── /guide/{n}     — split-pane view
  │   └── /ws/terminal   — xterm.js WebSocket
  └── PTY (bash)
      └── incus CLI (TLS, learn project only)
```

### Setup

```bash
anklume learn setup        # Create container + demo instances
anklume learn teardown     # Destroy everything
```

`anklume learn setup` creates:
- The `learn` Incus project
- The `anklume-learn` container with Python + FastAPI
- Demo instances (`learn-web`, `learn-db`) for guided exercises
- A TLS certificate restricted to the `learn` project

### Routes

| Route | Description |
|-------|-------------|
| `GET /` | Landing page (guide + labs links) |
| `GET /guide` | Chapter overview (8 chapters) |
| `GET /guide/{n}` | Split-pane: content + terminal |
| `GET /labs` | Educational labs (future) |
| `WS /ws/terminal/{id}` | Terminal WebSocket |

## Setup Wizard

```bash
anklume guide SETUP=1      # Run setup wizard
anklume guide STEP=3       # Resume from step 3 (legacy)
```

### Setup steps

| Step | Name | Description |
|------|------|-------------|
| 0 | Environment | Detect host vs container, delegate if needed |
| 1 | Prerequisites | Check required tools |
| 2 | Use case | Select example (student, teacher, pro, custom) |
| 3 | infra.yml | Create from template |
| 4 | Generate | Run `anklume sync` |
| 5 | Validate | Syntax check |
| 6 | Apply | Create Incus infrastructure |
| 7 | Verify & Snapshot | Check instances, create initial snapshot |
| 8 | Next steps | Links to capability tour and documentation |

## Auto mode

The `--auto` flag (or `AUTO=1`) runs non-interactively:
- Skips all prompts (selects default option)
- Skips steps requiring live interaction (GUI, dashboard launch)
- Exits immediately on prerequisite failure

## Deep dives

After the capability tour, explore specialized topics:

- [Network isolation](network-isolation.md) — nftables, firewall VM
- [GPU & AI](gpu-advanced.md) — Ollama, VRAM flush, sanitization
- [Educational labs](../labs/README.md) — guided exercises
- [Tor gateway](tor-gateway.md) — anonymous routing
- [LLM sanitizer](llm-sanitizer.md) — pattern-based anonymization proxy
- [STT service](stt-service.md) — Speech-to-Text diagnostics

## Production protection

Deployed instances can block `git push` to prevent accidental code changes
in production:

```bash
anklume setup production         # Enable (creates /etc/anklume/deployed)
anklume setup production --off   # Disable
```

When enabled, the `pre-push` git hook blocks pushes with a clear message.
The `bootstrap.sh --prod` flag automatically enables production mode.
Bypass once with `git push --no-verify`.

## LLM sanitizer dry-run

Preview what the sanitization proxy would redact before deploying:

```bash
echo '10.120.1.5 on net-pro' | anklume llm sanitize    # Show redactions
anklume llm sanitize --file prompt.txt                   # From file
anklume llm sanitize --file prompt.txt --json            # JSON output
anklume llm patterns                                     # List all patterns
anklume llm patterns --test "10.120.1.5"                 # Test a string
```

Patterns are loaded from the Ansible template
(`roles/llm_sanitizer/templates/patterns.yml.j2`) — 30 patterns in 7
categories: IP addresses, Incus resources, credentials, FQDNs, and more.

## STT diagnostics

Diagnose and manage the Speaches/Whisper STT service:

```bash
anklume stt status     # Health, VRAM, Ollama conflicts
anklume stt restart    # Unload Ollama models + restart Speaches
anklume stt logs       # Recent logs (--lines N)
anklume stt test       # Quick health check
```

The `restart` command first unloads all Ollama models to free VRAM,
then restarts Speaches and waits for the health endpoint.

## Host resource monitoring

Unified view of CPU, RAM, disk, GPU/VRAM, and loaded LLM models:

```bash
anklume system resources                  # Rich CLI table
anklume system resources --json           # JSON output
anklume system resources --output tmux    # Compact tmux status bar
anklume system resources --output web     # HTML dashboard widget
anklume system resources --watch          # Continuous refresh (2s)
```

The tmux output (`CPU:3% RAM:19% VRAM:98% T:41°`) is automatically
injected into the tmux status bar by the console launcher. The web
widget appears at the top of the dashboard with color-coded progress
bars.
