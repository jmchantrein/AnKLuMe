#!/usr/bin/env bash
# bootstrap.sh — Initialize anklume on a new machine
# Usage: bootstrap.sh [OPTIONS]
#
# Options:
#   --prod              Production mode (auto-detect FS, configure Incus preseed)
#   --dev               Development mode (minimal config)
#   --snapshot TYPE     Create FS snapshot before modifications (btrfs|zfs|snapper)
#   --YOLO              Enable YOLO mode (bypass security restrictions)
#   --import            Import existing Incus infrastructure
#   --help              Show this help

set -euo pipefail

MODE=""
SNAPSHOT_TYPE=""
YOLO=false
IMPORT=false

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --prod              Production mode (auto-detect FS, configure Incus)"
    echo "  --dev               Development mode (minimal config)"
    echo "  --snapshot TYPE     Snapshot before modifications (btrfs|zfs|snapper)"
    echo "  --YOLO              Bypass security restrictions"
    echo "  --import            Import existing Incus infrastructure after setup"
    echo "  --help              Show this help"
    exit 0
}

while [ $# -gt 0 ]; do
    case "$1" in
        --prod)    MODE="prod"; shift ;;
        --dev)     MODE="dev"; shift ;;
        --snapshot) SNAPSHOT_TYPE="$2"; shift 2 ;;
        --YOLO)    YOLO=true; shift ;;
        --import)  IMPORT=true; shift ;;
        --help|-h) usage ;;
        *)         echo "Unknown option: $1"; usage ;;
    esac
done

if [ -z "$MODE" ]; then
    echo "ERROR: Specify --prod or --dev"
    usage
fi

echo "=== anklume Bootstrap ($MODE mode) ==="

# ── Detect virtualization ────────────────────────────────
VIRT_TYPE="none"
if command -v systemd-detect-virt &>/dev/null; then
    VIRT_TYPE=$(systemd-detect-virt 2>/dev/null || echo "none")
fi

echo "Detected virtualization: $VIRT_TYPE"

# ── Determine vm_nested flag ────────────────────────────
VM_NESTED=false
PARENT_VM_NESTED=false
if [ -f /etc/anklume/vm_nested ]; then
    PARENT_VM_NESTED=$(cat /etc/anklume/vm_nested)
fi

case "$VIRT_TYPE" in
    kvm|qemu)
        VM_NESTED=true
        ;;
    *)
        VM_NESTED="$PARENT_VM_NESTED"
        ;;
esac

echo "vm_nested: $VM_NESTED"

# ── Determine absolute/relative levels ──────────────────
ABS_LEVEL=0
REL_LEVEL=0
if [ -f /etc/anklume/absolute_level ]; then
    PARENT_ABS=$(cat /etc/anklume/absolute_level)
    ABS_LEVEL=$((PARENT_ABS + 1))
fi
if [ -f /etc/anklume/relative_level ]; then
    PARENT_REL=$(cat /etc/anklume/relative_level)
    case "$VIRT_TYPE" in
        kvm|qemu)
            REL_LEVEL=0  # Reset at VM boundary
            ;;
        *)
            REL_LEVEL=$((PARENT_REL + 1))
            ;;
    esac
fi

echo "absolute_level: $ABS_LEVEL"
echo "relative_level: $REL_LEVEL"

# ── Create /etc/anklume context files ───────────────────
echo "--- Setting up /etc/anklume context ---"
mkdir -p /etc/anklume
echo "$ABS_LEVEL" > /etc/anklume/absolute_level
echo "$REL_LEVEL" > /etc/anklume/relative_level
echo "$VM_NESTED" > /etc/anklume/vm_nested
echo "$YOLO" > /etc/anklume/yolo

