# Security Audit — Operational Model

**Date**: 2026-02-26
**Scope**: Architecture, trust boundaries, operational flows, isolation model.
Not a code-level audit (no line-by-line review of implementations).
**Methodology**: Documentation review (SPEC, ARCHITECTURE, ADRs, operational
docs) cross-referenced with the declared threat model.

---

## Executive Summary

anklume's operational model is fundamentally sound. The architecture follows
defense-in-depth principles with multiple isolation layers (Incus namespaces,
nftables, Incus projects, socket-based management). The trust-zone IP scheme
(ADR-038) and the separation of control plane (Incus socket) from data plane
(network bridges) are strong design choices.

However, several architectural patterns introduce risks that range from
**medium** to **critical** depending on the deployment context. The findings
below are ordered by severity.

---

## FINDING-01: Incus Socket = God Mode (CRITICAL)

### Description

`anklume-instance` has the host Incus socket mounted read/write. This socket
provides **unrestricted, unauthenticated root-equivalent access** to the entire
Incus daemon. Any process inside `anklume-instance` that can write to
`/var/run/incus/unix.socket` can:

- Create/delete/modify ANY container or VM across ALL projects
- Execute arbitrary commands as root inside ANY instance (`incus exec`)
- Read/write ANY file in ANY instance (`incus file`)
- Modify network configuration, profiles, storage
- Effectively gain root on the host (via privileged container creation)

### Why It Matters

The entire security model depends on `anklume-instance` being trustworthy.
If this container is compromised (malicious Ansible role, supply chain attack
on a pip dependency, compromised Galaxy role from `roles_vendor/`, or a
vulnerability in the OpenClaw proxy), the attacker bypasses ALL isolation
boundaries instantly.

### Risk Factors

- The OpenClaw proxy (`docs/openclaw.md`) exposes REST API endpoints
  including `/api/incus_exec` and `/api/incus_list` — these are
  network-accessible attack surfaces backed by the all-powerful socket
- Claude Code runs with `bypassPermissions` inside the agent runner,
  and the proxy bridges commands from Telegram messages to infrastructure
- Galaxy roles (`roles_vendor/`) are third-party code executing inside
  the container that has socket access
- `pip install` dependencies (PyYAML, libtmux, mcp, etc.) run in the
  same trust domain as the socket

### Recommendations

1. **READ-ONLY socket where possible**: For operations that only need to
   query state (`incus list`, `incus info`), consider a read-only proxy
   or Incus fine-grained TLS certificates with restricted project scope.
   Incus supports project-confined client certificates since v6.0.
2. **Separate the proxy**: Move the OpenClaw proxy out of `anklume-instance`
   into its own container with a scoped Incus certificate (not the raw
   socket). The proxy only needs `incus exec` on specific instances.
3. **Network segmentation of anklume-instance**: The current model has
   anklume-instance with no special nftables exception (good), but the
   OpenClaw proxy creates a network path from the internet (Telegram) to
   the socket-wielding container. Consider a dedicated network policy
   review for this path.
4. **Audit pip dependencies**: Pin all pip dependencies with hashes in
   `requirements.txt` to prevent supply chain attacks on the container
   that holds the master key.

---

## FINDING-02: OpenClaw Proxy — Internet-to-Infrastructure Bridge (HIGH)

### Description

The `openclaw.md` architecture creates a direct path:

```
Telegram (internet) → OpenClaw (ai-tools project) → proxy (anklume-instance) → Incus socket → ANY container
```

The proxy on `anklume-instance:9090` accepts OpenAI-compatible API calls and
translates them into Claude Code CLI invocations. Claude Code then runs with
tool access including `incus exec` on arbitrary containers. The proxy also
exposes REST endpoints (`/api/incus_exec`, `/api/make_target`, etc.) that
directly interact with infrastructure.

### Why It Matters

- An attacker who compromises the OpenClaw container (which has internet
  access and messaging bridges) can send crafted requests to the proxy
- Prompt injection via Telegram messages could trick Claude Code into
  executing destructive infrastructure commands
- The `--allowedTools` restriction on Claude Code is an application-level
  control, not a kernel-level boundary — it can be bypassed by crafted
  tool-use sequences
- The blocklist for dangerous operations (`flush`, `nftables-deploy`) is
  a deny-list, not an allow-list — new dangerous commands won't be blocked

### Recommendations

1. **Reverse the security model**: Use an allow-list (only known-safe
   operations) instead of a block-list for proxy API endpoints
