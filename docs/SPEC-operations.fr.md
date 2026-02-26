# SPEC-operations.md -- Reference operationnelle anklume

> Traduction francaise de [`SPEC-operations.md`](SPEC-operations.md). En cas de divergence, la version anglaise fait foi.

Ce fichier contient les details d'implementation et operationnels extraits
de SPEC.md. Pour la specification principale (vision, concepts, modele PSOT,
format infra.yml), voir [SPEC.fr.md](SPEC.fr.md).

## 6. Generateur (scripts/generate.py)

Lit `infra.yml` et genere/met a jour l'arborescence de fichiers Ansible.

### Fichiers generes

```
inventory/<domain>.yml      # Hotes pour ce domaine
group_vars/all.yml          # Variables globales
group_vars/<domain>.yml     # Variables au niveau du domaine
host_vars/<machine>.yml     # Variables specifiques a la machine
```

### Modele de sections gerees

```yaml
# === MANAGED BY infra.yml ===
# Do not edit this section — it will be overwritten by `anklume sync`
incus_network:
  name: net-example
  subnet: 10.100.0.0/24   # Zone-aware: 10.<zone_base+offset>.<seq>.0/24
  gateway: 10.100.0.254
# === END MANAGED ===

# Your custom variables below:
```

### Comportement du generateur

1. **Fichier absent** -- cree avec une section geree + commentaires utiles
2. **Fichier existant** -- seule la section geree est reecrite, le reste est preserve
3. **Orphelins** -- listes dans un rapport, suppression interactive proposee
4. **Validation** -- toutes les contraintes sont verifiees avant d'ecrire un fichier

### Formats d'entree

Le generateur accepte deux formats d'entree :

- **Fichier unique** : `scripts/generate.py infra.yml` -- mode traditionnel
- **Repertoire** : `scripts/generate.py infra/` -- fusion automatique des fichiers

En mode repertoire, le generateur :
1. Charge `infra/base.yml` (requis : project_name, global)
2. Fusionne tous les fichiers `infra/domains/*.yml` (tries alphabetiquement)
3. Fusionne `infra/policies.yml` s'il existe
4. Valide la structure fusionnee de maniere identique au mode fichier unique
5. Les messages d'erreur incluent le nom du fichier source pour le debogage

### Variables de connection

`default_connection` et `default_user` de la section `global:` d'`infra.yml`
sont stockes dans `group_vars/all.yml` sous les noms `psot_default_connection`
et `psot_default_user` (a titre informatif uniquement). Les playbooks peuvent
referencer ces valeurs si necessaire.

