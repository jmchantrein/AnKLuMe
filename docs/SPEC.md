# SPEC.md — anklume

## 1. Vision

anklume est un framework déclaratif de compartimentalisation
d'infrastructure. Il fournit une isolation de type QubesOS en
utilisant les mécanismes natifs du noyau Linux (KVM/LXC),
orchestrés par Incus et nftables.

L'utilisateur décrit ses domaines dans des fichiers YAML (un par
domaine, style docker-compose), lance `anklume apply all`, et
obtient des environnements isolés et reproductibles.

**Principe de design : minimiser la friction.** Des défauts sensés
éliminent la configuration quand l'utilisateur n'a pas d'opinion.
Les messages d'erreur expliquent quoi faire, pas juste ce qui a
échoué.

### Utilisateurs cibles

- **Sysadmins** — compartimentalisation de poste de travail
- **Étudiants** — apprentissage de l'administration système
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
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe
uv sync

uv run anklume init mon-infra
cd mon-infra
vim domains/pro.yml
uv run anklume apply all
```

### Mode développement

```bash
uv sync --group dev
uv run anklume dev setup       # prépare l'environnement de dev
uv run anklume dev lint
uv run anklume dev test
```

`anklume dev setup` prépare l'environnement de développement :
nesting Incus vérifié, dépendances Ansible, conteneur de test,
hooks git, etc.

### Répertoire projet (créé par `anklume init`)

```
mon-infra/
  anklume.yml       # Config globale (addressing, défauts, schema_version)
  domains/          # Un fichier YAML par domaine
    pro.yml
    perso.yml
  policies.yml      # Politiques réseau inter-domaines (optionnel)
  ansible/          # Provisioning Ansible (généré + personnalisable)
    inventory/      # Inventaire (généré depuis domains/)
    group_vars/     # Variables par domaine
    host_vars/      # Variables par machine
    site.yml        # Playbook principal
  ansible_roles_custom/  # Rôles Ansible utilisateur (optionnel)
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

## 4. Modèle source de vérité (PSOT) — stateless

```
domains/*.yml ──[anklume apply]──> Incus (projets, réseaux, instances)
                                 ──> Ansible (provisioning)
```

- Les fichiers domaine sont la première source de vérité (quoi créer)
- Incus est la source de vérité secondaire (état réel)
- `anklume apply` réconcilie : lit le désiré (YAML), interroge le réel
  (Incus), applique les différences
