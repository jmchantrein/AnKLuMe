# Step 02: Create a Baseline Snapshot

## Goal

Save the current container state as a named snapshot.

## Instructions

1. First, create a known state. Write a marker file inside the
   container:

   ```bash
   incus exec snap-server --project lab-snap -- \
     bash -c 'echo "Lab 03 baseline" > /root/marker.txt'
   ```

2. Create a snapshot named `baseline`:

   ```bash
   make snapshot NAME=baseline
   ```

   Or directly with Incus:

   ```bash
   incus snapshot create snap-server baseline --project lab-snap
   ```

3. Verify the snapshot exists:

   ```bash
   make snapshot-list
   ```

   Or:

   ```bash
   incus info snap-server --project lab-snap
   ```

   Look for the `baseline` snapshot in the output.

## Key concept

Snapshots capture the full container state (filesystem, running
processes if stateful). They are instant and space-efficient
(copy-on-write with ZFS or BTRFS).

## Validation

The container must have a snapshot named `baseline`.
