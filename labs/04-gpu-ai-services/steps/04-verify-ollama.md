# Step 04: Verify Ollama and GPU Acceleration

## Goal

Confirm that the GPU is visible inside the container and that
Ollama can use it for accelerated inference.

## Instructions

1. Verify the GPU is accessible inside the container:

   ```bash
   incus exec gpu-server --project ai-tools -- nvidia-smi
   ```

   You should see the same GPU table as on the host. This confirms
   GPU passthrough is working correctly.

2. Install Ollama inside the container (if not already installed
   by a provisioning role):

   ```bash
   incus exec gpu-server --project ai-tools -- bash -c \
     'curl -fsSL https://ollama.com/install.sh | sh'
   ```

3. Start the Ollama service:

   ```bash
   incus exec gpu-server --project ai-tools -- systemctl start ollama
   ```

4. Verify Ollama is running and listening:

   ```bash
   incus exec gpu-server --project ai-tools -- \
     curl -s http://localhost:11434/api/tags
   ```

   This should return a JSON response (possibly with an empty
   `models` list if no models are pulled yet).

5. Check that Ollama detects the GPU:

   ```bash
   incus exec gpu-server --project ai-tools -- ollama list
   ```

   If Ollama started correctly with GPU support, it will use CUDA
   for inference. You can also check the Ollama logs:

   ```bash
   incus exec gpu-server --project ai-tools -- \
     journalctl -u ollama --no-pager -n 20
   ```

   Look for lines mentioning "CUDA" or your GPU model name.

## What to look for

- `nvidia-smi` works inside the container (GPU passthrough confirmed)
- Ollama service is active and listening on port 11434
- Ollama logs confirm CUDA/GPU detection

## Validation

This step passes when `nvidia-smi` runs successfully inside the
`gpu-server` container.