- Pas de state file — le système est stateless par design
- Ansible est utilisé pour le provisioning (quoi installer)
- Python pilote Incus directement (pas d'étape intermédiaire)
- Les fichiers domaine sont commités dans git

### Dry-run

`anklume apply --dry-run` affiche les changements prévus sans les
appliquer. Montre les créations, modifications et suppressions
pour chaque ressource (projet, réseau, instance).

### Gestion d'erreurs

En cas d'échec partiel (ex: domaine 3/5 échoue), anklume :
- continue les domaines indépendants (best-effort)
- rapporte clairement les succès et les échecs
- un `anklume apply` suivant reprend depuis l'état réel (idempotent)

Pas de rollback automatique : les domaines réussis restent en place.
L'utilisateur corrige et relance.

## 5. Format des fichiers

### `anklume.yml` (config globale)

```yaml
schema_version: 1

defaults:
  os_image: images:debian/13
  trust_level: semi-trusted

addressing:
  base: "10.100"
  zone_step: 10

nesting:
  prefix: true        # préfixer les ressources Incus par le niveau
```

`schema_version` permet la migration automatique quand le format
évolue. `anklume apply` vérifie la version et propose la migration
si nécessaire.

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
| `gpu` | false | Passthrough GPU (pour Ollama, STT, etc.) |
| `profiles` | [default] | Profils Incus à appliquer |
| `roles` | [] | Rôles Ansible pour le provisioning |
| `config` | {} | Config Incus (overrides) |
| `persistent` | {} | Volumes persistants (`nom: chemin`) |
| `vars` | {} | Variables Ansible pour cette machine |
| `weight` | 1 | Poids pour l'allocation de ressources (voir resource_policy) |

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

`bidirectional` contrôle qui peut initier la connexion :
- `false` (défaut) : seul `from` peut initier vers `to`
- `true` : les deux parties peuvent initier la connexion

### Contraintes de validation

- Noms de domaine : uniques, DNS-safe (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)
- Noms de machines : globalement uniques (après préfixage)
- IPs : globalement uniques, dans le bon sous-réseau
- Profils référencés par une machine doivent exister dans son domaine
- `trust_level` : admin, trusted, semi-trusted, untrusted, disposable

## 6. Commandes CLI

### Workflow principal

| Commande | Description |
|----------|-------------|
| `anklume init [dir]` | Créer un nouveau projet |
| `anklume apply all` | Déployer toute l'infrastructure |
| `anklume apply all --dry-run` | Afficher les changements sans appliquer |
| `anklume apply domain <nom>` | Déployer un seul domaine |
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
| `anklume dev setup` | Préparer l'environnement de dev |
| `anklume dev lint` | Tous les validateurs |
| `anklume dev test` | pytest + behave |

## 7. Modèle d'exécution

La CLI tourne directement sur l'hôte. Dépendances gérées par `uv`.
Incus et Ansible sont appelés via `subprocess`.

```
anklume apply all
  ├─ Lit anklume.yml + domains/*.yml
  ├─ Vérifie schema_version (migration si nécessaire)
  ├─ Valide (noms, IPs, contraintes)
  ├─ Calcule l'adressage automatique
  ├─ Interroge Incus via IncusDriver (état réel)
  ├─ Réconcilie : calcule le diff (désiré vs réel)
  ├─ Produit un plan d'actions ordonnées
  ├─ [--dry-run] Affiche le plan et s'arrête
  ├─ Exécute le plan (créations, mises à jour, démarrages)
  └─ Rapporte les succès et échecs par domaine
```

### 7.1 Incus driver (`engine/incus_driver.py`)

Seul module autorisé à appeler `subprocess` pour Incus.
Contrat : entrées/sorties typées, pas de logique métier.

#### Appels CLI encapsulés

| Méthode | Commande Incus |
|---------|---------------|
| `project_list()` | `incus project list --format json` |
| `project_create(name, desc)` | `incus project create <name> -c features.images=false -c features.profiles=false` |
| `project_exists(name)` | Vérifie dans `project_list()` |
| `network_list(project)` | `incus network list --project <p> --format json` |
| `network_create(name, project, config)` | `incus network create <name> --project <p> --type bridge` + config |
| `network_exists(name, project)` | Vérifie dans `network_list()` |
| `instance_list(project)` | `incus list --project <p> --format json` |
| `instance_create(name, project, image, ...)` | `incus init <image> <name> --project <p>` + profiles + config |
| `instance_start(name, project)` | `incus start <name> --project <p>` |
| `instance_stop(name, project)` | `incus stop <name> --project <p>` |
| `instance_delete(name, project)` | `incus delete <name> --project <p>` |

#### Gestion d'erreurs

`IncusError(command, returncode, stderr)` — levée quand la CLI
retourne un code non-zéro. Le message inclut la commande complète
et la sortie stderr pour le diagnostic.

#### Configuration du projet Incus

Chaque domaine crée un projet Incus avec :
- `features.images=false` — utilise les images du projet default
- `features.profiles=false` — utilise les profils du projet default

### 7.2 Réconciliateur (`engine/reconciler.py`)

Compare l'état désiré (Infrastructure) avec l'état réel (Incus)
et produit un plan d'actions ordonnées.

#### Actions de réconciliation

```python
@dataclass
class Action:
    verb: str        # "create" | "start" | "stop" | "delete" | "skip"
    resource: str    # "project" | "network" | "instance"
    target: str      # nom de la ressource
    project: str     # projet Incus concerné
    detail: str      # description lisible
```

#### Ordre d'exécution

Le plan est ordonné par dépendances :
1. Créer les projets manquants
2. Créer les réseaux manquants
3. Créer les instances manquantes
4. Démarrer les instances arrêtées
5. (Suppression : Phase 9, avec `anklume destroy`)

#### Logique de réconciliation par domaine

Pour chaque domaine activé (`enabled: true`) :

**Projet** :
- Si le projet n'existe pas → `Action("create", "project", ...)`
- Si le projet existe → rien (skip)

**Réseau** :
- Nom du bridge : `net-{domain_name}`
- Config : `ipv4.address={gateway}/24`, `ipv4.nat=true`
- Si le réseau n'existe pas → `Action("create", "network", ...)`
- Si le réseau existe → rien (skip)

**Instances** :
- Pour chaque machine du domaine :
  - Si l'instance n'existe pas → `Action("create", "instance", ...)` + `Action("start", "instance", ...)`
  - Si l'instance existe et est Stopped → `Action("start", "instance", ...)`
  - Si l'instance existe et est Running → rien (skip)

#### Instance Incus : configuration

Chaque instance est créée avec :
- Image : `defaults.os_image` (ex: `images:debian/13`)
- Type : `container` (LXC) ou `virtual-machine` (VM)
- Profils : ceux déclarés dans le YAML
- Config Incus : `config` du YAML + protection delete si non-éphémère

Protection delete : `security.protection.delete=true` si
`ephemeral=false` (ADR-011).

#### Dry-run

`reconcile(infra, driver, dry_run=True)` retourne le plan sans
l'exécuter. Le plan est affiché à l'utilisateur avec un résumé :
```
[dry-run] Domaine pro :
  + Créer projet : pro
  + Créer réseau : net-pro (10.120.0.254/24)
  + Créer instance : pro-dev (lxc, images:debian/13)
  + Démarrer instance : pro-dev
```

#### Gestion d'erreurs

Best-effort par domaine : si un domaine échoue, les autres
continuent. Le résultat final rapporte succès/échecs.

```python
@dataclass
class ReconcileResult:
    actions: list[Action]         # toutes les actions planifiées
    executed: list[Action]        # actions exécutées avec succès
    errors: list[tuple[Action, str]]  # (action, message d'erreur)
```

### Prérequis sur l'hôte

- Python 3.11+ avec uv
- Incus installé et configuré
- Ansible (optionnel, pour le provisioning)

### Sur la Live ISO

Tout est pré-installé dans le squashfs. L'utilisateur lance
`anklume apply all` directement après le boot.

## 8. Nesting Incus

Support du nesting LXC pour les architectures multi-niveaux
(conteneurs dans conteneurs).

### Préfixe de nesting

Quand `nesting.prefix: true` (défaut), les ressources Incus sont
préfixées par le niveau de profondeur pour éviter les collisions :

| Ressource | Hôte (L0) | Niveau 1 | Niveau 2 |
|-----------|-----------|----------|----------|
| Projet Incus | `pro` | `001-pro` | `002-pro` |
| Bridge réseau | `net-pro` | `001-net-pro` | `002-net-pro` |
| Instance | `pro-dev` | `001-pro-dev` | `002-pro-dev` |

Format du préfixe : `{level:03d}-`

Les chemins Ansible (inventory, group_vars, host_vars) restent
sans préfixe — ils sont locaux à chaque niveau.

### Fichiers de contexte

Chaque instance reçoit 4 fichiers dans `/etc/anklume/` pour
déterminer son niveau de nesting :

| Fichier | Description |
|---------|-------------|
| `absolute_level` | Profondeur depuis l'hôte physique (L0=0, L1=1, ...) |
| `relative_level` | Reset à 0 à chaque frontière VM |
| `vm_nested` | `true` si une VM existe dans la chaîne d'ancêtres |
| `yolo` | Mode override pour bypasser les checks de sécurité |

### Sécurité par niveau

| Niveau | Configuration |
|--------|---------------|
| L1 (dans l'hôte) | `security.nesting=true` + syscalls intercept (unprivileged) |
| L2+ (dans conteneur) | `security.privileged=true` + `security.nesting=true` |

L2+ utilise des conteneurs privilegiés à l'intérieur de conteneurs
unprivileged — sûr par design (recommandation stgraber).

## 9. Resource policy

Allocation automatique des ressources CPU/mémoire aux instances,
configurable dans `anklume.yml` :

```yaml
resource_policy:
  host_reserve:
    cpu: "20%"           # réserve hôte (pourcentage ou nombre absolu)
    memory: "20%"        # réserve hôte (pourcentage ou taille absolue)
  mode: proportional     # proportional ou equal
  cpu_mode: allowance    # allowance (%) ou count (vCPUs fixes)
  memory_enforce: soft   # soft (ballooning cgroups) ou hard (limite stricte)
  overcommit: false      # true = warning au lieu d'erreur si total > disponible
```

La distribution utilise le champ `weight` de chaque machine :
- `weight: 3` → reçoit 3x la part d'une machine `weight: 1`
- Les machines avec des limites explicites dans `config` sont
  exclues de l'auto-allocation pour ces ressources

Détection hardware : `incus info --resources --format json`,
fallback sur `/proc/cpuinfo` + `/proc/meminfo`.

## 10. Snapshots

Snapshots automatiques et manuels pour la sécurité des données.

### Snapshots automatiques

Avant et après chaque modification d'une instance par `anklume apply` :
- **Pré-apply** : snapshot de l'état avant modification
- **Post-apply** : snapshot de l'état après modification réussie

Convention de nommage : `anklume-{pre|post}-{timestamp}`

### Snapshots manuels

- `anklume snapshot create` — snapshot de toutes les instances
- `anklume snapshot create <instance>` — snapshot d'une instance
- `anklume snapshot restore <nom>` — restaurer un snapshot
- `anklume snapshot list` — lister les snapshots disponibles

## 11. Fonctionnalités additionnelles

### Intégration IA

Support natif de LLM locaux/externes :
- Ollama (local, GPU passthrough)
- OpenRouter (cloud, tokenisation)
- STT (Speaches, coexistence GPU)

### Live ISO — OS immuable avec persistance chiffrée

La Live ISO fournit un OS immuable prêt à l'emploi pour anklume.
Boot en RAM (squashfs), données pérennisées sur disque chiffré
(ZFS ou BTRFS). Elle vit dans `live/`.

**Objectif** : démarrer anklume sur n'importe quelle machine sans
installer de distribution. L'OS est en lecture seule (immuable),
seules les données utilisateur (domaines, instances, configs)
persistent sur un volume chiffré.

**Architecture** :
- Boot ISO → squashfs en RAM → KDE Plasma
- Détection automatique du disque de persistance (ZFS/BTRFS chiffré)
- Sans disque de persistance : mode RAM-only (éphémère)
- Si disque présent : montage automatique, reprise de l'infra

**Contraintes sur le core** :
- Les chemins de données d'anklume doivent être configurables
- Le storage backend d'Incus doit pouvoir vivre sur le volume
  chiffré (ZFS pool ou BTRFS subvolume)
- `anklume apply all` idempotent (survit aux redémarrages)

### Schema versioning

`schema_version` dans `anklume.yml` suit le format des fichiers.
Quand anklume détecte une version antérieure :
- affiche les changements nécessaires
- propose la migration automatique (`anklume apply` ou `anklume migrate`)
- refuse de continuer sur un schéma incompatible sans migration

## 12. Historique

La branche `poc` contient le prototype initial. Décisions retenues :

### Garder
- Adressage par niveau de confiance (IPs lisibles)
- Isolation nftables (drop-all + allow sélectif)
- KDE Plasma uniquement
- Bilingue fr/en
- Plateforme web pour l'apprentissage
- ttyd pour le terminal web
- Nesting Incus (préfixes, contexte, sécurité par niveau)
- Resource policy (allocation CPU/mémoire par poids)
- STT (Speaches)
- Intégration IA (LLM) local/externe, OpenRouter, tokenisation

### Abandonner
- Makefile comme backend
- `anklume sync` (étape intermédiaire)
- anklume-instance (conteneur de management)
- `infra.yml` monolithique (remplacé par `domains/*.yml`)
- 200+ lignes de HTML inline dans Python

### Changer
- CLI → Python directement (plus de scripts bash intermédiaires)
- Exécution directe sur l'hôte (uv)
- Installation par `git clone` + `uv sync`
