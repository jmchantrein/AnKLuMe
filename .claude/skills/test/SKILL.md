---
name: test
description: Lancer la suite de tests et rapporter les résultats. Utiliser après des modifications de code.
disable-model-invocation: true
---

# Test — Suite de tests

Exécuter : `python -m pytest tests/ -x -q --tb=short`

Si des tests échouent :
1. Afficher le nom du test et l'erreur
2. Lire le fichier source concerné
3. Proposer un correctif

Si tous les tests passent, rapporter le décompte.
