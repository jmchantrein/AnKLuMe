# DECISIONS.md — make help Restructuring (Phase 32)

## Target-to-Category Mapping

### GETTING STARTED (3 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `guide` | Interactive step-by-step tutorial | First thing a new user needs |
| `quickstart` | Copy example infra.yml and sync | Quick bootstrap |
| `init` | Install Ansible dependencies | One-time setup |

### CORE WORKFLOW (7 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `sync` | Generate Ansible files from infra.yml | Primary PSOT operation |
| `sync-dry` | Preview changes without writing | Safe preview before sync |
| `apply` | Apply full infrastructure + provisioning | Main deployment command |
| `apply-limit G=x` | Apply a single domain | Targeted deployment |
| `check` | Dry-run (--check --diff) | Safe preview before apply |
| `nftables` | Generate nftables isolation rules | Core network security |
| `doctor` | Diagnose infrastructure health | Troubleshooting entry point |

### SNAPSHOTS (4 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `snapshot` | Snapshot all instances | Basic backup operation |
| `restore NAME=x` | Restore a snapshot | Recovery operation |
| `rollback` | Restore last pre-apply snapshot | Quick undo after apply |
| `rollback-list` | List pre-apply snapshots | Browse available rollbacks |

### AI / LLM (7 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `apply-ai` | Deploy all AI services | One-command AI stack deploy |
| `llm-switch B=x` | Switch backend (llama/ollama) | Backend management |
| `llm-status` | Show backend, model, VRAM | Status check |
| `llm-bench` | Benchmark inference | Performance measurement |
| `llm-dev` | Local LLM dev assistant | Interactive AI coding |
| `ai-switch DOMAIN=x` | Switch exclusive AI access | Domain-level AI access |
| `claude-host` | Claude Code with root + guard hook | Host-level AI coding |

### CONSOLE (2 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `console` | Launch tmux domain-colored console | Primary UI entry point |
| `dashboard` | Web dashboard (PORT=8888) | Web-based monitoring |

### INSTANCE MANAGEMENT (3 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `disp` | Launch disposable ephemeral instance | Quick sandbox creation |
| `backup I=x` | Backup an instance | Data protection |
| `file-copy` | Copy file between instances | Cross-instance file transfer |

### LIFECYCLE (3 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `upgrade` | Safe framework update | Version management |
| `flush` | Destroy all infrastructure | Full teardown |
| `import-infra` | Generate infra.yml from Incus state | Reverse-engineering existing infra |

### DEVELOPMENT (3 targets)

| Target | Description | Rationale |
|--------|-------------|-----------|
| `lint` | Run all validators | Code quality gate |
| `test` | Run all tests | Test execution |
| `smoke` | Real-world smoke test | End-to-end verification |

**Total: 32 user-facing targets across 8 categories.**

---

## User-Facing vs Internal Targets

### Criteria for "user-facing"

A target is user-facing if a regular anklume user (sysadmin, teacher,
power user) would reasonably use it during normal operations.

### Internal targets (shown only in `help-all`)

These targets are either sub-targets of a user-facing command,
specialized developer tools, or rarely-used variations:

