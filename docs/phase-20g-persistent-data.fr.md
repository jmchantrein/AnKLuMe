> La version anglaise fait foi en cas de divergence.

# Phase 20g : Persistance des donnees et protection au flush

Plan d'implementation pour les montages persistants par machine
sur l'hote (style Docker) avec protection au flush pour les
ressources non ephemeres.

## Contexte

`anklume flush` detruit tout sans distinction, y compris les instances
avec `ephemeral: false` (protegees). Les `storage_volumes` (volumes de
pool Incus) sont detruits avec le projet. Il n'existe aucun mecanisme de
persistance des donnees comparable aux bind mounts Docker. Aucune commande
ne permet de supprimer des instances individuellement.

## Trois modifications

### A) Flush respecte `ephemeral: false` (ADR-041)

`scripts/flush.sh` (155 lignes) — modifier l'etape 1 (lignes 63-75) :
- Avant chaque `incus delete`, interroger `incus config get <instance>
  security.protection.delete --project <project>`
- Si `true` et pas `FORCE` -> ignorer avec le message `PROTECTED (skipped)`
- Etape 5 (projets) : ignorer les projets qui contiennent encore des instances
- Ne jamais supprimer `/srv/anklume/data/` ni `/srv/anklume/shares/`
- Compteur `skipped` + message recapitulatif final

### B) `anklume instance remove` — suppression ciblee

Nouveau script `scripts/instance-remove.sh` (~80 lignes) :

```
anklume instance remove DOMAIN=pro SCOPE=ephemeral  # ephemeral in domain
anklume instance remove DOMAIN=pro SCOPE=all         # entire domain
anklume instance remove pro-dev                     # single instance
anklume instance remove pro-dev FORCE=true          # bypass protection
```

Logique : trouver le projet Incus via `incus list --all-projects`, verifier
`security.protection.delete`, confirmation interactive si protege.

### C) `persistent_data` par machine (ADR-040)

Syntaxe dans infra.yml :

```yaml
global:
  persistent_data_base: /srv/anklume/data   # Default

machines:
  pro-dev:
    persistent_data:
      db:
        path: /var/lib/postgresql           # Required, absolute
      config:
        path: /etc/myapp
        readonly: true                      # Optional, default: false
```

Mecanisme (identique a shared_volumes) :
- Enrichissement : `_enrich_persistent_data()` construit
  `infra["_persistent_data_devices"]`
- Source par defaut : `<base>/<domain>/<machine>/<volume>`
  (ex. `/srv/anklume/data/pro/pro-dev/db`)
- Peripherique injecte : `pd-<name>` dans `instance_devices`
  (prefixe `pd-` comme `sv-` pour les volumes partages)
- Generation : fusion pd-* + sv-* + peripheriques utilisateur dans host_vars
- Repertoires hote : `scripts/create-data-dirs.py` + `anklume setup data-dirs`
- Le role `incus_instances` gere deja les peripheriques disque arbitraires
  -> aucune modification necessaire

## Fichiers a modifier

| Fichier | Action |
|---------|--------|
| `docs/SPEC.md` | Schema `persistent_data`, section dediee, contraintes de validation, mise a jour du flush |
| `docs/ARCHITECTURE.md` | ADR-040 (donnees persistantes), ADR-041 (protection au flush) |
| `docs/SPEC-operations.md` | Mise a jour de la section Flush |
| `scripts/generate.py` | validate() +30L, `_enrich_persistent_data()` +25L, generate() fusion +10L |
| `scripts/flush.sh` | Interroger la protection avant suppression, ignorer les projets avec instances restantes |
| `scripts/instance-remove.sh` | Nouveau (~80L) |
| `scripts/create-data-dirs.py` | Nouveau (~45L) |
| `Makefile` | Cibles `data-dirs`, `instance-remove` |
| `tests/test_persistent_data.py` | Nouveau — validation + generation (~200L) |
| `tests/test_flush.py` | Ajout des tests de protection au flush |
| `tests/behavior_matrix.yml` | Cellules PD-* et FP-* |

## Ce qui ne change PAS

- `roles/incus_instances/tasks/main.yml` — gere deja les peripheriques disque
- `shared_volumes` — fonctionnalite independante, non modifiee
- `storage_volumes` — reste en tant que volumes de pool Incus (non persistants)
- `site.yml` — pas de nouveaux plays

## Validation de persistent_data (dans generate.py validate())

- Noms DNS-safe : `^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`
- `path` : requis, chemin absolu
- `readonly` : booleen si present
- `persistent_data_base` : chemin absolu si present
- Collision de peripheriques : `pd-<name>` absent des peripheriques existants
- Collision de points de montage : verification croisee avec shared_volumes
  et les autres persistent_data

## Matrice comportementale (nouveaux identifiants)

**persistent_data** : PD-001 a PD-007 (profondeur 1), PD-2-001/002
(profondeur 2), PD-3-001 (profondeur 3)

**flush_protection** : FP-001 a FP-003 (profondeur 1), FP-2-001 (profondeur 2)

## Ordre d'implementation

1. SPEC.md + ARCHITECTURE.md (specification d'abord)
2. behavior_matrix.yml
3. tests/test_persistent_data.py + mise a jour de test_flush.py
4. generate.py : validate(), _enrich_persistent_data(), generate() fusion
5. flush.sh : protection ephemere
6. instance-remove.sh + create-data-dirs.py
7. Makefile : cibles
8. `anklume dev lint && anklume dev test` -> commit

## Verification

1. `python3 -m pytest tests/test_persistent_data.py -v` -> tous passent
2. `python3 -m pytest tests/ --ignore=tests/molecule -q` -> 0 regression
3. `python3 scripts/matrix-coverage.py` -> 100% (PD + FP couverts)
4. `ruff check scripts/generate.py`
5. `shellcheck scripts/instance-remove.sh scripts/flush.sh`
