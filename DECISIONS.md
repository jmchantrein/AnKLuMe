# DECISIONS.md -- Autonomous Implementation Decisions

Decisions made during autonomous implementation.
Reviewed 2026-02-25. Status per section below.

---

## Phase 33: Student Mode and Internationalization

### Architecture: Python helper for bilingual help

Rather than embedding complex shell logic or awk/sed in the Makefile,
bilingual help is rendered by `scripts/help-i18n.py`. The Makefile
dispatches to this script when `ANKLUME_MODE` is `student` or `dev`,
and uses the native printf-based help for `user` mode (no Python
dependency for the default path).

### Mode file location: `~/.anklume/mode`

Consistent with the existing `~/.anklume/` directory used by telemetry
(`~/.anklume/telemetry/`) and lab progress (`~/.anklume/labs/`).

### i18n directory: `i18n/fr.yml`

A flat YAML file (target: "description") was chosen over nested
structures or gettext `.po` files. Rationale:
- YAML is the project's native format (consistency)
- Flat structure is trivially auditable (one grep shows coverage)
- No build step needed (no `.po` -> `.mo` compilation)
- Easy to add new languages: `i18n/de.yml`, `i18n/es.yml`, etc.

### ANKLUME_LANG override

The `ANKLUME_LANG` env var allows forcing a language independent of
mode. This is useful for CI (always English) or for users who want
French help without the student mode restrictions.

### Matrix prefix: SM-* (Student Mode)

Used `SM-*` to avoid collision with existing prefixes.

---

## Phase 38: OpenClaw Heartbeat Monitoring

### D-057: Heartbeat templates as OpenClaw workspace files, not systemd services

**Problem**: Phase 38 requires monitoring for per-domain OpenClaw
instances. The monitoring could be implemented as systemd timers
running inside the container, or as OpenClaw workspace instructions
that the agent executes via its built-in cron/skill system.

**Choice**: Implement as OpenClaw workspace files (HEARTBEAT.md,
CRON.md, skills/) deployed via Jinja2 templates. The agent uses
OpenClaw's native cron system to schedule checks, not systemd timers.

**Status**: approved

---

### D-058: Domain-scoped monitoring only (no cross-domain checks)

**Choice**: Each agent monitors only its own domain's Incus project.
Cross-domain monitoring requires explicit network policies and is
left to the admin domain's agent (if any).

**Status**: approved

---

### D-059: Heartbeat tasks split into separate included file

**Choice**: Create `tasks/heartbeat.yml` and include it from `main.yml`
via `ansible.builtin.include_tasks`. This keeps each file under 200
lines and maintains single-responsibility.

**Status**: approved

---

## Phase 37: OpenClaw Instances — KISS Simplification

**Review outcome**: The original per-domain approach (openclaw: true
directive, auto-creation, domain-scoped templates) was rejected in
favor of the KISS principle. OpenClaw machines are declared like any
other machine.

### Changes implemented after review

- Removed `openclaw: true` domain-level field from SPEC and generator
- Removed `_enrich_openclaw()` auto-creation function
- Removed `domain_openclaw` from group_vars propagation
- Removed `openclaw_server_domain` and `openclaw_server_instance_name`
  variables from role defaults
- Simplified all templates (removed domain conditionals)
- Service name: always `openclaw.service` (each container is isolated)
- Templates now use standard `domain_name` and `incus_project` from
  group_vars instead of role-specific variables
- Agent identity (name, emoji) defaults to empty — users configure
  per instance. SOUL persisted via persistent_data volumes.
- Generator warns if openclaw_server role present without network_policy

### ADR-043 (superseded)

ADR-043 was rewritten to document the KISS approach. See ARCHITECTURE.md.

### Future directions (noted from review)

- Docker Compose-like CLI refonte (`anklume volume ls`, `anklume domain ls`)
- Device naming convention to be decided with CLI refonte

---

## Phase 36: Naming Convention Migration

### Name mapping

| Old name | New name | Context |
|----------|----------|---------|
| `sys-firewall` (auto-created) | `anklume-firewall` | Already done (prior commit) |
| `sys-print` (container) | `shared-print` | Container in `shared` domain |
| `print-service` (domain) | `shared` | Domain for user-facing services |
| `examples/sys-print/` | `examples/shared-services/` | Example directory |

### Script naming

The script `scripts/cups-setup.sh` (renamed from `sys-print.sh` per
user review) uses a descriptive name reflecting its function. Its
examples and usage messages reference `shared-print` as the default
instance name.

### Decision: `shared` domain in canonical infra.yml

The `shared` domain is NOT added to the canonical `infra.yml.example`.
Rationale: the canonical infra.yml is intentionally minimal (anklume +
work domains). The `shared` domain is documented in SPEC.md and
demonstrated in `examples/shared-services/`. Users add it when needed.

### `sys-` references NOT changed and why

| File | Reference | Reason |
|------|-----------|--------|
| `scripts/generate.py:941` | `"sys-firewall"` | Backward compatibility check |
| `tests/test_generate.py:541` | `sys-firewall` | Tests backward compatibility |
| `tests/test_generate_internals.py:1903` | `sys-firewall` | Tests backward compatibility |
| `docs/SPEC.md:402` | `sys-firewall` | Documents backward compatibility |
| `scripts/cups-setup.sh` (filename) | `cups-setup.sh` | Renamed per user review |
| `tests/test_cups_setup.py` (filename) | `test_cups_setup.py` | Tests the tool |