2. **Authentication on the proxy**: The proxy at `:9090` should require
   authentication (API key, mutual TLS) even for intra-network calls
3. **Rate limiting and request logging**: Log every `incus_exec` call
   with full arguments to an append-only log outside the container
4. **Consider removing `incus_exec` from the proxy**: If the OpenClaw
   agent only needs to manage its own container, scope the proxy to
   that single container rather than exposing cross-container execution

---

## FINDING-03: Credential Bind-Mount with World-Readable Permissions (HIGH)

### Description

From `docs/openclaw.md`:

> **Requirement**: The host credentials file must be world-readable
> (`chmod 644`) because Incus UID mapping maps the host user to
> `nobody:nogroup` inside the container.

Claude Code OAuth credentials (`~/.claude/.credentials.json`) are made
world-readable on the host to allow the container to read them through
the Incus disk device with UID shifting.

### Why It Matters

- Any process on the host can read these credentials
- Any other container with a disk device pointing to the host user's
  home directory can access them
- OAuth tokens for Anthropic Max plan provide access to the Claude API
  with the user's billing account
- The credentials file may contain refresh tokens that grant long-lived
  access

### Recommendations

1. **Use Incus idmap with raw.idmap**: Instead of world-readable
   permissions, configure `raw.idmap` on the container to map the host
   UID to the container's root UID. This allows `0600` permissions on
   the host while the container root can still read the file.
2. **Rotate and scope tokens**: If possible, use a scoped API key
   rather than an OAuth credential file for the proxy service
3. **Mount the credentials read-only with a wrapper**: Inject the
   token via an environment variable rather than a file bind-mount

---

## FINDING-04: LXC Container Escape Surface (MEDIUM)

### Description

The default instance type is LXC (container), not VM. LXC containers share
the host kernel. While Incus provides namespace isolation, seccomp filters,
and AppArmor profiles, the container-to-host kernel attack surface is
significantly larger than VM-to-host.

anklume does enforce some restrictions:
- `security.privileged: true` forbidden without VM nesting (ADR-020)
- `--YOLO` flag required to bypass this restriction
- `security.nesting: true` needed for nested Incus (increases surface)

### Why It Matters

- Kernel vulnerabilities (CVE-2024-1086, CVE-2023-32233, etc.) can be
  exploited from unprivileged containers to gain host root
- `security.nesting: true` containers have a broader syscall surface
- Consumer GPU passthrough (`type: gpu`) exposes the NVIDIA kernel driver
  (a massive attack surface) directly to the container
- The `untrusted` and `disposable` trust levels suggest these containers
  run untrusted code, yet they use LXC by default

### Recommendations

1. **Default to VM for untrusted/disposable trust levels**: The SPEC
   already recommends VMs for stronger isolation. Consider making `type: vm`
   the default when `trust_level: untrusted` or `trust_level: disposable`
2. **Document the LXC threat model explicitly**: Make it clear in the
   onboarding guide that LXC isolation is namespace-based, not
   hardware-based, and that a kernel vulnerability breaks all
   compartmentalization
3. **Harden the seccomp profile**: Consider applying a stricter seccomp
   profile for untrusted containers (Incus supports custom seccomp
   profiles via `raw.seccomp`)
4. **GPU containers are high-risk**: The NVIDIA kernel module is a
   frequent source of CVEs. Document that GPU passthrough in LXC
   significantly increases the attack surface compared to non-GPU
   containers

---

## FINDING-05: VRAM Flush is Best-Effort, Not Guaranteed (MEDIUM)

### Description

The AI-switch mechanism (`docs/ai-switch.md`) flushes GPU VRAM between
domain switches to prevent cross-domain data leakage. The flush process:

1. Stops GPU services (ollama, speaches)
2. Kills remaining GPU compute processes via `nvidia-smi`
3. Attempts `nvidia-smi --gpu-reset` (may not be supported)
4. Restarts GPU services

### Why It Matters

- `nvidia-smi --gpu-reset` is not supported on all GPUs (documented)
- Killing processes frees their VRAM allocations but does not zero the
  memory — the GPU driver may reuse pages without clearing them
- There is no verification step that VRAM was actually cleared
- The `--no-flush` option allows skipping the flush entirely
- Consumer GPUs lack hardware memory isolation (no SR-IOV, no MIG)

### Recommendations

