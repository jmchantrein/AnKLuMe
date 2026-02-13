# Speech-to-Text (STT) Service

AnKLuMe provides a local, GPU-accelerated speech-to-text service using
faster-whisper and the Speaches API server. This integrates with Open
WebUI for voice input and with any client supporting the OpenAI STT API.

## Architecture

The recommended architecture co-locates Ollama and Speaches in a single
container (`homelab-ai`), sharing the GPU within one process namespace.
This avoids the need for `gpu_policy: shared` and keeps the default
exclusive GPU policy.

```
┌─────────────────────────────────────────────────────┐
│ homelab domain (net-homelab, 10.100.3.0/24)         │
│                                                      │
│  ┌────────────────────────────────────┐             │
│  │ homelab-ai                         │             │
│  │ GPU (exclusive)                    │             │
│  │                                    │             │
│  │  ┌─────────────┐ ┌──────────────┐ │             │
│  │  │ Ollama      │ │ Speaches     │ │             │
│  │  │ :11434      │ │ :8000        │ │             │
│  │  │ (systemd)   │ │ (systemd)    │ │             │
│  │  └─────────────┘ └──────────────┘ │             │
│  │       VRAM shared within container │             │
│  └──────────┬──────────────┬─────────┘             │
│             │              │                        │
│  /api/generate    /v1/audio/transcriptions          │
│             │              │                        │
│             ▼              ▼                        │
│  ┌──────────────────────────────────┐              │
│  │ homelab-webui                    │              │
│  │ Open WebUI :3000                 │              │
│  │ LLM → homelab-ai:11434          │              │
│  │ STT → homelab-ai:8000           │              │
│  └──────────────────────────────────┘              │
└─────────────────────────────────────────────────────┘
```

## Quick start

### 1. Declare the AI instance in infra.yml

```yaml
global:
  base_subnet: "10.100"
  # gpu_policy: exclusive  # Default — one container owns the GPU

domains:
  homelab:
    subnet_id: 3
    profiles:
      nvidia-compute:
        devices:
          gpu:
            type: gpu
            gputype: physical
    machines:
      homelab-ai:
        description: "AI server — Ollama + Speaches STT"
        type: lxc
        ip: "10.100.3.10"
        gpu: true
        profiles: [default, nvidia-compute]
        roles: [base_system, ollama_server, stt_server]
      homelab-webui:
        type: lxc
        ip: "10.100.3.30"
        roles: [base_system, open_webui]
```

### 2. Deploy

```bash
make sync          # Generate Ansible files
make apply         # Full infrastructure + provisioning
# or:
make apply-stt     # STT role only
```

### 3. Configure Open WebUI

Set the STT endpoint in `host_vars/homelab-webui.yml`:

```yaml
open_webui_ollama_url: "http://10.100.3.10:11434"
open_webui_stt_url: "http://10.100.3.10:8000/v1"
```

The `open_webui_stt_url` variable automatically configures Open WebUI
with `AUDIO_STT_ENGINE=openai` and the correct API base URL. Leave it
empty (the default) to disable STT integration.

## Engine and model

**Engine**: faster-whisper (CTranslate2 backend)
- Up to 4x faster than vanilla Whisper on NVIDIA GPUs
- Lower memory usage via quantization
- Same accuracy as OpenAI Whisper

**Default model**: Whisper Large V3 Turbo
- Best accuracy/speed trade-off
- Multilingual (French + English and 90+ languages)
- ~6 GB VRAM with float16 quantization

**API server**: Speaches (formerly faster-whisper-server)
- OpenAI-compatible `/v1/audio/transcriptions` endpoint
- Drop-in replacement for OpenAI Whisper API
- Single process, no orchestration needed

## Configuration

### Role variables

| Variable | Default | Description |
|----------|---------|-------------|
| `stt_server_host` | `0.0.0.0` | Listen address |
| `stt_server_port` | `8000` | Listen port |
| `stt_server_model` | `large-v3-turbo` | Whisper model |
| `stt_server_quantization` | `float16` | Compute type |
| `stt_server_language` | `""` | Language (empty=auto) |
| `stt_server_enabled` | `true` | Enable service |

