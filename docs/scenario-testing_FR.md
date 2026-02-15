> **Note** : La version anglaise (`scenario-testing.md`) fait foi en
> cas de divergence.

# Tests de scénarios end-to-end (BDD)

AnKLuMe inclut des scénarios d'acceptation lisibles par un humain qui
testent des workflows utilisateur complets contre une infrastructure
Incus réelle. Les scénarios sont écrits au format Gherkin avec
`pytest-bdd`.

## Démarrage rapide

```bash
make scenario-test          # Tous les scénarios
make scenario-test-best     # Bonnes pratiques uniquement
make scenario-test-bad      # Mauvaises pratiques uniquement
make scenario-list          # Lister les scénarios disponibles
```

Ou directement avec pytest :

```bash
python3 -m pytest scenarios/ -v --tb=long
python3 -m pytest scenarios/best_practices/ -v
python3 -m pytest scenarios/bad_practices/ -v -k "duplicate"
```

## Architecture

```
scenarios/
├── best_practices/              # Workflows recommandés
│   ├── pro_workstation_setup.feature
│   ├── student_lab_deploy.feature
│   ├── snapshot_restore_cycle.feature
│   ├── sync_idempotency.feature
│   └── validation_before_apply.feature
├── bad_practices/               # Erreurs courantes
│   ├── apply_without_sync.feature
│   ├── duplicate_ips.feature
│   ├── delete_protected_instance.feature
│   ├── edit_managed_sections.feature
│   ├── forget_nftables_deploy.feature
│   └── wrong_operation_order.feature
├── conftest.py                  # Définitions des steps + fixtures
└── pitfalls.yml                 # Base de données des pièges pour guide.sh
```

## Deux catégories

### Bonnes pratiques

Valident les workflows recommandés. Ces scénarios servent de
documentation vivante sur la bonne utilisation d'AnKLuMe :

- **Pro workstation setup** : Déploiement complet avec isolation réseau
- **Student lab deploy** : Un enseignant déploie un environnement de TP
- **Snapshot restore cycle** : Snapshot avant modification, restauration
- **Sync idempotency** : Exécuter sync deux fois donne le même résultat
- **Validation before apply** : Toujours linter après sync

### Mauvaises pratiques

Vérifient qu'AnKLuMe détecte les erreurs tôt avec des messages clairs :

- **Apply without sync** : Pas de fichiers d'inventaire, inventaire obsolète
- **Duplicate IPs** : Le générateur rejette les adresses IP dupliquées
- **Delete protected instance** : Flush sans FORCE en production
- **Edit managed sections** : Contenu écrasé par sync
- **Forget nftables-deploy** : Nouveau domaine non isolé
- **Wrong operation order** : Étapes du workflow manquées

## Écrire des scénarios

Les scénarios utilisent la syntaxe Gherkin avec des steps
`Given/When/Then` :

```gherkin
# Matrix: XX-NNN
Feature: Nom descriptif
  Explication de ce que ce scénario teste.

  Background:
    Given a clean sandbox environment

  Scenario: Cas de test spécifique
    Given infra.yml from "student-sysadmin"
    When I run "make sync"
    Then exit code is 0
    And inventory files exist for all domains
```

### Annotations Matrix

Liez les scénarios aux IDs de la matrice comportementale :

```gherkin
# Matrix: DL-001, NI-002
Feature: ...
```

## Intégration avec le guide

Les scénarios de mauvaises pratiques alimentent le guide interactif
(`scripts/guide.sh`). Le fichier `scenarios/pitfalls.yml` associe
chaque piège à une étape du guide et un message d'avertissement.

Le guide affiche des avertissements proactifs aux étapes concernées :
- Étape 3 (édition infra.yml) : sections gérées, IPs dupliquées
- Étape 4 (génération) : ordre correct du workflow
- Étape 6 (application) : vérification inventaire, rappel nftables

## Dépendances

```bash
pip install pytest-bdd
```

## Notes d'exécution

- Les scénarios sont **à la demande uniquement** — pas dans la CI
- Certains scénarios nécessitent un démon Incus (ignorés sinon)
- Les scénarios de déploiement peuvent prendre plusieurs minutes
- Le pré-cache d'images (Phase 18e) réduit la latence de démarrage