---

## Phase 20g: Persistent Data & Flush Protection

### ADR numbering
- ADR-040 was already taken (credits/attribution). Used ADR-041 for
  persistent_data and ADR-042 for flush protection.

### persistent_data device prefix: `pd-` (temporary)
- Chose `pd-` prefix to avoid collisions with `sv-` (shared volumes)
  and user-declared devices.
- **Review note**: prefix naming deferred to future Docker Compose-like
  CLI refonte. Current `pd-`/`sv-` are temporary.

### persistent_data source path convention
- Source: `<persistent_data_base>/<domain_name>/<machine_name>/<volume_name>`
- Default base: `/srv/anklume/data`.
- **Review note**: domain added to path hierarchy for better organization.

### shift: true by default on persistent_data
- Mirrored the shared_volumes default.

### Flush protection uses FORCE env var (not --force flag)
- The `FORCE` env var is a separate concept: bypass delete protection.

---

## Phase 35: Development Workflow Simplification

### What was archived (moved to scripts/archive/)

| File | Original location | Reason |
|------|-------------------|--------|
| `mcp-anklume-dev.py` | `scripts/` | MCP proxy retired per Phase 35 roadmap |
| `mcp-anklume-dev.service` | `scripts/` | Systemd unit for the retired proxy |
| `sync-claude-credentials.sh` | `host/boot/` | Credential sync timer no longer needed |

### What was NOT extracted as a new MCP server

All 21+ tools in the proxy were analyzed. None justify extraction because
Claude Code provides native equivalents. `mcp-ollama-coder` covers local
LLM delegation.

### Credential references

The credential bind-mount device in OpenClaw's Incus profile was NOT
removed (still needed by OpenClaw). Only the sync timer was archived.

---

## Phase 32: Makefile UX and Robustness

### Backward compatibility approach
- `ollama-dev`: Added as a Make alias target that depends on `llm-dev`.

---

## Phase 30: Educational Lab Framework

### Lab framework split into runner + library
Split into `scripts/lab-runner.sh` (commands, dispatch, 190L) and
`scripts/lab-lib.sh` (shared helpers: YAML parsing, progress tracking,
125L). Follows the existing pattern (`snap.sh`, `live-os-lib.sh`).

### Three labs instead of five
Implemented labs 01 (first deploy), 02 (network isolation), 03
(snapshots). Labs 04 (GPU) and 05 (security audit) deferred — they
require running infrastructure. Three labs fully exercise the framework.

### Progress tracking via YAML in ~/.anklume/labs/
YAML files in `~/.anklume/labs/<lab-id>/progress.yml`. Consistent with
YAML-first approach. `~/.anklume/` already used by telemetry.

### Inline Python for YAML parsing in shell
Python heredoc (`python3 - "$arg" <<'PYEOF'`) — consistent with
disp.sh, console.sh, ai-switch.sh pattern. PyYAML already a dependency.

### Matrix prefix: ED-* (not EL-*)
Used `ED-*` for educational_labs to avoid collision with existing
`EL-*` (ephemeral_lifecycle).

---

## Phase 39: LLM Sanitization Proxy

### ai_provider / ai_sanitize as domain-level fields

Domain-level fields (`ai_provider`, `ai_sanitize`) because different
domains have fundamentally different sensitivity levels. An `admin`
domain should always sanitize cloud requests, while a `disposable`
sandbox may not need it.

### Default ai_sanitize based on ai_provider

Auto-default `ai_sanitize: true` when `ai_provider` is `cloud` or
`local-first`. Auto-default `false` for `local`. Safe by default,
explicit opt-out.

### Pattern-based detection, not ML-based

Regex patterns are predictable, auditable, have zero false positives
from model drift, and require no GPU. IaC identifiers follow strict
naming conventions (ADR-038 IP scheme, Incus naming) ideal for regex.

### ai_sanitize accepts "always" as a third value

Accept `"always"` as a third value (string, not boolean) for users who
need sanitization even for local requests (compliance, shared infra).

---

## Phase 40: Network Inspection and Security Monitoring

### 3-level pipeline architecture (Collection, Diffing, Triage)

Structured network inspection as a three-level pipeline rather than a
single monolithic scan-and-report tool. Level 1 collects raw data
(nmap/tshark), Level 2 diffs against baselines, Level 3 uses LLM for
classification. This separation allows each level to be used
independently: an operator can run nmap-diff.sh without OpenClaw, or
an agent can classify pre-existing scan output without running a scan.

### nmap-diff.sh as standalone script, not Ansible role

Following ADR-013 (snapshot) and D-050 (disposable) precedent: network
scans are imperative one-shot operations, not declarative reconciliation.
A shell script wrapping nmap + diff is simpler and more composable than
an Ansible role.

### Network scan disabled by default

`openclaw_server_network_scan_enabled: false` by default because nmap
scanning requires explicit installation of nmap in the container and may
trigger security alerts on some networks. The operator must consciously
enable it.

### Anonymization patterns for network data

Added MAC address, interface name, ARP entry, and nmap report patterns
to the llm_sanitizer. Network scan output is rich in infrastructure
identifiers that should not leak to cloud LLMs.

---
