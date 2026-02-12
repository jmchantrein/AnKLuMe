# Sandbox Isolation

Maximum isolation setup for testing untrusted software. All containers
are ephemeral and the sandbox domain has no external network access.

## Use case

You need to run untrusted software (downloaded binaries, suspicious
scripts, experimental code) in a fully isolated environment. The
sandbox can be destroyed and recreated at any time without affecting
your main system.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| admin | 0 | Ansible controller (protected) |
| sandbox | 10 | Ephemeral isolation sandbox |

## Machines

| Machine | Domain | IP | Role |
|---------|--------|-----|------|
| sbx-admin | admin | 10.100.0.10 | Ansible controller |
| sbx-test | sandbox | 10.100.10.10 | Disposable test container |
| sbx-monitor | sandbox | 10.100.10.11 | Monitoring container |

## Isolation features

- **Ephemeral domain**: the entire sandbox domain is `ephemeral: true`,
  allowing easy teardown
- **Ephemeral containers**: `sbx-test` is marked ephemeral at both the
  domain and machine level
- **No cross-domain traffic**: the sandbox network is isolated from the
  admin network (when nftables rules are configured)
- **Snapshot before each test**: take a snapshot, run the software,
  restore if needed

## Hardware requirements

- 2 CPU cores
- 4 GB RAM
- 10 GB disk

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
