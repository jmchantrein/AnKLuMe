# tmux Console — QubesOS-Style Visual Domain Isolation

anklume automatically generates a tmux session from `infra.yml` with
color-coded panes that reflect domain trust levels, providing visual
domain isolation similar to QubesOS colored window borders.

## Quick start

```bash
anklume console              # Launch tmux console
anklume console --dry-run    # Preview without creating session
anklume console --kill       # Force recreation (kill existing session)
```

Or use the script directly:

```bash
python3 scripts/console.py
python3 scripts/console.py --dry-run
python3 scripts/console.py --kill
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ tmux session "anklume"                                   │
│ ┌─────────────┐ ┌──────────┐ ┌──────────────────┐      │
│ │ pane bg:blue │ │ bg:green │ │ bg:yellow        │      │
│ │ admin-ctrl   │ │ pro-dev  │ │ perso-desktop    │      │
│ │ incus exec...│ │          │ │                  │      │
│ └─────────────┘ └──────────┘ └──────────────────┘      │
│ [0:admin]  [1:pro]  [2:perso]  [3:ai-tools]             │
└─────────────────────────────────────────────────────────┘
```

Each domain becomes a tmux window. Each machine in the domain becomes
a pane within that window. Pane background colors are set **server-side**
by tmux, not by the container — this means containers cannot spoof
their visual identity (same security model as QubesOS dom0 borders).

## Trust level colors

| Trust level | Color | Use case |
|------------|-------|----------|
| `admin` | Dark blue (`colour17`) | Administrative domains with full system access |
| `trusted` | Dark green (`colour22`) | Production workloads, personal data |
| `semi-trusted` | Dark yellow (`colour58`) | Development, testing, low-risk browsing |
| `untrusted` | Dark red (`colour52`) | Untrusted software, risky browsing |
| `disposable` | Dark magenta (`colour53`) | Ephemeral sandboxes, one-time tasks |

Colors are defined in `scripts/console.py` as `TRUST_COLORS` and
`TRUST_LABELS` dictionaries.

## Configuration

### Explicit trust level in infra.yml

Add `trust_level` to any domain:

```yaml
domains:
  admin:
    description: "Administration"
    trust_level: admin
    machines:
      sa-admin:
        type: lxc

  lab:
    description: "Lab environment"
    trust_level: disposable
    machines:
      lab-web:
        type: lxc
```

### Auto-inferred trust level

If `trust_level` is not set, the console infers it using these heuristics:

1. **Domain name contains "admin"** → `admin`
2. **`ephemeral: true`** → `disposable`
3. **Default** → `trusted`

Example:

```yaml
domains:
  admin:          # Inferred: admin (name contains "admin")
    subnet_id: 0
    machines: { ... }

  lab:            # Inferred: disposable (ephemeral: true)
    subnet_id: 1
    ephemeral: true
    machines: { ... }

  pro:            # Inferred: trusted (default)
    subnet_id: 2
    machines: { ... }
```

## Reconnection

The console creates a persistent tmux session named `anklume` (configurable
via `--session-name`). If you detach or your SSH connection drops, reconnect
with:

```bash
tmux attach -t anklume
```

If the session already exists, `anklume console` attaches to it instead of
creating a new one.

## Recreation

To force recreation of the session (e.g., after adding/removing domains):

```bash
anklume console --kill
```

This kills the existing session and creates a fresh one.

## Command-line options

```bash
python3 scripts/console.py [OPTIONS] [infra_file]

Options:
  infra_file              Path to infra.yml or infra/ (default: auto-detect)
  --dry-run               Print configuration without creating session
  --attach                Attach to session after creation (default)
  --no-attach             Do not attach to session after creation
  --session-name NAME     Tmux session name (default: anklume)
  --prefix KEY            Tmux prefix key (default: C-a, see below)
  --kill                  Kill existing session before creating new one
```

## Nested tmux (prefix key)

The anklume console uses **`Ctrl-a`** as its prefix key (not the default
`Ctrl-b`). This avoids conflicts when running tmux inside containers:

- **`Ctrl-a`** controls the **outer** anklume session (switch windows, panes)
- **`Ctrl-b`** passes through to **inner** tmux sessions inside containers

