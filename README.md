# anklume

Cloisonnez votre poste de travail Linux. Utilisez l'IA en sécurité.

Décrivez vos environnements en YAML, lancez `anklume apply all`,
obtenez des conteneurs et VMs isolés avec réseau cloisonné (nftables),
provisionnés par Ansible et prêts à l'emploi.

[![CI](https://github.com/jmchantrein/AnKLuMe/actions/workflows/ci.yml/badge.svg)](https://github.com/jmchantrein/AnKLuMe/actions/workflows/ci.yml)
[![Documentation](https://github.com/jmchantrein/AnKLuMe/actions/workflows/docs.yml/badge.svg)](https://jmchantrein.github.io/AnKLuMe/)

> **Statut : Proof of Concept** — Projet personnel publié en l'état.
> Pas de garantie de support ni de maintenance. Contributions bienvenues.

## Pourquoi anklume ?

### Tester et utiliser l'IA sans compromettre ses données

Les agents IA et LLM ont besoin d'un accès système (shell, fichiers,
réseau) pour être utiles. Sur un poste bare-metal, c'est un risque
majeur : fuites de données personnelles, credentials exposées,
exécution de code non audité.

**IA locale isolée** — faire tourner des LLM (Ollama) avec GPU
passthrough dans un domaine dédié, cloisonné par nftables. L'IA a
accès au GPU mais pas au reste du poste.

**IA cloud sanitisée** — proxy de sanitisation qui tokenise les IPs,
credentials, noms de machines avant envoi aux LLM cloud. Le
cloisonnement réseau garantit que le flux passe obligatoirement
par le proxy.

**Tester les nouveautés IA en sécurité** — chaque nouvel agent ou
outil IA tourne dans un conteneur/VM jetable. On teste, on évalue,
on détruit. Pas d'accès aux données personnelles, pas de persistance
non contrôlée.

### Donner aux LLM un accès root sans risque

Les agents IA (Claude Code, OpenHands, SWE-agent...) sont plus
performants quand ils ont un accès root à un système réel. Mais
root sur le poste hôte, c'est inacceptable.

**Root sandboxé** — l'agent tourne root dans une instance anklume
(conteneur ou VM), isolée par nftables. Il peut installer des
paquets, modifier la config système, lancer des services, exécuter
des tests E2E et BDD en situation réelle — sans aucun risque pour
l'hôte.

**Nesting** — un LLM root dans une instance anklume peut lui-même
utiliser anklume pour créer des sous-instances (Incus-in-Incus).
L'agent peut ainsi déployer, tester et détruire une infra complète
de manière autonome.

**Sandbox-aware prompting** — un fichier `CLAUDE.md` ou un system
prompt dédié explique au LLM ce qu'il peut faire dans son sandbox.
Les recherches montrent que la performance des agents augmente
significativement (+24%) quand on leur dit explicitement qu'ils sont
dans un environnement isolé et jetable (cf. LLM-in-Sandbox, arxiv
2601.16206).

### Enseigner l'administration système et le réseau

L'enseignant prépare une infrastructure (domaines, rôles, politiques
réseau) et la distribue via git. Les étudiants déploient avec
`anklume apply all` et apprennent en manipulant une vraie infra :
réseau, pare-feu, conteneurs, provisioning. Idempotent, reproductible,
jetable — l'étudiant casse, détruit, recommence.

### Compartimentaliser son poste de travail

Séparer pro/perso/dev/sandbox/IA sur une seule machine. Un domaine =
un sous-réseau + un projet Incus + des instances. Drop-all par défaut
entre domaines, politiques déclaratives.

## Principe

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

## Isolation : LXC vs VM

| | LXC | VM (KVM) |
|---|---|---|
| Noyau | Partagé (hôte) | Séparé (hyperviseur type 1) |
| Performance | Native | Overhead virtualisation |
| Usage recommandé | Charges de confiance | Charges non fiables, jetables |

anklume n'est pas un OS sécurisé. Les conteneurs LXC partagent le
noyau hôte. Pour les domaines untrusted et disposable, utiliser
`type: vm` (KVM, noyau séparé).

## Niveaux de confiance

Chaque domaine déclare un trust-level qui détermine son sous-réseau,
ses règles nftables, et sa couleur dans l'interface :

| Niveau | Réseau | Usage | Recommandation |
|---|---|---|---|
| `admin` | 10.100.x.x | Administration système | LXC ou VM |
| `trusted` | 10.110.x.x | Services de confiance | LXC |
| `semi-trusted` | 10.120.x.x | Travail quotidien (défaut) | LXC |
| `untrusted` | 10.130.x.x | Navigation, tests | VM recommandée |
| `disposable` | 10.140.x.x | Usage unique, éphémère | VM recommandée |

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
| **Nesting Incus** | 2 niveaux en usage réel, 5 niveaux validés en benchmark |
| **Réseau nftables** | Drop-all par défaut, politiques déclaratives |
| **Resource policy** | Allocation CPU/RAM proportionnelle par poids |
| **Push-to-talk STT** | Dictée vocale via Speaches (KDE Wayland) |
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
anklume resource show                   # Allocation CPU/mémoire
anklume doctor                          # Diagnostic automatique
anklume console                         # Console tmux colorée
```

## Ce que anklume n'est PAS

- **Pas un OS sécurisé.** QubesOS (Xen) offre une isolation hardware
  supérieure, mais ne supporte pas l'inférence LLM locale avec GPU
  passthrough (Ollama freeze à l'initialisation du modèle). anklume
  utilise KVM (hyperviseur type 1, noyau séparé) pour les VM et des
  conteneurs LXC (noyau partagé) pour les charges légères.
- **Pas une web app ni une API**
- **Pas un remplacement d'Ansible, d'Incus ou de nftables**
- **Pas un orchestrateur multi-machines**
- **Pas lié à une distribution Linux spécifique**

## Rôles Ansible embarqués

15 rôles prêts à l'emploi dans `provisioner/roles/` :

`admin_bootstrap` · `base` · `code_sandbox` · `desktop` · `dev_env` ·
`dev-tools` · `e2e_runner` · `llm_sanitizer` · `lobechat` ·
`ollama_server` · `openclaw_server` · `opencode_server` · `open_webui` ·
`stt_server` · `tor_gateway`

## Plugins

anklume supporte les plugins CLI via le mécanisme standard Python
[entry_points](https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/).

Un plugin est un package Python qui expose un `typer.Typer` :

```toml
# pyproject.toml du plugin
[project.entry-points."anklume.commands"]
myplugin = "my_package.cli:app"
```

```python
# my_package/cli.py
import typer
app = typer.Typer(help="Mon plugin anklume")

@app.command()
def hello():
    typer.echo("Hello from plugin!")
```

```bash
uv pip install ./my-plugin
anklume myplugin hello  # Plugin disponible comme sous-commande
```

## Développement

```bash
uv sync --group dev
anklume dev lint              # ruff check + format
anklume dev test              # pytest (1340+ tests)
anklume dev molecule          # Tests Molecule (rôles Ansible)
anklume dev test-real         # Tests E2E dans VM KVM
```

## Documentation

- **[Documentation en ligne](https://jmchantrein.github.io/AnKLuMe/)** — guide, concepts, CLI, IA, opérations
- [SPEC.md](docs/SPEC.md) — spécification complète (37 sections)
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — décisions d'architecture (26 ADRs)
- [ROADMAP.md](docs/ROADMAP.md) — 22 phases complétées

## Remerciements

anklume s'appuie sur ces projets remarquables :

**Infrastructure**

- [Incus](https://linuxcontainers.org/incus/) — gestionnaire de conteneurs et VMs (LXC/KVM)
- [nftables](https://nftables.org/) — pare-feu Linux
- [Ansible](https://www.ansible.com/) — provisioning et configuration
- [Tor](https://www.torproject.org/) — réseau d'anonymisation

**Python**

- [Typer](https://typer.tiangolo.com/) — framework CLI
- [Rich](https://github.com/Textualize/rich) — formatage terminal
- [Textual](https://textual.textualize.io/) — framework TUI
- [PyYAML](https://pyyaml.org/) — parsing YAML
- [uv](https://docs.astral.sh/uv/) — gestionnaire de paquets Python

**IA et LLM**

- [Ollama](https://ollama.com/) — inférence LLM locale
- [Speaches](https://github.com/speaches-ai/speaches) — serveur STT (Speech-to-Text)
- [Open WebUI](https://github.com/open-webui/open-webui) — interface web pour LLM
- [LobeChat](https://github.com/lobehub/lobe-chat) — chat multi-providers

**Qualité et documentation**

- [pytest](https://pytest.org/) — framework de tests
- [Ruff](https://docs.astral.sh/ruff/) — linter et formateur Python
- [Molecule](https://molecule.readthedocs.io/) — tests de rôles Ansible
- [MkDocs](https://www.mkdocs.org/) + [Material](https://squidfunk.github.io/mkdocs-material/) — documentation
- [Mermaid](https://mermaid.js.org/) — diagrammes
- [ShellCheck](https://www.shellcheck.net/) — analyse statique shell
- [behave](https://behave.readthedocs.io/) — tests BDD

**Desktop (KDE/Wayland)**

- [tmux](https://github.com/tmux/tmux) — multiplexeur de terminaux
- [PipeWire](https://pipewire.org/) — capture audio
- [wtype](https://github.com/atx/wtype) — saisie clavier Wayland
- [kdotool](https://github.com/jinliu/kdotool) — interaction fenêtres KDE

## Licence

MIT
