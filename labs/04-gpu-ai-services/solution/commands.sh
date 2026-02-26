#!/usr/bin/env bash
# Lab 04 — Reference solution commands
# These commands complete each step of the lab.

set -euo pipefail

echo "=== Step 01: Check GPU availability ==="
nvidia-smi
incus info --resources | grep -A 5 "GPU"

echo "=== Step 02: Create the infrastructure ==="
cp infra.yml infra.yml.bak 2>/dev/null || true
cp labs/04-gpu-ai-services/infra.yml infra.yml
anklume sync
cat group_vars/ai-tools.yml
cat host_vars/gpu-server.yml

echo "=== Step 03: Deploy the infrastructure ==="
anklume domain apply
incus list --project ai-tools

echo "=== Step 04: Verify Ollama and GPU acceleration ==="
incus exec gpu-server --project ai-tools -- nvidia-smi
incus exec gpu-server --project ai-tools -- bash -c \
  'curl -fsSL https://ollama.com/install.sh | sh'
incus exec gpu-server --project ai-tools -- systemctl start ollama
incus exec gpu-server --project ai-tools -- \
  curl -s http://localhost:11434/api/tags

echo "=== Step 05: Test inference ==="
incus exec gpu-server --project ai-tools -- ollama pull qwen2.5:0.5b
incus exec gpu-server --project ai-tools -- \
  ollama run qwen2.5:0.5b "What is Linux? Answer in one sentence."
incus exec gpu-server --project ai-tools -- nvidia-smi

echo "=== Cleanup ==="
incus delete gpu-server --project ai-tools --force
incus network delete net-ai-tools
incus project delete ai-tools
cp infra.yml.bak infra.yml 2>/dev/null || true
anklume sync

echo "Lab 04 complete."