Ils ne sont **PAS** generes comme `ansible_connection` ou `ansible_user` dans
aucun fichier genere. Justification : les variables d'inventaire Ansible
ecrasent les mots-cles au niveau du play ([precedence des variables](https://docs.ansible.com/ansible/latest/reference_appendices/general_precedence.html)).
Si `ansible_connection: community.general.incus` apparaissait dans les
group_vars d'un domaine, cela ecraserait `connection: local` dans le
playbook, ce qui amenerait les roles d'infrastructure a tenter de se
connecter a des containers qui n'existent pas encore. La connection est
une preoccupation operationnelle du playbook, pas une propriete declarative
de l'infrastructure.

## 7. Roles Ansible

### Phase 1 : Infrastructure (connection: local, cible : localhost)

| Role | Responsabilite | Tags |
|------|---------------|------|
| `incus_networks` | Creer/reconcilier les bridges | `networks`, `infra` |
| `incus_projects` | Creer/reconcilier les projets + profil par defaut | `projects`, `infra` |
| `incus_profiles` | Creer les profils supplementaires (GPU, imbrication) | `profiles`, `infra` |
| `incus_instances` | Creer/gerer les instances LXC + VM | `instances`, `infra` |
| `incus_nftables` | Generer les regles d'isolation inter-bridges | `nftables`, `infra` |
| `incus_firewall_vm` | Profil multi-NIC pour la VM pare-feu | `firewall`, `infra` |
| `incus_images` | Pre-telecharger les images OS en cache | `images`, `infra` |
| `incus_snapshots` | Gestion declarative des snapshots | `snapshots`, `infra` |

### Phase 2 : Provisionnement (connection: community.general.incus)

| Role | Responsabilite | Tags |
|------|---------------|------|
| `base_system` | Paquets de base, locale, fuseau horaire, utilisateur | `provision`, `base` |
| `ollama_server` | Serveur d'inference LLM Ollama | `provision`, `llm` |
| `open_webui` | Interface de chat Open WebUI | `provision`, `webui` |
| `stt_server` | Serveur STT Speaches (faster-whisper) | `provision`, `stt` |
| `lobechat` | Interface web multi-fournisseurs LobeChat | `provision`, `lobechat` |
| `opencode_server` | Serveur de codage IA headless OpenCode | `provision`, `opencode` |
| `firewall_router` | Routage nftables dans la VM pare-feu | `provision`, `firewall` |
| `dev_test_runner` | Provisionnement du bac a sable Incus-dans-Incus | `provision`, `test` |
| `admin_bootstrap` | Bootstrap de l'outillage admin dans anklume-instance | `provision`, `bootstrap` |
| `dev_agent_runner` | Configuration du lanceur d'agents IA | `provision`, `agent` |
| `code_sandbox` | Bac a sable de codage IA (Claude Code, Aider, etc.) | `provision`, `sandbox` |
| `openclaw_server` | Serveur d'agents OpenClaw | `provision`, `openclaw` |
| (defini par l'utilisateur) | Configuration specifique a l'application | `provision` |

### Notes d'implementation des roles

**`incus_instances`** (ADR-017) : La variable `instance_type` (issue de
`type: lxc|vm` dans infra.yml) determine le comportement :
- `incus launch` passe `--vm` quand `instance_type == 'vm'`
- Les instances VM peuvent necessiter des profils par defaut differents
  (ex. `agent.nic.enp5s0.mode` pour la configuration reseau). Concerne
  la Phase 8+.
- Le GPU dans les VM necessite le passthrough vfio-pci + groupes IOMMU
  (reporte a la Phase 9+)
- Les VM utilisent `incus exec` comme les containers LXC -- le plugin
  connection `community.general.incus` fonctionne pour les deux

**`openclaw_server`** (ADR-036) : Les fichiers operationnels des agents
sont des templates Jinja2 deployes avec `force: true` a chaque
`anklume domain apply` :
- `AGENTS.md.j2` -> `~/.openclaw/agents/main/AGENTS.md`
- `TOOLS.md.j2` -> `~/.openclaw/workspace/TOOLS.md`
- `USER.md.j2` -> `~/.openclaw/workspace/USER.md`
- `IDENTITY.md.j2` -> `~/.openclaw/workspace/IDENTITY.md`

Exceptions :
- `SOUL.md` : fichier de personnalite, propriete de l'agent, `.gitignored`
  globalement. Le seul fichier perdu definitivement si le container est
  detruit.
- `MEMORY.md` et `memory/` : deployes avec `force: false` (initialises
  une fois, jamais ecrases). Perdus lors de la reconstruction du
  container -- acceptable.

### Modele de reconciliation (tous les roles d'infrastructure)

Chaque role d'infrastructure suit exactement ce modele en 6 etapes :
1. **Lire** l'etat actuel : `incus <resource> list --format json`
2. **Analyser** en une structure comparable
3. **Construire** l'etat desire a partir de group_vars/host_vars
4. **Creer** ce qui est declare mais absent
5. **Mettre a jour** ce qui existe mais differe
6. **Detecter les orphelins** -- signaler, supprimer si `auto_cleanup: true`

## 8. Snapshots (scripts/snap.sh)

Operations imperatives (pas de reconciliation declarative). Encapsule
`incus snapshot`.

### Interface

```bash
scripts/snap.sh create  <instance|self> [snap-name]    # Default name: snap-YYYYMMDD-HHMMSS
scripts/snap.sh restore <instance|self> <snap-name>
scripts/snap.sh list    [instance|self]                 # All instances if omitted
scripts/snap.sh delete  <instance|self> <snap-name>
```

### Resolution instance-vers-projet

Interroge `incus list --all-projects --format json` pour trouver quel
projet Incus contient l'instance. L'ADR-008 (noms de machines
globalement uniques) garantit une resolution sans ambiguite.

### Mot-cle "self"

Quand `I=self`, le script utilise `hostname` pour detecter le nom de
l'instance courante. Fonctionne depuis n'importe quelle instance ayant
acces au socket Incus (typiquement le container anklume). Echoue avec
un message d'erreur clair si le hostname n'est pas trouve.

### Securite de la restauration sur soi-meme

Restaurer l'instance dans laquelle on s'execute tue la session en cours.
Le script avertit et demande confirmation (`Type 'yes' to confirm`).
Utiliser `--force` pour sauter la confirmation (pour un usage scripte).

## 8b. Snapshots pre-apply (scripts/snapshot-apply.sh)

Filet de securite automatique par snapshot pour `anklume domain apply`. Cree des
snapshots de toutes les instances concernees avant d'appliquer les
changements, avec une politique de retention et un rollback en une
seule commande. C'est un wrapper operationnel, pas declaratif.

### Interface

```bash
scripts/snapshot-apply.sh create [--limit <group>]    # Snapshot before apply
scripts/snapshot-apply.sh rollback [<timestamp>]      # Restore last pre-apply snapshot
scripts/snapshot-apply.sh list                        # List pre-apply snapshots
scripts/snapshot-apply.sh cleanup [--keep <N>]        # Remove old snapshots (default: keep 3)
```

### Integration au Makefile

La fonction Makefile `safe_apply_wrap` appelle `snapshot-apply.sh create`
avant chaque apply et `snapshot-apply.sh cleanup` apres. Controlable via
`SKIP_SNAPSHOT=1` pour ne pas executer. Le nombre de snapshots conserves
est configurable via `KEEP=N`.

```bash
anklume domain apply                      # Auto-snapshots all instances before apply
anklume domain apply ai-tools     # Auto-snapshots only ai-tools instances
anklume snapshot rollback                   # Restore most recent pre-apply snapshot
anklume snapshot rollback T=20260219-143022 # Restore specific pre-apply snapshot
anklume snapshot rollback --list              # List available pre-apply snapshots
anklume snapshot rollback --cleanup KEEP=5    # Remove old snapshots, keep 5
```

### Nommage des snapshots

Les snapshots sont nommes `pre-apply-YYYYMMDD-HHMMSS`. L'horodatage est
genere au moment de la creation. Ce prefixe distingue les snapshots
pre-apply des snapshots crees par l'utilisateur (qui utilisent le
prefixe `snap-` via `scripts/snap.sh`).

### Resolution instance-vers-projet

Utilise l'inventaire Ansible (`ansible-inventory -i inventory/ --list`)
pour decouvrir les instances, puis lit `group_vars/*/vars.yml` pour
trouver le projet Incus de chaque instance. Se rabat sur le projet
`default` si aucun projet n'est trouve.

Quand `--limit <group>` est specifie, seules les instances appartenant
a ce groupe Ansible sont sauvegardees.

### Suivi d'etat

Les metadonnees des snapshots sont stockees dans
`~/.anklume/pre-apply-snapshots/` :
- `latest` -- horodatage du snapshot le plus recent
- `latest-scope` -- nom du groupe ou "all"
- `history` -- liste ordonnee de tous les noms de snapshots (un par ligne)

### Comportement du rollback

- Sans argument : restaure le snapshot pre-apply le plus recent
- Avec horodatage : restaure le snapshot specifique `pre-apply-<timestamp>`
- Ignore les instances qui n'ont pas le snapshot demande (signale le nombre)
- Echoue avec une erreur si aucune instance n'est restauree

### Nettoyage et retention

Retention par defaut : 3 snapshots. La commande `cleanup` supprime les
snapshots les plus anciens sur toutes les instances, en conservant les N
plus recents. Le fichier `history` est reduit en consequence.

### Gestion des erreurs

- Instances manquantes (introuvables dans Incus) : averties et ignorees lors de la creation
- Snapshots echoues : avertis, l'apply continue, le rollback peut etre incomplet
- Pas d'inventaire : averti, retourne 0 (no-op)
- Pas de snapshots pour le rollback : erreur avec suggestion d'executer `anklume snapshot rollback --list`

## 9. Validateurs

Chaque type de fichier a un validateur dedie. Aucun fichier n'echappe
a la validation.

| Validateur | Fichiers cibles | Verifications |
|-----------|-------------|--------|
| `ansible-lint` | `roles/**/*.yml`, playbooks | Profil production, 0 violation |
| `yamllint` | Tous les `*.yml` / `*.yaml` | Syntaxe, formatage, longueur de ligne |
| `shellcheck` | `scripts/**/*.sh` | Bonnes pratiques shell, portabilite |
| `ruff` | `scripts/**/*.py`, `tests/**/*.py` | Linting + formatage Python |
| `markdownlint` | `**/*.md` (optionnel) | Coherence Markdown |
| `ansible-playbook --syntax-check` | Playbooks | Syntaxe YAML/Jinja2 |

`anklume dev lint` execute tous les validateurs en sequence. Le CI doit tous
les passer.

## 10. Flux de developpement

Ce projet suit le **developpement dirige par la documentation et le
comportement** (ADR-009). Pour les fonctionnalites et les refactorisations,
l'ordre strict est :

1. **Documenter d'abord** : Mettre a jour les docs, SPEC.md ou ARCHITECTURE.md
2. **Tests de comportement ensuite** : Ecrire des tests style Given/When/Then
   decrivant le comportement attendu a partir de la specification -- pas du
   code existant. Referencer les cellules de la matrice de comportement
   (`# Matrix: XX-NNN`) le cas echeant.
3. **Implementer ensuite** : Coder jusqu'a ce que les tests passent (Molecule
   pour les roles, pytest pour le generateur)
4. **Valider** : `anklume dev lint`
5. **Revoir** : Executer l'agent de revue
6. **Commiter** : Uniquement quand tout passe

Pour les corrections de bugs et les correctifs triviaux (< ~10 lignes,
cause evidente), les etapes 1-2 peuvent etre omises -- corriger, ajouter
un test de regression, valider, commiter.

## 11. Pile technique

| Composant | Version | Role |
|-----------|---------|------|
| Incus | >= 6.0 LTS | Containers LXC + VM KVM |
| Ansible | >= 2.16 | Orchestration, roles |
| community.general | >= 9.0 | Plugin connection `incus` |
| Molecule | >= 24.0 | Tests de roles |
| pytest | >= 8.0 | Tests du generateur |
| Python | >= 3.11 | Generateur PSOT |
| nftables | -- | Isolation inter-bridges |
| shellcheck | -- | Validation des scripts shell |
| ruff | -- | Linting Python |

## 12. Bootstrap et cycle de vie

### Script de bootstrap

`bootstrap.sh` initialise anklume sur une nouvelle machine :

```bash
./bootstrap.sh --prod                    # Production: auto-detect FS, configure Incus
./bootstrap.sh --dev                     # Development: minimal config
./bootstrap.sh --prod --snapshot btrfs   # Snapshot FS before modifications
./bootstrap.sh --YOLO                    # Bypass security restrictions
./bootstrap.sh --import                  # Import existing Incus infrastructure
./bootstrap.sh --help                    # Usage
```

Le mode production detecte automatiquement le systeme de fichiers (btrfs,
zfs, ext4) et configure le preseed Incus avec le backend de stockage
optimal.

### Resilience du proxy socket de anklume-instance (ADR-019)

Le peripherique proxy de `anklume-instance` mappe le socket Incus de
l'hote vers `/var/run/incus/unix.socket` a l'interieur du container.
Au redemarrage, `/var/run/` (tmpfs) est vide et le bind du proxy echoue.
Un service systemd oneshot cree le repertoire tot dans la sequence de
demarrage :

```ini
# /etc/systemd/system/incus-socket-dir.service
[Unit]
Description=Create Incus socket directory for proxy device
DefaultDependencies=no
Before=network.target
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/mkdir -p /var/run/incus
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

Ceci s'applique uniquement a `anklume-instance`. Les autres containers
n'ont pas le peripherique proxy.

### Importer une infrastructure existante

`anklume setup import` scanne l'etat Incus en cours et genere un
`infra.yml` correspondant. L'utilisateur modifie le resultat, puis
execute `anklume sync && anklume domain apply` pour converger de maniere idempotente.

### Flush (remise a zero)

`anklume flush` detruit toute l'infrastructure anklume :
- Toutes les instances, profils, projets et bridges `net-*`
- Les fichiers Ansible generes (inventory/, group_vars/, host_vars/)
- Preserve : infra.yml, roles/, scripts/, docs/
- Necessite `FORCE=true` en production (`absolute_level == 0`, `yolo != true`)

### Mise a jour (upgrade)

`anklume upgrade` met a jour les fichiers du framework anklume en toute securite :
- Tire les changements en amont
- Detecte les fichiers du framework modifies localement -- cree des `.bak`
- Regenere les sections gerees via `anklume sync`
- Verifie la compatibilite de version

Les fichiers utilisateur (`infra.yml`, `roles_custom/`, `anklume.conf.yml`)
ne sont jamais touches pendant la mise a jour.

### Repertoires de personnalisation utilisateur

- `roles_custom/` -- roles crees par l'utilisateur (gitignored, priorite dans roles_path)
- `anklume.conf.yml` -- configuration utilisateur (gitignored, modele fourni)
- Fichiers generes -- le contenu utilisateur en dehors des sections `=== MANAGED ===` est preserve

## 13. Hors perimetre (gere par le bootstrap ou l'hote)

Gere par `bootstrap.sh` ou la configuration manuelle de l'hote :
- Installation/configuration du pilote NVIDIA
- Configuration du noyau / mkinitcpio
- Installation du daemon Incus et preseed (`bootstrap.sh --prod` assiste)
- Configuration nftables de l'hote (`anklume network deploy` assiste)
- Configuration Sway/Wayland pour le transfert d'affichage GUI
- Snapshots du systeme de fichiers pour le rollback (`bootstrap.sh --snapshot` assiste)

Le framework anklume minimise les modifications de l'hote (ADR-004). Il
pilote principalement Incus via le socket. Les operations au niveau de
l'hote qui ameliorent le KISS/DRY sans compromettre la securite (ex.
regles nftables, prerequis, drop-ins systemd) peuvent etre appliquees
directement via des scripts dedies executes par l'operateur.

## 14. Tests par matrice de comportement

Une matrice de comportement YAML (`tests/behavior_matrix.yml`) associe
chaque capacite a des reactions attendues sur trois niveaux de
profondeur :

- **Profondeur 1** : tests mono-fonctionnalite (ex. creer un domaine avec un subnet_id valide)
- **Profondeur 2** : interactions par paires (ex. domaine ephemeral + surcharge machine)
- **Profondeur 3** : interactions a trois (ex. domaine + VM + GPU + firewall_mode)

Chaque cellule a un identifiant unique (ex. `DL-001`). Les tests
referencent les cellules via des commentaires `# Matrix: DL-001`.
`scripts/matrix-coverage.py` scanne les tests et rapporte la couverture.
`scripts/ai-matrix-test.sh` genere des tests pour les cellules non
couvertes en utilisant un backend LLM.

Les tests bases sur les proprietes Hypothesis (`tests/test_properties.py`)
completent la matrice avec des structures infra.yml aleatoires testant
les invariants du generateur.

## 15. Partage d'images entre niveaux d'imbrication

Pour eviter les telechargements redondants d'images dans les
environnements Incus imbriques :

1. L'hote exporte les images : `anklume setup export-images` (via le role
   `incus_images` avec `incus_images_export_for_nesting: true`)
