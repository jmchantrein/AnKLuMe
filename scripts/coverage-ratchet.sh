#!/usr/bin/env bash
# Coverage ratcheting : le seuil ne peut que monter.
# Usage : scripts/coverage-ratchet.sh
set -euo pipefail

THRESHOLD_FILE=".coverage-threshold"

if [[ ! -f "$THRESHOLD_FILE" ]]; then
    echo "Fichier $THRESHOLD_FILE introuvable. Initialisation a 70."
    echo 70 > "$THRESHOLD_FILE"
fi

stored=$(cat "$THRESHOLD_FILE" | tr -d '[:space:]')

# Lancer pytest avec couverture
uv run pytest tests/ --cov --cov-report=term -q --tb=line \
    --ignore=tests/e2e --ignore=tests/test_e2e_real.py \
    -m "not real and not slow" 2>&1 | tee /tmp/cov-output.txt

# Extraire le pourcentage total (derniere ligne TOTAL)
current=$(grep '^TOTAL' /tmp/cov-output.txt | awk '{print $NF}' | tr -d '%')

if [[ -z "$current" ]]; then
    echo "ERREUR: impossible d'extraire le pourcentage de couverture."
    exit 1
fi

echo ""
echo "Couverture actuelle : ${current}%  (seuil : ${stored}%)"

if (( current >= stored )); then
    if (( current > stored )); then
        echo "$current" > "$THRESHOLD_FILE"
        echo "Seuil mis a jour : ${stored}% -> ${current}%"
    else
        echo "Seuil inchange (${stored}%)."
    fi
    exit 0
else
    echo "ECHEC: couverture ${current}% < seuil ${stored}%"
    exit 1
fi
