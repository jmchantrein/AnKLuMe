# Professional Workstation

A 4-domain compartmentalized workstation with GPU passthrough for LLM
inference and speech-to-text. Follows the QubesOS philosophy: admin,
personal, professional, and homelab environments are fully isolated.

## Use case

A sysadmin or power user who wants strict compartmentalization between
personal use, professional work, and homelab experiments. The homelab
domain includes a single GPU container running both Ollama (LLM) and
Speaches (STT) services, avoiding the need for shared GPU policy.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller |
| perso | 1 | Personal environment |
| pro | 2 | Professional development |
| homelab | 3 | GPU-enabled AI homelab (LLM + STT) |

## Machines

| Machine | Domain | IP | Role |
|---------|--------|-----|------|
| pw-admin | anklume | 10.100.0.10 | Ansible controller with nesting |
| pw-perso | perso | 10.100.1.10 | Personal workspace |
| pw-dev | pro | 10.100.2.10 | Dev workspace (4 CPU, 8 GB RAM) |
| pw-ai | homelab | 10.100.3.10 | Ollama + Speaches STT with GPU |
| pw-webui | homelab | 10.100.3.11 | Open WebUI frontend |

## Architecture

The `pw-ai` container runs both Ollama and Speaches as separate systemd
services sharing the same GPU. This avoids needing `gpu_policy: shared`
(which requires two containers to share the GPU) and keeps the default
`gpu_policy: exclusive`. VRAM is shared within the same container
between the two processes.

## Hardware requirements

- 8 CPU cores
- 16 GB RAM
- 50 GB disk
- NVIDIA GPU (for homelab AI -- 8+ GB VRAM recommended for LLM + STT)

## Getting started

```bash
cp examples/pro-workstation/infra.yml infra.yml
make sync
make apply
```

After deployment, configure Open WebUI to connect to the AI server
by adding to `host_vars/pw-webui.yml`:

```yaml
open_webui_ollama_url: "http://10.100.3.10:11434"
open_webui_stt_url: "http://10.100.3.10:8000/v1"
```

The `open_webui_stt_url` variable enables speech-to-text in Open WebUI,
pointing to the Speaches API on the same AI container.

See [docs/gpu-llm.md](../../docs/gpu-llm.md) for the full GPU and LLM
setup guide and [docs/stt-service.md](../../docs/stt-service.md) for
STT configuration.
