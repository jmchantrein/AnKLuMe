#!/usr/bin/env bash
# CUPS print service management for AnKLuMe instances.
# Install CUPS, add USB printers, and configure network printer access.
# See docs/sys-print.md and ROADMAP.md Phase 20e.
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
    [[ $# -ge 1 ]] || die "Usage: sys-print.sh setup <instance> [--project PROJECT]"
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

    echo "Setting up CUPS print service in ${instance} (project: ${project})..."

    # Install CUPS and filters
    echo "Installing CUPS packages..."
    incus exec "$instance" --project "$project" -- \
        bash -c "DEBIAN_FRONTEND=noninteractive apt-get update -qq && apt-get install -y -qq cups cups-filters >/dev/null 2>&1"

    # Configure CUPS for remote access
    echo "Configuring CUPS for remote access (port 631)..."
    cat <<'CUPSCONF' | incus file push - "${instance}/etc/cups/cupsd.conf" --project "$project"
# AnKLuMe CUPS configuration - remote access enabled
LogLevel warn
MaxLogSize 0
Listen *:631
Listen /run/cups/cups.sock

# Web interface
WebInterface Yes

# Browsing
Browsing On
BrowseLocalProtocols dnssd

# Default authentication
DefaultAuthType Basic

# Access control
<Location />
  Order allow,deny
  Allow @LOCAL
</Location>

<Location /admin>
  Order allow,deny
  Allow @LOCAL
</Location>

<Location /admin/conf>
  AuthType Default
  Require user @SYSTEM
  Order allow,deny
  Allow @LOCAL
</Location>

<Policy default>
  JobPrivateAccess default
  JobPrivateValues default
  SubscriptionPrivateAccess default
  SubscriptionPrivateValues default

  <Limit Create-Job Print-Job Print-URI Validate-Job>
    Order deny,allow
  </Limit>

  <Limit Send-Document Send-URI Hold-Job Release-Job Restart-Job Purge-Jobs Set-Job-Attributes Create-Job-Subscription Renew-Subscription Cancel-Subscription Get-Notifications Reprocess-Job Cancel-Current-Job Suspend-Current-Job Resume-Job Cancel-My-Jobs Close-Job CUPS-Move-Job CUPS-Get-Document>
    Require user @OWNER @SYSTEM
    Order deny,allow
  </Limit>

  <Limit CUPS-Add-Modify-Printer CUPS-Delete-Printer CUPS-Add-Modify-Class CUPS-Delete-Class CUPS-Set-Default CUPS-Get-Devices>
    AuthType Default
    Require user @SYSTEM
    Order deny,allow
  </Limit>

  <Limit Pause-Printer Resume-Printer Enable-Printer Disable-Printer Pause-Printer-After-Current-Job Hold-New-Jobs Release-Held-New-Jobs Deactivate-Printer Activate-Printer Restart-Printer Shutdown-Printer Startup-Printer Promote-Job Schedule-Job-After Cancel-Jobs CUPS-Accept-Jobs CUPS-Reject-Jobs>
    AuthType Default
    Require user @SYSTEM
    Order deny,allow
  </Limit>

  <Limit Cancel-Job CUPS-Authenticate-Job>
    Require user @OWNER @SYSTEM
    Order deny,allow
  </Limit>

  <Limit All>
    Order deny,allow
  </Limit>
</Policy>
CUPSCONF

    # Enable and restart CUPS
    echo "Enabling and starting CUPS service..."
    incus exec "$instance" --project "$project" -- systemctl enable cups
    incus exec "$instance" --project "$project" -- systemctl restart cups

    echo "Done: CUPS print service configured in ${instance}."
    echo "Web interface: http://<instance-ip>:631"
    echo "Add printers with: sys-print.sh add-usb or sys-print.sh add-network"
}

cmd_add_usb() {
    local vendor="" product="" instance="" project=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --vendor)  vendor="$2"; shift 2 ;;
            --product) product="$2"; shift 2 ;;
            --project) project="$2"; shift 2 ;;
            -*)        die "Unknown option: $1" ;;
            *)
                if [[ -z "$instance" ]]; then
                    instance="$1"; shift
                else
                    die "Unexpected argument: $1"
                fi
                ;;
        esac
    done

    [[ -n "$instance" ]] || die "Usage: sys-print.sh add-usb <instance> --vendor VID --product PID [--project PROJECT]"
    [[ -n "$vendor" ]]   || die "Missing --vendor VID"
    [[ -n "$product" ]]  || die "Missing --product PID"

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$instance")"
    fi

    local device_name="printer-${vendor}-${product}"

    echo "Adding USB printer (vendor=${vendor}, product=${product}) to ${instance} (project: ${project})..."
    incus config device add "$instance" "$device_name" usb \
        "vendorid=${vendor}" "productid=${product}" \
        --project "$project"

    echo "Done: USB device '${device_name}' attached to ${instance}."
    echo "The printer should appear in CUPS at http://<instance-ip>:631/admin"
}

