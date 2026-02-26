# Step 01: Create the Lab Environment

## Goal

Set up a single container for snapshot exercises.

## Instructions

1. Examine the lab infrastructure:

   ```bash
   cat labs/03-snapshots/infra.yml
   ```

   One domain (`lab-snap`) with one container (`snap-server`).

2. Copy and generate:

   ```bash
   cp infra.yml infra.yml.bak 2>/dev/null || true
   cp labs/03-snapshots/infra.yml infra.yml
   anklume sync
   ```

3. Deploy the container:

   ```bash
   anklume domain apply
   ```

4. Verify it is running:

   ```bash
   incus list --project lab-snap
   ```

## Validation

The inventory file for `lab-snap` must exist.
