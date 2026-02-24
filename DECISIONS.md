# DECISIONS.md -- Autonomous Implementation Decisions

Decisions made during autonomous implementation.
Review and approve/decline each section.

---

## Phase 37: Per-Domain OpenClaw Instances

### ADR-043 numbering

ADR-043 was the next available number after ADR-042 (flush protection).

### Auto-creation pattern

Followed the exact same pattern as `_enrich_firewall()` (anklume-firewall
auto-creation): check if user declared the machine, if not, auto-create
with sensible defaults. The enrichment runs after validation but before
generation, and auto-created machines get IPs via `_enrich_addressing()`.

### Service name: `openclaw-<domain>.service`

Per-domain instances use `openclaw-<domain>` as the systemd service name
(e.g., `openclaw-pro.service`). The centralized instance (no domain set)
keeps the legacy `openclaw.service` name for backward compatibility.

### Template changes are additive

All template changes use `{% if openclaw_server_domain | default('') %}`
conditionals. When `openclaw_server_domain` is empty (centralized mode),
templates render identically to before. No breaking change.

### group_vars propagation

`domain_openclaw: true` is propagated to group_vars only when `true`.
When `false` or absent, the key is omitted (not set to `false`). This
matches the pattern used by `domain_trust_level` and other optional
fields.

### No network_policies auto-creation for openclaw

Unlike `ai_access_policy: exclusive` which auto-creates network policies,
per-domain OpenClaw instances do not auto-create network policies to the
LLM backend. The user must explicitly declare `network_policies` if
cross-domain AI access is needed. This is intentional: the default
posture is full isolation.

### Questions for review

1. Should `openclaw_server_agent_name` be auto-scoped per domain
   (e.g., `Ada-pro`, `Ada-perso`)? Currently defaults to `Ada` for all.
2. Should the generator warn if `openclaw: true` but no LLM backend
   (gpu-server / ollama_server) is reachable from the domain?
3. Should the SPEC examples show the per-domain pattern as the primary
   example, or keep the centralized pattern as primary?

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

The script `scripts/sys-print.sh` retains its filename. It is a tool
(like `snap.sh`), not a container. Its examples and usage messages now
reference `shared-print` as the default instance name.

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
| `scripts/sys-print.sh` (filename) | `sys-print.sh` | Tool name, not container name |
| `tests/test_sys_print.py` (filename) | `test_sys_print.py` | Tests the tool |

---

## Phase 20g: Persistent Data & Flush Protection

### ADR numbering
- ADR-040 was already taken (credits/attribution). Used ADR-041 for
  persistent_data and ADR-042 for flush protection.

### persistent_data device prefix: `pd-`
- Chose `pd-` prefix to avoid collisions with `sv-` (shared volumes)
  and user-declared devices.

### persistent_data source path convention
- Source: `<persistent_data_base>/<machine_name>/<volume_name>`
- Default base: `/srv/anklume/data`.

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
