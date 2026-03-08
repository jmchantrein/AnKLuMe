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

## Phase 6 — Réseau et sécurité nftables ✅

- [x] Parser `policies.yml` (existant depuis Phase 2 — parser.py + validator.py)
- [x] SPEC §12 détaillé (philosophie, structure nftables, résolution cibles, CLI)
- [x] `engine/nftables.py` — génération ruleset nftables (drop-all + allow sélectif)
- [x] Résolution de cibles : domaine (bridge), machine (bridge + IP), host (commentaire)
- [x] Support : bidirectionnel, UDP, ports "all", domaines désactivés
- [x] `anklume network rules` — affiche le ruleset sur stdout
- [x] `anklume network deploy` — applique via `nft -f`
- [x] Tests unitaires : 30 tests nftables
- [x] 233 tests unitaires au total, zéro régression

## Phase 7 — Nesting Incus ✅

- [x] Tests de nesting (LXC dans LXC, 5 niveaux validés)
- [x] SPEC §8 détaillé (détection, préfixes, contexte, sécurité, module)
- [x] `engine/nesting.py` — NestingContext, préfixes, sécurité, fichiers de contexte
- [x] Détection du contexte via `/etc/anklume/` (absolute_level, relative_level, vm_nested, yolo)
- [x] Préfixe de nesting (`{level:03d}-`) intégré au réconciliateur
- [x] Fichiers de contexte injectés dans les instances après démarrage
- [x] Sécurité par niveau (L0→L1 unprivileged+syscalls, L1+→L2+ privilegié)
- [x] Config explicite machine override la config nesting
- [x] `instance_exec` ajouté au driver Incus
- [x] Tests unitaires : 47 tests nesting + zéro régression réconciliateur
- [x] 280 tests unitaires au total, zéro régression

## Phase 8 — Resource policy ✅

- [x] SPEC §9 détaillé (détection, réserve, algorithme, modes, overcommit, intégration, CLI)
- [x] `engine/resources.py` — détection hardware (Incus + fallback /proc/)
- [x] Allocation proportionnelle/égale par poids (`weight`)
- [x] Réserve hôte (pourcentage ou absolu), overcommit (warning vs erreur)
- [x] Modes CPU : allowance (%) et count (vCPUs fixes)
- [x] Modes mémoire : soft (ballooning) et hard (limite stricte)
- [x] Exclusion des machines avec config explicite (par ressource)
- [x] `apply_resource_config` enrichit machine.config avant réconciliation
- [x] Tests unitaires : 44 tests resource policy
- [x] 325 tests unitaires au total, zéro régression

## Phase 9 — Status et destroy ✅

- [x] SPEC §13 détaillé (status : comparaison déclaré/réel, destroy : protection ephemeral, --force, dry-run)
- [x] `engine/status.py` — compute_status, InfraStatus, DomainStatus, InstanceStatus
- [x] `engine/destroy.py` — destroy, DestroyAction, DestroyResult, protection ephemeral
- [x] Driver Incus : `instance_config_set`, `network_delete`, `project_delete`
- [x] `anklume status` — tableau par domaine (projet, réseau, instances, sync)
- [x] `anklume destroy` — suppression avec respect ephemeral, `--force` pour tout détruire
- [x] Support nesting (préfixes) pour status et destroy
- [x] Dry-run destroy (plan sans exécuter)
- [x] Tests unitaires : 12 tests status + 18 tests destroy
- [x] 364 tests au total, zéro régression

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
