# LLM Onboarding Prompt — anklume Project

Use this file as a system prompt or initial context when onboarding any
LLM (Claude, GPT, Gemini, Mistral, local models) to work on anklume.

---

## What is anklume?

anklume is a **declarative infrastructure compartmentalization framework**.
It provides QubesOS-like isolation using native Linux kernel features
(KVM/LXC), orchestrated by Ansible and Incus. The user describes their
infrastructure in `infra.yml`, runs `anklume sync && anklume domain apply`, and gets
isolated, reproducible environments.

**It is NOT a web app, NOT an API.** It is Infrastructure-as-Code.

## Tech stack

| Component | Role |
|-----------|------|
| **Ansible** (YAML) | Orchestration, roles, playbooks |
| **Python** | PSOT generator (`scripts/generate.py`) |
| **Bash** | Helper scripts (`scripts/*.sh`) |
| **Incus** | Container/VM runtime (LXC + KVM) |
| **nftables** | Network isolation between domains |
| **Molecule** | Ansible role testing |
| **pytest** | Python generator testing |

## Source of truth model (PSOT)

```
infra.yml  --(anklume sync)-->  Ansible files  --(anklume domain apply)-->  Incus state
 (PSOT)                     (inventory/,                    (bridges, projects,
                             group_vars/,                    profiles, instances)
                             host_vars/)
```

- `infra.yml` = Primary Source of Truth (structural)
- Generated Ansible files = Secondary Source of Truth (operational)
- Users edit generated files OUTSIDE `=== MANAGED ===` sections
- Both are committed to git

## Essential files to read FIRST

Read these files in order to understand the project:

1. `CLAUDE.md` — Non-negotiable coding conventions and commands
2. `docs/SPEC.md` — Full specification (formats, roles, validation)
3. `docs/ARCHITECTURE.md` — Architecture decisions (ADR-001 to ADR-036)
4. `docs/ROADMAP.md` — Implementation phases (1-18, all complete)
5. `docs/decisions-log.md` — Recent autonomous decisions

## Non-negotiable conventions

You MUST follow these. Violations will be caught by linters.

### Ansible
- **FQCN mandatory**: `ansible.builtin.command`, never `command`
- **Task names**: `RoleName | Description with initial capital`
- **`changed_when`** on ALL `command`/`shell` tasks
- **No `ignore_errors`** — use `failed_when: false` when needed
- **Role variables**: prefix with `<role_name>_`

### Incus
- **CLI only**: `ansible.builtin.command` + `incus ... --format json`
- **Manual idempotency**: check existence before create
- **Reconciliation pattern**: read → compare → create/update → detect orphans
- **No SSH**: everything via Incus socket or `community.general.incus`

### General
- **Language**: code, comments, docs in English
- **French translations**: `*.fr.md` maintained for all docs (ADR-011)
- **DRY/KISS**: no file over 200 lines, one file = one responsibility
- **No wheel reinvented**: use native Ansible/Incus features first

## Validation commands

```bash
anklume dev lint          # ALL validators (ansible-lint, yamllint, shellcheck, ruff)
anklume dev test          # pytest (2238+ tests)
anklume domain check         # ansible-playbook --check --diff
anklume sync --dry-run      # Preview generator output
```

ALL must pass before committing. Zero violations tolerated.

## Development workflow

1. **Spec first**: update SPEC.md or ARCHITECTURE.md
2. **Test second**: write tests (Molecule for roles, pytest for generator)
3. **Implement third**: code until tests pass
4. **Validate**: `anklume dev lint`
5. **Commit**: one commit per logical change

## Project structure

```
anklume/
├── CLAUDE.md              # LLM coding conventions
├── infra.yml              # Primary Source of Truth
├── site.yml               # Master playbook (at root, ADR-016)
├── Makefile               # All commands
├── scripts/
│   ├── generate.py        # PSOT generator (Python)
│   ├── snap.sh            # Snapshot management
│   ├── ai-switch.sh       # Exclusive AI access switching
│   ├── deploy-nftables.sh # Host-side nftables deployment
│   ├── guide.sh           # Interactive onboarding
│   └── ...
├── roles/
│   ├── incus_networks/    # Bridge creation/reconciliation
│   ├── incus_projects/    # Incus project management
│   ├── incus_profiles/    # Profile management
│   ├── incus_instances/   # Instance lifecycle (LXC + VM)
│   ├── incus_nftables/    # nftables rule generation
│   ├── incus_firewall_vm/ # Firewall VM multi-NIC profile
│   ├── incus_images/      # Image pre-download + export
│   ├── incus_nesting/     # Nesting context propagation
│   ├── base_system/       # Base provisioning
│   ├── ollama_server/     # LLM inference server
│   ├── open_webui/        # Chat frontend
│   ├── stt_server/        # Speech-to-text (Speaches)
│   ├── lobechat/          # LobeChat multi-provider UI
│   ├── opencode_server/   # OpenCode headless AI coding
│   ├── firewall_router/   # nftables inside firewall VM
│   ├── dev_test_runner/   # Incus-in-Incus sandbox
│   └── dev_agent_runner/  # Claude Code Agent Teams setup
├── tests/                 # pytest test suite (2238+ tests)
├── docs/                  # Documentation (EN + FR)
├── examples/              # Example infra.yml files
└── experiences/           # Fix patterns and knowledge base
```

