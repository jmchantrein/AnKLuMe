# Vision: AI Integration in anklume

**Date**: 2026-02-23
**Status**: Draft — consolidation of design discussions, pending ROADMAP formalization

## 1. Context and motivation

anklume provides QubesOS-like compartmentalization using Incus and Ansible.
Today, AI tools (Claude Code, Ollama, OpenClaw) are used during development
but are not treated as first-class citizens of the compartmentalized
infrastructure. This document proposes a vision where AI is integrated
into anklume with the same isolation guarantees as everything else.

Three converging needs drive this vision:

1. **Development workflow**: Claude Code + local GPU should work together
   seamlessly, without a complex proxy middleware.
2. **Personal/professional assistant**: An always-on AI agent (OpenClaw)
   that lives inside the infrastructure, monitors it, and respects domain
   boundaries.
3. **Confidentiality**: When AI queries leave the local perimeter (cloud
   LLM APIs), sensitive infrastructure data must be anonymized. This is
   critical for professional environments where network topology, hostnames,
   and client data must never reach third-party servers.

## 2. Design principles

1. **Local by default, cloud by exception.** The local GPU handles 80-90%
   of AI tasks. Cloud LLMs intervene only when reasoning complexity exceeds
   local model capabilities.
2. **Isolation is structural, not applicative.** Security boundaries are
   enforced by Incus network bridges and nftables rules, not by application-
   level allow/deny lists (which have documented bypass bugs).
3. **AI is a domain citizen.** An AI instance (OpenClaw, Claude Code) in
   domain `pro` sees only domain `pro`. It cannot access `perso` or
   `sandbox` — the network prevents it, not a configuration flag.
4. **Sanitization protects what leaves.** Data stays raw inside the local
   perimeter. Anonymization applies only when a request exits toward a
   cloud API. The proxy sits at the boundary, not inside each container.
5. **Human controls escalation.** Automatic escalation from local to cloud
   is limited to deterministic, task-type-based routing. Confidence-score-
   based escalation is explicitly rejected as unreliable.

## 3. Three-layer architecture

### Layer 1: Development workflow (Claude Code)

The developer's daily tool. No OpenClaw involved.

| Component | Role |
|---|---|
| **Claude Code** | Primary orchestrator (terminal/IDE) |
| **claude-code-router** | Routes background tasks to Ollama automatically via `ANTHROPIC_BASE_URL` |
| **mcp-ollama-coder** | MCP tools for explicit delegation to local GPU (generate, review, fix, test) |
| **LLM sanitizer** (optional) | Anonymizes data when Claude Code talks to cloud API |

Since Ollama v0.14 (January 2026), Ollama implements the Anthropic Messages
API natively. Combined with `claude-code-router`, this solves the original
problem (using local GPU from Claude Code) without any custom proxy.

The existing `mcp-anklume-dev.py` proxy is retired in this vision. Its
useful MCP tools (incus_exec, git operations, etc.) can be preserved as
a lightweight MCP server without the OpenAI-compatible routing, session
management, brain switching, and credential forwarding that made it complex.

### Layer 2: Per-domain AI assistant (OpenClaw)

An always-on agent that lives inside the infrastructure.

**Key change: one OpenClaw instance per domain, not centralized.**

```
Domain pro       -> OpenClaw "pro"      (trust: trusted)
  - Sees only pro containers and network
  - Mode: local-first (Ollama, cloud fallback)
  - Heartbeat: monitors pro services
  - Channel: Telegram (or Signal, WhatsApp...)

Domain perso     -> OpenClaw "perso"    (trust: trusted)
  - Sees only perso containers and network
  - Mode: local (Ollama only, nothing leaves)
  - Heartbeat: personal reminders, perso service health
  - Channel: Telegram

Domain sandbox   -> OpenClaw "sandbox"  (trust: disposable)
  - Tests risky skills, untrusted prompts
  - Mode: local (never cloud for sandbox)
  - No heartbeat (ephemeral)
  - If compromised, destroy and recreate
```

