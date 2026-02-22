
# Network safety check - backup and monitor network config

set -euo pipefail

BACKUP_DIR="${HOME}/.anklume-network-backups"
mkdir -p "${BACKUP_DIR}"

backup_network_state() {
    local timestamp
    timestamp=$(date +%Y%m%d-%H%M%S)
    local backup_file="${BACKUP_DIR}/network-${timestamp}.txt"

    {
        echo "=== Routes ==="
        ip route show
        echo
        echo "=== nftables ==="
        nft list ruleset 2>/dev/null || echo "No nftables rules"
        echo
        echo "=== Interfaces ==="
        ip link show
        echo
        echo "=== Default gateway ==="
        ip route get 1.1.1.1 2>/dev/null || echo "No route to internet"
    } > "${backup_file}"

    echo "Network state backed up to ${backup_file}"
}

verify_connectivity() {
    if ! ping -c 1 -W 2 1.1.1.1 &>/dev/null; then
        echo "ERROR: Internet connectivity lost!" >&2
        return 1
    fi
    echo "Internet connectivity OK"

    # Check br_netfilter for nftables bridge filtering
    if ! lsmod | grep -q br_netfilter 2>/dev/null; then
        echo "WARNING: br_netfilter module is NOT loaded." >&2
        echo "         nftables rules will NOT filter traffic between bridges." >&2
        echo "         Load it with: modprobe br_netfilter" >&2
    fi

    local nf_call
    nf_call=$(sysctl -n net.bridge.bridge-nf-call-iptables 2>/dev/null || echo "unavailable")
    if [ "$nf_call" != "1" ]; then
        echo "WARNING: net.bridge.bridge-nf-call-iptables = ${nf_call} (expected 1)." >&2
        echo "         Bridge traffic will bypass nftables even if rules are loaded." >&2
    fi
}

restore_from_backup() {
    local latest_backup
    latest_backup=$(find "${BACKUP_DIR}" -maxdepth 1 -name 'network-*.txt' -printf '%T@\t%p\n' 2>/dev/null | sort -rn | head -1 | cut -f2)

    if [[ -z "${latest_backup}" ]]; then
        echo "No backup found" >&2
        return 1
    fi

    echo "Latest backup: ${latest_backup}"
    cat "${latest_backup}"
}

case "${1:-}" in
    backup)
        backup_network_state
        ;;
    verify)
        verify_connectivity
        ;;
    restore-info)
        restore_from_backup
        ;;
    *)
        echo "Usage: $0 {backup|verify|restore-info}"
        exit 1
        ;;
esac
