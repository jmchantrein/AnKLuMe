# Professional Workstation

A 4-domain compartmentalized workstation with GPU passthrough for LLM
inference. Follows the QubesOS philosophy: admin, personal,
professional, and homelab environments are fully isolated.

## Use case

A sysadmin or power user who wants strict compartmentalization between
personal use, professional work, and homelab experiments. The homelab
domain includes GPU access for running local LLMs with Ollama.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| admin | 0 | Ansible controller |
| perso | 1 | Personal environment |
| pro | 2 | Professional development |
| homelab | 3 | GPU-enabled LLM homelab |

## Machines

| Machine | Domain | IP | Role |
|---------|--------|-----|------|
| pw-admin | admin | 10.100.0.10 | Ansible controller with nesting |
| pw-perso | perso | 10.100.1.10 | Personal workspace |
| pw-dev | pro | 10.100.2.10 | Dev workspace (4 CPU, 8 GB RAM) |
| pw-llm | homelab | 10.100.3.10 | Ollama with GPU |
| pw-webui | homelab | 10.100.3.11 | Open WebUI frontend |

## Hardware requirements

- 8 CPU cores
- 16 GB RAM
- 50 GB disk
- NVIDIA GPU (for homelab LLM)

## Getting started

```bash
cp examples/pro-workstation/infra.yml infra.yml
make sync
make apply
```

After deployment, configure Open WebUI to connect to the Ollama server
by adding to `host_vars/pw-webui.yml`:

```yaml
open_webui_ollama_url: "http://10.100.3.10:11434"
```

See [docs/gpu-llm.md](../../docs/gpu-llm.md) for the full GPU and LLM
setup guide.
