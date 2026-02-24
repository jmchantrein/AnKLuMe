# anklume

A declarative infrastructure compartmentalization framework.
QubesOS-like isolation using native Linux kernel features (KVM/LXC),
calmly orchestrated by you, Ansible, Incus and Molecule.

## Project identity

- **Type**: Infrastructure-as-Code (not a web app, not an API)
- **Primary language**: YAML (Ansible roles + playbooks) + Python (PSOT generator)
- **Target audience**: sysadmins, teachers, power users
- **License**: AGPL-3.0

## Non-negotiable principles

1. **DRY**: Defaults are inherited, never copy-pasted between domains.
2. **KISS**: One file = one responsibility. No file over 200 lines.
3. **Native Ansible**: group_vars, host_vars, roles, defaults, tags, Jinja2.
   NEVER reinvent what Ansible already provides.
4. **Native Incus best practices**: Follow upstream Incus documentation.
   Projects for namespace isolation, profiles for reusable config, bridges
   for network isolation.
5. **Incus via CLI**: No stable native Ansible modules exist for Incus.
   Use `ansible.builtin.command` + `incus ... --format json` + manual
   idempotency checks.
6. **Reconciliation**: Every infra role follows the pattern:
   read → compare → create/update → detect orphans.
7. **No SSH**: Everything via Incus socket or `community.general.incus`
   connection plugin.
8. **Spec-driven, test-driven development**: Write/update spec first, write
   tests second, implement third. No code without a spec and a test.
9. **No wheel reinvented**: Glue standard, battle-tested tools together.

## Source of truth model (PSOT)

- **Primary Source of Truth (PSOT)**: `infra.yml` — describes the infrastructure
  at a high level (domains, machines, networks, profiles).
- **Secondary Source of Truth**: Generated Ansible files (inventory/, group_vars/,
  host_vars/) — enriched by the user outside of managed sections.
- Flow: `infra.yml` → `make sync` → Ansible files → `make apply` → Incus state.
- Users may freely edit generated files outside `=== MANAGED ===` sections.
- Both `infra.yml` AND the Ansible files should be committed to git.

## Commands

```bash
make sync          # Generate/update Ansible files from infra.yml
make sync-dry      # Preview changes without writing
make lint          # All validators (ansible-lint, yamllint, shellcheck, ruff)
make check         # Dry-run (ansible-playbook --check --diff)
make apply         # Apply full infrastructure
make apply-limit G=<group>  # Apply a single domain
make test          # Run Molecule + pytest
make shares        # Create host directories for shared_volumes
make snapshot      # Snapshot all instances
make nftables      # Generate nftables isolation rules
make nftables-deploy  # Deploy rules on host (run FROM host)
make flush         # Destroy all anklume infrastructure (dev mode)
make upgrade       # Safe framework update with conflict detection
make import-infra  # Generate infra.yml from existing Incus state
make help          # List all commands
```

## Ansible code conventions

- Task names: `RoleName | Description with initial capital`
- Role-internal variables: prefix with `<role_name>_` (e.g. `incus_networks_declared`)
- FQCN mandatory: `ansible.builtin.command`, not `command`
- Explicit `changed_when` on all `command`/`shell` tasks
- No `ignore_errors` — use `failed_when: false` when needed
- All code, comments, docs, and prompts in English
- A `README_FR.md` is maintained as a French translation of `README.md`

## Quality gates

No file escapes validation. `make lint` chains all validators (0 violations):

| Tool | Scope | Config |
|------|-------|--------|
| `ansible-lint` | `roles/`, `*.yml` playbooks | `.ansible-lint` (production profile) |
| `yamllint` | All `*.yml` / `*.yaml` | `.yamllint.yml` |
| `shellcheck` | `scripts/*.sh` | Inline directives |
| `ruff` | All `*.py` | `pyproject.toml` |

Additional gates: `--syntax-check` passes, Molecule tests for infra roles,
`pytest` for the generator, review via `.claude/agents/reviewer.md` before commit.

## Quality guardrails (learned from audits)

These rules prevent recurring mistakes. When an audit reveals a new
pattern, add a rule here.

### Python (generate.py, scripts/)
- **No `sys.exit()` outside `main()`** — raise `ValueError` or a custom
  exception; `main()` wraps in try/except.
- **No dead code** — if a variable is built but never read, delete it.
- **Spec before code** — every feature in `generate.py` must have a
  matching entry in `SPEC.md` (ADR-009).
