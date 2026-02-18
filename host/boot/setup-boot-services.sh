#!/usr/bin/env bash
# setup-boot-services.sh — Configuration unique pour que tout fonctionne au boot
#
# À lancer UNE FOIS avec : sudo bash /home/anklume/claude/setup-boot-services.sh
#
# Ce script configure :
#   1. Module uinput chargé au boot (pour ydotool)
#   2. Permissions /dev/uinput pour le groupe input
#   3. Autostart du conteneur Incus anklume-instance

set -euo pipefail

echo "=== 1/3 : Module uinput au boot ==="
if ! grep -qx "uinput" /etc/modules-load.d/*.conf 2>/dev/null; then
    echo "uinput" > /etc/modules-load.d/uinput.conf
    echo "  → /etc/modules-load.d/uinput.conf créé"
else
    echo "  → Déjà configuré"
fi

# Charger immédiatement si pas encore chargé
if ! lsmod | grep -q "^uinput"; then
    modprobe uinput
    echo "  → Module uinput chargé"
fi

echo ""
echo "=== 2/3 : Permissions /dev/uinput ==="
# Remplacer la règle incomplète par celle avec static_node
cat > /etc/udev/rules.d/80-uinput.rules << 'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660", OPTIONS+="static_node=uinput"
EOF
echo "  → /etc/udev/rules.d/80-uinput.rules mis à jour (avec static_node)"

# Appliquer immédiatement
udevadm control --reload-rules
udevadm trigger /dev/uinput
echo "  → Règle appliquée"

# Vérifier
sleep 0.5
PERMS=$(stat -c '%a %G' /dev/uinput)
echo "  → /dev/uinput : $PERMS"

echo ""
echo "=== 3/3 : Autostart conteneur Incus ==="
if command -v incus &>/dev/null; then
    incus config set anklume-instance boot.autostart true 2>/dev/null && \
        echo "  → anklume-instance : boot.autostart=true" || \
        echo "  → ERREUR: impossible de configurer autostart (conteneur existe ?)"
else
    echo "  → incus non trouvé, ignoré"
fi

echo ""
echo "=== Terminé ==="
echo "ydotoold devrait redémarrer automatiquement dans quelques secondes."
echo "Vérification : systemctl --user status ydotoold"
