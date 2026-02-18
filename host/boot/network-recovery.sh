#!/usr/bin/env bash
# network-recovery.sh — Restauration réseau d'urgence
# Usage: sudo bash network-recovery.sh
#
# Lance ce script si tu perds la connectivité réseau après une manipulation.
# Il restaure nftables, le NAT, l'IP forwarding et le DHCP checksum fix.
#
# Configuration (variables d'environnement) :
#   ANKLUME_SUBNET — Sous-réseau Incus à NATer (défaut: détecté via bridges)
#   LAN_GATEWAY    — Gateway LAN (défaut: détectée via route par défaut)
#   LAN_IFACE      — Interface WAN (défaut: détectée via route par défaut)

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

info()  { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${RED}[!!]${NC} $*"; }

# ── Auto-détection ────────────────────────────────────────
# Detect Incus subnet from bridge addresses (fallback to common default)
if [[ -z "${ANKLUME_SUBNET:-}" ]]; then
    BRIDGE_IP=$(ip -4 addr show | grep -oP '(?<=inet )10\.\d+\.\d+\.\d+' | head -1)
    if [[ -n "$BRIDGE_IP" ]]; then
        ANKLUME_SUBNET="${BRIDGE_IP%.*.*}.0.0/16"
    else
        warn "Impossible de détecter le sous-réseau Incus. Définir ANKLUME_SUBNET."
        exit 1
    fi
fi

# Detect LAN gateway and interface from current default route
if [[ -z "${LAN_GATEWAY:-}" ]] || [[ -z "${LAN_IFACE:-}" ]]; then
    DEFAULT_ROUTE=$(ip route show default 2>/dev/null | head -1)
    LAN_GATEWAY="${LAN_GATEWAY:-$(echo "$DEFAULT_ROUTE" | grep -oP '(?<=via )\S+')}"
    LAN_IFACE="${LAN_IFACE:-$(echo "$DEFAULT_ROUTE" | grep -oP '(?<=dev )\S+')}"
fi

echo "=== Récupération réseau d'urgence ==="
echo "  Subnet Incus : $ANKLUME_SUBNET"
echo "  Gateway LAN  : ${LAN_GATEWAY:-non détectée}"
echo "  Interface WAN : ${LAN_IFACE:-non détectée}"
echo ""

# ── 1. IP Forwarding ────────────────────────────────────
sysctl -w net.ipv4.ip_forward=1 >/dev/null 2>&1
info "IP forwarding activé"

# ── 2. Restaurer nftables ───────────────────────────────
nft flush ruleset 2>/dev/null

nft -f - <<NFTEOF
table inet filter {
    chain input {
        type filter hook input priority filter; policy drop;
        ct state established,related accept
        iif lo accept
        iifname "incusbr*" accept
        iifname "net-*" accept
        ip protocol icmp accept
        tcp dport ssh accept
    }
    chain forward {
        type filter hook forward priority filter; policy accept;
    }
}

table ip nat {
    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        ip saddr $ANKLUME_SUBNET counter masquerade
    }
}
NFTEOF
info "Règles nftables restaurées"

# ── 3. DHCP Checksum fix (CachyOS/Arch) ──────────────────
if iptables -t mangle -C POSTROUTING -p udp --dport 68 -j CHECKSUM --checksum-fill 2>/dev/null; then
    info "Règle DHCP checksum déjà présente"
else
    iptables -t mangle -A POSTROUTING -p udp --dport 68 -j CHECKSUM --checksum-fill 2>/dev/null
    info "Règle DHCP checksum ajoutée"
fi

# ── 4. Vérifier la gateway par défaut ───────────────────
if [[ -n "${LAN_GATEWAY:-}" ]]; then
    if ip route | grep -q "default via $LAN_GATEWAY"; then
        info "Route par défaut OK ($LAN_GATEWAY via ${LAN_IFACE:-?})"
    else
        warn "Route par défaut absente, tentative de restauration..."
        ip route add default via "$LAN_GATEWAY" ${LAN_IFACE:+dev "$LAN_IFACE"} 2>/dev/null || true
        if ip route | grep -q "default"; then
            info "Route par défaut restaurée"
        else
            warn "ÉCHEC restauration route. Vérifie manuellement: ip route"
        fi
    fi
else
    warn "Gateway LAN non détectée — vérification manuelle requise"
fi

# ── 5. Vérifier la connectivité ─────────────────────────
echo ""
echo "=== Tests de connectivité ==="

if [[ -n "${LAN_GATEWAY:-}" ]]; then
    if ping -c 1 -W 3 "$LAN_GATEWAY" >/dev/null 2>&1; then
        info "Gateway LAN joignable"
    else
        warn "Gateway LAN injoignable — vérifie ${LAN_IFACE:-l'interface réseau}"
    fi
fi

if ping -c 1 -W 3 8.8.8.8 >/dev/null 2>&1; then
    info "Internet (IP) OK"
else
    warn "Pas de connectivité Internet"
fi

if ping -c 1 -W 3 google.com >/dev/null 2>&1; then
    info "DNS OK"
else
    warn "Résolution DNS en échec"
fi

echo ""
echo "=== Récupération terminée ==="
