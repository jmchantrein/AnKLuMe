# Golden Images and Templates

anklume supports golden images — pre-provisioned instance templates
that can be efficiently cloned to create new instances. This enables
fast instance creation and centralized update management.

## How it works

A golden image is simply an Incus instance with a snapshot named
`pristine`. The workflow is:

1. **Create**: Provision an instance with desired roles, stop it,
   and create a `pristine` snapshot
2. **Derive**: Clone the snapshot to create new instances using
   `incus copy` (CoW on ZFS/Btrfs)
3. **Publish** (optional): Export the snapshot as a reusable Incus
   image that can be referenced in `infra.yml` as `os_image`

```
┌──────────────────┐       incus copy       ┌──────────────────┐
│ pro-dev          │  ──────────────────────▶│ pro-dev-clone    │
│ (golden image)   │     (CoW on ZFS/Btrfs)  │ (derived)        │
│                  │                          │                  │
│ snap: pristine   │       incus publish      │                  │
│                  │  ──────────────────────▶ local:golden-pro  │
└──────────────────┘       (Incus image)                        │
```

## Copy-on-Write (CoW) efficiency

When using ZFS or Btrfs storage backends, `incus copy` creates a
CoW clone of the snapshot. This means:

- **Instant creation**: the copy is nearly instantaneous
- **Minimal disk usage**: only differences from the template consume
  space
- **Independent instances**: changes to the clone do not affect the
  template, and vice versa

On the `dir` storage backend, `incus copy` performs a full copy
(slower, uses full disk space).

Verify your storage backend:

```bash
incus storage list
```

## Quick start

### 1. Provision and create a golden image

```bash
# Deploy the instance with its roles first
make apply

# Create the golden image (stops instance + creates pristine snapshot)
make golden-create NAME=pro-dev
```

### 2. Derive new instances

```bash
# Create a clone from the golden image
make golden-derive TEMPLATE=pro-dev INSTANCE=pro-dev-v2

# Start the clone
incus start pro-dev-v2 --project pro
```

### 3. Publish as a reusable image (optional)

```bash
# Publish the golden image as a local Incus image
make golden-publish TEMPLATE=pro-dev ALIAS=golden-pro

# Use in infra.yml
# machines:
#   new-instance:
#     os_image: "golden-pro"
```

### 4. List golden images

```bash
make golden-list                  # All projects
make golden-list PROJECT=admin    # Specific project
```

## Makefile targets

| Target | Description |
|--------|-------------|
| `make golden-create NAME=<name>` | Stop instance + create pristine snapshot |
| `make golden-derive TEMPLATE=<name> INSTANCE=<new>` | CoW copy from pristine |
| `make golden-publish TEMPLATE=<name> ALIAS=<alias>` | Publish as Incus image |
| `make golden-list` | List instances with pristine snapshots |

All targets accept an optional `PROJECT=<project>` parameter to specify
the Incus project (auto-detected if omitted).

## Profile propagation

When you modify an Incus profile, all instances using that profile
are automatically updated (native Incus behavior). This means:

- Golden images and their derived instances share profiles
- Updating a profile propagates to all derived instances
- No need to re-derive after profile changes

This is particularly useful for resource limits, device configurations,
and network settings managed via profiles.

## Workflow examples

### Development environment template

```bash
# 1. Provision a development environment
make apply-limit G=pro

# 2. Install additional tools manually
incus exec pro-dev --project pro -- apt install -y vim tmux git

# 3. Create golden image
make golden-create NAME=pro-dev

# 4. Derive for each developer
make golden-derive TEMPLATE=pro-dev INSTANCE=pro-alice
make golden-derive TEMPLATE=pro-dev INSTANCE=pro-bob
```

### Lab deployment for students

```bash
# 1. Create a reference lab instance
make apply-limit G=lab

# 2. Golden image it
make golden-create NAME=lab-reference

# 3. Derive N student instances
for i in $(seq 1 20); do
    make golden-derive TEMPLATE=lab-reference INSTANCE="lab-student-${i}"
done
```

### Update cycle

```bash
# 1. Start the golden image
incus start pro-dev --project pro

# 2. Apply updates
incus exec pro-dev --project pro -- apt update && apt upgrade -y

# 3. Re-create golden image (replaces pristine snapshot)
make golden-create NAME=pro-dev

# 4. Derive fresh instances from updated template
make golden-derive TEMPLATE=pro-dev INSTANCE=pro-dev-updated
```

## Troubleshooting

### "Instance not found"

Verify the instance exists and check the project:

```bash
incus list --all-projects | grep <name>
```

### Derived instance has wrong network config

Derived instances keep the same IP as the template. Update the IP
before starting:

```bash
incus config device override <instance> eth0 ipv4.address=<new-ip> --project <project>
```

### Full copy instead of CoW

If disk usage is unexpectedly high after derive, check your storage
backend. CoW only works on ZFS and Btrfs:

```bash
incus storage list
# Look for "driver: zfs" or "driver: btrfs"
```

### Publish fails with "snapshot not found"

Ensure the instance has a `pristine` snapshot:

```bash
incus snapshot list <instance> --project <project>
```

If not, create it first:

```bash
make golden-create NAME=<instance>
```