1. **Add a verification step**: After flush, allocate a small CUDA buffer
   and read it to verify it contains zeros (not residual data). This won't
   guarantee all VRAM is clean but provides a smoke test.
2. **Document the limitation clearly**: State that VRAM flush is
   best-effort and does not provide cryptographic guarantees against
   GPU memory forensics
3. **Consider CUDA memset**: Use a small CUDA program that allocates
   and zeros all available VRAM before the new domain's services start
4. **Warn on `--no-flush`**: The flag should be logged with a security
   warning, not silently accepted

---

## FINDING-06: nftables Isolation Depends on br_netfilter (MEDIUM)

### Description

From `docs/network-isolation.md`:

> If `br_netfilter` is not loaded, bridge traffic bypasses nftables entirely.

The entire network isolation model (inter-domain DROP rules) depends on the
`br_netfilter` kernel module being loaded and `net.bridge.bridge-nf-call-iptables`
being set to 1.

### Why It Matters

- If `br_netfilter` is not loaded (which is the default on many Linux
  distributions), all inter-domain traffic is silently allowed
- The nftables rules will appear to be loaded (`nft list table inet anklume`
  shows them) but they have no effect — a false sense of security
- There is no documented check in `make apply` or `make nftables-deploy`
  that verifies `br_netfilter` is loaded
- A kernel upgrade or system reconfiguration could unload the module

### Recommendations

1. **Mandatory pre-flight check**: `make nftables-deploy` and `bootstrap.sh`
   should verify `br_netfilter` is loaded and `bridge-nf-call-iptables=1`,
   failing with a clear error if not
2. **Persist the module**: Add `br_netfilter` to `/etc/modules-load.d/` and
   the sysctl setting to `/etc/sysctl.d/` during bootstrap
3. **Runtime monitoring**: The heartbeat monitoring (Phase 38) should
   periodically verify that `br_netfilter` is still loaded
4. **Document this dependency prominently**: Not just in troubleshooting —
   in the main security model documentation

---

## FINDING-07: Two-Step nftables Creates a Time Window (LOW-MEDIUM)

### Description

nftables rules are generated inside the container (`make nftables`) then
deployed on the host (`make nftables-deploy`). Between `make apply`
(which creates new domains/bridges) and `make nftables && make nftables-deploy`
(which updates isolation rules), there is a window where new bridges exist
without isolation rules.

### Why It Matters

- New domains created by `make apply` are immediately network-reachable
  from other domains until nftables rules are updated
- The documentation mentions running `make nftables && make nftables-deploy`
  after adding domains, but this is a manual step
- The `make apply` target does not automatically regenerate nftables

### Recommendations

1. **Integrate nftables into the apply workflow**: `make apply` should
   automatically run `make nftables` after infrastructure changes
2. **Default-deny on new bridges**: Consider a standing nftables rule
   that drops all inter-bridge traffic for bridges matching `net-*`
   that are not explicitly allowed, rather than enumerating known bridges
3. **Document the time window**: Explicitly state in the security model
   that new domains are not isolated until nftables are redeployed

---

## FINDING-08: Disposable Instances Default to `default` Project (LOW-MEDIUM)

### Description

From `docs/disposable.md`:

> Disposable instances run in the `default` project unless a `--domain` is specified.

### Why It Matters

- The `default` Incus project has no nftables isolation rules (only `net-*`
  prefixed bridges are isolated)
- A disposable instance in the default project shares the default bridge
  with Incus's own management traffic
- If a user runs `make disp` without `DOMAIN=`, the untrusted workload
  runs without domain isolation
- This contradicts the principle that disposable instances are for
  untrusted workloads

### Recommendations

1. **Default to a dedicated disposable domain**: Create a `disposable`
   domain in `infra.yml` and use it as the default for `make disp`
2. **Warn when using `default` project**: Print a warning when no
   `--domain` is specified that the instance has no network isolation
3. **Document the security implication**: The `disposable.md` doc
   mentions this in passing but should emphasize the security impact

---

## FINDING-09: Galaxy Roles in the Trust Boundary (LOW-MEDIUM)

### Description

ADR-045 introduces Galaxy roles installed to `roles_vendor/` from
`requirements.yml`. These roles execute inside `anklume-instance` during
`make apply`, with access to the Incus socket.

### Why It Matters

- Galaxy roles are third-party code with no formal security review
- A malicious or compromised Galaxy role could exfiltrate secrets,
  create backdoor containers, or modify nftables rules
