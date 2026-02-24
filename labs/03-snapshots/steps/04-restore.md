# Step 04: Restore from Snapshot

## Goal

Recover the container to its pre-break state.

## Instructions

1. Restore the `baseline` snapshot:

   ```bash
   make restore NAME=baseline
   ```

   Or directly:

   ```bash
   incus snapshot restore snap-server baseline --project lab-snap
   ```

   Note: restoring a snapshot may stop and restart the container.

2. Wait a moment for the container to restart, then verify recovery:

   ```bash
   incus exec snap-server --project lab-snap -- cat /root/marker.txt
   ```

   Should output: `Lab 03 baseline` — the file is back.

3. Verify the deleted directory is restored:

   ```bash
   incus exec snap-server --project lab-snap -- \
     ls /etc/apt/sources.list.d/
   ```

## Key concept

Snapshot restore is atomic and near-instant. The entire filesystem
reverts to the snapshot state. This is the foundation of safe
experimentation: snapshot before changes, restore if things go wrong.

anklume's `make apply` can automatically create pre-apply snapshots
(Phase 24) so you always have a rollback point.
