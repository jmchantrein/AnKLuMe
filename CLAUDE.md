# AnKLuMe

A declarative infrastructure compartmentalization framework.
QubesOS-like isolation using native Linux kernel features (KVM/LXC),
calmly orchestrated by you, Ansible, Incus and Molecule.

## Project identity

- **Type**: Infrastructure-as-Code (not a web app, not an API)
- **Primary language**: YAML (Ansible roles + playbooks) + Python (PSOT generator)
- **Target audience**: sysadmins, teachers, power users
- **License**: Apache 2.0

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
make snapshot      # Snapshot all instances
make help          # List all commands
```

## Validators — every file type has its checker

| Tool | Scope | Config |
|------|-------|--------|
| `ansible-lint` | `roles/`, `*.yml` playbooks | `.ansible-lint` (production profile) |
| `yamllint` | All `*.yml` / `*.yaml` files | `.yamllint.yml` |
| `shellcheck` | All `*.sh` files in `scripts/` | Inline directives if needed |
| `ruff` | All `*.py` files | `pyproject.toml` |
| `markdownlint` | All `*.md` files (optional) | `.markdownlint.yml` |

**Rule**: No file escapes validation. `make lint` chains all validators.
CI must pass all of them before merge.

## Ansible code conventions

- Task names: `RoleName | Description with initial capital`
- Role-internal variables: prefix with `<role_name>_` (e.g. `incus_networks_declared`)
- FQCN mandatory: `ansible.builtin.command`, not `command`
- Explicit `changed_when` on all `command`/`shell` tasks
- No `ignore_errors` — use `failed_when: false` when needed
- All code, comments, docs, and prompts in English
- A `README_FR.md` is maintained as a French translation of `README.md`

## Quality gates

- `ansible-lint` production profile, 0 violations
- `yamllint` clean
- `shellcheck` clean on all shell scripts
- `ruff` clean on all Python files
- `--syntax-check` passes
- Molecule tests for each infra role
- `pytest` for the generator (`scripts/generate.py`)
- Review via `.claude/agents/reviewer.md` before committing

## Context files

For details, read these files with `@path`:
- @docs/SPEC.md — Full specification (architecture, formats, roles)
- @docs/ARCHITECTURE.md — Architecture decisions (ADR-style)
- @docs/ROADMAP.md — Implementation phases and priorities