- **DRY helpers** — when logic is duplicated (>5 lines identical in 2+
  places), extract a helper immediately.
- **Validate all optional fields** — every optional `infra.yml` field must
  be type-checked in `validate()` (bool, int range, enum).
- **DNS-safe names** — domain and machine names must match
  `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$` (no trailing hyphen, no uppercase).

### Ansible roles
- **`changed_when` must be semantically correct** — never use
  `changed_when: false` on a task that mutates state (`incus config set`,
  `npm install`, etc.). Read current value first, compare, then set with
  `changed_when: true` (gated by condition).
- **`# noqa` is not a fix** — suppressing a lint warning without fixing
  the underlying issue is forbidden.
- **Role variable prefix** — ALL role-private variables (including
  defaults and register variables) must use `<role_name>_` prefix.
  The `.ansible-lint` `var-naming` skip is for PSOT shared variables only.
- **No duplicated patterns across roles** — shared setup (Node.js, dpkg
  lock wait, collection install) must be extracted to a shared task file
  or dependency role.

### Tests
- **Fixtures in `conftest.py`** — if a fixture appears in 2+ test files,
  move it to `conftest.py`.
- **Test from the spec, not from the code** — behavior tests describe
  what SPEC.md says, not what the implementation happens to do.
- **`skipif` for optional tools** — tests that call external binaries
  (`shellcheck`, `ruff`, etc.) must use `pytest.mark.skipif` with
  `shutil.which()`.

### Documentation
- **Update ADRs when implementation evolves** — if a decision is
  superseded by later work, update the ADR text or add a supersession
  note.
- **Deprecated syntax in examples = bug** — all code examples in docs
  and `*.example` files must use the current API (not `base_subnet` when
  `addressing:` is the current standard).
- **French translations** — every English doc update must note the FR
  file as out-of-sync if not updated simultaneously.

## LLM operating mode

At the start of each session or after a /clear, you MUST ask the user:

> Mode de fonctionnement ?
> 1. **Local (défaut)** — Je supervise, les LLM locaux (Ollama) codent
> 2. **Externe** — Je fais tout moi-même (consomme plus de tokens)

- Local mode is the default. If the user doesn't answer or says "ok", use local mode.
- In local mode, use the MCP `ollama-coder` tools for code generation/fixing.
  Delegate to the `local-coder` agent or call MCP tools directly.
- In external mode, work normally without delegation.
- The mode can be changed mid-session with "passe en mode local" or "passe en mode externe".

## Context files

Always loaded (core project instructions):
- @docs/SPEC.md — Core specification (vision, PSOT model, infra.yml format)
- @docs/ARCHITECTURE.md — Architecture decisions (ADR-style)

Read on demand with the Read tool (NOT auto-loaded — too large):
- `docs/SPEC-operations.md` — Operational reference (generator, roles, snapshots, validators, bootstrap)
- `docs/ROADMAP.md` — Implementation phases and priorities
- `docs/decisions-log.md` — Autonomous decisions pending review
- `docs/addressing-convention.md` — Trust-level IP addressing (ADR-038)
- `docs/network-isolation.md` — nftables inter-bridge isolation
- `docs/vm-support.md` — KVM VM support guide
- `docs/gpu-advanced.md` — GPU management and security policy
- `docs/firewall-vm.md` — Dedicated firewall VM
- `docs/ai-testing.md` — AI-assisted testing and development
- `docs/stt-service.md` — Speech-to-Text service
- `docs/agent-teams.md` — Claude Code Agent Teams
- `docs/ai-switch.md` — Exclusive AI-tools network access
- `docs/guide.md` — Interactive onboarding guide
- `docs/quickstart.md` — Quick start tutorial
- `docs/console.md` — Console / domain launcher (Phase 19a)
- `docs/desktop-integration.md` — GUI app forwarding (Phase 19b)
- `docs/live-os.md` — Live OS / USB boot
- `docs/openclaw.md` — OpenClaw AI agent framework
- `docs/claude-code-workflow.md` — Development workflow with Claude Code
- `docs/mcp-services.md` — MCP services architecture
- `docs/golden-images.md` — Pre-built OS images
- `docs/disposable.md` — Disposable containers
- `docs/tor-gateway.md` — Tor gateway routing
- `docs/llm-sanitizer.md` — LLM sanitization proxy (Phase 39)
