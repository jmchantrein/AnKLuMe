# anklume

Outil IaC déclaratif pour cloisonner un poste Linux — IA sécurisée
+ enseignement sys/réseaux. Isolation avec Incus (LXC/KVM) + nftables.
Provisioning des instances via Ansible (intégré, optionnel pour l'utilisateur).

## Règles non-négociables

2. **Modèle PSOT** — les fichiers domaine (`domains/*.yml`) sont la
   source de vérité. `anklume apply` déploie directement vers Incus.
3. **La CLI est la seule interface** — pas de Makefile. Toute opération
   passe par une commande CLI (`anklume <nom> <verbe>`).
4. **DRY + KISS** — un fichier = une responsabilité.
5. **Spec-driven, test-driven** — spec d'abord, tests exhaustifs ensuite
   (unitaires, Molecule, E2E et Behavior), code après.
6. **Incus via CLI** — `subprocess` + `incus --format json` +
   idempotence manuelle.
7. **Français par défaut** — docs, commentaires, UI en français.
   Code (variables, fonctions, CLI) en anglais (convention universelle).
8. **Prévoir internationalisation (i18n)**

## Structure du projet

```
src/anklume/        # Package Python
  cli/              # Commandes CLI (Typer)
  engine/           # Moteur PSOT (domains/*.yml → Incus)
  provisioner/      # Interface Ansible pour le provisioning
  i18n/             # Traductions
tests/              # pytest + behave
labs/               # Labs éducatifs
docs/               # SPEC, ARCHITECTURE
```

### Projet utilisateur (créé par `anklume init`)

```
mon-infra/
  anklume.yml               # Config globale
  domains/                  # Un fichier par domaine (docker-compose style)
    pro.yml
    perso.yml
    ai-tools.yml
  policies.yml              # Politiques réseau (optionnel)
  ansible/                  # Provisioning Ansible (généré + personnalisable)
    inventory/              # Inventaire (généré depuis domains/)
    group_vars/             # Variables par domaine
    host_vars/              # Variables par machine
    site.yml                # Playbook principal
  ansible_roles_custom/     # Rôles Ansible utilisateur (optionnel)
```


## Commandes

```bash
anklume init [dir]        # Créer un nouveau projet
anklume apply all             # Déployer toute l'infrastructure
anklume apply domain <nom>    # Déployer un seul domaine
anklume status            # Afficher l'état de l'infrastructure
anklume destroy           # Détruire (respecte les flags ephemeral)
anklume stt setup         # Configurer le STT (Voxtype + Speaches)
anklume stt start         # Démarrer le push-to-talk
anklume stt stop          # Arrêter le push-to-talk
anklume stt status        # État du service STT
anklume dev lint          # Tous les validateurs
anklume dev test          # pytest + behave
anklume dev molecule      # Tests Molecule (rôles Ansible)
```

## Conventions de code

### Python
- Typer pour la CLI, PyYAML pour le parsing
- Type hints sur les fonctions publiques
- `ruff` pour lint+format (zéro violation)

### Shell
- `shellcheck` propre, `set -euo pipefail`
- Uniquement pour les scripts de boot et l'intégration système

## Pyramide de tests

1. **Unitaires** (`pytest`) — logique Python, engine, CLI
2. **Molecule** — rôles Ansible isolés dans des conteneurs Incus
3. **E2E** (`pytest`) — déploiement réel Incus (apply, destroy, idempotence)
4. **Behavior** (`behave`) — scénarios utilisateur de bout en bout

## Modèle d'exécution

```
domains/*.yml ──[anklume apply]──> Incus (projets, réseaux, instances)
                                 ──> Ansible (provisioning des instances)
```

Python lit les domaines, crée les ressources
Incus directement, puis lance Ansible pour le provisioning.

La CLI tourne directement sur l'hôte. Dépendances gérées par `uv`.
Incus et Ansible sont appelés via `subprocess`.

### Réinstallation CLI après modification du code

La CLI `ank` est un wrapper script qui exécute `uv run` depuis le
repo `~/AnKLuMe`. Les modifications du code sont donc immédiates,
pas de réinstallation nécessaire.

Si les dépendances changent (pyproject.toml), relancer :

```bash
cd ~/AnKLuMe && uv sync
```

## Démarrage de session (après chaque /clear)

**OBLIGATOIRE** — à chaque nouvelle session, avant toute action :

1. Lire `docs/ROADMAP.md` pour connaître l'état courant et les priorités
2. Vérifier `git diff HEAD` et `git log --oneline -5` :
   - Si des fichiers ont été modifiés par l'utilisateur (non commités),
     **les analyser en priorité** : ce sont des corrections ou des
     orientations. Adapter la compréhension du projet en conséquence.
   - Si CLAUDE.md a changé, relire les sections modifiées.
3. Mettre à jour `docs/ROADMAP.md` si une étape est terminée
4. Résumer brièvement à l'utilisateur : état, modifications détectées,
   prochaine action proposée

### Apprentissage des modifications manuelles

Quand l'utilisateur modifie un fichier entre deux sessions :
- **Code modifié** → c'est une correction. Comprendre pourquoi et
  appliquer le pattern dans le code futur.
- **CLAUDE.md modifié** → c'est une directive. L'appliquer
  immédiatement et sans discussion.
- **Spec/Architecture modifiée** → c'est une réorientation.
  Vérifier la cohérence avec le code existant.

Ne jamais ignorer une modification manuelle. Ne jamais revenir
silencieusement à l'ancienne version.

## Impact des modifications (si tu touches X → vérifie Y)

IMPORTANT : avant de modifier un fichier, consulter cette table.

| Fichier modifié | Tester | Aussi vérifier |
|----------------|--------|----------------|
| `engine/models.py` | **TOUS les tests** (24 dépendants) | parser, validator, reconciler, nftables, addressing |
| `engine/incus_driver.py` | `test_incus_driver` | reconciler, destroy, snapshot, ops |
| `engine/reconciler.py` | `test_reconciler`, `test_e2e` | destroy (même patterns), nesting, gpu |
| `engine/nftables.py` | `test_nftables` | tor (import croisé), addressing |
| `engine/sanitizer.py` | `test_sanitizer` | llm_routing, llm_ops |
| `engine/addressing.py` | `test_addressing` | nftables (IPs dans les règles) |
| `engine/parser.py` | `test_parser` | validator (parsé → validé) |
| `engine/validator.py` | `test_validator` | parser (validé après parsing) |
| `engine/snapshot.py` | `test_snapshot` | reconciler (auto-snapshots dans apply) |
| `engine/nesting.py` | `test_nesting_engine` | reconciler (prefixes + security config) |
| `engine/gpu.py` | `test_gpu_engine` | reconciler (gpu profiles) |
| `engine/destroy.py` | `test_destroy` | reconciler (protection flags) |
| `provisioner/*.py` | `test_provisioner` | rôles Ansible (inventory/playbook generated) |
| `cli/__init__.py` | `test_cli` | **toute la CLI** (routage des commandes) |

## Pièges connus (gotchas)

- **ConfigParser ≠ dict** : `config.get("Section", {})` plante sur un ConfigParser.
  Utiliser `config["Section"] if "Section" in config else {}`.
- **nftables intégré au pipeline apply** : `anklume apply` déploie
  automatiquement les règles nftables après les snapshots post-apply.
  `anklume network deploy` reste disponible pour un redéploiement manuel.
- **`security.privileged=true` en nesting L2+** : inévitable pour LXC-in-LXC,
  documenté dans ADR-019. Ne pas essayer de le supprimer.
- **Incus image refs contiennent `/` et `:`** : le regex de validation dans
  incus_driver accepte `images:debian/13` via `_SAFE_IMAGE_REF`, pas `_SAFE_NAME`.
- **`uv tool install` interdit** : toujours utiliser le wrapper `uv run`.
  Voir `feedback_uv_reinstall.md` dans la mémoire.
- **Tests `@pytest.mark.real`** : nécessitent une VM KVM avec Incus.
  Ne jamais les lancer en CI ou sur la machine hôte directe.

## Règle de régression

**OBLIGATOIRE** : tout bug découvert pendant le développement doit produire
un test de régression AVANT le fix. Le test doit échouer sans le fix et
passer avec. Ne jamais fixer un bug sans ajouter de test.

## Fichiers de contexte

Toujours chargé : ce fichier (CLAUDE.md)

À lire sur demande (outil Read) :
- `docs/SPEC.md` — spécification complète
- `docs/ARCHITECTURE.md` — décisions d'architecture
- `docs/ROADMAP.md` — état courant et prochaines étapes
