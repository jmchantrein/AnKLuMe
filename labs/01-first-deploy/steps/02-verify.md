# Step 02: Deploy and Verify

## Goal

Apply the infrastructure and confirm both containers are running.

## Instructions

1. Deploy the infrastructure:

   ```bash
   anklume domain apply
   ```

   This creates the Incus project, network bridge, and both
   containers. Watch the output for each role executing.

2. Verify the containers are running:

   ```bash
   incus list --project lab-net
   ```

   Both `lab-web` and `lab-db` should show status `RUNNING`.

3. Test intra-domain connectivity. From `lab-web`, ping `lab-db`:

   ```bash
   incus exec lab-web --project lab-net -- ping -c 3 <lab-db-ip>
   ```

   Replace `<lab-db-ip>` with the IP shown in `incus list` output.
   Ping should succeed because both containers are on the same bridge.

4. Verify DNS or hostname resolution is not required for this lab.
   Containers communicate via IP within the `10.120.0.x/24` subnet.

## What to look for

- Both containers reach `RUNNING` state
- Ping between containers succeeds (same bridge, same subnet)
- The Incus project `lab-net` isolates these containers

## Validation

The step passes when at least one container in the `lab-net` project
reports `RUNNING` status.
