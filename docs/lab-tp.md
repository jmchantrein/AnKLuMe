# Lab Deployment Guide for Teachers

This guide explains how to use anklume to deploy networking labs for
students. Each student gets an isolated domain with its own subnet,
Incus project, and set of containers.

## Concept: domain-per-student

anklume's domain model maps naturally to lab deployments:

```
admin domain       = teacher's management environment
student-01 domain  = student 1's isolated lab
student-02 domain  = student 2's isolated lab
...
student-N  domain  = student N's isolated lab
```

Each student domain:
- Has its own isolated network (`net-student-XX`)
- Cannot communicate with other student domains
- Can be snapshotted, restored, or destroyed independently
- Is marked `ephemeral: true` for easy cleanup

## Step 1: Design your infra.yml

Use the [teacher-lab](../examples/teacher-lab/) example as a starting
point:

```bash
cp examples/teacher-lab/infra.yml infra.yml
```

The example includes 1 admin domain + 3 student domains, each with a
web server and a client container. Key naming conventions:

- Machine name prefix per student: `s01-web`, `s02-web`, etc. (globally
  unique as required by ADR-008)
- Domain names: `student-XX` pattern
- subnet_id increments per student (1, 2, 3, ...)

## Step 2: Deploy

```bash
make sync    # Generate Ansible files
make check   # Preview changes
make apply   # Create everything
```

For a class of 30 students with 2 containers each, this creates:
- 31 domains (1 admin + 30 students)
- 31 networks
- 61 containers (1 admin + 60 student containers)

## Step 3: Pre-lab snapshots

Before students start working, snapshot the clean state:

```bash
make snapshot NAME=pre-lab
```

This snapshots every instance across all domains. You can also snapshot
a single student domain:

```bash
make snapshot-domain D=student-01 NAME=pre-lab
```

## Network isolation

Each student domain has its own network bridge. By default, containers
within a domain can communicate with each other, but cross-domain traffic
is blocked (when nftables rules are configured, see Phase 8 in
[ROADMAP.md](ROADMAP.md)).

This means:
- Student 1's web server can talk to Student 1's client
- Student 1 cannot access Student 2's containers
- The admin domain manages all students via the Incus socket (not the network)

## Reset between sessions

### Reset a single student

Restore the pre-lab snapshot for one student:

```bash
make restore-domain D=student-05 NAME=pre-lab
```

### Reset all students

Restore the pre-lab snapshot globally:

```bash
make restore NAME=pre-lab
```

### Full teardown and rebuild

Since student domains are `ephemeral: true`, you can destroy and
recreate them. Remove the domain from `infra.yml`, run `make sync
--clean-orphans`, then re-add it and `make apply`.

## Scaling

### Adding a student

Add a new domain block in `infra.yml` with the next `subnet_id` and
unique machine names, then run `make sync && make apply-limit
G=student-04`.

### Removing a student

Remove the domain from `infra.yml` and run `make sync-clean`. Incus
resources must be destroyed separately via the `incus` CLI.

## Hardware requirements

As a guideline for LXC containers with `base_system`:

| Students | Containers | RAM (est.) | Disk (est.) |
|----------|-----------|------------|-------------|
| 10 | 21 | 8 GB | 20 GB |
| 20 | 41 | 16 GB | 40 GB |
| 30 | 61 | 24 GB | 60 GB |

You can limit resources per student using `config.limits.cpu` and
`config.limits.memory` in the machine definition.

## Student access

Students access containers via `incus exec s01-web --project student-01
-- bash` (from the host or admin container).

## Tips

- Use `ephemeral: true` for all student domains for easy cleanup
- Take snapshots before each lab session
- Use `make apply-limit G=student-XX` to rebuild a single student

## Example configurations

See the [examples](../examples/) directory for ready-to-use lab
configurations:

- [teacher-lab](../examples/teacher-lab/) — admin + 3 student domains
- [student-sysadmin](../examples/student-sysadmin/) — simple 2-domain
  setup for sysadmin students
