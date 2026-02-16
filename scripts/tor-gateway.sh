#!/usr/bin/env bash
# Tor transparent proxy setup for anklume instances.
# Install, configure, and verify Tor inside an Incus container.
# See docs/tor-gateway.md and ROADMAP.md Phase 20e.
set -euo pipefail

die() { echo "ERROR: $*" >&2; exit 1; }

# ── Pre-flight: verify Incus daemon is accessible ────────────

check_incus() {
    if ! incus project list --format csv >/dev/null 2>&1; then
        die "Cannot connect to the Incus daemon. Check that incus is installed and you have socket access."
    fi
}

# ── Instance-to-project resolution ──────────────────────────

find_project() {
    local instance="$1"
    local project
    project=$(incus list --all-projects --format json | python3 -c "
import json, sys
data = json.load(sys.stdin)
for item in data:
    if item.get('name') == sys.argv[1]:
        print(item.get('project', 'default'))
        sys.exit(0)
sys.exit(1)
" "$instance" 2>/dev/null) || die "Instance '${instance}' not found in any Incus project"
    echo "$project"
}

# ── Commands ─────────────────────────────────────────────────

cmd_setup() {
    [[ $# -ge 1 ]] || die "Usage: tor-gateway.sh setup <instance> [--project PROJECT]"
    local instance="$1"
    shift
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$instance")"
    fi

    echo "Setting up Tor transparent proxy in ${instance} (project: ${project})..."

    # Install Tor
    echo "Installing tor package..."
    incus exec "$instance" --project "$project" -- \
        bash -c "DEBIAN_FRONTEND=noninteractive apt-get update -qq && apt-get install -y -qq tor nftables >/dev/null 2>&1"

    # Configure Tor as transparent proxy
    echo "Configuring Tor transparent proxy (TransPort 9040, DNSPort 5353)..."
    printf '%s\n' \
        '# anklume Tor transparent proxy configuration' \
        'VirtualAddrNetworkIPv4 10.192.0.0/10' \
        'AutomapHostsOnResolve 1' \
        'TransPort 0.0.0.0:9040' \
        'DNSPort 0.0.0.0:5353' \
        'SocksPort 0' \
        'RunAsDaemon 0' \
        'Log notice syslog' \
        | incus file push - "${instance}/etc/tor/torrc" --project "$project"

    # Generate nftables rules for traffic redirection inside the container
    echo "Configuring nftables traffic redirection..."
    incus exec "$instance" --project "$project" -- mkdir -p /etc/nftables.d
    printf '%s\n' \
        '# anklume Tor transparent proxy nftables rules' \
        'table inet tor-redirect' \
        '' \
        'delete table inet tor-redirect' \
        '' \
        'table inet tor-redirect {' \
        '    chain prerouting {' \
        '        type nat hook prerouting priority dstnat; policy accept;' \
        '        # Redirect DNS to Tor DNSPort' \
        '        udp dport 53 redirect to :5353' \
        '        # Redirect TCP to Tor TransPort' \
        '        tcp dport != 9040 redirect to :9040' \
        '    }' \
        '' \
        '    chain output {' \
        '        type nat hook output priority -100; policy accept;' \
        '        # Do not redirect Tor own traffic' \
        '        meta skuid "debian-tor" accept' \
        '        # Redirect local DNS' \
        '        udp dport 53 redirect to :5353' \
        '        # Redirect local TCP' \
        '        tcp dport != 9040 redirect to :9040' \
        '    }' \
        '}' \
        | incus file push - "${instance}/etc/nftables.d/tor-redirect.nft" --project "$project"

    # Load the nftables rules
    incus exec "$instance" --project "$project" -- nft -f /etc/nftables.d/tor-redirect.nft

    # Enable and restart Tor
    echo "Enabling and starting Tor service..."
    incus exec "$instance" --project "$project" -- systemctl enable tor
    incus exec "$instance" --project "$project" -- systemctl restart tor

    echo "Done: Tor transparent proxy configured in ${instance}."
    echo "Verify with: tor-gateway.sh verify ${instance}"
}

cmd_status() {
    [[ $# -ge 1 ]] || die "Usage: tor-gateway.sh status <instance> [--project PROJECT]"
    local instance="$1"
    shift
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$instance")"
    fi

    echo "Tor status in ${instance} (project: ${project}):"
    echo ""
    incus exec "$instance" --project "$project" -- systemctl status tor --no-pager || true
    echo ""
    echo "nftables rules:"
    incus exec "$instance" --project "$project" -- nft list table inet tor-redirect 2>/dev/null || echo "  (no tor-redirect table found)"
}

cmd_verify() {
    [[ $# -ge 1 ]] || die "Usage: tor-gateway.sh verify <instance> [--project PROJECT]"
    local instance="$1"
    shift
    local project=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --project) project="$2"; shift 2 ;;
            *) die "Unknown option: $1" ;;
        esac
    done

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$instance")"
    fi

    echo "Verifying Tor connectivity in ${instance} (project: ${project})..."

    # Check Tor service is running
    if ! incus exec "$instance" --project "$project" -- systemctl is-active tor >/dev/null 2>&1; then
        die "Tor service is not running in ${instance}"
    fi
    echo "  Tor service: running"

    # Check Tor circuit establishment
    if incus exec "$instance" --project "$project" -- \
        bash -c 'journalctl -u tor --no-pager -n 50 2>/dev/null | grep -q "Bootstrapped 100%"'; then
        echo "  Tor circuit: established (100%)"
    else
        echo "  Tor circuit: not fully established (check: journalctl -u tor)"
    fi

    # Check nftables rules are loaded
    if incus exec "$instance" --project "$project" -- \
        nft list table inet tor-redirect >/dev/null 2>&1; then
        echo "  nftables redirect: active"
    else
        echo "  nftables redirect: NOT active"
    fi

    echo ""
    echo "Verification complete."
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: tor-gateway.sh <command> [args]

Commands:
  setup    <instance> [--project P]   Install and configure Tor transparent proxy
  status   <instance> [--project P]   Show Tor service and nftables status
  verify   <instance> [--project P]   Verify Tor connectivity and circuit
  help                                Show this help

Options:
  --project PROJECT   Incus project (auto-detected if omitted)

The setup command:
  1. Installs tor and nftables packages
  2. Configures Tor as transparent proxy (TransPort 9040, DNSPort 5353)
  3. Creates nftables rules to redirect all traffic through Tor
  4. Enables and starts the Tor service

Examples:
  tor-gateway.sh setup tor-gw                  # Setup Tor in container
  tor-gateway.sh setup tor-gw --project secure # Explicit project
  tor-gateway.sh status tor-gw                 # Check status
  tor-gateway.sh verify tor-gw                 # Verify Tor connectivity
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 0; }

case "$1" in
    setup)  shift; cmd_setup "$@" ;;
    status) shift; cmd_status "$@" ;;
    verify) shift; cmd_verify "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: $1. Run 'tor-gateway.sh help' for usage." ;;
esac
