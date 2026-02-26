# GPU Passthrough and LLM Guide

This guide explains how to configure GPU passthrough in anklume for
running local LLM inference with Ollama and Open WebUI.

## Prerequisites

### Host requirements

- NVIDIA GPU (consumer or data center)
- NVIDIA driver installed on the host (>= 535 recommended)
- `nvidia-smi` working on the host
- Incus >= 6.0 LTS

### Verify GPU on the host

```bash
nvidia-smi
```

You should see your GPU model, driver version, and CUDA version. If
this command fails, install the NVIDIA driver for your distribution
before proceeding.

### Incus GPU support

Incus can pass the host GPU into LXC containers using a `gpu` device
type. This shares the host's GPU driver with the container -- no driver
installation is needed inside the container.

## GPU profile in infra.yml

See [examples/pro-workstation/](../examples/pro-workstation/) for a
complete working example. Key configuration points:

1. Define a `nvidia-compute` profile at the domain level with a `gpu`
   device (`type: gpu`, `gputype: physical`)
2. Reference the profile in the machine's `profiles:` list (keep
   `default` as the first entry)
3. Set `gpu: true` on the machine to signal GPU usage
4. Open WebUI runs in a separate container without GPU access

## GPU policy (ADR-018)

By default, anklume enforces an **exclusive** GPU policy: only one
instance across all domains can have GPU access. This prevents
conflicts from multiple containers sharing the same GPU without
isolation.

If you need to share the GPU between multiple containers (for example,
Ollama and a future STT service), set the policy to `shared` in the
global section:

```yaml
global:
  addressing:
    base_octet: 10
    zone_base: 100
  gpu_policy: shared
```

With `shared` mode, the generator emits a warning but allows multiple
GPU instances. Be aware that consumer NVIDIA GPUs do not have hardware
VRAM isolation (no SR-IOV), so concurrent GPU workloads compete for
memory.

## Ollama configuration

The `ollama_server` role installs Ollama and starts it as a systemd
service. Default variables (overridable in `host_vars/`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ollama_host` | `0.0.0.0:11434` | Listen address |
| `ollama_default_model` | `""` (none) | Model to auto-pull |
| `ollama_service_enabled` | `true` | Enable systemd service |

To auto-pull a model during provisioning, set `ollama_default_model`
in the host_vars for your LLM container (outside the managed section):

```yaml
# host_vars/gpu-server.yml (below the managed section)
ollama_default_model: "llama3.2:3b"
```

## Open WebUI configuration

The `open_webui` role installs Open WebUI via pip and configures it as
a systemd service. Default variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `open_webui_port` | `3000` | Listen port |
| `open_webui_ollama_url` | `http://localhost:11434` | Ollama API URL |

Since Open WebUI and Ollama run in separate containers, configure the
Ollama URL to point to the LLM container's IP:

```yaml
# host_vars/webui.yml (below the managed section)
open_webui_ollama_url: "http://10.120.0.1:11434"
```

## Deployment

```bash
# Generate Ansible files
anklume sync

# Apply everything (or just the LLM roles)
anklume domain apply

# Or apply only LLM-related roles
anklume domain apply --tags llm
```

## Verification

### Check GPU inside the container

```bash
incus exec gpu-server --project ai-tools -- nvidia-smi
```

You should see the same GPU as on the host.

### Check Ollama

```bash
incus exec gpu-server --project ai-tools -- curl -s http://localhost:11434/api/tags
```

This should return a JSON response with available models.

### Check Open WebUI

```bash
incus exec webui --project ai-tools -- curl -s http://localhost:3000
```

Open WebUI should respond with HTML. Access it from a browser at
`http://<host-ip>:3000` (after configuring port forwarding or a proxy).

### Test inference

```bash
incus exec gpu-server --project ai-tools -- ollama run llama3.2:3b "Hello, world!"
```

## Storage volumes for models

LLM models can be large (3-70 GB). Use a `storage_volumes` entry to
mount a dedicated volume at `/root/.ollama`. See the
[pro-workstation](../examples/pro-workstation/) example.

## Troubleshooting

- **nvidia-smi not found**: Verify the GPU profile is applied and the
  host has NVIDIA drivers. Check with
  `incus profile show nvidia-compute --project ai-tools`
- **Ollama falls back to CPU**: Verify `nvidia-smi` works, then check
  Ollama logs with `journalctl -u ollama` inside the container
- **Open WebUI cannot connect to Ollama**: Test connectivity with
  `curl -s http://<llm-ip>:11434/api/tags` from the webui container.
  Ensure Ollama listens on `0.0.0.0` (not `127.0.0.1`)
- **Out of VRAM**: Use a smaller model (e.g. `llama3.2:3b` needs ~2 GB
  VRAM) or a quantized variant

## Next steps

- [Full specification](SPEC.md) for the complete infra.yml format
- [Architecture decisions](ARCHITECTURE.md) for GPU policy details
  (ADR-018)
- [Example configurations](../examples/) including
  [llm-supervisor](../examples/llm-supervisor/) for multi-LLM setups
