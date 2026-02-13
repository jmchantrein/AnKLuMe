# AnKLuMe 🔨

<!-- Dynamic badges (auto-updated from GitHub) -->
[![CI](https://github.com/jmchantrein/AnKLuMe/actions/workflows/ci.yml/badge.svg)](https://github.com/jmchantrein/AnKLuMe/actions)
[![License](https://img.shields.io/github/license/jmchantrein/AnKLuMe)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/jmchantrein/AnKLuMe)](https://github.com/jmchantrein/AnKLuMe/commits/main)
[![Issues](https://img.shields.io/github/issues/jmchantrein/AnKLuMe)](https://github.com/jmchantrein/AnKLuMe/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/jmchantrein/AnKLuMe)](https://github.com/jmchantrein/AnKLuMe/pulls)

<!-- Static badges — tech stack -->
[![Ansible](https://img.shields.io/badge/ansible-%3E%3D2.16-EE0000?logo=ansible&logoColor=white)](https://www.ansible.com/)
[![Incus](https://img.shields.io/badge/incus-%3E%3D6.0%20LTS-orange)](https://linuxcontainers.org/incus/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Molecule](https://img.shields.io/badge/molecule-tested-green)](https://molecule.readthedocs.io/)

<!-- Static badges — quality gates (validated by CI) -->
[![ansible-lint](https://img.shields.io/badge/ansible--lint-production-brightgreen)](https://ansible.readthedocs.io/projects/lint/)
[![shellcheck](https://img.shields.io/badge/shellcheck-passing-brightgreen)](https://www.shellcheck.net/)
[![ruff](https://img.shields.io/badge/ruff-passing-brightgreen)](https://docs.astral.sh/ruff/)
[![Roles](https://img.shields.io/badge/roles-18-informational)](roles/)

**QubesOS-like isolation using native Linux kernel features (KVM/LXC).**

Calmly orchestrated by you and forging standard tools together,
not reinventing them.

> [Ansible](https://www.ansible.com/), [KVM](https://linux-kvm.org/), [LXC](https://linuxcontainers.org/lxc/), [Molecule](https://molecule.readthedocs.io/) ⇒ **AnKLuMe** — from "enclume", french for [Incus](https://linuxcontainers.org/incus/) 🔨

---

## What is AnKLuMe?

AnKLuMe is a declarative infrastructure compartmentalization framework.
You describe your isolated environments in a single YAML file, run two
commands, and get reproducible, disposable, network-isolated domains — each
with its own subnet, Incus project, and set of containers or VMs.

Think [QubesOS](https://www.qubes-os.org/) philosophy, but:
- **No custom OS** — runs on any Linux distribution
- **No Xen** — uses native kernel features (KVM for VMs, LXC for containers)
- **No black box** — standard tools you already know, glued together
- **Declarative** — describe what you want, AnKLuMe converges

## Who is it for?

- **Sysadmins** who want to compartmentalize their workstation (admin,
  professional, personal, homelab — each in its own isolated network)
- **Teachers** deploying networking labs for N students with one command
- **Power users** who want QubesOS-like isolation without the QubesOS
  constraints

## How it works

```
infra.yml          →    make sync    →    Ansible files    →    make apply    →    Incus state
(you describe)          (generate)        (you enrich)          (converge)         (running infra)
```

1. **Describe** your infrastructure in `infra.yml` (Primary Source of Truth)
2. **Generate** the Ansible file tree: `make sync`
3. **Enrich** the generated files with your custom variables (Secondary Source of Truth)
4. **Apply**: `make apply` — networks, projects, profiles, instances, provisioning

## Prerequisites

Before using AnKLuMe, you need:

1. **A Linux host** with [Incus](https://linuxcontainers.org/incus/docs/main/installing/)
   installed and initialized
2. **An admin instance** (LXC container or VM) named `admin-ansible`, with:
   - The Incus socket mounted (`/var/run/incus/unix.socket`)
   - Ansible, Python 3.11+, git installed
3. **This repository** cloned inside the admin instance

AnKLuMe runs entirely from inside the admin instance. It never modifies
the host directly — everything goes through the Incus socket.

> Host installation guides for Debian and Arch Linux: see [ROADMAP](docs/ROADMAP.md).

## Quick start

Inside the `admin-ansible` instance:

```bash
# Clone
git clone https://github.com/<user>/anklume.git
cd anklume

# Install Ansible dependencies
make init

# Create your infrastructure descriptor
cp infra.yml.example infra.yml
# Edit infra.yml — define your domains and machines

# Generate Ansible files
make sync

# Preview what would happen
make check

# Apply
make apply
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Host (any Linux distro)                                 │
│  • Incus daemon + nftables + (optional) NVIDIA GPU      │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ net-aaa  │ │ net-bbb  │ │ net-ccc  │  ...           │
│  │ subnet A │ │ subnet B │ │ subnet C │                │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘                │
│       │             │             │                      │
│  ┌────┴────┐  ┌─────┴────┐ ┌────┴──────┐               │
│  │ LXC/VM  │  │ LXC/VM   │ │ LXC/VM   │               │
│  └─────────┘  └──────────┘ └──────────┘                │
│                                                         │
│  nftables isolation: subnet A ≠ B ≠ C (no forwarding)  │
└─────────────────────────────────────────────────────────┘
```

Each **domain** is an isolated subnet with its own Incus project. Containers
and VMs within a domain can talk to each other but not to other domains.
An admin container drives everything via the Incus socket — no SSH needed.

## Key features

- **Declarative**: Describe domains, machines, profiles in `infra.yml`
- **Two-phase execution**: Infrastructure (create networks, projects, instances)
  then provisioning (install packages, configure services)
- **Reconciliation**: Idempotent — detects drift, creates what's missing,
  reports orphans
- **GPU passthrough**: Optional NVIDIA GPU support for LXC containers (LLM, ML)
- **Snapshots**: Individual, per-domain, or global — with restore
- **Tested**: Molecule for roles, pytest for the generator

## Documentation

- [Quick start guide](docs/quickstart.md)
- [Lab deployment guide](docs/lab-tp.md) — for teachers deploying student labs
- [GPU + LLM guide](docs/gpu-llm.md) — GPU passthrough, Ollama, Open WebUI
- [Full specification](docs/SPEC.md)
- [Architecture decisions](docs/ARCHITECTURE.md)
- [Implementation roadmap](docs/ROADMAP.md)
- [Claude Code workflow](docs/claude-code-workflow.md)
- [Contributing](CONTRIBUTING.md)

## Examples

Ready-to-use `infra.yml` configurations for common use cases:

| Example | Description |
|---------|-------------|
| [Student sysadmin](examples/student-sysadmin/) | 2 domains (admin + lab) for sysadmin students, no GPU |
| [Teacher lab](examples/teacher-lab/) | Admin + N student domains with isolated networks and snapshots |
| [Pro workstation](examples/pro-workstation/) | Admin, personal, professional, homelab domains with GPU |
| [Sandbox isolation](examples/sandbox-isolation/) | Maximum isolation for untrusted software testing |
| [LLM supervisor](examples/llm-supervisor/) | 2 isolated LLMs + 1 supervisor for multi-LLM management |
| [Developer](examples/developer/) | AnKLuMe developer setup with Incus-in-Incus testing |

See [examples/README.md](examples/README.md) for details.

## Tech stack

| Tool | Role |
|------|------|
| [Ansible](https://www.ansible.com/) | Orchestration, roles, playbooks |
| [Incus](https://linuxcontainers.org/incus/) | Container/VM management (LXC + KVM) |
| [KVM](https://linux-kvm.org/) | Native kernel virtualization (VMs) |
| [LXC](https://linuxcontainers.org/lxc/) | Native kernel containers |
| [Molecule](https://molecule.readthedocs.io/) | Ansible role testing |
| [nftables](https://netfilter.org/projects/nftables/) | Inter-domain network isolation |
| [community.general](https://docs.ansible.com/ansible/latest/collections/community/general/) | Incus connection plugin |

## License

[Apache 2.0](LICENSE)

---

🇫🇷 [Version française](README_FR.md)
