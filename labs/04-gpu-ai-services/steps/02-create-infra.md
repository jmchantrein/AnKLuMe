# Step 02: Create the Infrastructure

## Goal

Set up an `infra.yml` with an ai-tools domain that includes a GPU
profile and an Ollama server container.

## Instructions

1. Examine the lab infrastructure file:

   ```bash
   cat labs/04-gpu-ai-services/infra.yml
   ```

   Notice the key elements:
   - **Domain**: `ai-tools` with trust level `trusted`
   - **Profile**: `gpu-passthrough` with a `gpu` device (type: gpu)
   - **Machine**: `gpu-server` with `gpu: true` and the GPU profile
   - **Roles**: `base_system` provides the foundation

2. Key concepts to understand:

   - `type: gpu` is an Incus device type that passes all GPUs to the
     container. The `gid: "44"` maps to the `video` group inside the
     container.
   - `gpu: true` on the machine tells anklume this machine uses GPU
     resources. The default policy (`gpu_policy: exclusive`) means
     only one machine can have GPU access at a time.
   - The `gpu-passthrough` profile is declared at the domain level
     and referenced by the machine.

3. Copy the lab's infra.yml to your project root:

   ```bash
   cp infra.yml infra.yml.bak 2>/dev/null || true
   cp labs/04-gpu-ai-services/infra.yml infra.yml
   ```

4. Generate the Ansible files:

   ```bash
   anklume sync
   ```

5. Inspect the generated files:

   ```bash
   cat group_vars/ai-tools.yml
   cat host_vars/gpu-server.yml
   ```

   Look for the `incus_profiles` section in group_vars and the
   `instance_profiles` list in host_vars.

## What to look for

- `group_vars/ai-tools.yml` contains the GPU profile definition
- `host_vars/gpu-server.yml` references the `gpu-passthrough` profile
- The trust level `trusted` places this domain in the `10.110.x.x`
  address range (zone offset 10)

## Validation

This step passes when inventory and group_vars files exist for the
`ai-tools` domain.