# ── Pre-modification snapshot ───────────────────────────
if [ -n "$SNAPSHOT_TYPE" ]; then
    SNAP_NAME="anklume-pre-bootstrap-$(date +%Y%m%d-%H%M%S)"
    echo "--- Creating $SNAPSHOT_TYPE snapshot: $SNAP_NAME ---"
    case "$SNAPSHOT_TYPE" in
        btrfs)
            if command -v btrfs &>/dev/null; then
                btrfs subvolume snapshot / "/.snapshots/$SNAP_NAME" 2>/dev/null || \
                    echo "WARNING: btrfs snapshot failed (check mount points)"
            else
                echo "WARNING: btrfs not available"
            fi
            ;;
        zfs)
            if command -v zfs &>/dev/null; then
                POOL=$(zfs list -H -o name / 2>/dev/null | head -1)
                if [ -n "$POOL" ]; then
                    zfs snapshot "${POOL}@${SNAP_NAME}"
                else
                    echo "WARNING: Could not determine ZFS pool for /"
                fi
            else
                echo "WARNING: zfs not available"
            fi
            ;;
        snapper)
            if command -v snapper &>/dev/null; then
                snapper create --description "$SNAP_NAME" --type pre
            else
                echo "WARNING: snapper not available"
            fi
            ;;
        *)
            echo "WARNING: Unknown snapshot type: $SNAPSHOT_TYPE"
            ;;
    esac
fi

# ── Detect filesystem ───────────────────────────────────
detect_fs() {
    local root_fs
    root_fs=$(df -T / | tail -1 | awk '{print $2}')
    case "$root_fs" in
        btrfs) echo "btrfs" ;;
        zfs)   echo "zfs" ;;
        *)     echo "dir" ;;
    esac
}

# ── Configure Incus ─────────────────────────────────────
if [ "$MODE" = "prod" ]; then
    echo "--- Production Incus configuration ---"

    # Distinguish "Incus not installed" from "daemon unreachable"
    if ! command -v incus &>/dev/null; then
        INCUS_STATE="missing"
    elif incus info &>/dev/null 2>&1; then
        INCUS_STATE="ready"
    else
        INCUS_STATE="installed"
    fi

    # Check if Incus is already initialized
    if [ "$INCUS_STATE" = "ready" ]; then
        echo "Incus already initialized."
        read -rp "Reconfigure? [y/N] " confirm
        if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
            echo "Skipping Incus configuration."
        else
            FS_TYPE=$(detect_fs)
            echo "Detected filesystem: $FS_TYPE"

            case "$FS_TYPE" in
                btrfs)
                    STORAGE_CONFIG="storage_pools:
- config:
    source: /var/lib/incus/storage-pools/default
  description: Default storage pool
  name: default
  driver: btrfs"
                    ;;
                zfs)
                    STORAGE_CONFIG="storage_pools:
- config: {}
  description: Default storage pool
  name: default
  driver: zfs"
                    ;;
                *)
                    STORAGE_CONFIG="storage_pools:
- config: {}
  description: Default storage pool
  name: default
  driver: dir"
                    ;;
            esac

            cat <<EOF | incus admin init --preseed
${STORAGE_CONFIG}

networks:
- config:
    ipv4.address: auto
    ipv6.address: auto
  description: Default network
  name: incusbr0
  type: bridge
  project: default

profiles:
- config: {}
  description: Default profile
  devices:
    eth0:
      name: eth0
      network: incusbr0
      type: nic
    root:
      path: /
      pool: default
      type: disk
  name: default

projects: []
EOF
            echo "Incus configured with $FS_TYPE storage backend."
        fi
    elif [ "$INCUS_STATE" = "installed" ]; then
        echo "Incus is installed but the daemon is not responding."
        echo "Attempting minimal initialization..."
        FS_TYPE=$(detect_fs)
        echo "Detected filesystem: $FS_TYPE"
        incus admin init --minimal
        echo "Incus initialized (minimal). Configure storage manually if needed."
    else
        echo "Installing Incus..."
        if command -v apt-get &>/dev/null; then
            apt-get update && apt-get install -y incus
        elif command -v pacman &>/dev/null; then
            pacman -Sy --noconfirm incus
        else
            echo "ERROR: Unsupported package manager. Install Incus manually."
            exit 1
        fi

        FS_TYPE=$(detect_fs)
        echo "Detected filesystem: $FS_TYPE"
        incus admin init --minimal
        echo "Incus installed and initialized (minimal). Configure storage manually if needed."
    fi

    # ── Enable br_netfilter for nftables bridge filtering ──
    echo "--- Configuring br_netfilter for bridge filtering ---"
    modprobe br_netfilter 2>/dev/null || echo "WARNING: Failed to load br_netfilter module"
    echo "br_netfilter" > /etc/modules-load.d/br_netfilter.conf 2>/dev/null || \
        echo "WARNING: Could not persist br_netfilter module (check permissions)"
    sysctl -w net.bridge.bridge-nf-call-iptables=1 >/dev/null 2>&1 || \
        echo "WARNING: Failed to set net.bridge.bridge-nf-call-iptables"
    echo "net.bridge.bridge-nf-call-iptables=1" > /etc/sysctl.d/99-anklume-bridge.conf 2>/dev/null || \
        echo "WARNING: Could not persist sysctl setting (check permissions)"
    echo "br_netfilter configured (nftables will filter bridge traffic)."

