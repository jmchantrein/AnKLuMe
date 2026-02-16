# LLM Supervisor

Two isolated LLM domains with a supervisor domain for monitoring and
management. Demonstrates multi-LLM orchestration with shared GPU.

## Use case

You want to run multiple LLM instances (different models or different
configurations) in separate isolated networks, with a supervisor
container that can communicate with both via their APIs. Useful for:

- Testing LLM monitoring and management
- Comparing model outputs
- Running an orchestrator that queries multiple LLMs
- LLM-supervising-LLM experiments

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller |
| llm-alpha | 1 | First LLM (primary model) |
| llm-beta | 2 | Second LLM (secondary model) |
| supervisor | 3 | Supervisor + Open WebUI |

## Machines

| Machine | Domain | IP | GPU | Role |
|---------|--------|-----|-----|------|
| llms-admin | anklume | 10.100.0.10 | No | Ansible controller |
| llm-alpha-server | llm-alpha | 10.100.1.10 | Yes | Ollama (primary) |
| llm-beta-server | llm-beta | 10.100.2.10 | Yes | Ollama (secondary) |
| llm-supervisor | supervisor | 10.100.3.10 | No | Supervisor scripts |
| llm-webui | supervisor | 10.100.3.11 | No | Open WebUI |

## GPU policy

This example uses `gpu_policy: shared` in the global section because
two containers share the same GPU. This requires a GPU with sufficient
VRAM for both models concurrently.

## Hardware requirements

- 8 CPU cores
- 16 GB RAM
- 50 GB disk
- NVIDIA GPU with >= 16 GB VRAM (for 2 concurrent models)

## Getting started

```bash
cp examples/llm-supervisor/infra.yml infra.yml
make sync
make apply
```

Configure each Ollama instance with a different model by adding to
their respective host_vars files:

```yaml
# host_vars/llm-alpha-server.yml
ollama_default_model: "llama3.1:8b"

# host_vars/llm-beta-server.yml
ollama_default_model: "qwen2.5-coder:7b"
```

Configure Open WebUI to connect to one of the LLM servers:

```yaml
# host_vars/llm-webui.yml
open_webui_ollama_url: "http://10.100.1.10:11434"
```

## Network considerations

Each LLM domain has its own network. The supervisor domain is on a
separate network. For the supervisor to communicate with both LLMs,
cross-domain routing must be configured (or use the admin domain as
a proxy). See Phase 8 in [ROADMAP.md](../../docs/ROADMAP.md).