### Quantization options

| Type | VRAM usage | Speed | Accuracy |
|------|-----------|-------|----------|
| `float16` | ~6 GB | Fast | Best |
| `int8_float16` | ~4 GB | Faster | Good |
| `int8` | ~3 GB | Fastest | Acceptable |

For GPUs with limited VRAM (< 8 GB), use `int8_float16` or a smaller
model (`medium`, `small`).

### Smaller models

If VRAM or latency is a concern:

```yaml
# In host_vars/homelab-ai.yml (outside managed section)
stt_server_model: "medium"
stt_server_quantization: "int8_float16"
```

| Model | Parameters | VRAM (float16) | Accuracy |
|-------|-----------|----------------|----------|
| tiny | 39M | ~1 GB | Low |
| base | 74M | ~1 GB | Fair |
| small | 244M | ~2 GB | Good |
| medium | 769M | ~4 GB | Very good |
| large-v3-turbo | 809M | ~6 GB | Excellent |
| large-v3 | 1.55B | ~10 GB | Best |

## VRAM sharing within a single container

When Ollama and Speaches run in the same container, they share the GPU
as two independent processes. The NVIDIA driver handles VRAM allocation
at the process level:

- Ollama loads LLM weights into VRAM on demand (and can offload)
- Speaches loads the Whisper model into VRAM on first transcription
- Both processes compete for VRAM at the driver level
- No container-level isolation overhead (no `gpu_policy: shared` needed)

**Recommendations**:
- Use `int8_float16` quantization for STT to reduce VRAM pressure
- Avoid running large LLM inference and transcription simultaneously
  on GPUs with less than 16 GB VRAM
- Monitor VRAM usage: `nvidia-smi` inside the container or on the host
- Ollama automatically offloads model layers to CPU when VRAM is full

This is simpler and more efficient than the previous two-container
approach, which required `gpu_policy: shared` and incurred Incus GPU
device overhead for each container.

## Verification

```bash
# Check service status
incus exec homelab-ai --project homelab -- systemctl status speaches

# Test the API endpoint
incus exec homelab-ai --project homelab -- \
  curl -s http://localhost:8000/health

# Verify both services are running
incus exec homelab-ai --project homelab -- systemctl status ollama
incus exec homelab-ai --project homelab -- systemctl status speaches

# Test transcription (from any container with network access)
curl -X POST http://homelab-ai:8000/v1/audio/transcriptions \
  -H "Content-Type: multipart/form-data" \
  -F "file=@audio.wav" \
  -F "model=large-v3-turbo"
```

## Alternative engines

The `stt_server` role uses Speaches (faster-whisper backend) by default.
For other use cases:

| Engine | Strengths | Limitations |
|--------|-----------|-------------|
| **Speaches** (default) | OpenAI-compatible, GPU, multilingual | Python/pip |
| **OWhisper** | Unified CLI, multiple backends | Newer, less mature |
| **NVIDIA Parakeet** | Blazing fast (RTFx 3386) | English-only |
| **Vosk** | Lightweight, CPU-only | Lower accuracy |

To use an alternative, create a custom role or override the systemd
service template.

## Troubleshooting

### Model download slow on first request

The Whisper model is downloaded on the first transcription request.
Large models (1-6 GB) take time to download. The service remains
responsive during download.

### Out of VRAM

If both Ollama and STT run out of VRAM:

```bash
# Check VRAM usage
nvidia-smi

# Switch to smaller model or quantization
# Edit host_vars/homelab-ai.yml:
stt_server_model: "small"
stt_server_quantization: "int8"

# Re-provision
make apply-stt
```

### Service not starting

```bash
# Check logs
incus exec homelab-ai --project homelab -- journalctl -u speaches -f

# Verify ffmpeg is installed (required dependency)
incus exec homelab-ai --project homelab -- ffmpeg -version
```
