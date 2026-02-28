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
#   --skip-apply        Skip make sync && make apply after container creation
#   --no-gpu            Skip GPU detection and AI offering
#   --yes               Non-interactive mode (accept all defaults)
#   --help              Show this help

set -euo pipefail

MODE=""
SNAPSHOT_TYPE=""
YOLO=false
IMPORT=false
SKIP_APPLY=false
NO_GPU=false
NON_INTERACTIVE=false
DISTRO=""
PKG_MANAGER=""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Helpers ───────────────────────────────────────────────

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }

ask() {
    local prompt="$1" default="${2:-y}"
    if [ "$NON_INTERACTIVE" = true ]; then
        echo "$default"
        return 0
    fi
    local yn
    read -rp "$prompt [$default]: " yn
    echo "${yn:-$default}"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --prod              Production mode (auto-detect FS, configure Incus)"
    echo "  --dev               Development mode (minimal config)"
    echo "  --snapshot TYPE     Snapshot before modifications (btrfs|zfs|snapper)"
    echo "  --YOLO              Bypass security restrictions"
    echo "  --import            Import existing Incus infrastructure after setup"
    echo "  --skip-apply        Skip make sync && make apply"
    echo "  --no-gpu            Skip GPU detection and AI offering"
    echo "  --yes               Non-interactive mode (accept all defaults)"
    echo "  --help              Show this help"
    exit 0
}

# ── Distro detection ──────────────────────────────────────

detect_distro() {
    if [ ! -f /etc/os-release ]; then
        return
    fi

    local id id_like
    # shellcheck source=/dev/null
    id=$(. /etc/os-release && echo "${ID:-unknown}")
    # shellcheck source=/dev/null
    id_like=$(. /etc/os-release && echo "${ID_LIKE:-}")

    case "$id" in
        cachyos)
            DISTRO="cachyos"
            PKG_MANAGER="pacman"
            ;;
        arch|endeavouros|manjaro)
            DISTRO="arch"
            PKG_MANAGER="pacman"
            ;;
        debian)
            DISTRO="debian"
            PKG_MANAGER="apt"
            ;;
        ubuntu|linuxmint|pop)
            DISTRO="ubuntu"
            PKG_MANAGER="apt"
            ;;
        fedora|nobara)
            DISTRO="fedora"
            PKG_MANAGER="dnf"
            ;;
        *)
            # Check ID_LIKE for derivatives
            if echo "$id_like" | grep -q "arch"; then
                DISTRO="arch"
                PKG_MANAGER="pacman"
            elif echo "$id_like" | grep -q "debian\|ubuntu"; then
                DISTRO="debian"
                PKG_MANAGER="apt"
            elif echo "$id_like" | grep -q "fedora"; then
                DISTRO="fedora"
                PKG_MANAGER="dnf"
            fi
            ;;
    esac

    if [ -n "$DISTRO" ]; then
        info "Detected distro: $id (family: $DISTRO, package manager: $PKG_MANAGER)"
    fi
}

# ── Detect filesystem ─────────────────────────────────────

detect_fs() {
    local root_fs
    root_fs=$(df -T / | tail -1 | awk '{print $2}')
    case "$root_fs" in
        btrfs) echo "btrfs" ;;
        zfs)   echo "zfs" ;;
        *)     echo "dir" ;;
    esac
}

# ── Container creation ────────────────────────────────────

create_container() {
    local container_name="${1:-anklume-instance}"
    local container_os="${2:-images:debian/13}"
    local project="${3:-default}"

    if incus info "$container_name" --project "$project" &>/dev/null 2>&1; then
        ok "Container $container_name already exists"
        # Start if stopped
        local state
        state=$(incus info "$container_name" --project "$project" 2>/dev/null | grep -i "^status:" | awk '{print $2}')
        if [ "$state" != "RUNNING" ] && [ "$state" != "Running" ]; then
            info "Starting stopped container $container_name..."
            incus start "$container_name" --project "$project"
        fi
        return 0
    fi

    info "Creating container $container_name ($container_os)..."
    incus launch "$container_os" "$container_name" --project "$project"

    # Wait for IP
    info "Waiting for network..."
    local retries=0
    while [ $retries -lt 30 ]; do
        local ip
        ip=$(incus list "$container_name" --project "$project" --format csv -c 4 2>/dev/null | cut -d' ' -f1)
        if [ -n "$ip" ] && echo "$ip" | grep -q "^[0-9]"; then
            ok "Container has IP: $ip"
            return 0
        fi
        sleep 1
        retries=$((retries + 1))
    done
    warn "No IP after 30s — container may need manual DHCP"
}

