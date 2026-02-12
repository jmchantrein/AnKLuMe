# Speech-to-Text (STT) Service

AnKLuMe provides a local, GPU-accelerated speech-to-text service using
faster-whisper and the Speaches API server. This integrates with Open
WebUI for voice input and with any client supporting the OpenAI STT API.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ homelab domain (net-homelab, 10.100.3.0/24)         │
│                                                      │
│  ┌──────────────┐    ┌──────────────────────┐       │
│  │ homelab-stt   │    │ homelab-llm          │       │
│  │ GPU (shared)  │    │ GPU (shared)         │       │
│  │               │    │                      │       │
│  │ faster-whisper│    │ Ollama               │       │
│  │ + Speaches    │    │ :11434               │       │
│  │ :8000         │    │                      │       │
│  └──────┬───────┘    └──────────────────────┘       │
│         │                      ▲                     │
│         │    /v1/audio/        │  /api/generate      │
│         │    transcriptions    │                     │
│         ▼                      │                     │
│  ┌──────────────────────────────┐                   │
│  │ homelab-webui                │                   │
│  │ Open WebUI :3000             │                   │
│  │ STT → homelab-stt:8000      │                   │
│  │ LLM → homelab-llm:11434     │                   │
│  └──────────────────────────────┘                   │
└─────────────────────────────────────────────────────┘
```

## Quick start

### 1. Declare the STT instance in infra.yml

```yaml
global:
  base_subnet: "10.100"
  gpu_policy: shared  # Required if STT and Ollama share the GPU

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
      homelab-llm:
        type: lxc
        ip: "10.100.3.10"
        gpu: true
        profiles: [default, nvidia-compute]
        roles: [base_system, ollama_server]
      homelab-stt:
        description: "Speech-to-text server"
        type: lxc
        ip: "10.100.3.20"
        gpu: true
        profiles: [default, nvidia-compute]
        roles: [base_system, stt_server]
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

In Open WebUI admin settings, set the STT endpoint:

```
STT Engine: OpenAI
STT API URL: http://homelab-stt:8000/v1/audio/transcriptions
```

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
# In host_vars/homelab-stt.yml (outside managed section)
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

## Shared GPU with Ollama

When both Ollama and the STT server use the same GPU:

1. Set `gpu_policy: shared` in infra.yml global section
2. Both containers get the `nvidia-compute` profile
3. VRAM is shared — concurrent inference competes for memory

**Recommendations**:
- Use `int8_float16` quantization for STT to reduce VRAM
- Avoid running large LLM inference and transcription simultaneously
- Monitor VRAM usage: `nvidia-smi` on the host

## Verification

```bash
# Check service status
incus exec homelab-stt --project homelab -- systemctl status speaches

# Test the API endpoint
incus exec homelab-stt --project homelab -- \
  curl -s http://localhost:8000/health

# Test transcription (from any container with network access)
curl -X POST http://homelab-stt:8000/v1/audio/transcriptions \
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
# Edit host_vars/homelab-stt.yml:
stt_server_model: "small"
stt_server_quantization: "int8"

# Re-provision
make apply-stt
```

### Service not starting

```bash
# Check logs
incus exec homelab-stt --project homelab -- journalctl -u speaches -f

# Verify ffmpeg is installed (required dependency)
incus exec homelab-stt --project homelab -- ffmpeg -version
```
