# Step 05: Clean Up Snapshots

## Goal

Remove snapshots and lab resources.

## Instructions

1. Delete the `baseline` snapshot:

   ```bash
   anklume snapshot create-delete NAME=baseline
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
   anklume flush --force
   cp infra.yml.bak infra.yml 2>/dev/null || true
   anklume sync
   ```

## What you learned

- How to create named snapshots (`anklume snapshot create NAME=...`)
- How to list snapshots (`anklume snapshot list`)
- How to restore from a snapshot (`anklume snapshot restore --name ...`)
- How to delete snapshots (`anklume snapshot create-delete NAME=...`)
- Snapshots enable fearless experimentation

## Next lab

Explore more advanced topics in the remaining labs:
- Network policies (selective cross-domain access)
- GPU passthrough and AI services
- Security audit and hardening