# ── Device setup ──────────────────────────────────────────

setup_container_devices() {
    local container_name="${1:-anklume-instance}"
    local project="${2:-default}"

    # Socket proxy for Incus API access from inside container
    if incus config device show "$container_name" --project "$project" 2>/dev/null | grep -q "incus-socket"; then
        ok "Socket proxy already configured"
    else
        info "Adding Incus socket proxy device..."
        incus exec "$container_name" --project "$project" -- mkdir -p /var/run/incus
        incus config device add "$container_name" incus-socket proxy \
            connect=unix:/var/lib/incus/unix.socket \
            listen=unix:/var/run/incus/unix.socket \
            bind=container \
            security.uid=0 \
            security.gid=0 \
            --project "$project"
        ok "Socket proxy added"
    fi

    # Bind mount: project repo into container
    if incus config device show "$container_name" --project "$project" 2>/dev/null | grep -q "anklume-repo"; then
        ok "Repo bind mount already configured"
    else
        info "Adding repo bind mount ($PROJECT_ROOT -> /root/anklume)..."
        incus config device add "$container_name" anklume-repo disk \
            source="$PROJECT_ROOT" \
            path=/root/anklume \
            --project "$project"
        ok "Repo bind-mounted at /root/anklume"
    fi
}

# ── Container provisioning ────────────────────────────────

provision_container() {
    local container_name="${1:-anklume-instance}"
    local project="${2:-default}"
    local exec_cmd="incus exec $container_name --project $project --"

    info "Provisioning container $container_name..."
    $exec_cmd apt-get update -qq
    $exec_cmd apt-get install -y -qq \
        python3 python3-pip python3-yaml ansible \
        git jq curl ca-certificates make

    # Install pip dependencies (PEP 668 on Debian 13)
    $exec_cmd pip install --break-system-packages pyyaml 2>/dev/null || true

    ok "Container provisioned"
}

# ── First apply ───────────────────────────────────────────

first_apply() {
    local container_name="${1:-anklume-instance}"
    local project="${2:-default}"

    if [ "$SKIP_APPLY" = true ]; then
        info "Skipping first apply (--skip-apply)"
        return 0
    fi

    local exec_cmd="incus exec $container_name --project $project --"

    if $exec_cmd test -f /root/anklume/Makefile 2>/dev/null; then
        info "Running first apply (make sync && make apply)..."
        $exec_cmd bash -c "cd /root/anklume && make sync && make apply"
        ok "First apply completed"
    else
        warn "Makefile not found — skipping first apply"
        warn "Run manually: incus exec $container_name --project $project -- bash -c 'cd /root/anklume && make sync && make apply'"
    fi
}

# ── Host networking ───────────────────────────────────────

setup_host_networking() {
    info "Configuring host networking..."

    # IP forwarding
    if [ ! -f /etc/sysctl.d/99-anklume.conf ]; then
        if cat > /etc/sysctl.d/99-anklume.conf 2>/dev/null <<'SYSCTL'
net.ipv4.ip_forward=1
net.ipv4.conf.all.forwarding=1
net.bridge.bridge-nf-call-iptables=1
SYSCTL
        then
            sysctl --system > /dev/null 2>&1 || true
            ok "IP forwarding persisted"
        else
            warn "Could not write /etc/sysctl.d/99-anklume.conf (check permissions)"
        fi
    else
        ok "IP forwarding already configured"
    fi
    sysctl -w net.ipv4.ip_forward=1 > /dev/null 2>&1 || true

    # NAT masquerade via nftables (if not already managed by Incus)
    if command -v nft &>/dev/null; then
        local nft_marker="# anklume-bootstrap-managed"
        if [ -f /etc/nftables.conf ] && grep -q "$nft_marker" /etc/nftables.conf 2>/dev/null; then
            ok "nftables already configured by bootstrap"
        else
            info "nftables NAT available — Incus manages its own NAT rules"
        fi
    fi

    # DHCP checksum fix (CachyOS/Arch specific)
    if [ "$DISTRO" = "cachyos" ] || [ "$DISTRO" = "arch" ]; then
        if command -v iptables &>/dev/null; then
            if iptables -t mangle -C POSTROUTING -p udp --dport 68 -j CHECKSUM --checksum-fill 2>/dev/null; then
                ok "DHCP checksum fix already applied"
            else
                iptables -t mangle -A POSTROUTING -p udp --dport 68 -j CHECKSUM --checksum-fill 2>/dev/null || true
                ok "DHCP checksum fix applied"
            fi
        fi
    fi
}

