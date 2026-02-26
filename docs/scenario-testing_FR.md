# Tests de scenarios end-to-end (BDD)

> Note : la version anglaise ([`scenario-testing.md`](scenario-testing.md)) fait reference en cas de divergence.

anklume inclut des scenarios d'acceptation lisibles par un humain qui
testent des workflows utilisateur complets contre une infrastructure
Incus reelle. Les scenarios sont ecrits au format Gherkin avec
`pytest-bdd`.

## Demarrage rapide

```bash
anklume dev scenario          # Tous les scenarios
anklume dev scenario --best     # Bonnes pratiques uniquement
anklume dev scenario --bad      # Mauvaises pratiques uniquement
anklume dev scenario --list          # Lister les scenarios disponibles
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
├── best_practices/              # Workflows recommandes
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
├── conftest.py                  # Definitions des steps + fixtures
└── pitfalls.yml                 # Base de donnees des pieges pour guide.sh
```

## Deux categories

### Bonnes pratiques

Valident les workflows recommandes. Ces scenarios servent de
documentation vivante sur la bonne utilisation d'anklume :

- **Pro workstation setup** : Deploiement complet avec isolation reseau
- **Student lab deploy** : Un enseignant deploie un environnement de TP
- **Snapshot restore cycle** : Snapshot avant modification, restauration en cas d'echec
- **Sync idempotency** : Executer sync deux fois donne le meme resultat
- **Validation before apply** : Toujours linter apres sync

### Mauvaises pratiques

Verifient qu'anklume detecte les erreurs tot avec des messages clairs :

- **Apply without sync** : Pas de fichiers d'inventaire, inventaire obsolete
- **Duplicate IPs** : Le generateur rejette les adresses IP dupliquees
- **Delete protected instance** : Flush sans FORCE en production
- **Edit managed sections** : Contenu ecrase par sync
- **Forget nftables-deploy** : Nouveau domaine non isole
- **Wrong operation order** : Etapes du workflow manquees

## Ecrire des scenarios

Les scenarios utilisent la syntaxe Gherkin avec des steps
`Given/When/Then` :

```gherkin
# Matrix: XX-NNN
Feature: Nom descriptif
  Explication de ce que ce scenario teste.

  Background:
    Given a clean sandbox environment

  Scenario: Cas de test specifique
    Given infra.yml from "student-sysadmin"
    When I run "anklume sync"
    Then exit code is 0
    And inventory files exist for all domains
```

### Steps disponibles

**Given** (preconditions) :
- `a clean sandbox environment` -- verifier le repertoire du projet anklume
- `images are pre-cached via shared repository` -- ignorer si pas d'Incus
- `infra.yml from "<example>"` -- copier un exemple d'infra.yml
- `infra.yml exists but no inventory files` -- simuler un sync manquant
- `a running infrastructure` -- ignorer si pas d'instances en cours
- `infra.yml with two machines sharing "<ip>"` -- test d'IP dupliquee
- `infra.yml with managed section content in "<file>"` -- verifier le fichier

**When** (actions) :
- `I run "<command>"` -- executer une commande shell
- `I run "<command>" and it may fail` -- commande attendue en echec
- `I add a domain "<name>" to infra.yml` -- modifier infra.yml
- `I edit the managed section in "<file>"` -- injecter du contenu

**Then** (assertions) :
- `exit code is 0` / `exit code is non-zero`
- `output contains "<text>"` / `stderr contains "<text>"`
- `inventory files exist for all domains`
- `file "<path>" exists` / `file "<path>" does not exist`
- `all declared instances are running`
- `intra-domain connectivity works`
- `inter-domain connectivity is blocked`
- `no Incus resources were created`
- `the managed section in "<file>" is unchanged`

### Annotations Matrix

Liez les scenarios aux IDs de la matrice comportementale pour le suivi
de couverture :

```gherkin
# Matrix: DL-001, NI-002
Feature: ...
```

L'outil `scripts/matrix-coverage.py` scanne ces annotations.

## Integration avec le guide

Les scenarios de mauvaises pratiques alimentent le guide interactif
(`scripts/guide.sh`). Le fichier `scenarios/pitfalls.yml` associe
chaque piege a une etape du guide et un message d'avertissement.

Le guide affiche des avertissements proactifs aux etapes concernees :
- Etape 3 (edition infra.yml) : sections gerees, IPs dupliquees
- Etape 4 (generation) : ordre correct du workflow
- Etape 6 (application) : verification inventaire, rappel nftables

## Dependances

```bash
pip install pytest-bdd
```

pytest-bdd est liste dans `pyproject.toml` sous
`[project.optional-dependencies]`.

## Notes d'execution

- Les scenarios sont **a la demande uniquement** -- pas dans la CI
- Certains scenarios necessitent un daemon Incus (ignores sinon)
- Les scenarios de deploiement en bonnes pratiques peuvent prendre
  plusieurs minutes
- Le pre-cache d'images via la Phase 18e reduit la latence de demarrage
