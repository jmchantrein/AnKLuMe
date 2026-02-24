# Step 03: Break the Container

## Goal

Intentionally corrupt the container state to simulate a failure.

## Instructions

1. Verify the marker file exists:

   ```bash
   incus exec snap-server --project lab-snap -- cat /root/marker.txt
   ```

   Should output: `Lab 03 baseline`

2. Now break things. Delete important files:

   ```bash
   incus exec snap-server --project lab-snap -- \
     rm -f /root/marker.txt

   incus exec snap-server --project lab-snap -- \
     rm -rf /etc/apt/sources.list.d/
   ```

3. Verify the damage:

   ```bash
   incus exec snap-server --project lab-snap -- \
     cat /root/marker.txt 2>&1 || echo "File is gone!"

   incus exec snap-server --project lab-snap -- \
     ls /etc/apt/sources.list.d/ 2>&1 || echo "Directory is gone!"
   ```

## Key concept

In a real scenario, this could be a failed upgrade, a
misconfiguration, or a security breach. Without snapshots, you
would need to rebuild from scratch. With snapshots, recovery
takes seconds.
