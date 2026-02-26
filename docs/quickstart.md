# Quick Start Guide

This guide walks you through deploying your first anklume infrastructure
from scratch.

## Prerequisites

### Host machine

- A Linux host (Debian, Arch, Ubuntu, Fedora)
- [Incus](https://linuxcontainers.org/incus/docs/main/installing/) >= 6.0
  LTS installed and initialized (`incus admin init`)
- At least 4 GB of RAM and 20 GB of free disk space

### Admin instance

anklume runs entirely from inside an admin container. Create it manually
on your host:

```bash
# Create the admin container
incus launch images:debian/13 anklume-instance

# Mount the Incus socket (required for managing other instances)
incus config device add anklume-instance incus-socket proxy \
  connect=unix:/var/lib/incus/unix.socket \
  listen=unix:/var/run/incus/unix.socket \
  bind=container \
  security.uid=0 security.gid=0

# Enable nesting (required for Incus CLI inside the container)
incus config set anklume-instance security.nesting=true

# Enter the container
incus exec anklume-instance -- bash
```

Inside the admin container, install the required tools:

```bash
apt update && apt install -y ansible python3-pip python3-yaml git curl
pip install --break-system-packages pyyaml pytest molecule ruff
```

## Step 1: Clone the repository

```bash
git clone https://github.com/<user>/anklume.git
cd anklume
```

## Step 2: Install dependencies

```bash
anklume setup init
```

This installs Ansible collections and Python tools. You should see output
ending with instructions for system packages.

## Step 3: Create your infrastructure descriptor

```bash
cp infra.yml.example infra.yml
```

Edit `infra.yml` to describe your infrastructure. Here is a minimal example
with two domains:

See `infra.yml.example` for a complete template, or copy one from the
[examples/](../examples/) directory. Key rules:

- **Domain names**: lowercase alphanumeric + hyphens only
- **Machine names**: must be globally unique across all domains
- **trust_level**: determines IP zone (`admin`, `trusted`, `semi-trusted`, `untrusted`, `disposable`)
- **IPs**: auto-assigned from `10.<zone>.<seq>.<host>` (see ADR-038)
- **Gateway**: `.254` is auto-assigned, do not use it for machines

See [SPEC.md section 5](SPEC.md) for the full format reference.

## Step 4: Generate Ansible files

```bash
anklume sync
```

Expected output:

```
Generating files for 2 domain(s)...
  Written: group_vars/all.yml
  Written: inventory/anklume.yml
  Written: group_vars/anklume.yml
  Written: host_vars/anklume-instance.yml
  Written: inventory/lab.yml
  Written: group_vars/lab.yml
  Written: host_vars/lab-server.yml

Done. Run `anklume dev lint` to validate.
```

This creates and updates files in `inventory/`, `group_vars/`, and
`host_vars/`. Each file contains a `=== MANAGED ===` section that is
overwritten on each `anklume sync`. You can add custom variables outside
this section.

## Step 5: Preview changes

```bash
anklume domain check
```

This runs `ansible-playbook --check --diff` to show what would change
without actually modifying anything. Review the output to verify your
infrastructure looks correct.

## Step 6: Apply

```bash
anklume domain apply
```

This creates all networks, Incus projects, profiles, and instances
defined in your `infra.yml`. On a fresh setup, you will see all
resources created. On subsequent runs, only changes are applied
(idempotent).

## Step 7: Verify

After `anklume domain apply` completes, verify your infrastructure:

```bash
# List all Incus instances across projects
incus list --all-projects

# Check a specific domain's network
incus network show net-lab

# Enter a container
incus exec lab-server --project lab -- bash
```

## Ongoing workflow

After your initial setup, the daily workflow is:

1. Edit `infra.yml` (add domains, machines, profiles)
2. `anklume sync` to regenerate Ansible files
3. `anklume domain check` to preview changes
4. `anklume domain apply` to converge

## Useful commands

| Command | Description |
|---------|-------------|
| `anklume sync` | Generate Ansible files from infra.yml |
| `anklume sync --dry-run` | Preview generation without writing |
| `anklume domain check` | Dry-run (--check --diff) |
| `anklume domain apply` | Apply full infrastructure |
| `anklume domain apply lab` | Apply a single domain |
| `anklume snapshot create` | Snapshot all instances |
| `anklume dev lint` | Run all validators |
| `anklume --help` | List all available targets |

## Troubleshooting

- **Validation errors on anklume sync**: The generator checks all
  constraints (unique names, unique subnets, valid IPs) before writing.
  Read the error message for the specific constraint that failed.
- **Incus socket not found**: Verify the proxy device is configured with
  `incus config device show anklume-instance`
- **Container fails to start after reboot**: The `/var/run/incus/`
  directory may not exist. See ADR-019 in [ARCHITECTURE.md](ARCHITECTURE.md).
- **anklume domain apply hangs**: Check Incus is running (`systemctl status incus`)
  and the socket is accessible (`incus list` from inside anklume-instance).

## Next steps

- [Lab deployment guide](lab-tp.md) for teachers
- [GPU + LLM guide](gpu-llm.md) for GPU passthrough and Ollama
- [Example configurations](../examples/) for ready-to-use infra.yml files
- [Full specification](SPEC.md) for the complete format reference
