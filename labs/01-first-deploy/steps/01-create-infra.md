# Step 01: Create the Infrastructure

## Goal

Generate the Ansible file tree from the lab's `infra.yml`.

## Instructions

1. Examine the lab infrastructure file:

   ```bash
   cat labs/01-first-deploy/infra.yml
   ```

   Notice the structure: one domain (`lab-net`) with two machines
   (`lab-web` and `lab-db`), both LXC containers on the same
   semi-trusted subnet.

2. Copy the lab's infra.yml to your project root (back up any
   existing file first):

   ```bash
   cp infra.yml infra.yml.bak 2>/dev/null || true
   cp labs/01-first-deploy/infra.yml infra.yml
   ```

3. Generate the Ansible files:

   ```bash
   anklume sync
   ```

4. Inspect the generated files:

   ```bash
   ls inventory/ group_vars/ host_vars/
   cat group_vars/lab-net.yml
   cat host_vars/lab-web.yml
   ```

## What to look for

- `inventory/lab-net.yml` lists both hosts under the `lab-net` group
- `group_vars/lab-net.yml` contains the network bridge configuration
- `host_vars/lab-web.yml` and `host_vars/lab-db.yml` contain instance
  metadata (type, IP, roles)
- IP addresses are auto-assigned within the `10.120.0.x/24` subnet
  (semi-trusted zone)

## Validation

The step passes when inventory and group_vars files exist for the
`lab-net` domain.
