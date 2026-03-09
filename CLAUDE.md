# anklume

Framework de compartimentalisation d'infrastructure déclaratif.
Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.
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
live/               # Live ISO — OS immuable avec persistance chiffrée (ZFS/BTRFS)
  boot/             # Scripts de boot, systemd, grub
platform/           # Plateforme web (FastAPI) (concern séparé) #REDONDANTS AVEC LABS ...
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
- Typer pour la CLI, FastAPI pour le web, PyYAML pour le parsing
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

## Fichiers de contexte

Toujours chargé : ce fichier (CLAUDE.md)

À lire sur demande (outil Read) :
- `docs/SPEC.md` — spécification complète
- `docs/ARCHITECTURE.md` — décisions d'architecture
- `docs/ROADMAP.md` — état courant et prochaines étapes
