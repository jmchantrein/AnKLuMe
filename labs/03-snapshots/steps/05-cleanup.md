# Step 05: Clean Up Snapshots

## Goal

Remove snapshots and lab resources.

## Instructions

1. Delete the `baseline` snapshot:

   ```bash
   make snapshot-delete NAME=baseline
   ```

   Or directly:

   ```bash
   incus snapshot delete snap-server baseline --project lab-snap
   ```

2. Verify the snapshot is gone:

   ```bash
   incus info snap-server --project lab-snap
   ```

3. Remove the lab infrastructure:

   ```bash
   make flush FORCE=true
   cp infra.yml.bak infra.yml 2>/dev/null || true
   make sync
   ```

## What you learned

- How to create named snapshots (`make snapshot NAME=...`)
- How to list snapshots (`make snapshot-list`)
- How to restore from a snapshot (`make restore NAME=...`)
- How to delete snapshots (`make snapshot-delete NAME=...`)
- Snapshots enable fearless experimentation

## Next lab

Explore more advanced topics in the remaining labs:
- Network policies (selective cross-domain access)
- GPU passthrough and AI services
- Security audit and hardening