## Key architectural decisions (must-know)

| ADR | Decision |
|-----|----------|
| ADR-001 | Ansible inventory mirrors real infrastructure |
| ADR-002 | infra.yml is the PSOT, generated files are secondary |
| ADR-004 | Host never in inventory; admin container drives Incus via socket |
| ADR-005 | Incus via CLI (no native Ansible modules) |
| ADR-006 | Two execution phases: infra (local) + provisioning (incus) |
| ADR-008 | Machine names globally unique |
| ADR-011 | English primary, French translations maintained |
| ADR-015 | hosts:all + connection:local (no run_once) |
| ADR-020 | Privileged LXC forbidden without VM in parent chain |
| ADR-021 | Network policies: declarative cross-domain allow rules |

## Current branch and state

- **Branch**: `feature/self-improvement`
- **All phases (1-18)**: complete
- **Tests**: 2238+ passing, 0 failing
- **Linters**: all clean

## Short-term roadmap (Phase 19+)

The following features are planned but not yet implemented:

### Phase 19: Terminal UX and Observability
- **tmux/tmuxp console** (`anklume console`): auto-generated tmux session
  from infra.yml — one window per domain, one pane per machine,
  per-pane background color by trust level (QubesOS-style visual
  domain isolation in the terminal). Uses libtmux (Python API) for
  programmatic generation. Pane border labels show domain/machine name.
  Colors are set server-side (`select-pane -P`) — containers cannot
  spoof them.
- **Local telemetry** (opt-in, local-only): usage logging in JSON Lines
  (`~/.anklume/telemetry/usage.jsonl`). No network calls, no phone home.
  Tracks: make targets, domains, duration, exit codes.
  `anklume telemetry on/off/report/clear`. Terminal visualization via
  plotext. Optional HTML report generation.
- **Static analysis** (`anklume dev graph --type code`): dead code detection (vulture
  for Python, shellcheck for bash), call graphs (pyan), dependency
  graphs (pydeps), unused Ansible variables (little-timmy). GraphViz
  visualization of the full codebase architecture.

### Phase 20: Native Incus Features and QubesOS Parity
- **Disposable instances**: `anklume instance disp --image debian/13 CMD=bash` using
  Incus native `--ephemeral` flag (auto-destroyed on stop)
- **Golden images / templates**: CoW-based instance derivation using
  `incus copy` on ZFS/Btrfs backends. `incus publish` for reusable
  images. Profile updates propagate automatically to all instances.
- **Inter-container services via MCP**: each container exposes services
  as MCP (Model Context Protocol) tools over Incus proxy devices
  (Unix sockets). Lightweight: only `tools/list` + `tools/call`
  needed. Standard protocol with SDKs in Python/Go/Rust. Policy
  engine in admin container controls which containers can call which
  services. AI agents can use the same MCP endpoints natively.
- **File transfer**: `anklume portal copy a:/path b:/path` wrapping
  `incus file pull/push` pipe. Shared volumes for bulk transfers.
- **Backup/export**: `anklume backup create` wrapping `incus export` + GPG
  encryption. `anklume backup restore` for import. Cross-machine
  migration via `incus copy local: remote:`.
- **Tor gateway domain**: transparent Tor proxy container with
  network_policies routing traffic from selected domains.
- **shared-print**: dedicated CUPS container in the `shared` domain.
  USB printers via Incus `usb` device passthrough. Network printers
  (WiFi/Ethernet) via macvlan NIC giving the container access to the
  physical LAN. Other domains access `shared-print` via IPP (port 631)
  through network_policies.

### Phase 21: Desktop Integration (optional)
- **Terminal background coloring**: per-domain colors via tmux
  server-side pane styles (unspooofable by containers)
- **Wayland clipboard forwarding**: controlled clipboard sharing
  between domains via MCP + proxy devices
- **Desktop environment hints**: Sway `app_id` / KDE / GNOME
  `_NET_WM_*` properties for per-domain window coloring
- **Web dashboard** (future): Flask/FastAPI + htmx for visual
  domain status, network policies, GPU allocation

## How to contribute

1. Read `CLAUDE.md` and this file
2. Read the specific docs for the area you're working on
3. Follow the dev workflow: spec → test → implement → lint → commit
4. Log autonomous decisions in `docs/decisions-log.md`
5. One commit per logical change
6. Never modify `=== MANAGED ===` sections manually
7. Run `anklume dev lint && anklume dev test` before every commit