Each instance communicates directly with Ollama (auto-discovery on the
GPU container's IP) for local mode. No intermediate proxy needed.

**OpenClaw features to exploit (currently unused):**

| Feature | Use case |
|---|---|
| Heartbeat (every 30 min) | Proactive infrastructure monitoring per domain |
| Cron | Scheduled reports, maintenance tasks, snapshot triggers |
| Memory + RAG | Accumulate operational knowledge per domain (SQLite hybrid search) |
| Multi-agent | Infra monitoring agent + personal assistant agent |
| Skills (custom) | anklume-specific automation skills (NOT ClawHub third-party, except in sandbox) |
| Sessions spawn | Isolated sub-tasks without polluting main session |

**Heartbeat monitoring pattern:**

Every heartbeat cycle, the per-domain OpenClaw agent:

1. Runs probes (container status, disk space, service health, network scan diff)
2. Feeds results to Ollama local (triage: normal / suspect / critical)
3. If anomaly detected -> alerts user via Telegram + optional cloud escalation
4. If routine -> logs to memory, no notification

This implements the "two-level IDS" pattern from academic research: lightweight
continuous monitoring locally, heavy analysis only on escalation.

### Layer 3: LLM sanitization proxy

A service in the anklume domain that anonymizes infrastructure data before
it reaches any cloud LLM API.

**Architecture:**

```
Container in domain pro
  -> LLM request (raw data: real IPs, hostnames, FQDNs)
      -> anklume-sanitizer (domain anklume, admin zone)
          -> Detects and tokenizes:
             - IPs (RFC1918 ranges, client ranges)
             - Hostnames, FQDNs (*.internal, *.corp, *.local)
             - Service names, database names
             - Credentials, tokens, API keys
             - Network topology indicators
          -> Forwards anonymized content to cloud API
          -> Receives response
          -> De-tokenizes response (token -> real value)
          -> Returns to requesting container
          -> Logs everything locally (audit trail)
```

**Why IaC is ideal for sanitization:** In Ansible playbooks, almost everything
sensitive is identifiers (machine names, IPs, ports, domains), not the logic
itself. A nginx template is the same whether the server is called
`prod-web-01.acme.corp` or `server_A`. Anonymization degrades response
quality very little for this use case.

**Candidate implementations** (to evaluate, not build from scratch):

| Project | Language | Strengths |
|---|---|---|
| LLM Sentinel | Go | 80+ PII types, Anthropic support |
| LLM Guard | Python | NER-based (BERT), token vault |
| Privacy Proxy (Ogou) | Python | 30+ regex patterns, zero-trust |

None of these understand IaC-specific data (Incus project names, bridge names,
anklume addressing convention IPs). anklume would add IaC-specific detection
patterns on top of a proven base.

**Transparent integration:** The sanitizer exposes an Anthropic-compatible
endpoint. Containers reach it via `ANTHROPIC_BASE_URL=http://anklume-sanitizer:8080`.
Claude Code, OpenClaw, or any tool that supports `ANTHROPIC_BASE_URL` works
without modification.

## 4. infra.yml integration

### New domain-level fields

```yaml
domains:
  pro:
    trust_level: trusted
    ai_provider: local-first       # local | cloud | local-first
    ai_sanitize: true              # false | true (= cloud-only) | always
    machines:
      pro-dev:
        type: lxc
        roles: [base_system]
      pro-gateway:
        type: lxc
        roles: [base_system, network_gateway]
```

### ai_provider

Controls where LLM requests from this domain are routed.

| Value | Behavior |
|---|---|
| `local` | All requests go to Ollama. Nothing leaves the machine. |
| `cloud` | All requests go to the cloud API (via sanitizer if `ai_sanitize` is set). |
| `local-first` | Ollama handles the request. If the task type requires cloud-level reasoning, falls back to cloud (via sanitizer if `ai_sanitize` is set). |

Default: `local` (safe by default — nothing leaves unless explicitly configured).

### ai_sanitize

Controls whether LLM requests are anonymized before leaving the local
perimeter.

| Value | Behavior |
|---|---|
| `false` | No sanitization. Use for sandbox, personal, or local-only domains. |
| `true` | Sanitize when the request goes to a cloud API. Local requests are raw. This is the default when `ai_provider` is `cloud` or `local-first`. |
| `always` | Sanitize even local requests. For strict compliance/audit requirements. |

Default: `false` when `ai_provider: local`, `true` otherwise.

The sanitizer logs every cloud-bound request with: anonymized text sent,
response received, token-to-value mapping (stored locally), timestamp,
source domain. This audit trail proves that AI tools did not expose
sensitive data — useful for client contracts and compliance.

### ai_provider escalation strategy (local-first mode)

Escalation from local to cloud uses two mechanisms:

**1. Static routing by task type (for automated tasks — heartbeat, cron):**

| Task type | Routing | Reason |
|---|---|---|
| Parsing, reformatting, inventory | Local | Structural, no reasoning needed |
| Alert triage (normal/suspect) | Local | Simple classification |
| Capture/scan summary | Local | Condensation, not analysis |
| Code/playbook generation | Local | 32B coder models are good enough |
| Multi-source correlation | Cloud | Long-chain reasoning required |
| Forensics, incident analysis | Cloud | Deep protocol knowledge needed |
| Architecture evaluation | Cloud | Multi-criteria expert judgment |
| Reports for management/clients | Cloud | Nuanced writing required |

**2. Explicit user escalation (for conversations):**

The user says "escalade" / "analyze this deeper" / "ask Claude". The agent
switches from local to cloud for that specific exchange.

**Explicitly rejected: confidence-score-based auto-escalation.** Local models
(7-32B) are unreliable at estimating their own confidence. A model that
hallucinates does so with conviction. Automatic escalation based on self-
reported uncertainty would produce both false positives (unnecessary cloud
calls) and false negatives (confident hallucinations staying local).

## 5. Naming conventions

### Domain anklume (admin zone)

Infrastructure services that need cross-domain visibility live in the
anklume domain. Container names are prefixed `anklume-`:

| Service | Container name | Role |
|---|---|---|
| Admin/controller | `anklume-instance` | Ansible, git, orchestration (exists) |
| Firewall | `anklume-firewall` | nftables cross-domain (currently `sys-firewall`, to rename) |
| Monitoring | `anklume-monitoring` | Infrastructure metrics, alerting |
| Backup | `anklume-backup` | Cross-domain snapshot management |
| Sanitizer | `anklume-sanitizer` | LLM anonymization proxy |

**Placement rule:** If a service needs to see beyond its own domain to
function, it goes in anklume. If it is a service accessed by other domains
via network_policies, it gets its own domain.

### Domain shared (shared services)

Services accessible by multiple domains via network_policies. They do not
need cross-domain visibility — other domains connect to them, not the
reverse.

```yaml
  shared:
    trust_level: trusted
    machines:
      shared-print:
        type: lxc
        roles: [base_system, cups_server]
      shared-dns:
        type: lxc
        roles: [base_system, dns_cache]
```

Container names are prefixed `shared-`, consistent with the convention
that containers are prefixed by their domain name (`pro-dev`, `perso-desktop`,
`anklume-instance`, `shared-print`).

### Migration notes

- `sys-firewall` -> `anklume-firewall` (code change in generator)
- `sys-print` example -> `shared-print` in domain `shared`
- The `sys-` prefix is retired. Services are either in `anklume` (admin
  infrastructure) or in `shared` (user-facing shared services).

## 6. Network inspection and security monitoring

### The three-level pipeline

LLM-assisted network inspection follows a strict pipeline where each
level adds intelligence but also risk (data exposure):

```
LEVEL 1 — Collection (no LLM)
  tcpdump, tshark, nmap, SNMP walks, LLDP/CDP
  Output: PCAP files, XML results, MIB tables, neighbor data
      |
      v
LEVEL 2 — Local triage (LLM local, 100% confidential)
  Ollama (llama3:8b, qwen2.5-coder:32b, mistral:7b)
  Tasks: parsing, inventory, triage, summaries, basic alerts
  Cost: zero (hardware amortized), no rate limit, 24/7
  Triggered by: OpenClaw heartbeat (every 30 min) or cron
      |
      | Only cases requiring advanced reasoning
      | (+ data anonymized by sanitizer)
      v
LEVEL 3 — Deep analysis (cloud LLM, via sanitizer)
  Claude Sonnet/Opus via API
  Tasks: forensics, multi-source correlation, architecture
  evaluation, incident reports, adversarial reasoning
  Triggered by: explicit user request or task-type routing
```

### What local models handle well

- Parse and structure raw output from nmap, SNMP, LLDP into JSON
- Generate inventories from scan data
- Compare current vs reference inventory (detect changes)
- Produce simple diagrams (Mermaid, DOT/Graphviz)
- Triage anomalies (normal / investigate / critical)
- Summarize captures (top talkers, protocol distribution)
- Basic alerts (unusual port, unauthorized IP range)
- Continuous monitoring loop (no cost, no rate limit)

### What requires cloud models

- Reconstruct intrusion timelines from multiple captures and logs
- Detect subtle corruptions (MitM timing, DNS spoofing TTL)
- Cross-reference network data + system logs + application events
- Analyze rare protocols (SCADA/Modbus, BGP, TLS 1.3 extensions)
- Write structured forensic reports for non-technical audiences
- Adversarial reasoning (identify evasion techniques)
- Evaluate architecture against best practices (segmentation,
  redundancy, single points of failure) across 50+ devices

### What LLMs do NOT replace

- IDS/NIDS (Suricata, Zeek, Snort) for real-time high-throughput detection
- SIEM (Splunk, Elastic) for large-scale correlation over months of logs
- Vulnerability scanners (Nessus, OpenVAS) for systematic CVE detection
- Human analyst judgment — the LLM guides investigation, it does not conclude

### Anonymization specifics for network data

Network captures are significantly more sensitive than IaC code. The
sanitizer must handle:

| Data type | Sensitivity | Anonymization method |
|---|---|---|
| Internal IPs and ranges | High | Replace with consistent fake IPs |
| Topology (who talks to who) | High | Anonymize endpoints, preserve structure |
| Services and versions | High | Generalize versions, keep service type |
| Internal DNS names | High | Replace with generic names |
| Application content (HTTP, etc.) | Critical | Never send payload, metadata only |
| Cleartext credentials | Critical | Strip entirely |
| Communication patterns | Medium | Preserve timing, anonymize endpoints |
| Traffic volumes | Low | Pass through (aggregated stats) |

## 7. Competitive landscape

### No existing framework combines all four features

As of February 2026, no IaC framework, platform, or open-source project
combines:

1. Declarative compartmentalized infrastructure (isolated domains with
   network enforcement)
2. Integrated AI assistant (cloud and local, infrastructure-topology-aware)
3. LLM sanitization proxy (IaC-specific anonymization, not just generic PII)
4. Per-domain AI isolation (different AI instances per security zone)

**Partial overlaps exist:**

| Tool | Compartmentalized | AI integrated | LLM sanitization | Per-domain AI |
|---|---|---|---|---|
| QubesOS | Yes (best in class) | No | No | No |
| Pulumi Neo | No (cloud resources) | Yes | No | No |
| Spacelift Intent | No | Yes | No | No |
| HashiCorp Vault+Terraform MCP | No | Partial | Partial (secrets) | No |
| Ansible Lightspeed | No | Yes (code gen) | Partial (PII) | No |
| LLM Guard / Sentinel | No | No | Yes (generic PII) | No |
| Proxmox MCP ecosystem | Partial | Yes | No | No |
| **anklume (this vision)** | **Yes** | **Yes** | **Yes** | **Yes** |

**Challengers to watch:**

- **Pulumi Neo**: evolving toward agentic infrastructure with governance.
  If it adds LXC/KVM, isolation enforcement, and sanitization, overlap grows.
- **HashiCorp Vault MCP + Terraform MCP**: already has RAG anonymization
  for secrets. If extended to topology data, partial overlap.
- **Proxmox MCP ecosystem** (6+ projects): gives LLMs access to Proxmox
  APIs, but without isolation enforcement or AI access policies.

The combination is unique today, but the landscape moves fast.

### anklume's strongest differentiators

- **Feature 4 (per-domain AI isolation)** is genuinely novel. No tool
  provides different AI instances per security zone with network-enforced
  boundaries.
- **Feature 3 applied to infrastructure topology** (not just generic PII)
  is unaddressed. No sanitization tool understands Incus project names,
  bridge names, or zone-based addressing conventions.
- The combination of features 1+2 (compartmentalized infra + AI that
  respects compartments) is what makes features 3+4 possible. Without
  structural isolation, application-level AI isolation is theater.

## 8. Security considerations

### Defense in depth (from IaC confidentiality report)

No single layer is sufficient. The recommended approach combines:

1. **Context isolation** (essential): dedicated IaC repos with zero secrets,
   zero real names. Anonymized inventories for AI-assisted work.
2. **LLM sanitization proxy** (strongly recommended): tokenize IPs, FQDNs,
   service names, credentials before cloud API calls.
3. **Network isolation** (recommended): bastion SSH with ProxyJump. AI
   tools see aliases, never real topology.
4. **Process discipline** (essential): human review before any apply/deploy.
   Document conventions in CLAUDE.md. Audit proxy logs regularly.

### Known risks

| Risk | Severity | Mitigation |
|---|---|---|
| Infrastructure topology leak | High | Sanitization proxy + context isolation |
| Deny rules bypass (Claude Code) | High | Structural isolation (Incus), not app-level rules |
| Cloud provider data retention | Medium | Sanitization (provider sees only anonymized data) |
| Prompt injection via IaC content | Medium | Human review + sandboxed execution |
| Permission inheritance | High | Dedicated OS user per domain, restricted permissions |

### ClawHub third-party skills

The ClawHavoc incident (February 2026) found 341-1,184 malicious skills
in ClawHub. Third-party skills must be treated as untrusted code.

**Policy:** ClawHub skills are installed ONLY in sandbox domains
(`trust_level: disposable`). Production domains use custom skills
defined in the anklume repository and deployed via Ansible templates
(ADR-036 pattern).

## 9. What this vision retires

| Component | Status | Replacement |
|---|---|---|
| `mcp-anklume-dev.py` (1200-line proxy) | Retire | claude-code-router + mcp-ollama-coder + per-domain OpenClaw |
| Centralized OpenClaw in ai-tools | Retire | Per-domain OpenClaw instances |
| Brain switching via JSON modification + systemd restart | Retire | Direct Ollama connection per instance |
| Claude Code sessions managed by proxy | Retire | Claude Code runs standalone with claude-code-router |
| Credential bind-mount from host to anklume-instance | Retire | Claude Code authenticates normally on host |
| `sys-` prefix for infrastructure services | Retire | `anklume-` prefix in admin domain, `shared-` in shared domain |

## 10. What this vision preserves

| Component | Status | Reason |
|---|---|---|
| ADR-036 (reproducible templates) | Keep | Excellent pattern for per-domain OpenClaw instances |
| `openclaw_server` Ansible role | Keep + enrich | Extend for multi-instance per-domain deployment |
| Incus network isolation | Keep | Foundation of all AI isolation guarantees |
| `mcp-ollama-coder` MCP tools | Keep | Claude Code delegates to local GPU via MCP |
| `ai_access_policy: exclusive` | Keep | GPU/VRAM isolation between domains |
| OpenClaw SOUL.md exception | Keep | Personality persists, not framework-managed |

## 11. Implementation phases (to formalize in ROADMAP)

Rough ordering, to be refined:

1. **claude-code-router integration**: documentation + optional role,
   replaces the proxy for development workflow.
2. **Per-domain OpenClaw**: extend `openclaw_server` role, support
   multiple instances, one per domain in infra.yml.
3. **OpenClaw heartbeat + cron exploitation**: custom skills for
   infrastructure monitoring per domain.
4. **LLM sanitization proxy**: evaluate LLM Sentinel / LLM Guard,
   add IaC-specific patterns, deploy as `anklume-sanitizer`.
5. **Network inspection integration**: MCP Wireshark + local triage
   pipeline + cloud escalation through sanitizer.
6. **Naming migration**: `sys-firewall` -> `anklume-firewall`, `sys-print`
   -> `shared-print` in domain `shared`.
7. **`ai_provider` and `ai_sanitize` in infra.yml**: generator support,
   validation, documentation.

## 12. Open questions

1. **Escalation threshold refinement**: The static task-type routing is
   the baseline. Can we improve it with lightweight heuristics (response
   length, token count, repetition detection) without falling into the
   confidence-score trap?

2. **OpenClaw MCP client support**: PR #21530 is open. When merged, it
   enables OpenClaw to consume MCP tools natively — potentially replacing
   the need for custom tool implementations inside OpenClaw.

3. **Multi-agent within a domain**: Should a domain have one OpenClaw
   agent (doing everything) or two (one for monitoring, one for personal
   assistance)? The multi-agent feature supports this but adds complexity.

4. **Sanitizer performance**: Adding a proxy in the LLM request path adds
   latency. Benchmarking is needed to ensure the overhead is acceptable
   for interactive use (target: < 200ms added latency).

5. **OpenClaw updates**: OpenClaw releases multiple times per week. The
   Ansible role pins a version or uses `@latest`. A strategy for safe
   updates is needed (test in sandbox domain first?).

6. **Gateway container for client networks**: When a domain contains a
   gateway to external networks (VPN/VLAN to client infrastructure), the
   domain-level `ai_sanitize: true` covers all containers including the
   gateway. Should we support additional client-specific anonymization
   patterns configurable in infra.yml?