- `roles_vendor/` is gitignored — the actual code running is not
  tracked in version control
- `make init` installs the latest matching version, which could be
  a compromised release published after the initial `requirements.yml`

### Recommendations

1. **Pin Galaxy roles to exact versions** (not `>=`): In `requirements.yml`,
   use exact version pins to prevent pulling a compromised newer version
2. **Commit `roles_vendor/` to git**: While this increases repo size, it
   provides an audit trail and prevents silent updates. Alternatively,
   generate and commit checksums
3. **Review Galaxy roles before adoption**: Document a review process
   for adding new Galaxy roles, similar to npm audit

---

## FINDING-10: Agent Teams with bypassPermissions (LOW)

### Description

From `docs/agent-teams.md`:

> `--dangerously-skip-permissions` (safe: isolated sandbox)

Claude Code Agent Teams run with all permissions bypassed inside the
Incus-in-Incus sandbox.

### Why It Matters

- The sandbox is a VM (ADR-029), providing hardware isolation — good
- However, the agents have network access for API calls (ANTHROPIC_API_KEY)
- A prompt injection in the codebase being worked on could cause the agent
  to exfiltrate the API key or other secrets via network calls
- The audit hook logs tool invocations but cannot prevent malicious actions
  in real-time

### Recommendations

1. **Network-restrict the sandbox**: Allow only outbound connections to
   Anthropic API endpoints (api.anthropic.com), block all other egress
2. **Rotate API keys**: Use a short-lived, scoped API key for agent
   sessions rather than a long-lived key
3. **Review the audit log as part of the PR review**: Require that the
   audit JSONL is attached to or referenced in the PR for human review

---

## FINDING-11: LLM Sanitizer — Two-Level Architecture (LOW)

### Description

The LLM sanitizer (Phase 39, ADR-044) is designed as a **two-level**
detection architecture (`docs/vision-ai-integration.md`):

1. **Level 1 — IaC-specific regex patterns** (implemented in
   `roles/llm_sanitizer/templates/patterns.yml.j2`): curated regexes
   targeting anklume-specific identifiers (trust-zone IPs, Incus
   resource names, bridges, FQDN, credentials, Ansible paths, MAC
   addresses, network scan output).
2. **Level 2 — ML/NER-based detection** (planned): integration with
   a proven base such as LLM Guard (NER via BERT, 30+ entity types)
   or LLM Sentinel (80+ PII types). These tools handle semantic
   detection that regex cannot cover.

The vision doc states: "None of these understand IaC-specific data
[...] anklume would add IaC-specific detection patterns on top of a
proven base."

### Current State

Only Level 1 (regex) is implemented. Level 2 (ML/NER) is planned but
not yet deployed. With only Level 1 active:

- Regex patterns cannot detect semantic information leakage (e.g.,
  describing the infrastructure topology in natural language without
  using actual IPs or names)
- New identifier patterns not covered by the regexes will pass through
- The sanitizer runs inside the domain container — if the container is
  compromised, the sanitizer can be bypassed
- Replacement mode `pseudonymize` uses consistent mappings — an
  attacker observing multiple requests could correlate pseudonyms

### Recommendations

1. **Prioritize Level 2 integration**: Adding NER-based detection
   (LLM Guard or equivalent) would close the semantic leakage gap
   that regex alone cannot address
2. **Extend Level 1 patterns proactively**: When new infrastructure
   identifiers are added (e.g., MCP service names), add corresponding
   patterns to `patterns.yml.j2`
3. **Log bypass metrics**: Track what percentage of requests have zero
   redactions — a sudden drop could indicate a new identifier type
   leaking through
4. **The two-level architecture is the right design**: Regex for
   IaC-specific identifiers (fast, no false positives) + ML for
   general PII/semantic detection (broad coverage) is a sound
   layered approach

---

## FINDING-12: No Integrity Verification of Generated Ansible Files (LOW)

### Description

Generated Ansible files (`group_vars/`, `host_vars/`, `inventory/`) are
the Secondary Source of Truth. Users can edit them outside managed sections.
`make apply` executes whatever is in these files.

### Why It Matters

- An attacker who gains write access to these files (e.g., via a
  compromised editor, a malicious git merge, or a supply chain attack)
  can inject arbitrary Ansible tasks
- The managed sections are re-generated by `make sync`, but user sections
  are preserved — a malicious payload in user sections would persist
- There is no signature or checksum verification of generated files
  before `make apply`

### Recommendations

