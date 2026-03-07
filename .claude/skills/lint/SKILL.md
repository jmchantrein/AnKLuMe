---
name: lint
description: Lancer tous les validateurs du projet et rapporter les résultats. Utiliser après des modifications de code ou avant un commit.
disable-model-invocation: true
---

# Lint — Validation complète

Exécuter ces commandes dans l'ordre et collecter les résultats :

1. `ruff check src/ tests/ live/platform/` — lint Python
2. `ruff format --check src/ tests/ live/platform/` — format Python
3. `yamllint ansible/ labs/` — lint YAML (si yamllint installé)
4. `shellcheck live/boot/**/*.sh` — lint Shell (si shellcheck installé)
5. `ansible-lint ansible/` — lint Ansible (si ansible-lint installé)

Rapporter un tableau résumé : outil, fichiers vérifiés, pass/fail, nombre d'erreurs.
Si un validateur échoue, montrer les 5 premières erreurs.
