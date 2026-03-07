# Roadmap anklume

## Phase 1 — Squelette et spécifications ✅

- [x] Archiver le prototype (branche `poc` sur GitHub)
- [x] Reset main avec squelette propre
- [x] CLAUDE.md, SPEC.md, ARCHITECTURE.md rédigés
- [x] CLI Typer avec sous-commandes (apply all/domain, dev, instance)
- [x] `anklume init` produit le format docker-compose-like
- [x] Skills Claude Code (architect, simplify, reviewer, lint, test)
- [x] Cycle d'itération dans CLAUDE.md (démarrage de session)
- [x] Analyse critique architecture + mise à jour docs (nesting POC,
      resource policy, snapshots, dry-run, schema versioning, stateless)

## Phase 2 — Moteur PSOT ✅

- [x] Parser les fichiers domaine (`domains/*.yml`)
- [x] Valider (noms, IPs, trust levels, contraintes)
- [x] Calcul d'adressage automatique
- [x] Vérification `schema_version` + migration
- [x] Tests unitaires exhaustifs pour le moteur (80 tests)

## Phase 3 — Incus driver ✅

- [x] `engine/incus_driver.py` — wrapper typé autour de subprocess
- [x] Réconciliateur (`engine/reconciler.py`) — diff désiré vs réel
- [x] Créer projets Incus depuis les domaines
- [x] Créer réseaux (bridges) avec adressage
- [x] Créer instances (LXC/VM)
- [x] Réconciliation stateless (lire état Incus → comparer → appliquer)
- [x] `--dry-run` (afficher le plan sans appliquer)
- [x] `anklume apply all` / `anklume apply domain <nom>` fonctionnels
- [x] Tests E2E pytest (7 scénarios) + BDD E2E behave (8 scénarios)

## Prochaines phases

## Phase 4 — Snapshots ✅

- [x] `IncusSnapshot` dataclass + méthodes driver (create, list, restore, delete)
- [x] Module `engine/snapshot.py` — logique métier snapshots
- [x] Snapshots automatiques pré/post-apply (intégrés au pipeline)
- [x] `anklume snapshot create [instance] [--name X]`
- [x] `anklume snapshot list [instance]`
- [x] `anklume snapshot restore <instance> <snapshot>`
- [x] Tests unitaires : 27 tests snapshot + 7 tests driver snapshot
- [x] SPEC.md §10 détaillé (nommage, CLI, résolution, driver)

## Phase 5 — Provisioner Ansible ✅

- [x] SPEC §11 détaillé (inventaire, playbook, connexion, rôles, CLI)
- [x] `provisioner/inventory.py` — génération inventaire YAML par domaine
- [x] `provisioner/playbook.py` — génération site.yml + host_vars
- [x] `provisioner/runner.py` — exécution ansible-playbook via subprocess
- [x] Plugin de connexion `anklume_incus` (incus exec, sans dépendance externe)
- [x] Rôles embarqués (base, desktop, dev-tools)
- [x] Support `ansible_roles_custom/` utilisateur (prioritaire sur builtin)
- [x] `--no-provision` flag sur `anklume apply`
- [x] Intégré au pipeline apply (après snapshots post-apply)
- [x] Tests unitaires : 39 tests provisioner
- [x] 205 tests unitaires au total, zéro régression

#### Phase 6 — Réseau et sécurité
- [ ] Parser `policies.yml`
- [ ] Générer règles nftables
- [ ] `anklume network rules` / `anklume network deploy`

#### Phase 7 — Nesting Incus
- [x] Tests de nesting (LXC dans LXC, 5 niveaux validés)
- [ ] Préfixe de nesting (`{level:03d}-`)
- [ ] Fichiers de contexte (`/etc/anklume/`)
- [ ] Sécurité par niveau (L1 unprivileged, L2+ privilegié)

#### Phase 8 — Resource policy
- [ ] Détection hardware (CPU, mémoire)
- [ ] Allocation proportionnelle/égale par poids
- [ ] Réserve hôte, overcommit
- [ ] Modes CPU (allowance vs count) et mémoire (soft vs hard)

#### Phase 9 — Status et destroy
- [ ] `anklume status` (état réel vs déclaré)
- [ ] `anklume destroy` (avec protection ephemeral)

### Reporté (post-MVP, mais design anticipé dès maintenant)
- Live ISO — OS immuable + persistance chiffrée ZFS/BTRFS (`live/`)
- Plateforme web (`platform/`)
- Labs (`labs/`)
- Gestion distante via SSH (optionnel)
- Intégration IA (LLM, STT)
- Internationalisation (i18n)

### Contraintes Live ISO à respecter dès le core
- Chemins de données configurables
- Storage Incus sur volume chiffré (ZFS pool / BTRFS subvolume)
- `anklume apply all` idempotent (survit aux redémarrages)
- Compatible avec tout mode de boot (installé ou live)