elif [ "$MODE" = "dev" ]; then
    echo "--- Development Incus configuration ---"
    if ! command -v incus &>/dev/null; then
        echo "ERROR: Incus is not installed. Install it first, then re-run bootstrap." >&2
        exit 1
    fi
    if ! incus info &>/dev/null 2>&1; then
        echo "Incus not initialized. Running minimal init..."
        incus admin init --minimal
    fi
    echo "Development mode: using existing Incus configuration."
fi

# ── Ensure user has Incus socket access ───────────────────
ensure_incus_group() {
    # Detect the Incus admin group (incus-admin on Debian/Ubuntu, incus on some distros)
    local incus_group=""
    if getent group incus-admin &>/dev/null; then
        incus_group="incus-admin"
    elif getent group incus &>/dev/null; then
        incus_group="incus"
    else
        echo "WARNING: No Incus group found (incus-admin or incus)."
        echo "         Incus socket access may require manual configuration."
        return
    fi

    # Determine the target user: if run via sudo, use the real user
    local target_user="${SUDO_USER:-$(whoami)}"

    # Skip if running as root without SUDO_USER (direct root login)
    if [ "$target_user" = "root" ]; then
        return
    fi

    # Check if user is already in the group
    if id -nG "$target_user" 2>/dev/null | grep -qw "$incus_group"; then
        echo "User '$target_user' already in group '$incus_group'."
        return
    fi

    echo "User '$target_user' is NOT in group '$incus_group'."
    echo "Adding '$target_user' to '$incus_group' for Incus socket access..."

    if [ "$(id -u)" -eq 0 ]; then
        usermod -aG "$incus_group" "$target_user"
        echo "Done. Group membership will take effect on next login or with: newgrp $incus_group"
    else
        echo "Attempting with sudo..."
        if sudo usermod -aG "$incus_group" "$target_user"; then
            echo "Done. Group membership will take effect on next login or with: newgrp $incus_group"
        else
            echo "ERROR: Failed to add '$target_user' to '$incus_group'."
            echo "       Run manually: sudo usermod -aG $incus_group $target_user"
        fi
    fi
}

if command -v incus &>/dev/null; then
    echo "--- Ensuring Incus socket access ---"
    ensure_incus_group
fi

# ── Import existing infrastructure ──────────────────────
if [ "$IMPORT" = true ]; then
    echo "--- Importing existing infrastructure ---"
    if [ -f scripts/import-infra.sh ]; then
        bash scripts/import-infra.sh
    else
        echo "WARNING: scripts/import-infra.sh not found. Skipping import."
    fi
fi

# ── Install dependencies ────────────────────────────────
echo "--- Checking dependencies ---"
MISSING=()
for cmd in ansible-playbook ansible-lint yamllint python3 pip3; do
    if ! command -v "$cmd" &>/dev/null; then
        MISSING+=("$cmd")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "Missing tools: ${MISSING[*]}"
    echo "Install with: make init"
fi

echo ""
echo "=== Bootstrap complete ==="
echo "Context: absolute_level=$ABS_LEVEL relative_level=$REL_LEVEL vm_nested=$VM_NESTED yolo=$YOLO"
echo ""
echo "Next steps:"
echo "  1. Edit infra.yml (or copy an example)"
echo "  2. make sync       # Generate Ansible files"
echo "  3. make apply      # Deploy infrastructure"
