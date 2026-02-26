# Developer

An anklume developer setup with a dev-test domain configured for
Incus-in-Incus testing.

## Use case

You are contributing to anklume and need a test environment where you
can run Molecule tests in isolation using nested Incus containers. The
dev-runner container runs its own Incus daemon inside, creating a
complete sandbox for testing without affecting production.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller |
| dev-test | 1 | Ephemeral development and testing |

## Machines

| Machine | Domain | IP | Role |
|---------|--------|-----|------|
| dev-admin | anklume | 10.100.0.10 | Ansible controller |
| dev-runner | dev-test | 10.100.1.10 | Test runner (nested Incus) |
| dev-sandbox | dev-test | 10.100.1.11 | Manual testing sandbox |

## Nesting configuration

The `dev-runner` container has the following security options for
Incus-in-Incus support:

- `security.nesting: "true"` -- allows running containers inside
- `security.syscalls.intercept.mknod: "true"` -- required for device
  creation in nested containers
- `security.syscalls.intercept.setxattr: "true"` -- required for
  extended attributes in nested containers

## Hardware requirements

- 4 CPU cores
- 8 GB RAM
- 30 GB disk

## Getting started

```bash
cp examples/developer/infra.yml infra.yml
anklume sync
anklume domain apply
```

After deployment, enter the test runner and install Incus inside:

```bash
incus exec dev-runner --project dev-test -- bash

# Inside dev-runner:
apt install -y incus
incus admin init --minimal
# Now you can run Molecule tests with nested containers
```

See Phase 12 in [ROADMAP.md](../../docs/ROADMAP.md) for the full
Incus-in-Incus testing setup.
