# LLM Sanitization Proxy

Phase 39 — Transparent anonymization of cloud-bound LLM requests.

## Overview

When a domain sends prompts to cloud LLM providers, those prompts
may contain infrastructure-specific data: internal IP addresses,
Incus resource names, Ansible hostnames, credentials, or internal
FQDNs. The LLM sanitization proxy intercepts these requests and
replaces sensitive identifiers with generic placeholders before
the data leaves the local perimeter.

## Architecture

```
Domain instance          Sanitizer proxy          Cloud LLM API
  (LLM client)   --->   (regex patterns)   --->  (OpenAI, etc.)
                         |                |
                         | audit.log      |
                         | (redactions)   |
```

The proxy runs inside the domain's network perimeter. It is
transparent to the LLM client: the client sends requests to the
proxy endpoint, which sanitizes the content and forwards it to
the upstream API. Responses from the API are passed through
unchanged.

## Configuration

### infra.yml

Per-domain settings in `infra.yml`:

```yaml
domains:
  pro:
    trust_level: trusted
    ai_provider: cloud          # local | cloud | local-first
    ai_sanitize: true           # true | false | "always"
    machines:
      pro-dev:
        type: lxc
        roles: [base_system, llm_sanitizer]
```

### Defaults

| Field | Default | Effect |
|-------|---------|--------|
| `ai_provider` | `local` | All inference on local network |
| `ai_sanitize` | auto | `false` for local, `true` for cloud/local-first |

### Propagation

The generator writes to `group_vars/<domain>.yml`:
- `domain_ai_provider`: the resolved provider value
- `domain_ai_sanitize`: the resolved sanitize value

## Detection patterns

The proxy ships with curated regex patterns organized by category:

### IP addresses
- anklume zone IPs (`10.100-159.x.x`, ADR-038 convention)
- RFC 1918 Class A (`10.0.0.0/8`)
- RFC 1918 Class B (`172.16.0.0/12`)
- RFC 1918 Class C (`192.168.0.0/16`)
- CIDR notation subnets

### Incus resources
- Project names (with optional nesting prefix)
- Bridge names (`net-<domain>`)
- Instance names (`<domain>-<machine>`)
- Incus CLI commands with resource arguments

### Internal FQDNs
- `*.internal`, `*.corp`, `*.local`, `*.lan` domains

### Service identifiers
- Incus Unix socket paths
- Ollama API endpoints
- Local service URLs on private IPs

### Ansible names
- `ansible_host` with IP values
- `group_vars/`, `host_vars/`, `inventory/` file paths

### Credentials
- Bearer tokens
- API key headers
- Common secret variable patterns (`password=`, `token=`)
- SSH private key headers
- Long base64 strings (likely secrets)

## Role variables

All variables use the `llm_sanitizer_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `llm_sanitizer_listen_port` | `8089` | Proxy listen port |
| `llm_sanitizer_upstream_endpoint` | `http://localhost:11434` | Upstream LLM API |
| `llm_sanitizer_replacement_mode` | `mask` | `mask` or `pseudonymize` |
| `llm_sanitizer_audit_enabled` | `true` | Enable audit logging |
| `llm_sanitizer_audit_log_path` | `/var/log/llm-sanitizer/audit.log` | Audit log location |
| `llm_sanitizer_enable_ip_patterns` | `true` | Enable IP detection |
| `llm_sanitizer_enable_incus_patterns` | `true` | Enable Incus name detection |
| `llm_sanitizer_enable_fqdn_patterns` | `true` | Enable FQDN detection |
| `llm_sanitizer_enable_credential_patterns` | `true` | Enable credential detection |
| `llm_sanitizer_enable_ansible_patterns` | `true` | Enable Ansible name detection |
| `llm_sanitizer_enable_service_patterns` | `true` | Enable service ID detection |

## Replacement modes

### Mask (default)
Replaces matches with generic placeholders:
- `10.120.0.5` -> `10.ZONE.SEQ.HOST`
- `net-pro` -> `net-DOMAIN`
- `Bearer eyJhbG...` -> `Bearer [REDACTED]`

### Pseudonymize
Replaces matches with consistent pseudonyms (same input always
produces the same output within a session). Useful when the LLM
needs to reason about relationships between entities without
knowing their real names.

## Audit log

When `llm_sanitizer_audit_enabled` is `true`, every redaction is
logged with:
- Timestamp
- Pattern category and name that matched
- Original and replacement values
- Request metadata (model, endpoint)

The `llm_sanitizer_audit_log_redacted_only` flag (default `true`)
limits logging to requests that had at least one redaction.

## Related

- ADR-044: LLM sanitization proxy decision record
- ADR-038: Trust-level-aware IP addressing (patterns target 10.1xx)
- ADR-032: Exclusive AI-tools network access
- SPEC.md: `ai_provider` and `ai_sanitize` validation constraints