# ── Model recommendation (VRAM-based) ────────────────────

recommend_models() {
    local vram_mb="${1:-0}"

    # No GPU or empty VRAM
    if [ -z "$vram_mb" ] || [ "$vram_mb" -eq 0 ] 2>/dev/null; then
        echo ""
        return 0
    fi

    if [ "$vram_mb" -le 8192 ]; then
        echo "qwen2.5-coder:7b nomic-embed-text"
    elif [ "$vram_mb" -le 16384 ]; then
        echo "qwen2.5-coder:14b nomic-embed-text"
    elif [ "$vram_mb" -le 24576 ]; then
        echo "qwen2.5-coder:32b nomic-embed-text"
    else
        echo "deepseek-coder-v2:latest qwen2.5-coder:32b nomic-embed-text"
    fi
}

# ── Model provisioning ──────────────────────────────────

provision_models() {
    local vram_mb="${1:-0}"
    local gpu_instance="${2:-gpu-server}"
    local project="${3:-default}"

    local recommended
    recommended=$(recommend_models "$vram_mb")

    if [ -z "$recommended" ]; then
        info "No GPU detected — skipping model provisioning"
        return 0
    fi

    info "Recommended models for ${vram_mb} MiB VRAM: $recommended"

    local models="$recommended"
    local answer
    answer=$(ask "Use recommended models? (or type your own list) [y/n]" "y")
    if echo "$answer" | grep -qi "^y"; then
        info "Using recommended models"
    elif echo "$answer" | grep -qi "^n"; then
        info "Skipping model provisioning"
        return 0
    else
        # User typed a custom model list
        models="$answer"
        info "Using custom models: $models"
    fi

    # Pull each model
    for model in $models; do
        info "Pulling model: $model ..."
        if incus exec "$gpu_instance" --project "$project" -- ollama pull "$model" 2>/dev/null; then
            ok "Model $model pulled"
        else
            warn "Could not pull $model — Ollama may not be running yet in $gpu_instance"
            warn "Pull manually later: incus exec $gpu_instance --project $project -- ollama pull $model"
        fi
    done
}

# ── GPU detection ─────────────────────────────────────────

detect_gpu() {
    if [ "$NO_GPU" = true ]; then
        return 0
    fi

    local has_nvidia=false
    local vram=""

    if command -v nvidia-smi &>/dev/null && nvidia-smi &>/dev/null; then
        has_nvidia=true
        vram=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
        ok "NVIDIA GPU detected (${vram:-unknown} MiB VRAM)"
    elif command -v lspci &>/dev/null && lspci 2>/dev/null | grep -qi nvidia; then
        has_nvidia=true
        warn "NVIDIA GPU detected but nvidia-smi not available"
    fi

    if [ "$has_nvidia" = true ]; then
        local answer
        answer=$(ask "Deploy AI-tools domain (stt_server, ollama)? [y/n]" "y")
        if echo "$answer" | grep -qi "^y"; then
            info "AI-tools will be deployed on next 'make apply'"

            # Offer model provisioning if VRAM was detected
            if [ -n "$vram" ] && [ "$vram" -gt 0 ] 2>/dev/null; then
                local provision_answer
                provision_answer=$(ask "Pre-download AI models based on GPU VRAM? [y/n]" "y")
                if echo "$provision_answer" | grep -qi "^y"; then
                    provision_models "$vram"
                fi
            fi
        else
            info "Skipping AI-tools deployment"
        fi
    fi
}

