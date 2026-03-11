# Intelligence artificielle

anklume intègre une stack IA complète : GPU passthrough, LLM local
(Ollama), STT (Speaches), interfaces de chat, sanitisation et routage.

## Architecture IA

```mermaid
graph TB
    subgraph "Domaine ai-tools (trusted)"
        GPU["gpu-server<br/>Ollama + Speaches<br/>🎮 GPU"]
        WEB["ai-webui<br/>Open WebUI"]
        CHAT["ai-chat<br/>LobeChat"]
        SAN["sanitizer<br/>Proxy LLM"]
        OC["ai-assistant<br/>OpenClaw"]
    end

    subgraph "Domaine pro (semi-trusted)"
        DEV[pro-dev]
    end

    DEV -->|"port 11434<br/>(policy)"| GPU
    DEV -->|"port 3000<br/>(policy)"| WEB
    GPU --> WEB
    GPU --> CHAT
    SAN -.->|"sanitise"| GPU
    OC --> GPU

    style GPU fill:#22c55e,color:#fff
    style SAN fill:#ef4444,color:#fff
    style DEV fill:#eab308,color:#000
```

## Services IA disponibles

| Service | Rôle Ansible | Port | Description |
|---|---|---|---|
| Ollama | `ollama_server` | 11434 | Serveur LLM local |
| Speaches | `stt_server` | 8000 | STT (Whisper) |
| Open WebUI | `open_webui` | 3000 | Interface web Ollama |
| LobeChat | `lobechat` | 3210 | Chat multi-providers |
| Sanitizer | `llm_sanitizer` | 8089 | Proxy d'anonymisation |
| OpenClaw | `openclaw_server` | — | Assistant autonome |
| Code Sandbox | `code_sandbox` | — | Sandbox de coding IA |

## Gestion GPU

```bash
# État des services IA
anklume ai status

# Libérer la VRAM
anklume ai flush

# Basculer l'accès GPU
anklume ai switch ai-tools
```

## Pages détaillées

- [GPU passthrough](gpu.md) — détection, profils, politique d'accès
- [Routage LLM](routage-llm.md) — choix local/externe + sanitisation
- [Push-to-talk STT](stt.md) — dictée vocale sur KDE Wayland
