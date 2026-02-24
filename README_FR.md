# AnKLuMe

> **Note** : La version anglaise (`README.md`) fait reference en cas
> de divergence.

<!-- Badges -->
[![CI](https://github.com/jmchantrein/anklume/actions/workflows/ci.yml/badge.svg)](https://github.com/jmchantrein/anklume/actions)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/jmchantrein/anklume)](https://github.com/jmchantrein/anklume/commits/main)
[![Issues](https://img.shields.io/github/issues/jmchantrein/anklume)](https://github.com/jmchantrein/anklume/issues)
[![Pull Requests](https://img.shields.io/github/issues-pr/jmchantrein/anklume)](https://github.com/jmchantrein/anklume/pulls)

<!-- Badges statiques — stack technique -->
[![Ansible](https://img.shields.io/badge/ansible-%3E%3D2.16-EE0000?logo=ansible&logoColor=white)](https://www.ansible.com/)
[![Incus](https://img.shields.io/badge/incus-%3E%3D6.0%20LTS-orange)](https://linuxcontainers.org/incus/)
[![Python](https://img.shields.io/badge/python-%3E%3D3.11-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Molecule](https://img.shields.io/badge/molecule-tested-green)](https://molecule.readthedocs.io/)

<!-- Badges statiques — quality gates (valides par la CI) -->
[![ansible-lint](https://img.shields.io/badge/ansible--lint-production-brightgreen)](https://ansible.readthedocs.io/projects/lint/)
[![shellcheck](https://img.shields.io/badge/shellcheck-passing-brightgreen)](https://www.shellcheck.net/)
[![ruff](https://img.shields.io/badge/ruff-passing-brightgreen)](https://docs.astral.sh/ruff/)
[![Roles](https://img.shields.io/badge/roles-20-informational)](roles/)

> **⚠️ Ce projet est une preuve de concept en cours de développement actif. Il n'est PAS prêt pour la production. Utilisation à vos risques et périls.**

> **🤖 Ce projet est co-développé avec des LLM** (Claude Code, Aider). Les décisions d'architecture, le code, les tests et la documentation sont produits en collaboration humain-IA. Toutes les contributions sont revues par le mainteneur.

**Une interface declarative haut niveau pour Incus.**

Isolation type QubesOS utilisant les fonctionnalites natives du noyau
Linux (KVM/LXC), orchestree sereinement par vous en assemblant des
outils standards eprouves.

> [Ansible](https://www.ansible.com/), [KVM](https://linux-kvm.org/), [LXC](https://linuxcontainers.org/lxc/), [Molecule](https://molecule.readthedocs.io/) => **anklume** — de "enclume", traduction francaise d'[Incus](https://linuxcontainers.org/incus/) (enclume)

---

## Qu'est-ce qu'anklume ?

anklume est un framework declaratif de cloisonnement d'infrastructure.
Vous decrivez vos environnements isoles dans un seul fichier YAML, lancez
deux commandes, et obtenez des domaines reproductibles, jetables et isoles
par reseau — chacun avec son propre sous-reseau, projet Incus et ensemble
de containers ou VMs.

La philosophie [QubesOS](https://www.qubes-os.org/), mais :
- **Pas d'OS dedie** — fonctionne sur n'importe quelle distribution Linux
- **Pas de Xen** — utilise les fonctionnalites natives du noyau (KVM pour les VMs, LXC pour les containers)
- **Pas de boite noire** — des outils standards que vous connaissez deja, assembles intelligemment
- **Declaratif** — decrivez ce que vous voulez, anklume converge

## Pour qui ?

- **Administrateurs systemes** qui veulent cloisonner leur poste de travail
  (admin, professionnel, personnel, homelab — chacun dans son reseau isole)
- **Enseignants en informatique** deployant des TPs reseau pour N etudiants
  en une commande
- **Etudiants en informatique** apprenant l'administration systeme, le reseau
  et la securite dans des environnements isoles et reproductibles qu'ils
  peuvent casser et reconstruire librement
- **Utilisateurs avances** qui veulent l'isolation QubesOS sans les contraintes
  QubesOS

## Comment ca marche

```
infra.yml          ->    make sync    ->    Fichiers Ansible  ->    make apply    ->    Etat Incus
(vous decrivez)         (generation)      (vous enrichissez)     (convergence)      (infra active)
```

1. **Decrivez** votre infrastructure dans `infra.yml` (Source de Verite Primaire)
2. **Generez** l'arborescence Ansible : `make sync`
3. **Enrichissez** les fichiers generes avec vos variables personnalisees (Source de Verite Secondaire)
4. **Appliquez** : `make apply` — reseaux, projets, profils, instances, provisioning

## Prerequis

Avant d'utiliser anklume, il vous faut :

1. **Un hote Linux** avec [Incus](https://linuxcontainers.org/incus/docs/main/installing/)
   installe et initialise
2. **Une instance anklume** (container LXC ou VM) nommee `anklume-instance`, avec :
   - Le socket Incus monte (`/var/run/incus/unix.socket`)
   - Ansible, Python 3.11+, git installes
3. **Ce depot** clone dans l'instance anklume

anklume s'execute entierement depuis l'instance anklume. Il ne modifie
jamais l'hote directement — tout passe par le socket Incus.

## Demarrage rapide

```bash
# Dans le container anklume-instance :
git clone https://github.com/jmchantrein/anklume.git
cd anklume

# Installer les dependances Ansible
make init

# Configuration guidee interactive (recommandee pour les nouveaux utilisateurs)
make guide

# Ou configuration manuelle :
cp infra.yml.example infra.yml   # Editez infra.yml selon vos besoins
make sync                        # Generer les fichiers Ansible
make check                       # Previsualiser les changements (dry-run)
make apply                       # Appliquer l'infrastructure
```

Voir le [guide de demarrage rapide](docs/quickstart.md) pour plus de details.

## Architecture

```
+---------------------------------------------------------------+
| Hote (n'importe quelle distro Linux)                          |
|  Incus daemon + nftables + (optionnel) GPU NVIDIA             |
|                                                               |
|  +-----------+ +-----------+ +-----------+                    |
|  | net-aaa   | | net-bbb   | | net-ccc   |  ...              |
|  | subnet A  | | subnet B  | | subnet C  |                   |
|  +-----+-----+ +-----+-----+ +-----+-----+                  |
|        |              |              |                         |
|  +-----+-----+ +-----+-----+ +-----+-----+                  |
|  | LXC / VM  | | LXC / VM  | | LXC / VM  |                  |
|  +-----------+ +-----------+ +-----------+                    |
|                                                               |
|  Isolation nftables : subnet A != B != C (pas de forwarding)  |
|  Acces inter-domaines selectif via network_policies            |
+---------------------------------------------------------------+
```

Chaque **domaine** est un sous-reseau isole avec son propre projet Incus.
Les containers et VMs d'un domaine communiquent entre eux mais le trafic
inter-domaines est bloque par nftables. Les exceptions selectives sont
declarees via `network_policies`. Le container anklume pilote tout via
le socket Incus — pas besoin de SSH.

## Fonctionnalites

| Categorie | Fonctionnalite |
|-----------|---------------|
| **Coeur** | YAML declaratif (`infra.yml`) avec generateur PSOT |
| | Execution en deux phases : infrastructure puis provisioning |
| | Gestion idempotente par reconciliation |
| | Detection et nettoyage des orphelins |
| **Isolation** | Bridges par domaine avec isolation nftables cross-bridge |
| | Acces inter-domaines selectif via `network_policies` |
| | Firewall VM dedie optionnel (style QubesOS sys-firewall) |
| | Niveaux de confiance avec console tmux coloree |
| **Calcul** | Containers LXC et VMs KVM dans le meme domaine |
| | GPU passthrough NVIDIA (politique exclusive ou partagee) |
| | Allocation automatique CPU/memoire (`resource_policy`) |
| | Demarrage automatique avec priorite d'ordonnancement |
| **Services IA** | Serveur LLM Ollama avec GPU |
| | Interface chat Open WebUI |
| | Interface web multi-fournisseur LobeChat |
| | STT Speaches (faster-whisper, API compatible OpenAI) |
| | Serveur de code IA headless OpenCode |
| | Assistant IA OpenClaw avec proxy (multi-cerveau, inter-conteneur, suivi des couts) |
| | Acces reseau exclusif aux outils IA avec flush VRAM |
| **Cycle de vie** | Snapshots (manuels + automatiques avec schedule/expiry) |
| | Images gold avec derivation CoW |
| | Instances jetables (ephemeres) |
| | Sauvegarde/restauration chiffree |
| | Reinitialisation (`make flush && make sync && make apply`) |
| | Mise a jour securisee du framework (`make upgrade`) |
| | Import d'etat Incus existant (`make import-infra`) |
| **Bureau** | Console tmux coloree style QubesOS (`make console`) |
| | Partage de presse-papiers (hote <-> container) |
| | Generateur de regles Sway/i3 |
| | Tableau de bord web lecture seule |
| **Reseau** | Passerelle proxy transparent Tor |
| | Serveur d'impression CUPS avec passthrough USB/reseau |
| | Services inter-containers via MCP |
| **Tests** | Tests Molecule pour les 20 roles |
| | pytest pour le generateur PSOT (2600+ tests) |
| | Tests de scenarios BDD (bonnes/mauvaises pratiques) |
| | Matrice comportementale avec suivi de couverture |
| | Tests property-based Hypothesis |
| | Sandbox Incus-dans-Incus pour tests isoles |
| **Dev assiste par IA** | Correction de tests par LLM (Ollama, Claude, Aider) |
| | Claude Code Agent Teams pour developpement autonome |
| | Bibliotheque d'experience pour auto-amelioration |
| **Observabilite** | Telemetrie locale (opt-in, ne quitte jamais la machine) |
| | Detection de code mort et generation de graphe d'appels |
| | Propagation du contexte d'imbrication entre niveaux |

## Documentation

| Categorie | Document |
|-----------|----------|
| **Demarrage** | [Demarrage rapide](docs/quickstart.md) |
| | [Guide interactif](docs/guide.md) |
| | [Specification complete](docs/SPEC.md) |
| **Architecture** | [Decisions d'architecture (ADR-001 a ADR-036)](docs/ARCHITECTURE.md) |
| | [Couverture des fonctionnalites Incus](docs/incus-coverage.md) |
| | [Feuille de route](docs/ROADMAP.md) |
| | [Journal des decisions](docs/decisions-log.md) |
| **Reseau** | [Isolation reseau (nftables)](docs/network-isolation.md) |
| | [Firewall VM dedie](docs/firewall-vm.md) |
| | [Passerelle Tor](docs/tor-gateway.md) |
| **Services IA** | [Assistant IA OpenClaw](docs/openclaw_FR.md) |
| | [Acces exclusif aux outils IA](docs/ai-switch.md) |
| | [Service Speech-to-Text](docs/stt-service.md) |
| **Calcul** | [Guide VM](docs/vm-support.md) |
| | [Gestion GPU et securite](docs/gpu-advanced.md) |
| **Bureau** | [Integration bureau](docs/desktop-integration.md) |
| **Cycle de vie** | [Transfert de fichiers et sauvegarde](docs/file-transfer.md) |
| **Developpement** | [Tests assistes par IA](docs/ai-testing.md) |
| | [Agent Teams](docs/agent-teams.md) |
| | [Tests de scenarios BDD](docs/scenario-testing.md) |
| | [Guide de deploiement TP](docs/lab-tp.md) |
| | [Contribuer](CONTRIBUTING.md) |

## Exemples

Configurations `infra.yml` pretes a l'emploi :

| Exemple | Description |
|---------|-------------|
| [Etudiant sysadmin](examples/student-sysadmin/) | 2 domaines (anklume + lab), sans GPU |
| [TP enseignant](examples/teacher-lab/) | Anklume + N domaines etudiants avec snapshots |
| [Poste professionnel](examples/pro-workstation/) | Anklume/pro/perso/homelab avec GPU |
| [Sandbox isolation](examples/sandbox-isolation/) | Isolation maximale pour logiciels non fiables |
| [Superviseur LLM](examples/llm-supervisor/) | 2 LLMs isoles + 1 superviseur |
| [Developpeur](examples/developer/) | Environnement dev anklume avec Incus-dans-Incus |
| [Outils IA](examples/ai-tools/) | Stack IA complete (Ollama, WebUI, LobeChat, STT) |
| [Passerelle Tor](examples/tor-gateway/) | Navigation anonyme via proxy transparent Tor |
| [Service d'impression](examples/sys-print/) | Serveur CUPS dedie avec imprimantes USB/reseau |

## Roles Ansible

### Roles d'infrastructure (Phase 1 : `connection: local`)

| Role | Responsabilite |
|------|---------------|
| `incus_networks` | Creation/reconciliation des bridges par domaine |
| `incus_projects` | Creation/reconciliation des projets Incus + profil par defaut |
| `incus_profiles` | Creation des profils supplementaires (GPU, nesting, ressources) |
| `incus_instances` | Creation/gestion des instances LXC + VM |
| `incus_nftables` | Generation des regles d'isolation inter-bridges |
| `incus_firewall_vm` | Profil multi-NIC pour firewall VM |
| `incus_images` | Pre-telechargement et export des images OS |
| `incus_nesting` | Propagation du contexte d'imbrication |

### Roles de provisioning (Phase 2 : `connection: community.general.incus`)

| Role | Responsabilite |
|------|---------------|
| `base_system` | Paquets de base, locale, fuseau horaire |
| `admin_bootstrap` | Provisioning specifique anklume (Ansible, git) |
| `ollama_server` | Serveur d'inference LLM Ollama |
| `open_webui` | Interface chat Open WebUI |
| `stt_server` | Serveur STT Speaches (faster-whisper) |
| `lobechat` | Interface web multi-fournisseur LobeChat |
| `opencode_server` | Serveur de code IA headless OpenCode |
| `firewall_router` | Routage nftables dans la firewall VM |
| `openclaw_server` | Assistant IA auto-heberge OpenClaw |
| `code_sandbox` | Environnement de code IA sandboxe |
| `dev_test_runner` | Provisioning sandbox Incus-dans-Incus |
| `dev_agent_runner` | Configuration Claude Code Agent Teams |

## Commandes Make

| Commande | Description |
|----------|-------------|
| `make guide` | Tutoriel interactif d'integration |
| `make sync` | Generer les fichiers Ansible depuis infra.yml |
| `make sync-dry` | Previsualiser les changements sans ecrire |
| `make lint` | Lancer tous les validateurs (ansible-lint, yamllint, shellcheck, ruff) |
| `make check` | Dry-run (--check --diff) |
| `make apply` | Appliquer toute l'infrastructure |
| `make apply-limit G=<domaine>` | Appliquer un seul domaine |
| `make console` | Lancer la session tmux coloree |
| `make nftables` | Generer les regles d'isolation nftables |
| `make nftables-deploy` | Deployer les regles sur l'hote |
| `make snap I=<nom>` | Creer un snapshot |
| `make flush` | Detruire toute l'infrastructure anklume |
| `make upgrade` | Mise a jour securisee du framework |
| `make import-infra` | Generer infra.yml depuis l'etat Incus existant |
| `make help` | Lister toutes les commandes disponibles |

## Stack technique

| Composant | Version | Role |
|-----------|---------|------|
| [Incus](https://linuxcontainers.org/incus/) | >= 6.0 LTS | Containers LXC + VMs KVM |
| [Ansible](https://www.ansible.com/) | >= 2.16 | Orchestration, roles, playbooks |
| [community.general](https://docs.ansible.com/ansible/latest/collections/community/general/) | >= 9.0 | Plugin de connexion Incus |
| [Molecule](https://molecule.readthedocs.io/) | >= 24.0 | Tests des roles Ansible |
| [pytest](https://docs.pytest.org/) | >= 8.0 | Tests generateur + BDD |
| [Python](https://www.python.org/) | >= 3.11 | Generateur PSOT, scripts |
| [nftables](https://netfilter.org/projects/nftables/) | -- | Isolation inter-bridges |
| [shellcheck](https://www.shellcheck.net/) | -- | Validation scripts shell |
| [ruff](https://docs.astral.sh/ruff/) | -- | Linting Python |

## Credits

anklume est un framework d'assemblage — il orchestre ces excellents projets
open-source (ADR-040) :

### Infrastructure

| Outil | Role |
|-------|------|
| [Incus](https://linuxcontainers.org/incus/) | Containers LXC + machines virtuelles KVM |
| [Ansible](https://www.ansible.com/) | Orchestration, roles, playbooks |
| [community.general](https://docs.ansible.com/ansible/latest/collections/community/general/) | Plugin de connexion Incus pour Ansible |
| [nftables](https://netfilter.org/projects/nftables/) | Isolation reseau inter-bridges |
| [Python](https://www.python.org/) | Generateur PSOT et scripts |
| [PyYAML](https://pyyaml.org/) | Parsing YAML pour le generateur |
| [Noyau Linux](https://kernel.org/) | KVM, LXC, namespaces, cgroups |

### Services IA / ML

| Outil | Role |
|-------|------|
| [Ollama](https://ollama.com/) | Serveur d'inference LLM local |
| [Open WebUI](https://openwebui.com/) | Interface de chat pour LLMs |
| [LobeChat](https://lobechat.com/) | Interface web multi-fournisseurs |
| [Speaches](https://github.com/speaches-ai/speaches) | Reconnaissance vocale (faster-whisper, API OpenAI-compatible) |
| [OpenCode](https://opencode.ai/) | Serveur de codage IA headless |
| [OpenClaw](https://github.com/openclaw-ai/openclaw) | Assistant IA auto-heberge |

### Qualite et tests

| Outil | Role |
|-------|------|
| [Molecule](https://molecule.readthedocs.io/) | Tests des roles Ansible |
| [pytest](https://docs.pytest.org/) | Tests generateur et BDD |
| [Hypothesis](https://hypothesis.readthedocs.io/) | Tests bases sur les proprietes |
| [ansible-lint](https://ansible.readthedocs.io/projects/lint/) | Linting Ansible |
| [yamllint](https://yamllint.readthedocs.io/) | Validation YAML |
| [shellcheck](https://www.shellcheck.net/) | Validation scripts shell |
| [ruff](https://docs.astral.sh/ruff/) | Linting Python |

### Bureau et reseau

| Outil | Role |
|-------|------|
| [tmux](https://github.com/tmux/tmux) | Multiplexeur de terminaux pour la console coloree |
| [libtmux](https://libtmux.git-pull.com/) | API Python pour tmux |
| [Tor](https://www.torproject.org/) | Passerelle de routage anonyme |
| [CUPS](https://openprinting.github.io/cups/) | Serveur d'impression |

### Developpement

| Outil | Role |
|-------|------|
| [Claude Code](https://claude.ai/claude-code) | Developpement assiste par IA |
| [Aider](https://aider.chat/) | Codage assiste par IA |
| [uv](https://docs.astral.sh/uv/) | Gestion des paquets Python |
| [Git](https://git-scm.com/) | Controle de version |

## Licence

[AGPL-3.0](LICENSE)

---

[English version](README.md)
