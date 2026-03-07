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

## Phase actuelle : 3 — Incus driver

### En cours
- [ ] `engine/incus_driver.py` — wrapper typé autour de subprocess
- [ ] Réconciliateur (`engine/reconciler.py`) — diff désiré vs réel
- [ ] Créer projets Incus depuis les domaines
- [ ] Créer réseaux (bridges) avec adressage
- [ ] Créer instances (LXC/VM)
- [ ] Réconciliation stateless (lire état Incus → comparer → appliquer)
- [ ] `--dry-run` (afficher le plan sans appliquer)
- [ ] `anklume apply all` / `anklume apply domain <nom>` fonctionnels

### Prochaines phases

#### Phase 4 — Snapshots
- [ ] Snapshots automatiques pré/post-apply
- [ ] `anklume snapshot create [instance]`
- [ ] `anklume snapshot list`
- [ ] `anklume snapshot restore <nom>`

#### Phase 5 — Provisioner Ansible
- [ ] Générer inventaire + group_vars + host_vars
- [ ] Lancer `ansible-playbook` sur les instances créées
- [ ] Rôles embarqués (base, desktop, dev-tools)
- [ ] Support `ansible_roles_custom/` utilisateur

#### Phase 6 — Réseau et sécurité
- [ ] Parser `policies.yml`
- [ ] Générer règles nftables
- [ ] `anklume network rules` / `anklume network deploy`

#### Phase 7 — Nesting Incus
- [ ] Préfixe de nesting (`{level:03d}-`)
- [ ] Fichiers de contexte (`/etc/anklume/`)
- [ ] Sécurité par niveau (L1 unprivileged, L2+ privilegié)
- [ ] Tests de nesting (LXC dans LXC, VM dans LXC)

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
