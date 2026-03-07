# SPEC.md — anklume v2

## 1. Vision

anklume est un framework déclaratif de compartimentalisation
d'infrastructure. Il fournit une isolation de type QubesOS en
utilisant les mécanismes natifs du noyau Linux (KVM/LXC),
orchestrés par Incus et nftables.

L'utilisateur décrit ses domaines dans des fichiers YAML (un par
domaine, style docker-compose), lance `anklume apply`, et obtient
des environnements isolés et reproductibles.

**Principe de design : minimiser la friction.** Des défauts sensés
éliminent la configuration quand l'utilisateur n'a pas d'opinion.
Les messages d'erreur expliquent quoi faire, pas juste ce qui a
échoué.

### Utilisateurs cibles

- **Sysadmins** — compartimentalisation de poste de travail
- **Étudiants** — apprentissage de l'administration système
- **Enseignants** — déploiement de labs réseau pour N étudiants
- **Power users** — isolation type QubesOS sans les contraintes
- **Utilisateurs soucieux de leur vie privée** — routage via
  des passerelles isolées (Tor, VPN)

### Ce que anklume n'est PAS

- Pas une web app ni une API — c'est un outil IaC
- Pas un remplacement d'Ansible — il l'utilise pour le provisioning
- Pas un orchestrateur de conteneurs — il utilise Incus pour ça
- Pas lié à une distribution Linux spécifique

## 2. Installation et utilisation

```bash
pip install anklume          # ou : pipx install anklume
anklume init mon-infra       # crée un répertoire projet
cd mon-infra
vim domains/pro.yml          # décrire un domaine
anklume apply                # déployer vers Incus
```

### Répertoire projet (créé par `anklume init`)

```
mon-infra/
  anklume.yml       # Config globale (projet, addressing, défauts)
  domains/          # Un fichier YAML par domaine
    pro.yml
    perso.yml
  policies.yml      # Politiques réseau inter-domaines (optionnel)
  roles_custom/     # Rôles Ansible utilisateur (optionnel)
```

## 3. Concepts clés

### Domaine

Une zone isolée : un sous-réseau + un projet Incus + N instances.
Chaque domaine est décrit dans son propre fichier (`domains/<nom>.yml`).
Le nom du fichier = le nom du domaine.

### Instance (machine)

Un conteneur LXC ou une VM KVM. Défini dans le fichier domaine.
Les noms courts sont auto-préfixés avec le nom du domaine :
`dev` dans `pro.yml` → `pro-dev` dans Incus.

### Profil

Configuration Incus réutilisable (GPU, nesting, limites de
ressources). Défini au niveau du domaine.

### Niveau de confiance (trust level)

Posture de sécurité d'un domaine, encodée dans l'adressage IP :

| Niveau | Offset zone | 2e octet par défaut | Couleur |
|--------|-------------|---------------------|---------|
| admin | 0 | 100 | bleu |
| trusted | 10 | 110 | vert |
| semi-trusted | 20 | 120 | jaune |
| untrusted | 40 | 140 | rouge |
| disposable | 50 | 150 | magenta |

Depuis `10.140.0.5`, un admin sait : zone 140 = 100+40 = untrusted.

## 4. Modèle source de vérité (PSOT)

```
domains/*.yml ──[anklume apply]──> Incus (projets, réseaux, instances)
                                 ──> Ansible (provisioning)
```

- Les fichiers domaine sont la vérité structurelle (quoi créer)
- Ansible est utilisé uniquement pour le provisioning (quoi installer)
- Pas d'étape intermédiaire `sync` — Python pilote Incus directement
- Les fichiers domaine sont commités dans git

## 5. Format des fichiers

### `anklume.yml` (config globale)

```yaml
project: mon-infra

defaults:
  os_image: images:debian/13
  trust_level: semi-trusted

addressing:
  base: "10.100"
  zone_step: 10
```

### `domains/<nom>.yml` (un domaine)

```yaml
description: "Environnement professionnel"
trust_level: semi-trusted

machines:
  dev:                          # → nom Incus : pro-dev
    description: "Développement"
    type: lxc
    roles: [base, dev-tools]
    persistent:
      projects: /home/user/projects

  desktop:                      # → nom Incus : pro-desktop
    description: "Bureau KDE"
    type: lxc
    gpu: true
    roles: [base, desktop]

profiles:
  gpu-passthrough:
    devices:
      gpu:
        type: gpu
```

### `policies.yml` (politiques réseau)

```yaml
policies:
  - from: pro
    to: ai-tools
    ports: [11434, 3000]
    description: "Pro accède à Ollama et Open WebUI"

  - from: host
    to: shared-dns
    ports: [53]
    protocol: udp
    description: "DNS local"
```

### Champs domaine

| Champ | Défaut | Description |
|-------|--------|-------------|
| `description` | requis | À quoi sert ce domaine |
| `trust_level` | semi-trusted | Posture de sécurité |
| `enabled` | true | false ignore ce domaine |
| `ephemeral` | false | true autorise la suppression |
| `profiles` | {} | Profils Incus à créer |
| `machines` | {} | Instances dans ce domaine |

### Champs machine

