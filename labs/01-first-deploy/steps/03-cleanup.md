# Step 03: Clean Up

## Goal

Remove lab resources and restore your original infrastructure.

## Instructions

1. Delete the lab containers and project:

   ```bash
   incus delete lab-web --project lab-net --force
   incus delete lab-db --project lab-net --force
   incus network delete net-lab-net
   incus project delete lab-net
   ```

   Alternatively, if you have no other infrastructure to preserve:

   ```bash
   make flush FORCE=true
   ```

2. Restore your original infra.yml:

   ```bash
   cp infra.yml.bak infra.yml 2>/dev/null || true
   ```

3. Regenerate your original Ansible files:

   ```bash
   make sync
   ```

## What you learned

- The `infra.yml -> make sync -> make apply` workflow
- How domains map to Incus projects, bridges, and subnets
- How containers on the same bridge can communicate
- How to inspect generated Ansible files

## Next lab

Try **Lab 02: Network Isolation** to learn how separate domains
are isolated from each other by default.
