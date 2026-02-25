# Step 03: Deploy the Infrastructure

## Goal

Apply the infrastructure to create the ai-tools domain with its
GPU-enabled container.

## Instructions

1. Deploy the infrastructure:

   ```bash
   make apply
   ```

   Watch the output carefully. The playbook will:
   - Create the `ai-tools` Incus project
   - Create the `net-ai-tools` network bridge
   - Create the `gpu-passthrough` profile with GPU device
   - Launch the `gpu-server` container with the GPU profile attached

2. Verify the container is running:

   ```bash
   incus list --project ai-tools
   ```

   `gpu-server` should show status `RUNNING` with an IP address
   in the `10.110.x.x` range (trusted zone).

3. Verify the GPU profile was applied:

   ```bash
   incus config show gpu-server --project ai-tools
   ```

   Look for `gpu-passthrough` in the profiles list.

4. Check the Incus project isolation:

   ```bash
   incus project list
   ```

   The `ai-tools` project should appear alongside the `default`
   project.

## What to look for

- Container reaches `RUNNING` state
- IP address is in the trusted zone (`10.110.x.x`)
- The `gpu-passthrough` profile is listed in the container config
- The `ai-tools` Incus project exists and provides namespace isolation

## Validation

This step passes when the `gpu-server` container is running in the
`ai-tools` project.
