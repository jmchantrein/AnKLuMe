# anklume v2

Framework de compartimentalisation d'infrastructure déclaratif.
Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.

## Règles non-négociables

1. **anklume est un outil installé** — comme docker ou terraform.
   `anklume init`, pas `git clone`. Le projet utilisateur est indépendant.
2. **Modèle PSOT** — les fichiers domaine (`domains/*.yml`) sont la
   source de vérité. `anklume apply` déploie directement vers Incus.
   Pas d'étape intermédiaire `sync`.
3. **La CLI est la seule interface** — pas de Makefile. Toute opération
   passe par une commande CLI (`anklume <nom> <verbe>`).
4. **DRY + KISS** — un fichier = une responsabilité. Pas de fichier
   de plus de 200 lignes. Pas d'abstraction prématurée.
5. **Spec-driven, test-driven** — spec d'abord, test ensuite, code après.
6. **Incus via CLI** — `subprocess` + `incus --format json` +
   idempotence manuelle. Pas de modules Ansible natifs.
7. **Français par défaut** — docs, commentaires, UI en français.
   Code (variables, fonctions, CLI) en anglais (convention universelle).

## Structure du projet

```
src/anklume/        # Package Python (pip installable)
  cli/              # Commandes CLI (Typer)
  engine/           # Moteur PSOT (domains/*.yml → Incus)
  provisioner/      # Interface Ansible pour le provisioning
  i18n/             # Traductions
live/               # Live ISO (concern séparé)
  boot/             # Scripts de boot, systemd, grub
  platform/         # Plateforme web d'apprentissage (FastAPI)
tests/              # pytest + behave
labs/               # Labs éducatifs
docs/               # SPEC, ARCHITECTURE
```

### Projet utilisateur (créé par `anklume init`)

```
mon-infra/
  anklume.yml       # Config globale
  domains/          # Un fichier par domaine (docker-compose style)
    pro.yml
    perso.yml
    ai-tools.yml
  policies.yml      # Politiques réseau (optionnel)
  roles_custom/     # Rôles Ansible utilisateur (optionnel)
```

## Commandes

```bash
anklume init [dir]        # Créer un nouveau projet
anklume apply             # Déployer toute l'infrastructure
anklume apply <domaine>   # Déployer un seul domaine
anklume status            # Afficher l'état de l'infrastructure
anklume destroy           # Détruire (respecte les flags ephemeral)
anklume dev lint          # Tous les validateurs
anklume dev test          # pytest + behave
```

## Conventions de code

### Python
- Typer pour la CLI, FastAPI pour le web, PyYAML pour le parsing
- Type hints sur les fonctions publiques
- `ruff` pour lint+format (zéro violation)

### Shell
- `shellcheck` propre, `set -euo pipefail`
- Uniquement pour les scripts de boot et l'intégration système

## Modèle d'exécution

```
domains/*.yml ──[anklume apply]──> Incus (projets, réseaux, instances)
                                 ──> Ansible (provisioning des instances)
```

Pas d'étape `sync`. Python lit les domaines, crée les ressources
Incus directement, puis lance Ansible pour le provisioning.

La CLI tourne sur l'hôte. Les opérations nécessitant Incus/Ansible
sont déléguées de manière transparente à `anklume-instance`.
L'utilisateur ne tape jamais `incus exec anklume-instance`.

## Fichiers de contexte

Toujours chargé : ce fichier (CLAUDE.md)

À lire sur demande (outil Read) :
- `docs/SPEC.md` — spécification complète
- `docs/ARCHITECTURE.md` — décisions d'architecture
