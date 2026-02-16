# Sandbox Isolation

Maximum isolation setup for testing untrusted software. Includes both
LXC containers (lightweight) and a KVM VM (hardware-level isolation).
All sandbox instances are ephemeral and the domain has no external
network access.

## Use case

You need to run untrusted software (downloaded binaries, suspicious
scripts, experimental code) in a fully isolated environment. Choose
between LXC (fast, lightweight) or VM (stronger isolation with
separate kernel). The sandbox can be destroyed and recreated at any
time without affecting your main system.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller (protected) |
| sandbox | 10 | Ephemeral isolation sandbox |

## Machines

| Machine | Domain | Type | IP | Role |
|---------|--------|------|-----|------|
| sbx-admin | anklume | lxc | 10.100.0.10 | Ansible controller |
| sbx-test | sandbox | lxc | 10.100.10.10 | Disposable test container |
| sbx-vm | sandbox | vm | 10.100.10.20 | Disposable VM sandbox |
| sbx-monitor | sandbox | lxc | 10.100.10.11 | Monitoring container |

## Isolation features

- **Ephemeral domain**: the entire sandbox domain is `ephemeral: true`,
  allowing easy teardown
- **Ephemeral instances**: `sbx-test` and `sbx-vm` are ephemeral at
  both domain and machine level
- **VM isolation**: `sbx-vm` runs as a KVM VM with its own kernel,
  providing hardware-level isolation for untrusted workloads
- **No cross-domain traffic**: the sandbox network is isolated from the
  admin network (when nftables rules are configured)
- **Snapshot before each test**: take a snapshot, run the software,
  restore if needed

## Hardware requirements

- 4 CPU cores (2 dedicated to VM)
- 8 GB RAM (2 GiB allocated to VM)
- 20 GB disk

## Getting started

```bash
cp examples/sandbox-isolation/infra.yml infra.yml
make sync
make apply
```

## Workflow

```bash
# Snapshot clean state
make snapshot-domain D=sandbox NAME=clean

# Enter the test container
incus exec sbx-test --project sandbox -- bash

# ... run untrusted software ...

# Restore clean state
make restore-domain D=sandbox NAME=clean
```

## Network isolation

To fully block external network access from the sandbox domain,
configure nftables on the host to drop outbound traffic from
`net-sandbox`. See Phase 8 in
[ROADMAP.md](../../docs/ROADMAP.md) for details.
