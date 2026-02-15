# Tor Gateway

AnKLuMe supports setting up a Tor transparent proxy inside a container.
Traffic from selected domains can be routed through the gateway for
anonymous internet access, controlled by `network_policies` in `infra.yml`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         Host                             │
│                                                          │
│  net-anonymous ────┐                                    │
│                    │      ┌───────────────────┐         │
│                    ├─────▶│ net-tor-gateway    │         │
│                    │      │  tor-gw            │         │
│                    │      │  TransPort 9040    │         │
│                    │      │  DNSPort 5353      │         │
│  net-admin ────────┘      │  nftables redirect │         │
│    (blocked)              └────────┬──────────┘         │
│                                    │                     │
│                              Tor network                 │
│                                    │                     │
│                               Internet                   │
└─────────────────────────────────────────────────────────┘
```

The Tor gateway container runs Tor as a transparent proxy. Inside the
container, nftables rules redirect all TCP and DNS traffic through Tor.
Other domains access the gateway via `network_policies`, which control
which domains can route traffic through it.

## Quick start

### 1. Declare the Tor gateway in infra.yml

```yaml
domains:
  tor-gateway:
    description: "Tor transparent proxy gateway"
    subnet_id: 5
    trust_level: untrusted
    ephemeral: true
    machines:
      tor-gw:
        description: "Tor transparent proxy"
        type: lxc
        ip: "10.100.5.10"
        roles:
          - base_system

  anonymous:
    description: "Domain routed through Tor"
    subnet_id: 6
    trust_level: untrusted
    ephemeral: true
    machines:
      anon-browser:
        type: lxc
        ip: "10.100.6.10"
        roles:
          - base_system

network_policies:
  - description: "Anonymous domain routes through Tor gateway"
    from: anonymous
    to: tor-gateway
    ports: all
    bidirectional: true
```

### 2. Deploy infrastructure

```bash
make sync
make apply
```

### 3. Setup Tor in the gateway container

```bash
make apply-tor I=tor-gw
```

This installs Tor, configures it as a transparent proxy, creates nftables
traffic redirection rules, and starts the service.

### 4. Verify Tor connectivity

```bash
scripts/tor-gateway.sh verify tor-gw
```

## Commands

### setup

Install and configure Tor as a transparent proxy:

```bash
scripts/tor-gateway.sh setup <instance> [--project PROJECT]
```

The setup command:
1. Installs `tor` and `nftables` packages
2. Configures Tor with TransPort 9040 and DNSPort 5353
3. Creates nftables rules to redirect all traffic through Tor
4. Enables and starts the Tor service

### status

Show Tor service and nftables status:

```bash
scripts/tor-gateway.sh status <instance> [--project PROJECT]
```

### verify

Verify Tor connectivity and circuit establishment:

```bash
scripts/tor-gateway.sh verify <instance> [--project PROJECT]
```

Checks:
- Tor service is running
- Tor circuit is established (Bootstrapped 100%)
- nftables redirect rules are active

## Makefile targets

| Target | Description |
|--------|-------------|
| `make apply-tor I=<instance>` | Setup Tor transparent proxy in container |

Accepts optional `PROJECT=<project>` parameter.

## Tor configuration

The setup creates `/etc/tor/torrc` with:

| Setting | Value | Description |
|---------|-------|-------------|
| `TransPort` | `0.0.0.0:9040` | Transparent TCP proxy port |
| `DNSPort` | `0.0.0.0:5353` | DNS resolution via Tor |
| `SocksPort` | `0` | Disabled (transparent proxy only) |
| `VirtualAddrNetworkIPv4` | `10.192.0.0/10` | Virtual address range for .onion |
| `AutomapHostsOnResolve` | `1` | Auto-map hostnames via Tor |

## nftables redirect rules

Inside the Tor container, nftables redirects traffic:

| Chain | Rule | Description |
|-------|------|-------------|
| `prerouting` | `udp dport 53 redirect to :5353` | Redirect DNS to Tor |
| `prerouting` | `tcp dport != 9040 redirect to :9040` | Redirect TCP to Tor |
| `output` | `meta skuid "debian-tor" accept` | Skip Tor's own traffic |
| `output` | `udp dport 53 redirect to :5353` | Local DNS redirect |
| `output` | `tcp dport != 9040 redirect to :9040` | Local TCP redirect |

## Routing client traffic through Tor

After setup, clients in other domains need their traffic routed to the
Tor gateway. Two approaches:

### Via network policies + static routes

Add a `network_policy` allowing the client domain to reach the Tor
gateway, then configure a default route in the client to point to the
Tor gateway IP.

### Via iptables/nftables in the client

Configure the client container to forward all outbound traffic to the
Tor gateway's TransPort.

## Troubleshooting

### Tor not bootstrapping

Check Tor logs inside the container:

```bash
incus exec tor-gw --project tor-gateway -- journalctl -u tor -f
```

Common causes:
- No internet access from the container (check NAT rules)
- DNS resolution failing (check bridge DNS config)
- Tor blocked by network firewall

### nftables rules not loading

Verify the rules file exists:

```bash
incus exec tor-gw --project tor-gateway -- cat /etc/nftables.d/tor-redirect.nft
```

Reload manually:

```bash
incus exec tor-gw --project tor-gateway -- nft -f /etc/nftables.d/tor-redirect.nft
```

### Traffic not going through Tor

Verify from inside the Tor container:

```bash
incus exec tor-gw --project tor-gateway -- curl -s https://check.torproject.org/api/ip
```

If this returns `"IsTor": true`, Tor is working. If client traffic
is not routed through Tor, check the network policies and routing
configuration.
