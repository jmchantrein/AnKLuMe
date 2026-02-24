---
name: incus-ansible
description: |
  Patterns and reference for writing Ansible roles that drive Incus via CLI.
  Auto-load when working on files in roles/.
---

# Skill: Ansible Roles for Incus

## Reconciliation pattern (follow for ALL infra roles)

```yaml
---
# 1. READ current state
- name: "RoleName | Retrieve current state"
  ansible.builtin.command:
    cmd: incus <resource> list --format json
  register: <role>_raw
  changed_when: false

# 2. PARSE
- name: "RoleName | Parse existing resources"
  ansible.builtin.set_fact:
    <role>_existing: >-
      {{ <role>_raw.stdout | from_json | map(attribute='name') | list }}

# 3. BUILD desired state (from group_vars)
- name: "RoleName | Build desired state"
  ansible.builtin.set_fact:
    <role>_desired: "{{ <variable_from_group_vars> }}"

# 4. CREATE what is missing
- name: "RoleName | Create missing resources"
  ansible.builtin.command:
    cmd: "incus <resource> create {{ item.name }} ..."
  loop: "{{ <role>_desired }}"
  when: item.name not in <role>_existing
  changed_when: true

# 5. UPDATE what exists
- name: "RoleName | Update existing resources"
  ansible.builtin.command:
    cmd: "incus <resource> set {{ item.name }} ..."
  loop: "{{ <role>_desired }}"
  when: item.name in <role>_existing
  changed_when: false  # `set` is idempotent

# 6. ORPHANS
- name: "RoleName | Detect orphans"
  ansible.builtin.set_fact:
    <role>_orphans: >-
      {{ <role>_existing | difference(<role>_desired | map(attribute='name') | list) }}

- name: "RoleName | Report orphans"
  ansible.builtin.debug:
    msg: "ORPHAN — {{ item }} exists in Incus but not in config"
  loop: "{{ <role>_orphans }}"
  when: <role>_orphans | length > 0

- name: "RoleName | Remove orphans if auto_cleanup"
  ansible.builtin.command:
    cmd: "incus <resource> delete {{ item }}"
  loop: "{{ <role>_orphans }}"
  when:
    - <role>_orphans | length > 0
    - auto_cleanup | default(false) | bool
  changed_when: true
```

## Common Incus commands

```bash
# Networks
incus network list --format json
incus network create <n> ipv4.address=<cidr> ipv4.nat=true ipv6.address=none
incus network set <n> <key>=<value>
incus network delete <n>

# Projects
incus project list --format json
incus project create <n> -c features.networks=false -c features.images=true
incus project show <n>
incus project delete <n>

# Profiles (scoped to project)
incus profile list --project <project> --format json
incus profile create <n> --project <project>
incus profile device add <n> <device> <type> --project <project>
incus profile set <n> <key>=<value> --project <project>

# Instances
incus launch <image> <n> --project <project> [--vm]
incus list --project <project> --format json
incus config set <n> <key>=<value> --project <project>
incus delete <n> --force --project <project>

# Snapshots
incus snapshot create <instance> <snap-name> --project <project>
incus snapshot restore <instance> <snap-name> --project <project>
incus snapshot delete <instance> <snap-name> --project <project>
incus snapshot list <instance> --project <project> --format json

# Exec (for provisioning)
incus exec <instance> --project <project> -- <command>
```

## Incus socket path

The socket is at `/var/run/incus/unix.socket` (NOT `/var/lib/incus/...`).
In the admin container, mounted via a proxy device (ADR-019):
```bash
incus config device add <admin> incus-socket proxy \
  connect=unix:/var/lib/incus/unix.socket \
  listen=unix:/var/run/incus/unix.socket \
  bind=container
```

## Shared volume devices (ADR-039)

The generator injects `sv-<name>` disk devices into `instance_devices`
for shared_volumes consumers. These are standard Incus disk devices:
```yaml
instance_devices:
  sv-docs:
    type: disk
    source: /srv/anklume/shares/docs
    path: /shared/docs
    shift: "true"
    readonly: "true"  # only for ro consumers
```

The `incus_instances` role handles these like any other declared device.

## Connection plugin: community.general.incus

For provisioning (phase 2), set in inventory:
```yaml
ansible_connection: community.general.incus
incus_project: <project_name>
```

Executes commands inside containers via the Incus API. No SSH needed.
