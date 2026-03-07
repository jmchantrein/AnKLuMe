---
name: simplify
description: Analyser le code modifié pour détecter le sur-engineering, puis corriger. Utiliser après avoir ajouté des fonctionnalités pour vérifier qu'on n'a pas sur-conçu.
---

# Simplifier — Détection du sur-engineering

1. Lancer `git diff --name-only HEAD~1` pour trouver les fichiers modifiés
2. Pour chaque fichier modifié, vérifier :
   - Le nouveau code peut-il réutiliser des utilitaires existants ?
   - Y a-t-il des abstractions pour des opérations ponctuelles ?
   - Y a-t-il de la gestion d'erreurs pour des scénarios impossibles ?
   - Y a-t-il des commentaires expliquant du code évident ?
   - Y a-t-il du code mort ou des imports inutilisés ?
3. Corriger les problèmes trouvés, en gardant les changements minimaux
4. Lancer `/lint` et `/test` pour vérifier
