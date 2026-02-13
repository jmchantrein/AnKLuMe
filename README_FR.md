# AnKLuMe 🔨

[![WIP](https://img.shields.io/badge/status-WIP-yellow)](docs/ROADMAP.md)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Ansible](https://img.shields.io/badge/ansible-%3E%3D2.16-EE0000?logo=ansible&logoColor=white)](https://www.ansible.com/)
[![Incus](https://img.shields.io/badge/incus-%3E%3D6.0%20LTS-orange)](https://linuxcontainers.org/incus/)
[![Molecule](https://img.shields.io/badge/molecule-tested-green)](https://molecule.readthedocs.io/)
[![ansible-lint](https://img.shields.io/badge/ansible--lint-production-brightgreen)](https://ansible.readthedocs.io/projects/lint/)
[![shellcheck](https://img.shields.io/badge/shellcheck-passing-brightgreen)](https://www.shellcheck.net/)
[![CI](https://github.com/jmchantrein/AnKLuMe/actions/workflows/ci.yml/badge.svg)](https://github.com/jmchantrein/AnKLuMe/actions)

**Isolation type QubesOS utilisant les fonctionnalités natives du noyau Linux (KVM/LXC).**

Orchestré sereinement par vous, en assemblant des outils standards éprouvés
sans réinventer la roue.

> [Ansible](https://www.ansible.com/), [KVM](https://linux-kvm.org/), [LXC](https://linuxcontainers.org/lxc/), [Molecule](https://molecule.readthedocs.io/) ⇒ **AnKLuMe** — de "enclume", traduction française d'[Incus](https://linuxcontainers.org/incus/) 🔨

---

## Qu'est-ce qu'AnKLuMe ?

AnKLuMe est un framework déclaratif de cloisonnement d'infrastructure.
Vous décrivez vos environnements isolés dans un seul fichier YAML, lancez
deux commandes, et obtenez des domaines reproductibles, jetables et isolés
par réseau — chacun avec son propre sous-réseau, projet Incus et ensemble
de containers ou VMs.

La philosophie [QubesOS](https://www.qubes-os.org/), mais :
- **Pas d'OS dédié** — fonctionne sur n'importe quelle distribution Linux
- **Pas de Xen** — utilise les fonctionnalités natives du noyau (KVM pour les VMs, LXC pour les containers)
- **Pas de boîte noire** — des outils standards que vous connaissez déjà, assemblés intelligemment
- **Déclaratif** — décrivez ce que vous voulez, AnKLuMe converge

## Pour qui ?

- **Administrateurs systèmes** qui veulent cloisonner leur poste de travail
  (admin, professionnel, personnel, homelab — chacun dans son réseau isolé)
- **Enseignants** déployant des TPs réseau pour N étudiants en une commande
- **Utilisateurs avancés** qui veulent l'isolation QubesOS sans les contraintes
  QubesOS

## Comment ça marche

```
infra.yml          →    make sync    →    Fichiers Ansible  →    make apply    →    État Incus
(vous décrivez)         (génération)      (vous enrichissez)     (convergence)      (infra active)
```

1. **Décrivez** votre infrastructure dans `infra.yml` (Source de Vérité Primaire)
2. **Générez** l'arborescence Ansible : `make sync`
3. **Enrichissez** les fichiers générés avec vos variables personnalisées (Source de Vérité Secondaire)
4. **Appliquez** : `make apply` — réseaux, projets, profils, instances, provisioning

## Prérequis

Avant d'utiliser AnKLuMe, il vous faut :

1. **Un hôte Linux** avec [Incus](https://linuxcontainers.org/incus/docs/main/installing/)
   installé et initialisé
2. **Une instance d'administration** (container LXC ou VM) nommée `admin-ansible`, avec :
   - Le socket Incus monté (`/var/run/incus/unix.socket`)
   - Ansible, Python 3.11+, git installés
3. **Ce dépôt** cloné dans l'instance d'administration

AnKLuMe s'exécute entièrement depuis l'instance d'administration. Il ne modifie
jamais l'hôte directement — tout passe par le socket Incus.

> Guides d'installation de l'hôte pour Debian et Arch Linux : voir [ROADMAP](docs/ROADMAP.md).

## Démarrage rapide

Dans l'instance `admin-ansible` :

```bash
# Cloner
git clone https://github.com/<user>/anklume.git
cd anklume

# Installer les dépendances Ansible
make init

# Créer votre descripteur d'infrastructure
cp infra.yml.example infra.yml
# Éditez infra.yml — définissez vos domaines et machines

# Générer les fichiers Ansible
make sync

# Prévisualiser les changements
make check

# Appliquer
make apply
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ Hôte (n'importe quelle distro Linux)                    │
│  • Incus daemon + nftables + (optionnel) GPU NVIDIA     │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ net-aaa  │ │ net-bbb  │ │ net-ccc  │  ...           │
│  │ subnet A │ │ subnet B │ │ subnet C │                │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘                │
│       │             │             │                      │
│  ┌────┴────┐  ┌─────┴────┐ ┌────┴──────┐               │
│  │ LXC/VM  │  │ LXC/VM   │ │ LXC/VM   │               │
│  └─────────┘  └──────────┘ └──────────┘                │
│                                                         │
│  Isolation nftables : subnet A ≠ B ≠ C (pas de forward)│
└─────────────────────────────────────────────────────────┘
```

Chaque **domaine** est un sous-réseau isolé avec son propre projet Incus.
Les containers et VMs d'un domaine communiquent entre eux mais pas avec les
autres domaines. Un container d'administration pilote tout via le socket
Incus — pas besoin de SSH.

## Fonctionnalités

- **Déclaratif** : Décrivez domaines, machines, profils dans `infra.yml`
- **Exécution en deux phases** : Infrastructure (réseaux, projets, instances)
  puis provisioning (paquets, services)
- **Réconciliation** : Idempotent — détecte la dérive, crée ce qui manque,
  signale les orphelins
- **GPU passthrough** : Support optionnel NVIDIA pour containers LXC (LLM, ML)
- **Snapshots** : Individuels, par domaine, ou globaux — avec restauration
- **Testé** : Molecule pour les rôles, pytest pour le générateur

## Documentation

- [Guide de démarrage rapide](docs/quickstart.md)
- [Guide de déploiement TP](docs/lab-tp.md) — pour les enseignants déployant des TPs étudiants
- [Guide GPU + LLM](docs/gpu-llm.md) — GPU passthrough, Ollama, Open WebUI
- [Spécification complète](docs/SPEC.md)
- [Décisions d'architecture](docs/ARCHITECTURE.md)
- [Feuille de route](docs/ROADMAP.md)
- [Workflow Claude Code](docs/claude-code-workflow.md)
- [Contribuer](CONTRIBUTING.md)

## Exemples

Configurations `infra.yml` prêtes à l'emploi pour les cas d'usage courants :

| Exemple | Description |
|---------|-------------|
| [Étudiant sysadmin](examples/student-sysadmin/) | 2 domaines (admin + lab) pour étudiants sysadmin, sans GPU |
| [TP enseignant](examples/teacher-lab/) | Admin + N domaines étudiants avec réseaux isolés et snapshots |
| [Poste professionnel](examples/pro-workstation/) | Domaines admin, perso, pro, homelab avec GPU |
| [Sandbox isolation](examples/sandbox-isolation/) | Isolation maximale pour tests de logiciels non fiables |
| [Superviseur LLM](examples/llm-supervisor/) | 2 LLMs isolés + 1 superviseur pour gestion multi-LLM |
| [Développeur](examples/developer/) | Environnement développeur AnKLuMe avec tests Incus-in-Incus |

Voir [examples/README.md](examples/README.md) pour plus de détails.

## Stack technique

| Outil | Rôle |
|-------|------|
| [Ansible](https://www.ansible.com/) | Orchestration, rôles, playbooks |
| [Incus](https://linuxcontainers.org/incus/) | Gestion containers/VMs (LXC + KVM) |
| [KVM](https://linux-kvm.org/) | Virtualisation native du noyau (VMs) |
| [LXC](https://linuxcontainers.org/lxc/) | Containers natifs du noyau |
| [Molecule](https://molecule.readthedocs.io/) | Tests des rôles Ansible |
| [nftables](https://netfilter.org/projects/nftables/) | Isolation réseau inter-domaines |
| [community.general](https://docs.ansible.com/ansible/latest/collections/community/general/) | Plugin de connexion Incus |

## Licence

[Apache 2.0](LICENSE)

---

🇬🇧 [English version](README.md)