2. Le repertoire d'export est monte en lecture seule dans les VM
   imbriquees comme peripherique disque
3. L'Incus imbrique importe depuis les fichiers locaux (role
   `dev_test_runner`)

Aucun acces reseau requis pour les imports d'images imbriques. Le
montage en lecture seule preserve l'isolation.

## 16. Audit de code (scripts/code-audit.py)

Un script Python qui produit un rapport d'audit structure du code source.

**Utilisation** :
```bash
anklume dev audit          # Terminal report
anklume dev audit --json     # JSON to reports/audit.json
scripts/code-audit.py --json --output FILE
```

**Contenu du rapport** :
- Nombre de lignes par type de fichier (Python implementation, Python tests, Shell, YAML roles)
- Ratio tests/implementation par module
- Scripts sans couverture de tests identifies
- Roles tries par taille avec candidats a la simplification signales (>200 lignes)
- Detection de code mort (delegue a `scripts/code-analysis.sh dead-code`)
- Resume global (total lignes implementation, lignes de tests, ratio)

**Sortie JSON** : le drapeau `--json` produit une sortie lisible par
machine pour l'integration CI ou le suivi de tendances.

## 17. Garde reseau Incus (scripts/incus-guard.sh)

Script de garde consolide qui empeche les bridges Incus de casser la
connectivite reseau de l'hote quand les sous-reseaux des bridges entrent
en conflit avec le reseau reel de l'hote.

