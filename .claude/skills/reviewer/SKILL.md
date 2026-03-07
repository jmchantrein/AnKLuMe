---
name: reviewer
description: Revue de code avant commit. Utiliser avant chaque commit pour vérifier la qualité, la conformité aux ADRs, et les régressions potentielles.
disable-model-invocation: true
---

# Revue de code anklume

Tu fais la revue des changements de code dans le projet anklume avant commit.

## Checklist

### Architecture
- [ ] Respecte les ADRs dans docs/ARCHITECTURE.md
- [ ] Pas de Makefile — la CLI est la seule interface
- [ ] Pas de mélange code framework / fichiers projet utilisateur
- [ ] Le code Live ISO reste dans live/, le framework dans src/

### Python
- [ ] Pas de `sys.exit()` hors de `main()`
- [ ] Aucun fichier de plus de 200 lignes
- [ ] Pas de HTML inline dans le Python
- [ ] Pas de code mort (variables inutilisées, branches inatteignables)
- [ ] Type hints sur les fonctions publiques
- [ ] `ruff` propre

### Ansible
- [ ] FQCN sur tous les modules
- [ ] `changed_when` sémantiquement correct
- [ ] Variables de rôle préfixées avec `<nom_role>_`
- [ ] Pattern de réconciliation : lire → comparer → créer/modifier

### Shell
- [ ] `set -euo pipefail` en haut
- [ ] `shellcheck` propre

### Tests
- [ ] Le nouveau code a des tests correspondants
- [ ] Les tests décrivent le comportement spec, pas l'implémentation

### Documentation
- [ ] SPEC.md mis à jour si le comportement a changé

## Format de sortie

```
[BLOQUEUR] fichier:ligne — description
[ATTENTION] fichier:ligne — description
[SUGGESTION] fichier:ligne — description
```

Conclure par : APPROUVÉ, CHANGEMENTS REQUIS, ou DISCUSSION NÉCESSAIRE.
