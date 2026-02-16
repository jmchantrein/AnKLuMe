#!/usr/bin/env bash
# install-incus-guard.sh — Install the Incus network guard as a systemd override
#
# Creates a systemd drop-in for incus.service that runs
# incus-network-guard.sh after every Incus startup.
set -euo pipefail

GUARD_SCRIPT="/opt/anklume/incus-network-guard.sh"
DROPIN_DIR="/etc/systemd/system/incus.service.d"
DROPIN_FILE="$DROPIN_DIR/network-guard.conf"

echo "Installing Incus network guard..."

# Copy guard script to a stable location
install -Dm755 "$(dirname "$0")/incus-network-guard.sh" "$GUARD_SCRIPT"

# Create systemd drop-in
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN_FILE" << 'EOF'
[Service]
ExecStartPost=/opt/anklume/incus-network-guard.sh
EOF

# Reload systemd
systemctl daemon-reload

echo "Installed:"
echo "  Guard script: $GUARD_SCRIPT"
echo "  Systemd drop-in: $DROPIN_FILE"
echo ""
echo "The guard will run automatically after every Incus startup."
echo "It removes any Incus bridge that conflicts with the host network."
