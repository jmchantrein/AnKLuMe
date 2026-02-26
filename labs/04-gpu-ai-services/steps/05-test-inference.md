# Step 05: Test Inference

## Goal

Pull a small language model, run inference, and verify that GPU
acceleration is being used.

## Instructions

1. Pull a small model. We use `qwen2.5:0.5b` because it is fast to
   download and runs on any GPU:

   ```bash
   incus exec gpu-server --project ai-tools -- ollama pull qwen2.5:0.5b
   ```

   Wait for the download to complete. The model is approximately
   400MB.

2. Run a test prompt:

   ```bash
   incus exec gpu-server --project ai-tools -- \
     ollama run qwen2.5:0.5b "What is Linux? Answer in one sentence."
   ```

   You should receive a coherent response within a few seconds.

3. Verify GPU usage during inference. While a prompt is running
   (or immediately after), check GPU utilization:

   ```bash
   incus exec gpu-server --project ai-tools -- nvidia-smi
   ```

   Look at the "GPU-Util" column and the "Memory-Usage" column.
   During inference, you should see memory allocated by the Ollama
   process.

4. Test the API endpoint directly:

   ```bash
   incus exec gpu-server --project ai-tools -- \
     curl -s http://localhost:11434/api/generate \
     -d '{"model":"qwen2.5:0.5b","prompt":"Hello","stream":false}' \
     | python3 -m json.tool
   ```

   This sends a prompt via the REST API and returns a JSON response
   with the generated text and performance metrics (tokens per
   second).

5. Clean up the lab when finished:

   ```bash
   incus delete gpu-server --project ai-tools --force
   incus network delete net-ai-tools
   incus project delete ai-tools
   cp infra.yml.bak infra.yml 2>/dev/null || true
   anklume sync
   ```

## What you learned

- How to configure GPU passthrough using Incus profiles
- How anklume's GPU policy (`gpu_policy: exclusive`) controls access
- How to deploy and verify an AI inference service (Ollama) in an
  isolated domain
- How trust levels map to IP address ranges
- How to test GPU-accelerated inference end-to-end

## Next lab

Try **Lab 05: Security Audit** to learn how to audit your
infrastructure's network isolation and security posture.
