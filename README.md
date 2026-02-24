# AnKLuMe

<!-- Badges -->
[![CI](https://github.com/jmchantrein/anklume/actions/workflows/ci.yml/badge.svg)](https://github.com/jmchantrein/anklume/actions)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/jmchantrein/anklume)](https://github.com/jmchantrein/anklume/commits/main)
[![Issues](https://img.shields.io/github/issues/jmchantrein/anklume)](https://github.com/jmchantrein/anklume/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/jmchantrein/anklume)](https://github.com/jmchantrein/anklume/pulls)

<!-- Static badges — tech stack -->
[![Ansible](https://img.shields.io/badge/ansible-%3E%3D2.16-EE0000?logo=ansible&logoColor=white)](https://www.ansible.com/)
[![Incus](https://img.shields.io/badge/incus-%3E%3D6.0%20LTS-orange)](https://linuxcontainers.org/incus/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Molecule](https://img.shields.io/badge/molecule-tested-green)](https://molecule.readthedocs.io/)

<!-- Static badges — quality gates (validated by CI) -->
[![ansible-lint](https://img.shields.io/badge/ansible--lint-production-brightgreen)](https://ansible.readthedocs.io/projects/lint/)
[![shellcheck](https://img.shields.io/badge/shellcheck-passing-brightgreen)](https://www.shellcheck.net/)
[![ruff](https://img.shields.io/badge/ruff-passing-brightgreen)](https://docs.astral.sh/ruff/)
[![Roles](https://img.shields.io/badge/roles-20-informational)](roles/)

> **⚠️ This project is a proof of concept under active development. It is NOT production-ready. Use at your own risk.**

> **🤖 This project is co-developed with LLMs** (Claude Code, Aider). Architecture decisions, code, tests, and documentation are produced through human-AI collaboration. All contributions are reviewed by the maintainer.

**A declarative high-level interface to Incus.**

QubesOS-like isolation using native Linux kernel features (KVM/LXC),
calmly orchestrated by you and forging standard tools together.

> [Ansible](https://www.ansible.com/), [KVM](https://linux-kvm.org/), [LXC](https://linuxcontainers.org/lxc/), [Molecule](https://molecule.readthedocs.io/) => **anklume** — from "enclume", French for [Incus](https://linuxcontainers.org/incus/) (anvil)

---

## What is anklume?

anklume is a declarative infrastructure compartmentalization framework.
You describe your isolated environments in a single YAML file, run two
commands, and get reproducible, disposable, network-isolated domains — each
with its own subnet, Incus project, and set of containers or VMs.

Think [QubesOS](https://www.qubes-os.org/) philosophy, but:
- **No custom OS** — runs on any Linux distribution
- **No Xen** — uses native kernel features (KVM for VMs, LXC for containers)
- **No black box** — standard tools you already know, glued together
- **Declarative** — describe what you want, anklume converges

## Who is it for?

- **Sysadmins** who want to compartmentalize their workstation (admin,
  professional, personal, homelab — each in its own isolated network)
- **CS teachers** deploying networking labs for N students with one command
- **CS students** learning system administration, networking, and security
  in reproducible, isolated sandboxes they can break and rebuild freely
- **Power users** who want QubesOS-like isolation without the QubesOS
  constraints

## How it works

```
infra.yml          ->    make sync    ->    Ansible files    ->    make apply    ->    Incus state
(you describe)          (generate)        (you enrich)          (converge)         (running infra)
```

1. **Describe** your infrastructure in `infra.yml` (Primary Source of Truth)
2. **Generate** the Ansible file tree: `make sync`
3. **Enrich** the generated files with your custom variables (Secondary Source of Truth)
4. **Apply**: `make apply` — networks, projects, profiles, instances, provisioning

## Prerequisites

Before using anklume, you need:

1. **A Linux host** with [Incus](https://linuxcontainers.org/incus/docs/main/installing/)
   installed and initialized
2. **An anklume instance** (LXC container or VM) named `anklume-instance`, with:
   - The Incus socket mounted (`/var/run/incus/unix.socket`)
   - Ansible, Python 3.11+, git installed
3. **This repository** cloned inside the anklume instance

anklume runs entirely from inside the anklume instance. It never modifies
the host directly — everything goes through the Incus socket.

## Quick start

```bash
# Inside the anklume-instance container:
git clone https://github.com/jmchantrein/anklume.git
cd anklume

# Install Ansible dependencies
make init

# Interactive guided setup (recommended for new users)
make guide

# Or manual setup:
cp infra.yml.example infra.yml   # Edit infra.yml to match your needs
make sync                        # Generate Ansible files
make check                       # Preview changes (dry-run)
make apply                       # Apply infrastructure
```

See the [quick start guide](docs/quickstart.md) for details.

## Architecture

```
+---------------------------------------------------------------+
| Host (any Linux distro)                                       |
|  Incus daemon + nftables + (optional) NVIDIA GPU              |
|                                                               |
|  +-----------+ +-----------+ +-----------+                    |
|  | net-aaa   | | net-bbb   | | net-ccc   |  ...              |
|  | subnet A  | | subnet B  | | subnet C  |                   |
|  +-----+-----+ +-----+-----+ +-----+-----+                  |
|        |              |              |                         |
|  +-----+-----+ +-----+-----+ +-----+-----+                  |
|  | LXC / VM  | | LXC / VM  | | LXC / VM  |                  |
|  +-----------+ +-----------+ +-----------+                    |
|                                                               |
|  nftables isolation: subnet A != B != C (no forwarding)       |
|  Selective cross-domain access via network_policies            |
+---------------------------------------------------------------+
```

Each **domain** is an isolated subnet with its own Incus project. Containers
and VMs within a domain can communicate but cross-domain traffic is blocked
by nftables. Selective exceptions are declared via `network_policies`.
The anklume container drives everything via the Incus socket — no SSH needed.

## Key features

| Category | Feature |
|----------|---------|
| **Core** | Declarative YAML (`infra.yml`) with PSOT generator |
| | Two-phase execution: infrastructure then provisioning |
| | Reconciliation-based idempotent management |
| | Orphan detection and cleanup |
| **Isolation** | Per-domain bridges with nftables cross-bridge isolation |
| | Selective cross-domain access via `network_policies` |
| | Optional dedicated firewall VM (QubesOS sys-firewall style) |
| | Trust levels with color-coded tmux console |
| **Compute** | LXC containers and KVM VMs in the same domain |
| | NVIDIA GPU passthrough (exclusive or shared policy) |
| | Automatic CPU/memory allocation (`resource_policy`) |
| | Boot autostart with priority ordering |
| **AI services** | Ollama LLM server with GPU |
| | Open WebUI chat frontend |
| | LobeChat multi-provider web UI |
| | Speaches STT (faster-whisper, OpenAI-compatible API) |
| | OpenCode headless AI coding server |
| | OpenClaw AI assistant with proxy (multi-brain, cross-container, cost tracking) |
| | Exclusive AI-tools network access with VRAM flush |
| **Lifecycle** | Snapshots (manual + automatic with schedule/expiry) |
| | Golden images with CoW-based derivation |
| | Disposable (ephemeral) instances |
| | Encrypted backup/restore |
| | Flush and rebuild (`make flush && make sync && make apply`) |
| | Safe framework upgrade (`make upgrade`) |
| | Import existing Incus state (`make import-infra`) |
| **Desktop** | QubesOS-style colored tmux console (`make console`) |
| | Clipboard bridging (host <-> container) |
| | Sway/i3 window rules generator |
| | Read-only web dashboard |
| **Networking** | Tor transparent proxy gateway |
| | CUPS print server with USB/network printer passthrough |
| | MCP inter-container services |
| **Testing** | Molecule tests for all 20 roles |
| | pytest for the PSOT generator (2600+ tests) |
| | BDD scenario tests (best/bad practices) |
| | Behavior matrix with coverage tracking |
| | Hypothesis property-based testing |
| | Incus-in-Incus sandbox for isolated testing |
| **AI-assisted dev** | LLM-powered test fixing (Ollama, Claude, Aider) |
| | Claude Code Agent Teams for autonomous development |
| | Experience library for self-improvement |
| **Observability** | Local telemetry (opt-in, never leaves the machine) |
| | Dead code detection and call graph generation |
| | Nesting context propagation across levels |

## Documentation

| Category | Document |
|----------|----------|
| **Getting started** | [Quick start](docs/quickstart.md) |
| | [Interactive guide](docs/guide.md) |
| | [Full specification](docs/SPEC.md) |
| **Architecture** | [Architecture decisions (ADR-001 to ADR-036)](docs/ARCHITECTURE.md) |
| | [Incus native feature coverage](docs/incus-coverage.md) |
| | [Implementation roadmap](docs/ROADMAP.md) |
| | [Decisions log](docs/decisions-log.md) |
| **Networking** | [Network isolation (nftables)](docs/network-isolation.md) |
| | [Dedicated firewall VM](docs/firewall-vm.md) |
| | [Tor gateway](docs/tor-gateway.md) |
| **AI services** | [OpenClaw AI assistant](docs/openclaw.md) |
| | [Exclusive AI-tools access](docs/ai-switch.md) |
| | [Speech-to-Text service](docs/stt-service.md) |
| **Compute** | [VM support guide](docs/vm-support.md) |
| | [GPU management and security](docs/gpu-advanced.md) |
| **Desktop** | [Desktop integration](docs/desktop-integration.md) |
| **Lifecycle** | [File transfer and backup](docs/file-transfer.md) |
| **Development** | [AI-assisted testing](docs/ai-testing.md) |
| | [Agent Teams](docs/agent-teams.md) |
| | [BDD scenario testing](docs/scenario-testing.md) |
| | [Lab deployment guide](docs/lab-tp.md) |
| | [Contributing](CONTRIBUTING.md) |

## Examples

Ready-to-use `infra.yml` configurations:

| Example | Description |
|---------|-------------|
| [Student sysadmin](examples/student-sysadmin/) | 2 domains (anklume + lab), no GPU |
| [Teacher lab](examples/teacher-lab/) | Anklume + N student domains with snapshots |
| [Pro workstation](examples/pro-workstation/) | Anklume/pro/perso/homelab with GPU |
| [Sandbox isolation](examples/sandbox-isolation/) | Maximum isolation for untrusted software |
| [LLM supervisor](examples/llm-supervisor/) | 2 isolated LLMs + 1 supervisor |
| [Developer](examples/developer/) | anklume dev setup with Incus-in-Incus |
| [AI tools](examples/ai-tools/) | Full AI stack (Ollama, WebUI, LobeChat, STT) |
| [Tor gateway](examples/tor-gateway/) | Anonymous browsing via Tor transparent proxy |
| [Print service](examples/sys-print/) | Dedicated CUPS server with USB/network printers |

## Ansible roles

### Infrastructure roles (Phase 1: `connection: local`)

| Role | Responsibility |
|------|---------------|
| `incus_networks` | Create/reconcile domain bridges |
| `incus_projects` | Create/reconcile Incus projects + default profile |
| `incus_profiles` | Create extra profiles (GPU, nesting, resources) |
| `incus_instances` | Create/manage LXC + VM instances |
| `incus_nftables` | Generate inter-bridge isolation rules |
| `incus_firewall_vm` | Multi-NIC profile for firewall VM |
| `incus_images` | Pre-download and export OS images |
| `incus_nesting` | Nesting context propagation |

### Provisioning roles (Phase 2: `connection: community.general.incus`)

| Role | Responsibility |
|------|---------------|
| `base_system` | Base packages, locale, timezone |
| `admin_bootstrap` | Anklume-specific provisioning (Ansible, git) |
| `ollama_server` | Ollama LLM inference server |
| `open_webui` | Open WebUI chat frontend |
| `stt_server` | Speaches STT server (faster-whisper) |
| `lobechat` | LobeChat multi-provider web UI |
| `opencode_server` | OpenCode headless AI coding server |
| `firewall_router` | nftables routing inside firewall VM |
| `openclaw_server` | OpenClaw self-hosted AI assistant |
| `code_sandbox` | Sandboxed AI coding environment |
| `dev_test_runner` | Incus-in-Incus sandbox provisioning |
| `dev_agent_runner` | Claude Code Agent Teams setup |

## Make targets

| Target | Description |
|--------|-------------|
| `make guide` | Interactive onboarding tutorial |
| `make sync` | Generate Ansible files from infra.yml |
| `make sync-dry` | Preview changes without writing |
| `make lint` | Run all validators (ansible-lint, yamllint, shellcheck, ruff) |
| `make check` | Dry-run (--check --diff) |
| `make apply` | Apply full infrastructure |
| `make apply-limit G=<domain>` | Apply a single domain |
| `make console` | Launch colored tmux session |
| `make nftables` | Generate nftables isolation rules |
| `make nftables-deploy` | Deploy rules on host |
| `make snap I=<name>` | Create snapshot |
| `make flush` | Destroy all anklume infrastructure |
| `make upgrade` | Safe framework update |
| `make import-infra` | Generate infra.yml from existing Incus state |
| `make help` | List all available targets |

## Tech stack

| Component | Version | Role |
|-----------|---------|------|
| [Incus](https://linuxcontainers.org/incus/) | >= 6.0 LTS | LXC containers + KVM VMs |
| [Ansible](https://www.ansible.com/) | >= 2.16 | Orchestration, roles, playbooks |
| [community.general](https://docs.ansible.com/ansible/latest/collections/community/general/) | >= 9.0 | Incus connection plugin |
| [Molecule](https://molecule.readthedocs.io/) | >= 24.0 | Ansible role testing |
| [pytest](https://docs.pytest.org/) | >= 8.0 | Generator + BDD testing |
| [Python](https://www.python.org/) | >= 3.11 | PSOT generator, scripts |
| [nftables](https://netfilter.org/projects/nftables/) | -- | Inter-bridge isolation |
| [shellcheck](https://www.shellcheck.net/) | -- | Shell script validation |
| [ruff](https://docs.astral.sh/ruff/) | -- | Python linting |

## Credits

anklume is a glue framework — it orchestrates these excellent open-source
projects (ADR-040):

### Core infrastructure

| Tool | Role |
|------|------|
| [Incus](https://linuxcontainers.org/incus/) | LXC containers + KVM virtual machines |
| [Ansible](https://www.ansible.com/) | Orchestration, roles, playbooks |
| [community.general](https://docs.ansible.com/ansible/latest/collections/community/general/) | Incus connection plugin for Ansible |
| [nftables](https://netfilter.org/projects/nftables/) | Inter-bridge network isolation |
| [Python](https://www.python.org/) | PSOT generator and scripts |
| [PyYAML](https://pyyaml.org/) | YAML parsing for the generator |
| [Linux kernel](https://kernel.org/) | KVM, LXC, namespaces, cgroups |

### AI / ML services

| Tool | Role |
|------|------|
| [Ollama](https://ollama.com/) | Local LLM inference server |
| [Open WebUI](https://openwebui.com/) | Chat frontend for LLMs |
| [LobeChat](https://lobechat.com/) | Multi-provider web UI |
| [Speaches](https://github.com/speaches-ai/speaches) | Speech-to-text (faster-whisper, OpenAI-compatible API) |
| [OpenCode](https://opencode.ai/) | Headless AI coding server |
| [OpenClaw](https://github.com/openclaw-ai/openclaw) | Self-hosted AI assistant |

### Quality and testing

| Tool | Role |
|------|------|
| [Molecule](https://molecule.readthedocs.io/) | Ansible role testing |
| [pytest](https://docs.pytest.org/) | Generator and BDD testing |
| [Hypothesis](https://hypothesis.readthedocs.io/) | Property-based testing |
| [ansible-lint](https://ansible.readthedocs.io/projects/lint/) | Ansible linting |
| [yamllint](https://yamllint.readthedocs.io/) | YAML validation |
| [shellcheck](https://www.shellcheck.net/) | Shell script validation |
| [ruff](https://docs.astral.sh/ruff/) | Python linting |

### Desktop and networking

| Tool | Role |
|------|------|
| [tmux](https://github.com/tmux/tmux) | Terminal multiplexer for colored console |
| [libtmux](https://libtmux.git-pull.com/) | Python API for tmux |
| [Tor](https://www.torproject.org/) | Anonymous routing gateway |
| [CUPS](https://openprinting.github.io/cups/) | Print server |

### Development

| Tool | Role |
|------|------|
| [Claude Code](https://claude.ai/claude-code) | AI-assisted development |
| [Aider](https://aider.chat/) | AI-assisted coding |
| [uv](https://docs.astral.sh/uv/) | Python package management |
| [Git](https://git-scm.com/) | Version control |

## License

[AGPL-3.0](LICENSE)

---

[Version francaise](README_FR.md)