| Champ | Défaut | Description |
|-------|--------|-------------|
| `description` | requis | À quoi sert cette machine |
| `type` | lxc | lxc ou vm |
| `ip` | auto | Auto-assigné depuis le sous-réseau |
| `ephemeral` | hérité | Hérite du domaine |
| `gpu` | false | Passthrough GPU |
| `profiles` | [default] | Profils Incus à appliquer |
| `roles` | [] | Rôles Ansible pour le provisioning |
| `config` | {} | Config Incus (overrides) |
| `persistent` | {} | Volumes persistants (`nom: chemin`) |
| `vars` | {} | Variables Ansible pour cette machine |
| `weight` | 1 | Poids d'allocation de ressources |

### Convention d'adressage

```
10.<zone_base + zone_offset>.<domain_seq>.<host>/24
```

- `domain_seq` : auto-assigné alphabétiquement dans chaque zone
- `.1-.99` : statique (machines), `.100-.199` : DHCP, `.254` : passerelle
- IPs explicites aussi supportées (champ `ip` sur la machine)

### Nommage des machines

Le nom court dans le fichier domaine est auto-préfixé :

```
domains/pro.yml → machine "dev" → nom Incus "pro-dev"
domains/ai-tools.yml → machine "gpu" → nom Incus "ai-tools-gpu"
```

Les noms complets (après préfixage) doivent être globalement uniques.

### Politiques réseau

Tout le trafic inter-domaines est bloqué par défaut. Les exceptions
sont déclarées dans `policies.yml` :

```yaml
policies:
  - description: "Pourquoi cet accès est nécessaire"
    from: pro              # domaine, machine, ou "host"
    to: ai-tools           # domaine ou machine
    ports: [3000, 8080]    # ou "all"
    protocol: tcp          # tcp ou udp (défaut : tcp)
    bidirectional: false   # défaut false
```

### Contraintes de validation

- Noms de domaine : uniques, DNS-safe (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)
- Noms de machines : globalement uniques (après préfixage)
- IPs : globalement uniques, dans le bon sous-réseau
- Profils référencés par une machine doivent exister dans son domaine
- GPU : exclusif par défaut (une seule instance GPU sauf override)
- `trust_level` : admin, trusted, semi-trusted, untrusted, disposable

## 6. Commandes CLI

### Workflow principal

| Commande | Description |
|----------|-------------|
| `anklume init [dir]` | Créer un nouveau projet |
| `anklume apply` | Déployer toute l'infrastructure |
| `anklume apply <domaine>` | Déployer un seul domaine |
| `anklume status` | Afficher l'état des instances |
| `anklume destroy` | Détruire (respecte ephemeral) |
| `anklume destroy --force` | Tout détruire |

### Gestion des instances

| Commande | Description |
|----------|-------------|
| `anklume instance list` | Lister les instances |
| `anklume instance shell <nom>` | Shell dans une instance |
| `anklume snapshot create` | Snapshotter toutes les instances |
| `anklume snapshot restore <nom>` | Restaurer un snapshot |
| `anklume network rules` | Générer les règles nftables |
| `anklume network deploy` | Appliquer les règles sur l'hôte |

### Développement

| Commande | Description |
|----------|-------------|
| `anklume dev lint` | Tous les validateurs |
| `anklume dev test` | pytest + behave |

## 7. Modèle d'exécution

### Deux contextes

1. **Hôte** — où l'utilisateur lance les commandes CLI, où Incus tourne
2. **anklume-instance** — conteneur avec socket Incus, Ansible, le
   framework. Où les opérations d'infrastructure s'exécutent réellement.

La CLI détecte le contexte et délègue de manière transparente :

```
anklume apply
  ├─ Détecte : exécution sur l'hôte
  ├─ Vérifie : anklume-instance existe et tourne
  ├─ Délègue : incus exec anklume-instance -- anklume apply
  └─ Retransmet la sortie à l'utilisateur
```

### Bootstrap

`anklume apply` sur un système vierge :
1. Crée `anklume-instance` (si inexistant)
2. Monte le socket Incus en lecture/écriture
3. Installe le framework dans le conteneur
4. Lance `anklume apply` à l'intérieur

## 8. Live ISO (concern séparé)

La Live ISO est un produit éducatif/démo construit au-dessus
d'anklume. Elle vit dans `live/` et n'est pas requise pour
l'utilisation normale.

### Flow de boot

```
Boot ISO → tty1 → bash_profile → KDE Plasma
  └─ Le navigateur ouvre la plateforme d'apprentissage (/setup)
```

### Plateforme web

- Serveur FastAPI sur l'hôte (lecture seule)
- UI split-pane : contenu à gauche, terminal à droite (ttyd)
- Guide interactif, labs, configuration de persistance
- Bilingue (fr/en)

### La Live ISO n'est PAS le framework

Le builder ISO (`live/build.sh`) empaquète anklume + dépendances
dans une image bootable. Les changements au framework (`src/`)
nécessitent un rebuild ISO uniquement pour tester la Live ISO.

## 9. Leçons du POC

### Garder
- Adressage par niveau de confiance (IPs lisibles)
- Isolation nftables (drop-all + allow sélectif)
- KDE Plasma uniquement
- Bilingue fr/en
- Plateforme web pour l'apprentissage
- ttyd pour le terminal web

### Abandonner
- Makefile comme backend
- `anklume sync` (étape intermédiaire inutile)
- `incus exec anklume-instance` manuel
- Fichiers Ansible générés comme source de vérité secondaire
- `infra.yml` monolithique (remplacé par `domains/*.yml`)
- 200+ lignes de HTML inline dans Python

### Changer
- CLI → Python directement (plus de scripts bash intermédiaires)
- Délégation transparente host ↔ container
- Framework séparé du projet utilisateur
