# Student Sysadmin

A minimal 2-domain setup for sysadmin students learning Linux
administration.

## Use case

A student wants to practice system administration (web servers,
databases, networking) in an isolated environment without risking
their main system.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller |
| lab | 1 | Ephemeral lab environment |

## Machines

| Machine | Domain | IP | Role |
|---------|--------|-----|------|
| sa-admin | anklume | 10.100.0.10 | Ansible controller with nesting |
| sa-web | lab | 10.100.1.10 | Web server for exercises |
| sa-db | lab | 10.100.1.11 | Database server for exercises |

## Hardware requirements

- 2 CPU cores
- 4 GB RAM
- 10 GB disk

## Getting started

```bash
cp examples/student-sysadmin/infra.yml infra.yml
make sync
make apply
```

The lab domain is ephemeral, so you can freely destroy and recreate it.
Take snapshots before experiments:

```bash
make snapshot-domain D=lab NAME=clean-state
# ... do your exercises ...
make restore-domain D=lab NAME=clean-state
```