1. **Git-based integrity**: Require a clean `git status` before
   `make apply` (or at least warn on uncommitted changes to
   generated files)
2. **Managed section checksums**: The generator could embed a hash
   of the managed section content that `make apply` verifies before
   execution
3. **This is acceptable for the target audience**: anklume targets
   sysadmins and power users who manage their own git repos. The risk
   is low in the intended deployment model.

---

## Positive Security Properties

The audit identified several strong security properties that should be
preserved:

1. **Socket-based management, no SSH**: Using the Incus socket instead
   of SSH eliminates an entire class of attacks (SSH key management,
   network-exposed sshd, brute-force). This is a significant advantage.

2. **No special nftables exception for anklume**: The anklume domain
   has no network privileges beyond other domains. Management traffic
   flows through the socket, not the network. This is correct and
   should never change.

3. **Privileged LXC restriction (ADR-020)**: Requiring a VM boundary
   for privileged containers is a strong security stance. The `--YOLO`
   escape hatch is properly documented as a training-only tool.

4. **Defense-in-depth nftables**: Host-level and VM-level firewalling
   can coexist, ensuring that compromise of one layer doesn't break
   isolation.

5. **tmux color security model**: Pane colors set server-side (not by
   the container) prevents visual spoofing — same principle as QubesOS
   dom0 borders.

6. **Two-step nftables deployment**: Separating generation from
   deployment gives the operator review time and keeps the container
   from needing host-level privileges.

7. **Atomic nftables replacement**: The `delete table; create table`
   pattern ensures no gap in rule coverage during updates.

8. **Trust-zone IP addressing (ADR-038)**: Encoding trust levels in IP
   addresses provides immediate visual identification and enables
   zone-based firewall rules.

9. **Ephemeral protection (ADR-042)**: `make flush` respecting
   `security.protection.delete` prevents accidental destruction of
   important instances.

10. **Agent reproducibility (ADR-036)**: All agent operational knowledge
    reproduced from git templates ensures no hidden state accumulates.

---

## Summary Matrix

| Finding | Severity | Exploitability | Impact | Status |
|---------|----------|----------------|--------|--------|
| FINDING-01: Incus socket = god mode | CRITICAL | Medium | Total compromise | Architectural |
| FINDING-02: OpenClaw internet-to-infra bridge | HIGH | Medium | Arbitrary execution | Architectural |
| FINDING-03: World-readable credentials | HIGH | Low | Token theft | Fixable |
| FINDING-04: LXC for untrusted workloads | MEDIUM | Low-Medium | Container escape | Configurable |
| FINDING-05: VRAM flush best-effort | MEDIUM | Low | Cross-domain data leak | By design |
| FINDING-06: br_netfilter dependency | MEDIUM | Low | Silent isolation failure | Fixable |
| FINDING-07: nftables time window | LOW-MEDIUM | Low | Temporary isolation gap | Fixable |
| FINDING-08: Disposable default project | LOW-MEDIUM | Low | No isolation | Fixable |
| FINDING-09: Galaxy roles in trust boundary | LOW-MEDIUM | Low | Supply chain | Mitigable |
| FINDING-10: Agent Teams bypass permissions | LOW | Very Low | API key exfiltration | Mitigable |
| FINDING-11: LLM sanitizer Level 2 not yet deployed | LOW | Low | Data leakage | Planned |
| FINDING-12: No file integrity check | LOW | Very Low | Config injection | Acceptable |

---

## Recommendations Priority

### Immediate (before production deployment)

1. Verify `br_netfilter` in bootstrap and nftables-deploy (FINDING-06)
2. Pin Galaxy role versions exactly (FINDING-09)
3. Fix credential permissions with `raw.idmap` (FINDING-03)
4. Add proxy authentication on `:9090` (FINDING-02)

### Short-term (next development cycle)

5. Integrate nftables regeneration into `make apply` (FINDING-07)
6. Default disposable instances to a dedicated domain (FINDING-08)
7. Add warning for untrusted LXC containers (FINDING-04)
8. Add VRAM verification step (FINDING-05)

### Long-term (architectural evolution)

9. Scope Incus access via project-confined TLS certificates (FINDING-01)
10. Separate OpenClaw proxy from anklume-instance (FINDING-02)
11. Network-restrict agent sandbox to API-only egress (FINDING-10)

---

*This audit covers the operational model as documented. A complementary
code-level audit should verify that the documented security properties
are correctly implemented.*
