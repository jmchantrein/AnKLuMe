# AI Tools Domain

A complete local AI stack in an isolated domain.

## Architecture

```
ai-tools domain (net-ai-tools, 10.100.4.0/24)

  gpu-server (.10)     ai-openwebui (.20)   ai-lobechat (.30)   ai-opencode (.40)
  GPU (exclusive)
  Ollama :11434        Open WebUI :3000     LobeChat :3210      OpenCode :4096
  Speaches :8000       -> gpu-server:11434   -> gpu-server:11434  -> gpu-server:11434/v1
```

## Services

| Machine | Service | Port | Description |
|---------|---------|------|-------------|
| gpu-server | Ollama | 11434 | LLM inference (GPU-accelerated) |
| gpu-server | Speaches | 8000 | Speech-to-text (OpenAI-compatible) |
| ai-openwebui | Open WebUI | 3000 | Chat interface with voice support |
| ai-lobechat | LobeChat | 3210 | Multi-provider chat UI |
| ai-opencode | OpenCode | 4096 | AI coding assistant (headless server) |

## Requirements

- **GPU**: NVIDIA GPU recommended (8+ GB VRAM for LLM + STT)
- **RAM**: 16 GB minimum (32 GB recommended)
- **Disk**: 50 GB for models (100 GB recommended)
- **CPU**: 4+ cores

## Quick start

```bash
cp examples/ai-tools/infra.yml infra.yml
anklume sync
anklume domain apply
```

## Configuration

Override Ollama URL in host_vars for each UI container:

```yaml
# host_vars/ai-openwebui.yml (outside managed section)
open_webui_ollama_url: "http://10.100.4.10:11434"
open_webui_stt_url: "http://10.100.4.10:8000/v1"

# host_vars/ai-lobechat.yml (outside managed section)
lobechat_ollama_url: "http://10.100.4.10:11434"

# host_vars/ai-opencode.yml (outside managed section)
opencode_server_ollama_url: "http://10.100.4.10:11434/v1"
```

## Cross-domain access

The example includes network policies allowing the `pro` domain
to access all AI chat UIs. Adjust in `infra.yml` as needed.
