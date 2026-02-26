# Step 02: Deploy the Infrastructure

## Goal

Create all Incus resources and start the containers.

## Instructions

1. Apply the full infrastructure:

   ```bash
   anklume domain apply
   ```

2. List containers in both projects:

   ```bash
   incus list --project lab-office
   incus list --project lab-dmz
   ```

3. Verify the network bridges exist:

   ```bash
   incus network list
   ```

   You should see `net-lab-office` and `net-lab-dmz`.

## What to look for

- Three containers total: two in `lab-office`, one in `lab-dmz`
- All containers in `RUNNING` state
- Two separate network bridges

## Validation

At least one container in `lab-office` is running.
