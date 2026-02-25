#!/usr/bin/env bash
# nmap-diff.sh — Run nmap scan per domain, compare to baseline, output diff.
# Part of Phase 40: Network Inspection and Security Monitoring.
#
# Usage: scripts/nmap-diff.sh <domain> [--subnet <cidr>] [--baseline-dir <dir>]
#
# Requires: nmap, diff
# shellcheck disable=SC2312

set -euo pipefail

# --- Defaults ----------------------------------------------------------------

BASELINE_DIR="/var/lib/openclaw/baselines"
DOMAIN=""
SUBNET=""

# --- Usage -------------------------------------------------------------------

usage() {
    cat <<'EOF'
Usage: nmap-diff.sh <domain> [OPTIONS]

Run an nmap scan for a domain subnet and compare against a saved baseline.

Options:
  --subnet <cidr>          Override subnet (default: auto-detect from Incus)
  --baseline-dir <dir>     Baseline storage directory
                           (default: /var/lib/openclaw/baselines)
  -h, --help               Show this help

Examples:
  scripts/nmap-diff.sh pro
  scripts/nmap-diff.sh pro --subnet 10.ZONE.SEQ.0/24
  scripts/nmap-diff.sh pro --baseline-dir /tmp/baselines
EOF
    exit 0
}

# --- Argument parsing --------------------------------------------------------

if [[ $# -lt 1 ]]; then
    echo "Error: domain argument required" >&2
    usage
fi

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage ;;
        --subnet) SUBNET="$2"; shift 2 ;;
        --baseline-dir) BASELINE_DIR="$2"; shift 2 ;;
        -*) echo "Error: unknown option $1" >&2; exit 1 ;;
        *) DOMAIN="$1"; shift ;;
    esac
done

if [[ -z "$DOMAIN" ]]; then
    echo "Error: domain argument required" >&2
    exit 1
fi

# --- Subnet detection --------------------------------------------------------

if [[ -z "$SUBNET" ]]; then
    if ! command -v incus >/dev/null 2>&1; then
        echo "Error: incus not found and --subnet not specified" >&2
        exit 1
    fi
    SUBNET=$(incus network get "net-${DOMAIN}" ipv4.address 2>/dev/null || true)
    if [[ -z "$SUBNET" ]]; then
        echo "Error: cannot detect subnet for domain '${DOMAIN}'" >&2
        echo "Use --subnet to specify manually" >&2
        exit 1
    fi
fi

# --- Directories -------------------------------------------------------------

DOMAIN_DIR="${BASELINE_DIR}/${DOMAIN}"
mkdir -p "$DOMAIN_DIR"

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
CURRENT_FILE="${DOMAIN_DIR}/scan-${TIMESTAMP}.xml"
BASELINE_FILE="${DOMAIN_DIR}/baseline.xml"

# --- Scan --------------------------------------------------------------------

echo "Scanning ${SUBNET} for domain '${DOMAIN}'..."
nmap -sV -oX "$CURRENT_FILE" "$SUBNET" >/dev/null 2>&1

echo "Scan saved to: ${CURRENT_FILE}"

# --- Compare -----------------------------------------------------------------

if [[ ! -f "$BASELINE_FILE" ]]; then
    echo "No baseline found. Saving current scan as baseline."
    cp "$CURRENT_FILE" "$BASELINE_FILE"
    echo "Baseline created: ${BASELINE_FILE}"
    echo "Run again later to see differences."
    exit 0
fi

echo ""
echo "=== Network Diff: ${DOMAIN} ==="
echo "Baseline: ${BASELINE_FILE}"
echo "Current:  ${CURRENT_FILE}"
echo ""

# Extract host/port summaries for comparison
extract_summary() {
    local xml_file="$1"
    # Extract host IP + open ports from nmap XML using grep/sed
    # This produces a sorted summary suitable for diff
    grep -E '(addr addr=|portid=.*state="open")' "$xml_file" 2>/dev/null \
        | sed 's/.*addr="\([^"]*\)".*/HOST: \1/' \
        | sed 's/.*portid="\([^"]*\)".*protocol="\([^"]*\)".*state="open".*service name="\([^"]*\)".*/  PORT: \1\/\2 (\3)/' \
        | sort
}

BASELINE_SUMMARY=$(extract_summary "$BASELINE_FILE")
CURRENT_SUMMARY=$(extract_summary "$CURRENT_FILE")

DIFF_OUTPUT=$(diff <(echo "$BASELINE_SUMMARY") <(echo "$CURRENT_SUMMARY") || true)

if [[ -z "$DIFF_OUTPUT" ]]; then
    echo "No changes detected."
else
    echo "$DIFF_OUTPUT"
fi

# Update baseline with current scan
cp "$CURRENT_FILE" "$BASELINE_FILE"
echo ""
echo "Baseline updated."