# ── Boot services ─────────────────────────────────────────

setup_boot_services() {
    local boot_script="$PROJECT_ROOT/host/boot/setup-boot-services.sh"

    if [ -x "$boot_script" ]; then
        info "Running setup-boot-services.sh..."
        bash "$boot_script"
        ok "Boot services configured"
    else
        info "setup-boot-services.sh not found — skipping"
    fi
}

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

# ── Main ──────────────────────────────────────────────────

main() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --prod)       MODE="prod"; shift ;;
            --dev)        MODE="dev"; shift ;;
            --snapshot)   SNAPSHOT_TYPE="$2"; shift 2 ;;
            --YOLO)       YOLO=true; shift ;;
            --import)     IMPORT=true; shift ;;
            --skip-apply) SKIP_APPLY=true; shift ;;
            --no-gpu)     NO_GPU=true; shift ;;
            --yes|-y)     NON_INTERACTIVE=true; shift ;;
            --help|-h)    usage ;;
            *)            echo "Unknown option: $1"; usage ;;
        esac
    done

    if [ -z "$MODE" ]; then
        echo "ERROR: Specify --prod or --dev"
        usage
    fi

    # Detect distro early (used by networking and package install)
    detect_distro

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

    # ── Create shared_volumes base directory ─────────────────
    mkdir -p /srv/anklume/shares

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
            local confirm
            if [ "$NON_INTERACTIVE" = true ]; then
                confirm="n"
            else
                read -rp "Reconfigure? [y/N] " confirm
            fi
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
            case "$PKG_MANAGER" in
                apt)
                    local codename
                    # shellcheck source=/dev/null
                    codename=$(. /etc/os-release && echo "${VERSION_CODENAME:-bookworm}")
                    # Trixie+ has Incus in official repos; older releases use backports
                    if apt-cache show incus >/dev/null 2>&1; then
                        info "Incus available in Debian repos"
                        apt-get update && apt-get install -y incus
                    else
                        info "Adding Debian backports for Incus"
                        echo "deb http://deb.debian.org/debian ${codename}-backports main" \
                            > /etc/apt/sources.list.d/backports.list
                        apt-get update && apt-get install -y -t "${codename}-backports" incus
                    fi
                    ;;
                pacman)
                    pacman -Sy --noconfirm incus
                    ;;
                dnf)
                    dnf install -y incus
                    ;;
                *)
                    if command -v apt-get &>/dev/null; then
                        apt-get update && apt-get install -y incus
                    elif command -v pacman &>/dev/null; then
                        pacman -Sy --noconfirm incus
                    else
                        echo "ERROR: Unsupported package manager. Install Incus manually."
                        exit 1
                    fi
                    ;;
            esac

            FS_TYPE=$(detect_fs)
            echo "Detected filesystem: $FS_TYPE"
            incus admin init --minimal
            echo "Incus installed and initialized (minimal). Configure storage manually if needed."
        fi

        # ── Enable br_netfilter for nftables bridge filtering ──
        info "Configuring br_netfilter for bridge filtering..."
        modprobe br_netfilter 2>/dev/null || warn "Failed to load br_netfilter module"
        echo "br_netfilter" > /etc/modules-load.d/anklume.conf 2>/dev/null || \
            warn "Could not persist br_netfilter module"
        sysctl -w net.bridge.bridge-nf-call-iptables=1 >/dev/null 2>&1 || \
            warn "Failed to set net.bridge.bridge-nf-call-iptables"
        ok "br_netfilter configured (nftables will filter bridge traffic)"

        # ── Container creation (prod only) ──────────────────────
        create_container "anklume-instance"

        # ── Device setup ────────────────────────────────────────
        setup_container_devices "anklume-instance"

        # ── Provisioning ────────────────────────────────────────
        provision_container "anklume-instance"

        # ── Host networking ─────────────────────────────────────
        setup_host_networking

        # ── First apply ─────────────────────────────────────────
        first_apply "anklume-instance"

        # ── GPU detection ───────────────────────────────────────
        detect_gpu

        # ── Boot services ───────────────────────────────────────
        setup_boot_services

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
    for cmd in ansible-playbook ansible-lint yamllint python3; do
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
}

main "$@"
