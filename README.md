# anklume

Framework déclaratif de compartimentalisation d'infrastructure.
Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.
Provisioning intégré via Ansible.

[![CI](https://github.com/jmchantrein/AnKLuMe/actions/workflows/ci.yml/badge.svg)](https://github.com/jmchantrein/AnKLuMe/actions/workflows/ci.yml)
[![Documentation](https://github.com/jmchantrein/AnKLuMe/actions/workflows/docs.yml/badge.svg)](https://jmchantrein.github.io/AnKLuMe/)

## Principe

Décrivez vos domaines en YAML. Lancez `anklume apply all`. Obtenez des
environnements isolés et reproductibles.

```yaml
# domains/pro.yml
description: "Environnement professionnel"
trust_level: semi-trusted

machines:
  dev:
    description: "Développement"
    roles: [base, dev-tools]

  desktop:
    description: "Bureau KDE"
    gpu: true
    gui: true
    roles: [base, desktop]
```

```
domains/*.yml ──[anklume apply]──> Incus (projets, réseaux, instances)
                                 ──> Ansible (provisioning)
                                 ──> nftables (isolation réseau)
```

## Installation

```bash
# Prérequis : Incus, uv (https://docs.astral.sh/uv/)
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe
uv sync
```

## Démarrage rapide

```bash
anklume init mon-infra      # Créer un projet
cd mon-infra
vim domains/pro.yml         # Éditer les domaines
anklume apply all           # Déployer
anklume status              # Vérifier
```

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| **Isolation par domaines** | Un projet Incus + sous-réseau + nftables par domaine |
| **PSOT stateless** | Réconciliation sans state file — YAML + Incus = vérité |
| **TUI interactif** | Éditeur visuel de domaines et politiques (`anklume tui`) |
| **GPU passthrough** | Accès exclusif ou partagé au GPU (Ollama, STT, LLM) |
| **Provisioning Ansible** | 15 rôles embarqués + rôles custom + Galaxy |
| **Routage LLM** | Backend local/cloud, proxy de sanitisation automatique |
| **Snapshots** | Automatiques pré/post-apply, rollback destructif |
| **Nesting Incus** | Conteneurs dans conteneurs (5 niveaux validés) |
| **Réseau nftables** | Drop-all par défaut, politiques déclaratives |
| **Resource policy** | Allocation CPU/RAM proportionnelle par poids |
| **Push-to-talk STT** | Dictée vocale via Speaches (KDE Wayland) |
| **Portails fichiers** | Transfert hôte ↔ conteneur isolé |
| **Golden images** | Publier des instances comme images réutilisables |
| **Passerelle Tor** | VM routeur transparent Tor |
| **Conteneurs jetables** | `anklume disp <image>` — usage unique |
| **Workspace layout** | Placement déclaratif des fenêtres GUI (KDE) |

## Commandes principales

```bash
# Infrastructure
anklume apply all                       # Déployer tout
anklume apply all --dry-run             # Voir les changements
anklume apply domain <nom>              # Déployer un domaine
anklume status                          # État des instances
anklume destroy                         # Supprimer (respecte ephemeral)

# TUI
anklume tui                             # Éditeur interactif

# Instances
anklume instance list                   # Tableau des instances
anklume instance exec <inst> -- <cmd>   # Exécuter dans une instance

# Réseau
anklume network deploy                  # Appliquer les règles nftables
anklume network status                  # État réseau

# IA
anklume ai status                       # GPU, Ollama, STT
anklume ai flush                        # Libérer la VRAM
anklume llm bench                       # Benchmark inférence

# Snapshots
anklume snapshot create                 # Snapshotter toutes les instances
anklume snapshot restore <inst> <snap>  # Restaurer

# Opérations
anklume portal push <inst> <src> <dst>  # Envoyer un fichier
anklume golden create <inst>            # Publier une image
anklume doctor                          # Diagnostic automatique
anklume console                         # Console tmux colorée
```

## Niveaux de confiance

Chaque domaine déclare un trust-level qui détermine son sous-réseau,
ses règles nftables, et sa couleur dans l'interface :

| Niveau | Réseau | Usage |
|---|---|---|
| `admin` | 10.100.x.x | Administration système |
| `trusted` | 10.110.x.x | Services de confiance |
| `semi-trusted` | 10.120.x.x | Travail quotidien (défaut) |
| `untrusted` | 10.130.x.x | Navigation, tests |
| `disposable` | 10.140.x.x | Usage unique, éphémère |

## Rôles Ansible embarqués

15 rôles prêts à l'emploi dans `provisioner/roles/` :

`admin_bootstrap` · `base` · `code_sandbox` · `desktop` · `dev_env` ·
`dev-tools` · `e2e_runner` · `llm_sanitizer` · `lobechat` ·
`ollama_server` · `openclaw_server` · `opencode_server` · `open_webui` ·
`stt_server` · `tor_gateway`

## Développement

```bash
uv sync --group dev
anklume dev lint              # ruff check + format
anklume dev test              # pytest (1330+ tests)
anklume dev molecule          # Tests Molecule (rôles Ansible)
anklume dev test-real         # Tests E2E dans VM KVM
```

## Documentation

- **[Documentation en ligne](https://jmchantrein.github.io/AnKLuMe/)** — guide, concepts, CLI, IA, opérations
- [SPEC.md](docs/SPEC.md) — spécification complète (37 sections)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — décisions d'architecture (26 ADRs)
- [ROADMAP.md](docs/ROADMAP.md) — 22 phases complétées

## Licence

AGPL-3.0