cmd_add_network() {
    local nic_parent="" instance="" project=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --nic-parent) nic_parent="$2"; shift 2 ;;
            --project)    project="$2"; shift 2 ;;
            -*)           die "Unknown option: $1" ;;
            *)
                if [[ -z "$instance" ]]; then
                    instance="$1"; shift
                else
                    die "Unexpected argument: $1"
                fi
                ;;
        esac
    done

    [[ -n "$instance" ]]   || die "Usage: sys-print.sh add-network <instance> --nic-parent IFACE [--project PROJECT]"
    [[ -n "$nic_parent" ]] || die "Missing --nic-parent IFACE (host network interface, e.g. eth0, enp3s0)"

    check_incus

    if [[ -z "$project" ]]; then
        project="$(find_project "$instance")"
    fi

    echo "Adding macvlan NIC (parent=${nic_parent}) to ${instance} (project: ${project})..."
    incus config device add "$instance" "lan-access" nic \
        "nictype=macvlan" "parent=${nic_parent}" \
        --project "$project"

    echo "Done: macvlan NIC 'lan-access' attached to ${instance}."
    echo "The instance can now discover network printers on the physical LAN."
    echo "Restart the instance for the NIC to take effect: incus restart ${instance} --project ${project}"
}

cmd_status() {
    [[ $# -ge 1 ]] || die "Usage: sys-print.sh status <instance> [--project PROJECT]"
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

    echo "CUPS status in ${instance} (project: ${project}):"
    echo ""
    incus exec "$instance" --project "$project" -- systemctl status cups --no-pager || true
    echo ""
    echo "Configured printers:"
    incus exec "$instance" --project "$project" -- lpstat -p 2>/dev/null || echo "  (no printers configured)"
    echo ""
    echo "Incus devices attached to instance:"
    local config_yaml
    config_yaml=$(incus config show "$instance" --project "$project" 2>/dev/null) || true
    if [[ -n "$config_yaml" ]]; then
        python3 - "$config_yaml" <<'PYEOF' || echo "  (could not parse devices)"
import sys, yaml

try:
    data = yaml.safe_load(sys.argv[1])
    devices = data.get("devices", {})
    if not devices:
        print("  (no devices)")
    for name, conf in devices.items():
        dtype = conf.get("type", "unknown")
        if dtype == "usb":
            vid = conf.get("vendorid", "?")
            pid = conf.get("productid", "?")
            print(f"  {name}: USB vendorid={vid} productid={pid}")
        elif dtype == "nic" and conf.get("nictype") == "macvlan":
            parent = conf.get("parent", "?")
            print(f"  {name}: macvlan parent={parent}")
except Exception:
    pass
PYEOF
    else
        echo "  (could not read instance config)"
    fi
}

# ── Entry point ──────────────────────────────────────────────

usage() {
    cat <<'USAGE'
Usage: sys-print.sh <command> [args]

Commands:
  setup       <instance> [--project P]                           Install and configure CUPS
  add-usb     <instance> --vendor VID --product PID [--project P] Add USB printer passthrough
  add-network <instance> --nic-parent IFACE [--project P]        Add macvlan NIC for network printers
  status      <instance> [--project P]                           Show CUPS and printer status
  help                                                           Show this help

Options:
  --project PROJECT   Incus project (auto-detected if omitted)

The setup command:
  1. Installs cups and cups-filters packages
  2. Configures CUPS for remote access (Listen *:631, Allow @LOCAL)
  3. Enables and starts the CUPS service

The add-usb command adds a USB device passthrough to the instance using
Incus's usb device type with vendorid and productid.

The add-network command adds a macvlan NIC to give the instance direct
access to the physical LAN for discovering network printers (WiFi/Ethernet).
Other domains access the CUPS service via IPP (port 631) through network_policies.

Examples:
  sys-print.sh setup sys-print                                # Install CUPS
  sys-print.sh add-usb sys-print --vendor 04b8 --product 0005 # Add Epson USB
  sys-print.sh add-network sys-print --nic-parent enp3s0      # LAN access
  sys-print.sh status sys-print                               # Check status
USAGE
}

[[ $# -ge 1 ]] || { usage; exit 0; }

case "$1" in
    setup)       shift; cmd_setup "$@" ;;
    add-usb)     shift; cmd_add_usb "$@" ;;
    add-network) shift; cmd_add_network "$@" ;;
    status)      shift; cmd_status "$@" ;;
    -h|--help|help) usage ;;
    *) die "Unknown command: $1. Run 'sys-print.sh help' for usage." ;;
esac