**Sous-commandes** :
```bash
scripts/incus-guard.sh start       # Safe startup with bridge watcher
scripts/incus-guard.sh post-start  # Systemd ExecStartPost hook
scripts/incus-guard.sh install     # Install as systemd drop-in
```

**`start`** : Detecte le reseau de l'hote, lance un observateur de
bridges au niveau noyau (supprime les bridges en conflit toutes les
100ms), demarre Incus, nettoie la base de donnees Incus, restaure la
route par defaut si perdue, verifie la connectivite vers la passerelle.

**`post-start`** : S'execute apres chaque demarrage d'Incus via systemd.
N'utilise que des appels noyau locaux (`ip link`) -- fonctionne meme si
le reseau est casse. Scanne tous les bridges pour les conflits de
sous-reseau, supprime ceux en conflit, nettoie la base de donnees Incus,
restaure la route par defaut.

**`install`** : Copie le script de garde vers `/opt/anklume/incus-guard.sh`,
cree un drop-in systemd pour `incus.service` avec
`ExecStartPost=/opt/anklume/incus-guard.sh post-start`, recharge systemd.

**Principes de conception** :
- Non bloquant : `post-start` retourne 0 meme en cas d'erreur (ne bloque jamais Incus)
- Exhaustif : verifie tous les bridges, pas seulement ceux prefixes `net-*`
- Defensif : sauvegarde l'interface hote dans `/run/incus-guard-host-dev` pour
  la recuperation quand la route par defaut est deja perdue
- Journalise dans `/var/log/incus-network-guard.log` avec horodatage

## 18. Test de fumee (smoke testing)

Test minimal de deploiement en conditions reelles qui verifie les
fonctionnalites de base d'anklume sur une infrastructure Incus reelle
(pas simulee).

**Utilisation** :
```bash
anklume dev smoke    # Requires running Incus daemon
```

**Deroulement du test** (5 etapes) :
1. `anklume sync --dry-run` -- verifier que le generateur fonctionne sur le vrai `infra.yml`
2. `anklume domain check` -- dry-run de l'apply (aucun changement reel)
3. `anklume dev lint` -- tous les validateurs passent
4. `snapshot-list` -- l'infrastructure de snapshot repond
5. `incus list` -- le daemon Incus est joignable

**Objectif** : Validation rapide que toute la chaine d'outils fonctionne
de bout en bout sur l'hote. Detecte les problemes d'integration que les
tests unitaires ne peuvent pas attraper (paquets manquants, etat Incus
casse, derive de configuration).