This is essential for sysadmins who use tmux as their daily workflow
inside the containers they manage.

To use a different prefix:

```bash
python3 scripts/console.py --prefix C-q     # Use Ctrl-q instead
python3 scripts/console.py --prefix C-b     # Use standard Ctrl-b (no nesting comfort)
```

## Pane commands

Each pane runs `incus exec <machine> --project <domain> -- bash`, which
gives you a shell inside the machine. All communication happens via the
Incus socket (not the network), so the admin domain does not need special
network access rules.

## Pane border labels

Each pane has a border label showing `[domain] machine-name`. This is set
server-side by tmux and cannot be spoofed by the container.

Example:

```
┌────────────────────────────┐
│ [admin] sa-admin           │
│ root@sa-admin:~#           │
│                            │
└────────────────────────────┘
```

## Layouts

Windows with multiple panes use the `tiled` layout, which distributes
panes evenly. You can change the layout after creation with standard
tmux keybindings:

- `Ctrl-a Space` — cycle through layouts
- `Ctrl-a Alt-1` — even-horizontal
- `Ctrl-a Alt-2` — even-vertical
- `Ctrl-a Alt-5` — tiled (default)

## Navigation

The anklume session uses `Ctrl-a` as prefix (see above):

| Action | anklume session | Inner tmux (in container) |
|--------|----------------|--------------------------|
| Switch window | `Ctrl-a 0`, `Ctrl-a 1`, ... | `Ctrl-b 0`, `Ctrl-b 1`, ... |
| Next window | `Ctrl-a n` | `Ctrl-b n` |
| Previous window | `Ctrl-a p` | `Ctrl-b p` |
| Switch pane | `Ctrl-a o` or `Ctrl-a <arrow>` | `Ctrl-b o` |
| Detach | `Ctrl-a d` | `Ctrl-b d` |

## Troubleshooting

### "Session 'anklume' already exists"

Expected behavior — the console attaches to the existing session.
Use `KILL=1` to force recreation.

### Pane colors not showing

Verify your terminal supports 256 colors:

```bash
echo $TERM    # Should be "screen-256color" or "tmux-256color" inside tmux
```

If not, set it in your `~/.tmux.conf`:

```
set -g default-terminal "tmux-256color"
```

### "incus exec" fails in pane

Verify the machine exists and is running:

```bash
incus list --all-projects
```

If the machine does not exist yet, run `anklume domain apply` to create infrastructure.

### Cannot attach to session

If `tmux attach -t anklume` fails with "session not found", the session
was killed or tmux was restarted. Run `anklume console` to recreate it.

### Pane border labels not showing

Pane border labels require tmux >= 3.0. Check your version:

```bash
tmux -V    # Should be "tmux 3.0" or higher
```

On older tmux versions, the console works but border labels are not displayed.

## Examples

### Standard usage

```bash
# Create and attach to console
anklume console

# Detach
Ctrl-a d

# Reconnect later
tmux attach -t anklume
```

### Dry-run preview

```bash
anklume console --dry-run
```

Output:

```
Session: anklume
  Window [0] admin (trust: admin, color: dark blue)
    Pane: sa-admin → incus exec sa-admin --project admin -- bash
  Window [1] lab (trust: disposable, color: dark magenta)
    Pane: sa-db → incus exec sa-db --project lab -- bash
    Pane: sa-web → incus exec sa-web --project lab -- bash
```

### Custom session name

```bash
python3 scripts/console.py --session-name my-infra
tmux attach -t my-infra
```

### Non-interactive creation

```bash
python3 scripts/console.py --no-attach
# Session created but not attached — attach later when needed
```

## Dependencies

- Python 3.11+
- `pip install libtmux` (installed via `anklume setup init`)
- tmux >= 3.0 (for pane border labels)

## Security model

Colors are set **server-side** by tmux using `select-pane -P 'bg=...'`.
Containers cannot change their pane background color or border label,
preventing visual spoofing. This matches the QubesOS security model where
colored borders are drawn by dom0 (the hypervisor), not by the VM guests.

Pane commands run `incus exec` over the Incus socket, not over the network.
No SSH keys, no network traffic between admin and domains.
