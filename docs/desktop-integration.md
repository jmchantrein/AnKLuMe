# Desktop Integration

anklume provides desktop environment integration for workstation users.
Domain-colored visual cues in terminals and window managers give instant
feedback about which security domain you're working in — the same model
as QubesOS colored window borders.

## Quick start

```bash
make console                    # tmux console with colored panes
make domain-exec I=pro-dev TERMINAL=1  # Colored terminal window
make clipboard-to I=pro-dev     # Copy host clipboard to container
make clipboard-from I=pro-dev   # Copy container clipboard to host
make desktop-config             # Generate Sway/foot/.desktop configs
make dashboard                  # Web dashboard on http://localhost:8888
```

## tmux Console (Phase 19a)

The tmux console auto-generates a session from `infra.yml` with
per-domain colored panes:

```bash
make console          # Create and attach
make console KILL=1   # Recreate session
make console DRY_RUN=1  # Preview without creating
```

Colors are set **server-side** via `select-pane -P 'bg=...'` — containers
cannot spoof their visual identity (same security model as QubesOS dom0
colored borders).

| Trust Level | Color | tmux Code |
|------------|-------|-----------|
| admin | Dark blue | colour17 |
| trusted | Dark green | colour22 |
| semi-trusted | Dark yellow | colour58 |
| untrusted | Dark red | colour52 |
| disposable | Dark magenta | colour53 |

Reconnect: `tmux attach -t anklume`

## Clipboard Forwarding

Controlled clipboard sharing between host and containers. Each transfer
is an **explicit user action** — no automatic clipboard sync between
domains.

```bash
# Host clipboard → container
make clipboard-to I=pro-dev
scripts/clipboard.sh copy-to pro-dev --project pro

# Container clipboard → host
make clipboard-from I=pro-dev
scripts/clipboard.sh copy-from pro-dev --project pro
```

### How it works

- Uses `wl-copy`/`wl-paste` (Wayland) or `xclip`/`xsel` (X11) on the host
- Transfers via `incus file push`/`pull` to `/tmp/anklume-clipboard`
- Compatible with the MCP `clipboard_get`/`clipboard_set` tools (Phase 20c)
- Auto-detects display server and clipboard backend

### Security model

- Every clipboard transfer is a conscious user decision
- No daemon, no background sync, no automatic bridging
- Each direction is a separate command — read and write are explicit
- Container cannot trigger clipboard reads from the host

## Domain-Exec Wrapper

Launch commands in containers with domain context:

```bash
# Interactive shell in container
make domain-exec I=pro-dev

# Colored terminal window
make domain-exec I=pro-dev TERMINAL=1

# Run a specific command
scripts/domain-exec.sh pro-dev -- htop

# Colored terminal with specific command
scripts/domain-exec.sh pro-dev --terminal -- firefox
```

### Environment variables

The wrapper sets these inside the container:

| Variable | Description |
|----------|-------------|
| `ANKLUME_DOMAIN` | Domain name (e.g., `pro`) |
| `ANKLUME_TRUST_LEVEL` | Trust level (e.g., `trusted`) |
| `ANKLUME_INSTANCE` | Instance name (e.g., `pro-dev`) |

### Terminal mode

With `--terminal`, the wrapper opens a new terminal window with:
- Window title: `[domain] instance` (e.g., `[pro] pro-dev`)
- Background color matching the domain trust level
- Supported terminals: foot (Wayland), alacritty, xterm

## Desktop Environment Integration

Generate configuration snippets for desktop environments:

```bash
make desktop-config             # Generate all configs
python3 scripts/desktop_config.py --sway    # Sway/i3 only
python3 scripts/desktop_config.py --foot    # foot terminal only
python3 scripts/desktop_config.py --desktop # .desktop entries only
```

Output goes to `desktop/` directory.

### Sway/i3

Generated config colorizes window borders by domain:

```
# In ~/.config/sway/config (or config.d/anklume.conf)
default_border pixel 3
for_window [title="^\[admin\]"] border pixel 3
for_window [title="^\[admin\]"] client.focused #3333ff #3333ff #ffffff #3333ff
for_window [title="^\[pro\]"] border pixel 3
for_window [title="^\[pro\]"] client.focused #33cc33 #33cc33 #ffffff #33cc33
```

Windows are matched by title pattern (set by `domain-exec.sh`) or
`app_id` pattern (set by `--terminal` mode).

### foot terminal

Generated profiles provide domain-colored backgrounds:

```ini
# foot --override 'colors.background=#0a0a2a'   # admin (dark blue)
# foot --override 'colors.background=#0a1a0a'   # pro (dark green)
```

### .desktop entries

Generated `.desktop` files for quick-launch from application menus:

```
~/.local/share/applications/
├── anklume-anklume-instance.desktop
├── anklume-pro-dev.desktop
└── anklume-perso-desktop.desktop
```

Each entry launches `domain-exec.sh` with `--terminal` for the
corresponding instance.

## Web Dashboard

Live infrastructure status in a browser:

```bash
make dashboard              # http://localhost:8888
make dashboard PORT=9090    # Custom port
make dashboard HOST=0.0.0.0 # Listen on all interfaces
```

### Features

- Real-time instance status (auto-refresh every 5s via htmx)
- Domain-colored instance cards with trust level badges
- Network listing with subnet information
- Network policy visualization
- No external Python dependencies (uses stdlib `http.server` + htmx CDN)

### API endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /` | Main dashboard page |
| `GET /api/status` | JSON: instances, networks, policies |
| `GET /api/infra` | JSON: parsed infra.yml |
| `GET /api/html` | HTML fragment for htmx updates |

### Security

- **Read-only** — the dashboard does not modify infrastructure
- **Local only** by default (binds to `127.0.0.1`)
- Use `HOST=0.0.0.0` to expose on the network (use with caution)
- No authentication — rely on network-level access control

## Color scheme

All desktop integration tools share the same trust level → color mapping:

| Trust Level | Border (bright) | Background (dark) | Description |
|-------------|----------------|-------------------|-------------|
| admin | `#3333ff` | `#0a0a2a` | Full system access |
| trusted | `#33cc33` | `#0a1a0a` | Production, personal |
| semi-trusted | `#cccc33` | `#1a1a0a` | Development, testing |
| untrusted | `#cc3333` | `#1a0a0a` | Risky software |
| disposable | `#cc33cc` | `#1a0a1a` | Ephemeral sandboxes |

Colors are configurable via `trust_level` in `infra.yml` (see SPEC.md).
