# Addressing Convention

AnKLuMe encodes trust zones in IP addresses so that an administrator
can determine the security posture of any machine from its IP alone.

## Scheme

```
10.<zone_base + zone_offset>.<domain_seq>.<host>/24
```

- **First octet** (10): RFC 1918 private range
- **Second octet**: trust zone (zone_base + zone_offset)
- **Third octet**: domain sequence within the zone
- **Fourth octet**: host address within the domain

## Zone mapping

| trust_level    | zone_offset | Default second octet | Zone name  | Color   |
|----------------|-------------|----------------------|------------|---------|
| admin          | 0           | 100                  | MGMT       | blue    |
| trusted        | 10          | 110                  | TRUSTED    | green   |
| semi-trusted   | 20          | 120                  | SERVICES   | yellow  |
| untrusted      | 40          | 140                  | SANDBOX    | red     |
| disposable     | 50          | 150                  | GATEWAY    | magenta |

Gaps (130, 160-199) are reserved for future sub-zones or user-defined
zones. Range 200-249 is available for custom use.

## Configuration

```yaml
global:
  addressing:
    base_octet: 10     # First octet (default: 10, only RFC 1918 /8)
    zone_base: 100     # Starting second octet (default: 100)
    zone_step: 10      # Gap between zones (default: 10)
```

### Why zone_base=100?

The `10.0-60.x.x` range is heavily used by enterprise VPNs, home
routers (`10.0.0.x`, `10.0.1.x`), Kubernetes (`10.96.x.x`,
`10.244.x.x`), and other tools. Starting at 100 avoids both real
routing conflicts and cognitive confusion ("is this my laptop or
the enterprise network?").

## Domain sequence (third octet)

Within each zone, domains are assigned a sequence number (third octet)
automatically in alphabetical order. This can be overridden with an
explicit `subnet_id` on the domain.

Example with two trusted domains:
- `perso` → alphabetically first → domain_seq = 0 → `10.110.0.0/24`
- `pro` → alphabetically second → domain_seq = 1 → `10.110.1.0/24`

To force `pro` as the primary (seq 0), use `subnet_id: 0` on `pro`
and `subnet_id: 1` on `perso`.

## IP reservation per /24 subnet

| Range       | Usage                                    |
|-------------|------------------------------------------|
| `.0`        | Network address (reserved)               |
| `.1-.99`    | Static assignment (machines in infra.yml)|
| `.100-.199` | DHCP range (Incus managed)               |
| `.200-.249` | Available for future use                 |
| `.250`      | Monitoring probe (reserved)              |
| `.251-.253` | Infrastructure (firewall .253, etc.)     |
| `.254`      | Gateway (immutable convention)           |
| `.255`      | Broadcast (reserved)                     |

## Auto-IP assignment

Machines without an explicit `ip:` field receive an auto-assigned
address starting from `.1` within their domain subnet, incrementing
for each machine in declaration order. Auto-assigned IPs stay in the
`.1-.99` range.

```yaml
machines:
  ai-gpu:       # → .1 (auto)
    type: lxc
  ai-webui:     # → .2 (auto)
    type: lxc
  ai-chat:
    ip: "10.120.0.30"  # explicit → .30
  ai-code:      # → .3 (auto, skips .30)
    type: lxc
```

## Nesting

Each nesting level uses identical IP addresses. Network isolation
between levels is provided by Incus virtualization (separate bridges,
separate Incus daemons), not by IP differentiation. The `nesting_prefix`
global setting only affects Incus resource names (`001-net-pro`, etc.).

This means the same `infra.yml` produces identical results at any
nesting level — the framework is fully reproducible.

## Machine naming convention

Recommended pattern: `<domain>-<role>` or `<domain_abbrev>-<role>`.

| Domain      | Machine         | Role            |
|-------------|-----------------|-----------------|
| anklume     | anklume-instance| Ansible controller |
| pro         | pro-dev         | Development workspace |
| perso       | perso-desktop   | Personal desktop |
| ai-tools    | ai-gpu          | GPU server (Ollama+STT) |
| ai-tools    | ai-webui        | Open WebUI interface |
| tor-gateway | torgw-proxy     | Tor transparent proxy |
| anonymous   | anon-browser    | Isolated browser |

Exception: system machines use the `sys-` prefix (QubesOS convention):
`sys-firewall`, `sys-dns`, `sys-vpn`.

## Domain naming convention

Domain names should be short, English, descriptive of usage:

| Good          | Bad              | Why                      |
|---------------|------------------|--------------------------|
| `pro`         | `domain-02`      | Not semantic             |
| `ai-tools`    | `gpu-stuff`      | Not descriptive enough   |
| `tor-gateway`  | `torgw`          | Too abbreviated          |
| `lab-01`      | `student-dupont` | Personal data in name    |

## Complete example

Canonical AnKLuMe infrastructure:

```
IP               Machine           Domain       Zone       trust_level
───────────────────────────────────────────────────────────────────────
10.100.0.10      anklume-instance  anklume      MGMT       admin
10.110.0.10      pro-dev           pro          TRUSTED    trusted
10.110.1.10      perso-desktop     perso        TRUSTED    trusted
10.120.0.10      ai-gpu            ai-tools     SERVICES   semi-trusted
10.120.0.20      ai-webui          ai-tools     SERVICES   semi-trusted
10.120.0.30      ai-chat           ai-tools     SERVICES   semi-trusted
10.120.0.40      ai-code           ai-tools     SERVICES   semi-trusted
10.140.0.1       anon-browser      anonymous    SANDBOX    untrusted
10.150.0.1       torgw-proxy       tor-gateway  GATEWAY    disposable
```

Reading `10.120.0.30`: second octet 120 = 100+20 → semi-trusted
(SERVICES zone). Third octet 0 → first domain in zone. Host 30.
