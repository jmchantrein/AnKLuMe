# Teacher Lab

A lab deployment with an admin domain and 3 student domains. Each
student gets an isolated network with a web server and a client.

## Use case

A teacher deploying a networking or sysadmin lab for a class. Each
student works in isolation. The teacher can snapshot, restore, and
reset environments between sessions.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Teacher administration |
| student-01 | 1 | Student 1 isolated lab |
| student-02 | 2 | Student 2 isolated lab |
| student-03 | 3 | Student 3 isolated lab |

## Machines

| Machine | Domain | IP | Role |
|---------|--------|-----|------|
| lab-admin | anklume | 10.100.0.10 | Ansible controller |
| s01-web | student-01 | 10.100.1.10 | Student 1 web server |
| s01-client | student-01 | 10.100.1.11 | Student 1 client |
| s02-web | student-02 | 10.100.2.10 | Student 2 web server |
| s02-client | student-02 | 10.100.2.11 | Student 2 client |
| s03-web | student-03 | 10.100.3.10 | Student 3 web server |
| s03-client | student-03 | 10.100.3.11 | Student 3 client |

## Scaling

To add more students, copy a student domain block and change:
- Domain name: `student-04`
- subnet_id: `4`
- Machine name prefix: `s04-`
- IP addresses: `10.100.4.X`

## Hardware requirements

- 4 CPU cores
- 8 GB RAM
- 20 GB disk

Scales linearly: add ~2 GB RAM and ~5 GB disk per student.

## Getting started

```bash
cp examples/teacher-lab/infra.yml infra.yml
make sync
make apply
```

## Lab workflow

```bash
# Before lab: snapshot clean state
make snapshot NAME=pre-lab

# After lab: reset all students
make restore NAME=pre-lab

# Reset a single student
make restore-domain D=student-01 NAME=pre-lab

# Apply only one student domain
make apply-limit G=student-02
```

See [docs/lab-tp.md](../../docs/lab-tp.md) for the full lab deployment
guide.
