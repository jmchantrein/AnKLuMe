# Step 01: Check GPU Availability

## Goal

Verify that your host has a working NVIDIA GPU with drivers installed.
GPU passthrough requires the host to have a functioning GPU driver
before containers can access the hardware.

## Instructions

1. Check that the NVIDIA driver is loaded:

   ```bash
   nvidia-smi
   ```

   You should see a table showing your GPU model, driver version,
   CUDA version, and current memory usage.

2. Note the GPU model and total VRAM. This information is useful
   for choosing which AI models to run (larger models need more VRAM).

3. Verify the Incus daemon can see the GPU:

   ```bash
   incus info --resources | grep -A 5 "GPU"
   ```

   Incus must detect the GPU to pass it through to containers.

## What to look for

- `nvidia-smi` outputs a valid GPU table (not an error)
- The driver version is recent enough for your GPU model
- Incus reports the GPU in its resource list

## Troubleshooting

If `nvidia-smi` fails:
- Ensure NVIDIA drivers are installed (`apt install nvidia-driver` on
  Debian, or your distribution's equivalent)
- Check that the `nvidia` kernel module is loaded: `lsmod | grep nvidia`
- Reboot if you recently installed drivers

## Validation

This step passes when `nvidia-smi` exits successfully on the host.
