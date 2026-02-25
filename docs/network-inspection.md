# Network Inspection and Security Monitoring (Phase 40)

LLM-assisted network inspection per domain via custom OpenClaw skills
and collection scripts.

## Architecture: 3-level pipeline

Network inspection follows a three-level pipeline, from raw data
collection to LLM-assisted analysis:

```
Level 1: Collection        Level 2: Diffing          Level 3: Triage
 nmap scan                  nmap-diff.sh               anklume-network-triage
 tshark capture             anklume-inventory-diff     anklume-pcap-summary
                            anklume-network-diff
```

**Level 1 (Collection)**: Raw network data gathering using standard
tools (nmap, tshark). Runs inside the domain's containers via
`incus exec`. Output stored in domain-specific directories.

**Level 2 (Diffing)**: Baseline comparison to detect changes since
the last scan. Uses `scripts/nmap-diff.sh` for standalone operation
or the `anklume-inventory-diff` skill for OpenClaw-driven workflows.

**Level 3 (Triage)**: LLM-assisted classification of findings into
normal/suspect/critical categories. The `anklume-network-triage`
skill uses Ollama to analyze scan output with domain context.

## OpenClaw skills

All skills are Jinja2 templates deployed by the `openclaw_server`
role (ADR-036). Each skill is domain-scoped: it operates only
within its assigned Incus project.

### anklume-network-triage

Parses nmap or tshark output and classifies anomalies using LLM
analysis via Ollama. Classification levels:

| Level | Meaning |
|-------|---------|
| normal | Expected services on known hosts |
| suspect | Unexpected but not necessarily malicious |
| critical | Requires immediate attention |

### anklume-inventory-diff

Compares current nmap service detection scan against a stored
baseline. Detects new hosts, missing hosts, new/closed ports,
and service version changes.

### anklume-pcap-summary

Condenses packet capture files into readable summaries. Extracts
protocol distribution, top conversations, DNS queries, and flags
anomalous traffic patterns.

## nmap-diff.sh

Standalone shell script for domain-scoped nmap scanning with
baseline comparison.

```bash
scripts/nmap-diff.sh <domain> [--subnet <cidr>] [--baseline-dir <dir>]
```

**Auto-detection**: When `--subnet` is not specified, the script
queries `incus network get net-<domain> ipv4.address` to determine
the subnet automatically.

**Baseline management**: First run saves the scan as baseline.
Subsequent runs compare against the baseline and update it.

**Output format**: Unified diff of host/port summaries.

## Anonymization patterns

Phase 40 adds network-specific patterns to the LLM sanitizer
(`roles/llm_sanitizer/templates/patterns.yml.j2`):

| Pattern | Matches | Replacement |
|---------|---------|-------------|
| `mac_address` | `aa:bb:cc:dd:ee:ff` | `XX:XX:XX:XX:XX:XX` |
| `mac_address_dash` | `aa-bb-cc-dd-ee-ff` | `XX-XX-XX-XX-XX-XX` |
| `linux_interface` | `eth0`, `veth123`, `enp5s0` | `IFACE_REDACTED` |
| `arp_entry` | ARP table lines | Fully redacted |
| `nmap_host_report` | Nmap scan report headers | `REDACTED_HOST` |

These patterns ensure that network scan output sent to cloud LLMs
(when `ai_sanitize: true`) does not leak MAC addresses, interface
names, or ARP table contents.

## Configuration

New defaults in `roles/openclaw_server/defaults/main.yml`:

```yaml
# Enable periodic network scanning via cron
openclaw_server_network_scan_enabled: false

# Network scan interval in seconds (default: 1 hour)
openclaw_server_network_scan_interval: 3600

# Directory for nmap baseline storage
openclaw_server_nmap_baseline_dir: "/var/lib/openclaw/baselines"
```

When `openclaw_server_network_scan_enabled: true`, the CRON.md
template includes a network inventory scan entry that runs at the
configured interval.

## Prerequisites

The following tools must be installed in containers where network
inspection is used:

- **nmap**: Network scanning (`apt install nmap`)
- **tshark**: Packet capture analysis (`apt install wireshark-common`)

These are not installed by the `openclaw_server` role by default.
Install them manually or via a custom role when enabling network
inspection.
