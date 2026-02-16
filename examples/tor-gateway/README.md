# Tor Gateway

Route traffic from selected domains through a Tor transparent proxy
for anonymous internet access. The Tor gateway runs in its own
container with nftables traffic redirection.

## Use case

You want certain domains (e.g., untrusted browsing) to route all
internet traffic through the Tor network for anonymity. The Tor
gateway container handles transparent proxying, so client containers
do not need any Tor-specific configuration.

## Domains

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller (protected) |
| tor-gateway | 5 | Tor transparent proxy |
| anonymous | 6 | Domain routed through Tor |

## Machines

| Machine | Domain | Type | IP | Role |
|---------|--------|------|-----|------|
| anklume-instance | anklume | lxc | 10.100.0.10 | Ansible controller |
| tor-gw | tor-gateway | lxc | 10.100.5.10 | Tor transparent proxy |
| anon-browser | anonymous | lxc | 10.100.6.10 | Anonymous browsing |

## Network policies

- `anonymous` can route all traffic through `tor-gateway` (bidirectional)

## Hardware requirements

- 2 CPU cores
- 4 GB RAM
- 10 GB disk

## Getting started

```bash
cp examples/tor-gateway/infra.yml infra.yml
make sync
make apply

# Setup Tor in the gateway container
make apply-tor I=tor-gw

# Verify Tor connectivity
scripts/tor-gateway.sh verify tor-gw
```

## Verification

```bash
# Check Tor status
scripts/tor-gateway.sh status tor-gw

# Verify Tor circuit from inside the container
incus exec tor-gw --project tor-gateway -- \
    curl -s https://check.torproject.org/api/ip
```