| Target | Reason for exclusion |
|--------|---------------------|
| `sync-clean` | Destructive, advanced usage |
| `shares` | Rarely needed standalone |
| `lint-yaml`, `lint-ansible`, `lint-shell`, `lint-python` | Sub-targets of `lint` |
| `syntax` | Sub-target of quality checks |
| `apply-infra`, `apply-provision`, `apply-base` | Sub-targets of `apply` |
| `apply-images`, `apply-llm`, `apply-stt` | Specialized apply variants |
| `apply-code-sandbox`, `apply-openclaw` | Specialized deploy targets |
| `export-images` | Niche (nesting image cache) |
| `nftables-deploy` | Run from host, not container |
| `snapshot-domain`, `restore-domain` | Narrower variants of snapshot/restore |
| `snapshot-delete`, `snapshot-list` | Secondary snapshot operations |
| `rollback-cleanup` | Maintenance operation |
| `test-generator`, `test-roles`, `test-role` | Sub-targets of `test` |
| `test-sandboxed`, `test-sandboxed-role` | Specialized test modes |
| `runner-create`, `runner-destroy` | Test infrastructure management |
| `scenario-test`, `scenario-test-best`, `scenario-test-bad`, `scenario-list` | Dev-only scenario testing |
| `matrix-coverage`, `matrix-generate` | Dev-only behavior matrix |
| `test-report` | Dev/CI reporting |
| `ai-test`, `ai-test-role`, `ai-develop` | AI-assisted dev tools |
| `agent-runner-setup`, `agent-fix`, `agent-develop` | Agent Teams dev tools |
| `mine-experiences`, `ai-improve` | Dev automation |
| `clipboard-to`, `clipboard-from`, `domain-exec` | Desktop integration (niche) |
| `desktop-config` | Desktop env config generation |
| `export-app`, `export-list`, `export-remove` | App export (niche) |
| `build-image`, `live-update`, `live-status` | Live OS (niche) |
| `portal-open`, `portal-push`, `portal-pull`, `portal-list` | File portal (niche) |
| `golden-create`, `golden-derive`, `golden-publish`, `golden-list` | Golden images (niche) |
| `mcp-list`, `mcp-call` | MCP service calls |
| `mcp-dev-start`, `mcp-dev-stop`, `mcp-dev-status`, `mcp-dev-logs` | MCP dev server mgmt |
| `apply-tor`, `apply-print` | Specialized service setup |
| `dead-code`, `call-graph`, `dep-graph`, `code-graph` | Code analysis (dev) |
| `audit`, `audit-json` | Code audit (dev) |
| `telemetry-on`, `telemetry-off`, `telemetry-status`, `telemetry-clear`, `telemetry-report` | Telemetry management |
| `restore-backup` | Backup restore variant |
| `claude-host-resume`, `claude-host-audit` | Claude Code variants |
| `install-hooks`, `install-update-notifier` | One-time setup |
| `llm-switch` (already in help) | — |

---

## Category Color Scheme

| Category | ANSI Code | Color |
|----------|-----------|-------|
| GETTING STARTED | `\033[1;32m` | Bold Green |
| CORE WORKFLOW | `\033[1;36m` | Bold Cyan |
| SNAPSHOTS | `\033[1;33m` | Bold Yellow |
| AI / LLM | `\033[1;35m` | Bold Magenta |
| CONSOLE | `\033[1;34m` | Bold Blue |
| INSTANCE MANAGEMENT | `\033[1;36m` | Bold Cyan |
| LIFECYCLE | `\033[1;31m` | Bold Red |
| DEVELOPMENT | `\033[1;32m` | Bold Green |

---

## `make help` Output

```
  anklume — Infrastructure Compartmentalization

  GETTING STARTED
    make guide              Interactive step-by-step tutorial
    make quickstart         Copy example infra.yml and sync
    make init               Install Ansible dependencies

  CORE WORKFLOW
    make sync               Generate Ansible files from infra.yml
    make sync-dry           Preview changes without writing
    make apply              Apply full infrastructure + provisioning
    make apply-limit G=x    Apply a single domain
    make check              Dry-run (--check --diff)
    make nftables           Generate nftables isolation rules
    make doctor             Diagnose infrastructure health

  SNAPSHOTS
    make snapshot           Snapshot all instances
    make restore NAME=x     Restore a snapshot
    make rollback           Restore last pre-apply snapshot
    make rollback-list      List pre-apply snapshots

  AI / LLM
    make apply-ai           Deploy all AI services
    make llm-switch B=x     Switch backend (B=llama|ollama [MODEL=])
    make llm-status         Show backend, model, VRAM
    make llm-bench          Benchmark inference (MODEL= COMPARE=1)
    make llm-dev            Local LLM dev assistant (no API credits)
    make ai-switch DOMAIN=x Switch exclusive AI access
    make claude-host        Claude Code with root + guard hook (sudo)

  CONSOLE
    make console            Launch tmux domain-colored console
    make dashboard          Web dashboard (PORT=8888)

  INSTANCE MANAGEMENT
    make disp               Launch disposable ephemeral instance
    make backup I=x         Backup an instance
    make file-copy          Copy file between instances (SRC= DST=)

  LIFECYCLE
    make upgrade            Safe framework update
    make flush              Destroy all infrastructure (FORCE=true)
    make import-infra       Generate infra.yml from Incus state

  DEVELOPMENT
    make lint               Run all validators
    make test               Run all tests
    make smoke              Real-world smoke test

  Run make help-all for all targets.
```
