# Disposable Instances

anklume supports on-demand, auto-destroyed instances using Incus native
`--ephemeral` flag. Disposable instances are ideal for one-time tasks,
untrusted software testing, and temporary sandboxes.

## How it works

Disposable instances use the Incus `--ephemeral` flag at launch time.
When an ephemeral instance is stopped, Incus automatically destroys it
and reclaims all storage. No manual cleanup is needed.

The instance name is auto-generated with a timestamp pattern:
`disp-YYYYMMDD-HHMMSS`.

## Quick start

```bash
# Launch a disposable instance and attach a shell
make disp

# Launch with a specific image
make disp IMAGE=images:alpine/3.20

# Launch in a specific domain/project
make disp DOMAIN=sandbox

# Run a command and auto-destroy
make disp CMD="apt update && apt upgrade -y"

# Launch as a VM (instead of container)
make disp VM=1
```

Or use the script directly:

```bash
scripts/disp.sh                                    # Launch + attach shell
scripts/disp.sh --image images:alpine/3.20         # Different image
scripts/disp.sh --domain sandbox                   # In specific project
scripts/disp.sh --cmd "apt update && apt upgrade"  # Run command then destroy
scripts/disp.sh --console                          # Attach console
scripts/disp.sh --no-attach                        # Background instance
scripts/disp.sh --vm                               # Launch a VM
```

## Options

| Option | Description |
|--------|-------------|
| `--image IMAGE` | OS image (default: from `infra.yml` or `images:debian/13`) |
| `--domain DOMAIN` | Incus project/domain (default: `default`) |
| `--cmd CMD` | Run CMD inside the instance, then stop (auto-destroys) |
| `--console` | Attach console instead of shell |
| `--no-attach` | Launch without attaching (background) |
| `--vm` | Launch as KVM VM instead of LXC container |
| `-h, --help` | Show help |

## Default image

The script reads `default_os_image` from `infra.yml` (or `infra/base.yml`
for directory mode) to determine the default image. If no `infra.yml` is
found, it falls back to `images:debian/13`.

## Behavior modes

### Interactive shell (default)

```bash
scripts/disp.sh
```

Launches the instance, attaches a bash shell (falls back to sh if bash
is not available). When you exit the shell, the instance is stopped and
auto-destroyed.

### Command mode

```bash
scripts/disp.sh --cmd "curl -sL https://example.com | sha256sum"
```

Launches the instance, runs the command, and stops the instance
(auto-destroying it). Useful for one-shot tasks.

### Console mode

```bash
scripts/disp.sh --console
```

Attaches the Incus console (serial console). Detach with `Ctrl+a q`.

### Background mode

```bash
scripts/disp.sh --no-attach
```

Launches the instance without attaching. The script prints the instance
name and instructions for connecting manually. Stop the instance to
destroy it.

## Security notes

- Disposable instances run in the `default` project unless a `--domain`
  is specified. Use `--domain` to place them in a domain with appropriate
  network isolation.
- Ephemeral instances are completely destroyed on stop — no data persists.
- If you need to preserve files, copy them out with `incus file pull`
  before stopping the instance.
- VM mode (`--vm`) provides stronger isolation than LXC containers.
- The instance name includes a timestamp, making it easy to identify
  when each disposable was created.

## Makefile target

```makefile
make disp [IMAGE=...] [CMD=...] [DOMAIN=...] [VM=1]
```

| Variable | Default | Description |
|----------|---------|-------------|
| `IMAGE` | From `infra.yml` | OS image to use |
| `CMD` | *(none)* | Command to run then destroy |
| `DOMAIN` | `default` | Incus project/domain |
| `VM` | *(unset)* | Set to `1` for VM mode |

## Troubleshooting

### "Cannot connect to the Incus daemon"

Verify Incus is installed and running:

```bash
incus version
systemctl status incus
```

If running inside a container, ensure the Incus socket is mounted.

### "Project not found"

The specified domain must exist as an Incus project. List available
projects:

```bash
incus project list
```

### Instance not destroyed after stopping

Verify the instance was created with `--ephemeral`:

```bash
incus info <instance-name> | grep Ephemeral
```

If `Ephemeral: false`, the instance was not created with the
`--ephemeral` flag.
