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
| `anklume apply all --no-provision` | Déployer sans provisioning Ansible |
| `anklume apply domain <nom>` | Déployer un seul domaine |
| `anklume status` | Afficher l'état des instances |
| `anklume destroy` | Détruire (respecte ephemeral) |
| `anklume destroy --force` | Tout détruire |

### Gestion des instances

| Commande | Description |
|----------|-------------|
| `anklume instance list` | Tableau des instances (nom, domaine, état, IP, type) |
| `anklume instance exec <inst> -- <cmd>` | Exécuter dans une instance |
| `anklume instance info <inst>` | Détails d'une instance |

### Gestion des domaines

| Commande | Description |
|----------|-------------|
| `anklume domain list` | Tableau des domaines |
| `anklume domain check <nom>` | Valider un domaine isolément |
| `anklume domain exec <nom> -- <cmd>` | Exécuter dans toutes les instances |
| `anklume domain status <nom>` | État détaillé d'un domaine |

### Snapshots

| Commande | Description |
|----------|-------------|
| `anklume snapshot create [instance]` | Snapshotter toutes les instances ou une seule |
| `anklume snapshot create --name X` | Snapshot avec nom personnalisé |
| `anklume snapshot list [instance]` | Lister les snapshots |
| `anklume snapshot restore <inst> <snap>` | Restaurer un snapshot |
| `anklume snapshot delete <inst> <snap>` | Supprimer un snapshot |
| `anklume snapshot rollback <inst> <snap>` | Rollback destructif |

### Réseau

| Commande | Description |
|----------|-------------|
| `anklume network rules` | Générer les règles nftables |
| `anklume network deploy` | Appliquer les règles sur l'hôte |
| `anklume network status` | État réseau (bridges, IPs, nftables) |

### LLM

| Commande | Description |
|----------|-------------|
| `anklume llm status` | Vue dédiée backends LLM |
| `anklume llm bench` | Benchmark inférence |

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
  ├─ Snapshots pré-apply (instances existantes à modifier)
  ├─ Exécute le plan (créations, mises à jour, démarrages)
  ├─ Snapshots post-apply (instances modifiées/créées)
  ├─ [sauf --no-provision] Provisioning Ansible (roles)
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

### Détection du contexte de nesting

Au démarrage, anklume lit son contexte de nesting depuis les fichiers
dans `/etc/anklume/`. Si le répertoire ou les fichiers sont absents,
le niveau est 0 (hôte physique).

```python
@dataclass
class NestingContext:
    absolute_level: int = 0    # 0 = hôte, 1 = L1, 2 = L2, ...
    relative_level: int = 0    # reset à 0 après frontière VM
    vm_nested: bool = False    # true si VM dans la chaîne d'ancêtres
    yolo: bool = False         # override des checks de sécurité
```

`detect_nesting_context()` lit `/etc/anklume/absolute_level` etc.
et retourne un `NestingContext`. Fonction pure (fichiers injectés
par le niveau parent).

### Préfixe de nesting

Quand `nesting.prefix: true` (défaut) ET `absolute_level > 0`,
les ressources Incus sont préfixées par le niveau de profondeur
pour éviter les collisions de noms entre niveaux :

| Ressource | Hôte (L0) | Niveau 1 | Niveau 2 |
|-----------|-----------|----------|----------|
| Projet Incus | `pro` | `001-pro` | `002-pro` |
| Bridge réseau | `net-pro` | `001-net-pro` | `002-net-pro` |
| Instance | `pro-dev` | `001-pro-dev` | `002-pro-dev` |

Format du préfixe : `{level:03d}-`

À L0 (hôte), aucun préfixe — même avec `nesting.prefix: true`.
Le préfixe sert uniquement aux niveaux imbriqués pour éviter les
collisions avec les ressources du niveau parent.

Les chemins Ansible (inventory, group_vars, host_vars) restent
sans préfixe — ils sont locaux à chaque niveau.

#### Application du préfixe

```python
def prefix_name(name: str, context: NestingContext, nesting_config: NestingConfig) -> str:
    if nesting_config.prefix and context.absolute_level > 0:
        return f"{context.absolute_level:03d}-{name}"
    return name
```

Le préfixe est appliqué dans le réconciliateur, sur les noms
de ressources Incus : projets, réseaux et instances.

### Fichiers de contexte

Chaque instance créée par anklume reçoit 4 fichiers dans
`/etc/anklume/` pour que le prochain niveau puisse déterminer
son contexte de nesting :

| Fichier | Contenu | Exemple L1 |
|---------|---------|------------|
| `absolute_level` | parent.absolute_level + 1 | `1` |
| `relative_level` | parent.relative_level + 1 (reset si VM) | `1` |
| `vm_nested` | `true` si instance VM ou parent.vm_nested | `false` |
| `yolo` | hérité du parent | `false` |

Pour `relative_level` : si l'instance créée est de type VM,
`relative_level` est remis à 0 (frontière VM). Sinon, il est
incrémenté de 1 par rapport au parent.

Pour `vm_nested` : `true` si l'instance créée est une VM, ou si
le parent a déjà `vm_nested: true`.

#### Injection dans les instances

Après le démarrage d'une instance, le réconciliateur :
1. Crée `/etc/anklume/` via `incus exec -- mkdir -p /etc/anklume`
2. Écrit chaque fichier via `incus exec -- sh -c 'echo VALUE > /etc/anklume/FILE'`

Injection best-effort : si l'instance refuse les commandes (VM pas
encore bootée, image sans shell), un warning est affiché et le
pipeline continue.

### Driver Incus — méthodes nesting

| Méthode | Commande Incus |
|---------|---------------|
| `instance_exec(inst, project, cmd)` | `incus exec <inst> --project <p> -- <cmd...>` |

### Sécurité par niveau

La configuration de sécurité des instances créées dépend du niveau
courant d'anklume :

| Niveau courant | Instances créées | Configuration |
|----------------|------------------|---------------|
| L0 (hôte) | L1 | `security.nesting=true`, `security.syscalls.intercept.mknod=true`, `security.syscalls.intercept.setxattr=true` |
| L1+ (conteneur) | L2+ | `security.nesting=true`, `security.privileged=true` |

L1 : instances unprivileged avec nesting activé et interception
des syscalls nécessaires au fonctionnement d'Incus à l'intérieur.

L2+ : conteneurs privilegiés à l'intérieur de conteneurs
unprivileged — sûr par design (recommandation stgraber).

```python
def nesting_security_config(level: int) -> dict[str, str]:
    if level == 0:
        return {
            "security.nesting": "true",
            "security.syscalls.intercept.mknod": "true",
            "security.syscalls.intercept.setxattr": "true",
        }
    return {
        "security.nesting": "true",
        "security.privileged": "true",
    }
```

La config de sécurité nesting est fusionnée (merge) avec la config
explicite de la machine. La config explicite a priorité (override).

### Module `engine/nesting.py`

```python
detect_nesting_context() -> NestingContext
prefix_name(name, context, nesting_config) -> str
nesting_security_config(level) -> dict[str, str]
context_files_for_instance(parent: NestingContext, machine_type: str) -> dict[str, str]
```

Fonctions pures (sauf `detect_nesting_context` qui lit le filesystem).

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

### 9.1 Détection hardware

Sources de détection (dans l'ordre de priorité) :

1. **`incus info --resources --format json`** — source principale.
   Retourne `cpu.total` (threads logiques) et `memory.total` (octets).
2. **Fallback `/proc/`** — si Incus indisponible :
   - `/proc/cpuinfo` → compte des lignes `processor`
   - `/proc/meminfo` → `MemTotal` en kB → converti en octets

Le résultat est un `HardwareInfo(cpu_threads: int, memory_bytes: int)`.

### 9.2 Réserve hôte

La réserve hôte déduit des ressources avant allocation aux instances.

Formats acceptés :
- **Pourcentage** : `"20%"` → 20% du total hardware
- **Absolu CPU** : `"4"` → 4 threads
- **Absolu mémoire** : `"4GB"`, `"4096MB"` → taille fixe
  Suffixes : `KB`, `MB`, `GB`, `TB` (puissances de 1024)

```
available_cpu = total_cpu - reserve_cpu
available_memory = total_memory - reserve_memory
```

### 9.3 Exclusion des machines avec config explicite

Avant l'allocation, les machines avec des limites explicites dans
`config` sont exclues pour la ressource concernée :

- `limits.cpu` défini → exclue de l'allocation CPU
- `limits.memory` défini → exclue de l'allocation mémoire

Leur consommation est déduite du pool disponible :
```
allocatable_cpu = available_cpu - sum(explicit_cpu)
allocatable_memory = available_memory - sum(explicit_memory)
```

Si une machine a `limits.cpu` mais pas `limits.memory`, elle est
exclue uniquement pour le CPU et participe à l'allocation mémoire.

### 9.4 Algorithme d'allocation

Deux modes via `resource_policy.mode` :

**`proportional`** (défaut) — par poids :
```
part_cpu[i] = allocatable_cpu × weight[i] / sum(weights)
part_memory[i] = allocatable_memory × weight[i] / sum(weights)
```

**`equal`** — parts égales (weight ignoré) :
```
part_cpu[i] = allocatable_cpu / N
part_memory[i] = allocatable_memory / N
```

### 9.5 Modes CPU

Via `resource_policy.cpu_mode` :

- **`allowance`** (défaut) — pourcentage CPU (`limits.cpu.allowance`
  dans Incus). Ex : 4 threads sur 16 total → `"25%"`.
- **`count`** — nombre fixe de vCPUs (`limits.cpu` dans Incus).
  Arrondi à l'entier supérieur (minimum 1).

### 9.6 Modes mémoire

Via `resource_policy.memory_enforce` :

- **`soft`** (défaut) — `limits.memory.soft` dans Incus.
  Ballooning cgroups : la mémoire est partagée élastiquement.
- **`hard`** — `limits.memory` dans Incus.
  Limite stricte, l'instance est tuée (OOM) si dépassée.

Les valeurs sont formatées en `MB` (arrondi à l'entier supérieur,
minimum 64MB).

### 9.7 Overcommit

Si `overcommit: false` (défaut) et que la somme des allocations
(explicites + calculées) dépasse le total hardware, **erreur**.

Si `overcommit: true`, **warning** au lieu d'erreur. L'allocation
est appliquée malgré le dépassement.

### 9.8 Intégration au réconciliateur

Le calcul d'allocation est exécuté **avant** la réconciliation.
La fonction `compute_resource_allocation` enrichit le `config` de
chaque `Machine` avec les clés `limits.*` calculées.

Pipeline :
```
parse → validate → compute_resources → reconcile → snapshot → provision
```

Si `resource_policy` est `None` dans `GlobalConfig`, le calcul est
sauté (aucune limite appliquée).

### 9.9 CLI

```
anklume resource show    # Affiche l'allocation calculée (tableau)
```

Colonnes : instance, weight, CPU (mode), mémoire (enforce), source
(auto/explicit).

### 9.10 Module

`engine/resources.py` — fonctions pures (sauf détection hardware) :

```python
@dataclass
class HardwareInfo:
    cpu_threads: int
    memory_bytes: int

@dataclass
class ResourceAllocation:
    instance_name: str
    cpu_value: str        # "25%" ou "4" selon cpu_mode
    cpu_key: str          # "limits.cpu.allowance" ou "limits.cpu"
    memory_value: str     # "512MB"
    memory_key: str       # "limits.memory.soft" ou "limits.memory"
    source: str           # "auto" ou "explicit"

def detect_hardware() -> HardwareInfo
def detect_hardware_fallback() -> HardwareInfo
def parse_reserve(value: str, total: int) -> int
def compute_resource_allocation(
    infra: Infrastructure,
    hardware: HardwareInfo,
) -> list[ResourceAllocation]
def apply_resource_config(
    infra: Infrastructure,
    allocations: list[ResourceAllocation],
) -> None  # modifie machine.config en place
```

## 10. Snapshots

Snapshots automatiques et manuels pour la sécurité des données.
Basés sur les snapshots natifs d'Incus (instantanés, copy-on-write).

### Convention de nommage

| Type | Format | Exemple |
|------|--------|---------|
| Auto pré-apply | `anklume-pre-{YYYYMMDD-HHMMSS}` | `anklume-pre-20260307-143022` |
| Auto post-apply | `anklume-post-{YYYYMMDD-HHMMSS}` | `anklume-post-20260307-143025` |
| Manuel (défaut) | `anklume-snap-{YYYYMMDD-HHMMSS}` | `anklume-snap-20260307-150000` |
| Manuel (nommé) | nom fourni par l'utilisateur | `avant-migration` |

### Snapshots automatiques

Intégrés au pipeline `anklume apply` :

1. **Pré-apply** : avant toute modification, snapshot de chaque instance
   existante dans les domaines concernés. Les instances nouvellement
   créées sont ignorées (rien à sauvegarder).
2. **Post-apply** : après application réussie, snapshot de chaque
   instance modifiée ou démarrée.

Les auto-snapshots sont créés silencieusement. En cas d'échec du
snapshot, un warning est affiché mais l'apply continue (best-effort).

En `--dry-run`, aucun snapshot n'est créé.

### Commandes CLI

```
anklume snapshot create [instance]           # Toutes les instances ou une seule
anklume snapshot create [instance] --name X  # Nom personnalisé
anklume snapshot list [instance]             # Lister les snapshots
anklume snapshot restore <instance> <snap>   # Restaurer un snapshot
```

#### `anklume snapshot create [instance]`

Sans argument : snapshot toutes les instances running de tous les
domaines activés. Avec un nom d'instance (nom complet, ex: `pro-dev`) :
snapshot uniquement cette instance.

L'option `--name` permet de donner un nom personnalisé au snapshot.
Sans `--name`, le nom est généré automatiquement (`anklume-snap-{ts}`).

#### `anklume snapshot list [instance]`

Sans argument : liste les snapshots de toutes les instances, groupés
par domaine/instance. Avec un nom d'instance : liste uniquement ses
snapshots.

Affichage :
```
pro-dev:
  anklume-pre-20260307-143022   (2026-03-07 14:30:22)
  anklume-post-20260307-143025  (2026-03-07 14:30:25)
  avant-migration               (2026-03-07 15:00:00)
```

#### `anklume snapshot restore <instance> <snapshot>`

Restaure un snapshot nommé sur une instance. L'instance est arrêtée
avant la restauration si elle est running, puis redémarrée.

### Résolution d'instance

Les commandes snapshot acceptent le nom complet de l'instance
(ex: `pro-dev`). Le projet Incus est déduit automatiquement en
cherchant l'instance dans tous les projets anklume.

### Driver Incus — méthodes snapshot

| Méthode | Commande Incus |
|---------|---------------|
| `snapshot_create(instance, project, name)` | `incus snapshot create <inst> <name> --project <p>` |
| `snapshot_list(instance, project)` | `incus snapshot list <inst> --project <p> --format json` |
| `snapshot_restore(instance, project, name)` | `incus snapshot restore <inst> <name> --project <p>` |
| `snapshot_delete(instance, project, name)` | `incus snapshot delete <inst> <name> --project <p>` |

## 11. Provisioner Ansible

Après la réconciliation Incus, anklume provisionne les instances via
Ansible. Le provisioning installe les logiciels et configure les
services à l'intérieur des instances créées.

### Vue d'ensemble

Le provisioning est déclenché automatiquement par `anklume apply`
après la création/démarrage des instances. Seules les machines avec
`roles: [...]` non vide sont provisionnées. Si aucune machine n'a
de rôle, le provisioning est ignoré silencieusement.

Pipeline complet :
```
anklume apply all
  ├─ ... réconciliation Incus ...
  ├─ Snapshots post-apply
  ├─ Attente de la disponibilité des instances
  ├─ Génère inventaire + playbook Ansible
  ├─ Exécute ansible-playbook
  └─ Rapporte succès/échecs provisioning
```

### Prérequis

- Ansible installé sur l'hôte (`ansible-playbook` dans le PATH)
- Si Ansible absent : warning affiché, provisioning ignoré (pas d'erreur)

### Connexion aux instances

Connexion via `incus exec` — pas de SSH requis. Le provisioner
embarque un plugin de connexion Ansible minimaliste
(`provisioner/plugins/connection/anklume_incus.py`) qui encapsule :

| Opération | Commande Incus |
|-----------|---------------|
| `exec_command(cmd)` | `incus exec <inst> --project <p> -- sh -c <cmd>` |
| `put_file(src, dest)` | `incus file push <src> <inst>/<dest> --project <p>` |
| `fetch_file(src, dest)` | `incus file pull <inst>/<src> <dest> --project <p>` |

Zéro dépendance externe (pas de `community.general` requis).

### Fichiers générés

Tout est généré dans `ansible/` du projet utilisateur :

| Fichier | Contenu |
|---------|---------|
| `ansible/inventory/<domain>.yml` | Inventaire par domaine |
| `ansible/host_vars/<machine>.yml` | Variables machine (depuis `vars:` du YAML) |
| `ansible/site.yml` | Playbook assignant les rôles par machine |

Les fichiers générés portent un en-tête :
```yaml
# Généré par anklume — sera écrasé au prochain apply
```

### Inventaire

Un fichier YAML par domaine. Les machines sans rôles sont quand même
inventoriées (elles seront juste ignorées par le playbook).

```yaml
# ansible/inventory/pro.yml
all:
  children:
    pro:
      hosts:
        pro-dev:
          ansible_connection: anklume_incus
          anklume_incus_project: pro
        pro-desktop:
          ansible_connection: anklume_incus
          anklume_incus_project: pro
```

### Variables machine

Générées uniquement si `vars:` est défini dans le domaine YAML.

```yaml
# ansible/host_vars/pro-dev.yml
custom_packages:
  - nodejs
  - docker.io
```

### Playbook (site.yml)

Un play par machine ayant des rôles. `become: true` par défaut
(provisioning requiert root).

```yaml
# ansible/site.yml
---
- hosts: pro-dev
  become: true
  roles:
    - base
    - dev-tools

- hosts: pro-desktop
  become: true
  roles:
    - base
    - desktop
```

### Rôles embarqués

Stockés dans `src/anklume/provisioner/roles/` :

| Rôle | Description |
|------|-------------|
| `base` | Paquets essentiels (curl, ca-certificates, sudo), locale fr |
| `desktop` | KDE Plasma, Wayland, polices |
| `dev-tools` | Build tools, git, python3, outils de développement |

Les rôles embarqués sont minimalistes et Debian-centric.

### Rôles personnalisés

Les rôles dans `ansible_roles_custom/` du projet utilisateur sont
prioritaires sur les rôles embarqués (même nom = override).

L'ordre de recherche des rôles :
1. `ansible_roles_custom/` (projet utilisateur)
2. `src/anklume/provisioner/roles/` (rôles embarqués)

### Flag `--no-provision`

`anklume apply --no-provision` exécute la réconciliation Incus
sans le provisioning Ansible. Utile pour débugger ou quand
Ansible n'est pas nécessaire.

### Attente de disponibilité

Avant de lancer Ansible, le provisioner attend que chaque instance
soit accessible via `incus exec`. Timeout de 30 secondes par instance.
Les instances non-accessibles sont exclues du provisioning avec un
warning.

### Gestion d'erreurs

- Ansible absent : warning, provisioning ignoré
- Échec sur un domaine : logué, les autres domaines continuent
- Le résultat du provisioning est rapporté séparément des résultats
  de réconciliation Incus

### Module `provisioner/`

```
src/anklume/provisioner/
    __init__.py             # provision(infra, driver, project_dir)
    inventory.py            # Génération de l'inventaire
    playbook.py             # Génération du playbook
    runner.py               # Exécution ansible-playbook
    roles/                  # Rôles embarqués
        base/tasks/main.yml
        desktop/tasks/main.yml
        dev-tools/tasks/main.yml
    plugins/connection/
        anklume_incus.py    # Plugin de connexion Incus
```

## 12. Réseau et sécurité nftables

Isolation réseau entre domaines via nftables sur l'hôte.

### Philosophie

- **Drop-all par défaut** : tout trafic inter-domaines bloqué
- **Allow sélectif** : exceptions déclarées dans `policies.yml`
- **Intra-domaine autorisé** : trafic sur le même bridge libre
- **Table dédiée** : `inet anklume` isolée des autres règles nftables

### Structure nftables

```nft
table inet anklume
flush table inet anklume

table inet anklume {
    chain forward {
        type filter hook forward priority 0; policy drop;

        ct state established,related accept

        # Intra-domaine
        iifname "net-pro" oifname "net-pro" accept
        iifname "net-perso" oifname "net-perso" accept

        # Politiques inter-domaines
        # Pro accède à Ollama et Open WebUI
        iifname "net-pro" oifname "net-ai-tools" tcp dport { 3000, 11434 } accept
    }
}
```

La table `inet anklume` est flushée puis recréée à chaque deploy
(idempotent). Les autres tables nftables restent intactes.

### Résolution des cibles

Chaque cible d'une politique (`from`/`to`) est résolue en identifiants
nftables :

| Cible | Type | Filtrage nftables |
|-------|------|-------------------|
| `pro` (domaine) | bridge | `iifname/oifname "net-pro"` |
| `pro-dev` (machine) | bridge + IP | bridge + `ip saddr/daddr <ip>` |
| `host` | — | Commentaire informatif |

**Domaine** : résolu par le nom du bridge (`net-{domain}`).

**Machine** : résolu par le bridge du domaine parent + l'IP de la
machine. Permet un filtrage plus fin que le domaine.

**Host** : les politiques `from: host` ou `to: host` sont validées
mais génèrent un commentaire informatif dans le ruleset. Le trafic
hôte↔domaines reste libre (l'hôte est le plan de management).

### Génération des règles

Pour chaque politique dans `policies.yml` :

1. Résoudre `from_target` → bridge source + IP optionnelle
2. Résoudre `to_target` → bridge destination + IP optionnelle
3. Générer la règle nftables :
   - `iifname` (bridge source)
   - `ip saddr` (si machine source)
   - `oifname` (bridge destination)
   - `ip daddr` (si machine destination)
   - `<protocol> dport { <ports> }` (sauf `ports: "all"` ou `[]`)
   - `accept`
4. Si `bidirectional: true`, générer la règle inverse

Les ports sont triés numériquement dans les sets nftables.

### Domaines désactivés

Les domaines avec `enabled: false` sont exclus du ruleset :
- Pas de règle intra-domaine
- Les politiques les référençant génèrent un commentaire `[ignoré]`

### Commandes CLI

```
anklume network rules     # Affiche le ruleset nftables sur stdout
anklume network deploy    # Applique le ruleset via nft -f
```

#### `anklume network rules`

Génère le ruleset depuis l'infrastructure courante et l'affiche
sur stdout. Permet de vérifier les règles avant de les appliquer.

#### `anklume network deploy`

Génère le ruleset et l'applique sur l'hôte via `nft -f`.
Requiert les privilèges root. Si nftables (`nft`) n'est pas
installé, affiche une erreur.

### Prérequis

- `nft` installé sur l'hôte (pour `network deploy`)
- Adressage calculé (les politiques ciblant des machines nécessitent
  des IPs assignées)

### Module `engine/nftables.py`

```python
generate_ruleset(infra: Infrastructure) -> str
```

Fonction pure : prend une Infrastructure (avec adresses assignées),
retourne le ruleset nftables complet sous forme de string.

### Gestion d'erreurs

- `nft` absent : erreur explicite sur `network deploy`
- Politique référençant un domaine désactivé : commentaire `[ignoré]`
- Politique `host` : commentaire informatif `[hôte]`
- Échec `nft -f` : message d'erreur nftables affiché

## 13. Status et Destroy

Commandes de supervision et de nettoyage de l'infrastructure.

### 13.1 `anklume status`

Compare l'état déclaré (YAML) avec l'état réel (Incus) et affiche
un tableau par domaine.

#### Logique

Pour chaque domaine activé :
1. Vérifie si le projet Incus existe
2. Vérifie si le réseau bridge existe
3. Pour chaque machine déclarée, vérifie son état dans Incus

#### États d'une instance

| État | Signification |
|------|---------------|
| `Running` | Instance active |
| `Stopped` | Instance existante mais arrêtée |
| `Absent` | Déclarée dans le YAML, absente dans Incus |

L'état attendu est toujours `Running` (apply démarre toutes les
instances déclarées).

#### Affichage

```
pro:
  Projet : oui    Réseau : oui
  pro-dev          lxc   Running  [ok]
  pro-desktop      lxc   Stopped  [arrêtée]

perso:
  Projet : oui    Réseau : non
  perso-web        lxc   Absent   [absente]

Résumé : 2/2 projets, 1/2 réseaux, 1/3 instances running
```

`[ok]` = synchronisé, sinon raison de la désynchronisation.

#### Support nesting

Le préfixe de nesting est appliqué lors de la requête Incus
(comme dans le réconciliateur). L'affichage montre les noms logiques
(sans préfixe).

#### Module `engine/status.py`

```python
@dataclass
class InstanceStatus:
    name: str          # nom complet logique (pro-dev)
    machine_type: str  # lxc/vm
    state: str         # "Running", "Stopped", "Absent"
    synced: bool       # True si Running

@dataclass
class DomainStatus:
    name: str
    project_exists: bool
    network_exists: bool
    instances: list[InstanceStatus]

@dataclass
class InfraStatus:
    domains: list[DomainStatus]

    @property
    def projects_total(self) -> int: ...
    @property
    def projects_found(self) -> int: ...
    @property
    def networks_total(self) -> int: ...
    @property
    def networks_found(self) -> int: ...
    @property
    def instances_total(self) -> int: ...
    @property
    def instances_running(self) -> int: ...

def compute_status(
    infra: Infrastructure,
    driver: IncusDriver,
    nesting_context: NestingContext | None = None,
) -> InfraStatus
```

Fonction pure (sauf lecture Incus via driver).

### 13.2 `anklume destroy`

Supprime l'infrastructure créée par anklume. Respecte la protection
`ephemeral` par défaut.

#### Comportement sans `--force`

Pour chaque domaine activé :
1. Lister les instances dans le projet Incus
2. Pour chaque machine déclarée :
   - Si `ephemeral: true` → arrêter et supprimer
   - Si `ephemeral: false` → ignorer (protégée)
3. Si toutes les instances du domaine sont supprimées :
   - Supprimer le réseau
   - Supprimer le projet
4. Sinon : réseau et projet conservés (instances protégées restantes)

#### Comportement avec `--force`

1. Pour chaque machine déclarée :
   - Retirer `security.protection.delete` si présent
   - Arrêter et supprimer l'instance
2. Supprimer le réseau
3. Supprimer le projet

#### Ordre de destruction (inverse de la création)

1. Arrêter les instances running
2. Retirer la protection delete (si `--force`)
3. Supprimer les instances
4. Supprimer le réseau
5. Supprimer le projet

#### Affichage

```
pro:
  Arrêter pro-dev
  Supprimer pro-dev
  [protégée] pro-desktop (utiliser --force)
  Réseau net-pro conservé (instances protégées)
  Projet pro conservé (instances protégées)

1 instance(s) supprimée(s), 1 protégée(s), 0 erreur(s).
```

Avec `--force` :
```
pro:
  Arrêter pro-dev
  Supprimer pro-dev
  Déprotéger pro-desktop
  Arrêter pro-desktop
  Supprimer pro-desktop
  Supprimer réseau net-pro
  Supprimer projet pro

2 instance(s) supprimée(s), 0 erreur(s).
```

#### Support nesting

Comme pour status, le préfixe nesting est appliqué sur les noms
Incus. L'affichage montre les noms logiques.

#### Driver Incus — méthodes destroy

| Méthode | Commande Incus |
|---------|---------------|
| `instance_config_set(inst, project, key, val)` | `incus config set <inst> <key>=<val> --project <p>` |
| `network_delete(name, project)` | `incus network delete <name> --project <p>` |
| `project_delete(name)` | `incus project delete <name>` |

#### Module `engine/destroy.py`

```python
@dataclass
class DestroyAction:
    verb: str        # "stop", "unprotect", "delete"
    resource: str    # "instance", "network", "project"
    target: str      # nom de la ressource
    project: str     # projet Incus
    detail: str      # description lisible

@dataclass
class DestroyResult:
    actions: list[DestroyAction]
    executed: list[DestroyAction]
    errors: list[tuple[DestroyAction, str]]
    skipped: list[tuple[str, str]]  # (instance, raison)

    @property
    def success(self) -> bool: ...

def destroy(
    infra: Infrastructure,
    driver: IncusDriver,
    *,
    force: bool = False,
    dry_run: bool = False,
    nesting_context: NestingContext | None = None,
) -> DestroyResult
```

## 14. Fonctionnalités additionnelles

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

## 15. Historique

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

## 16. GPU passthrough et profils

Gestion du GPU pour les instances nécessitant de l'accélération
matérielle (LLM, STT, calcul). Le flag `gpu: true` sur une machine
déclenche la détection GPU hôte, la création d'un profil Incus dédié,
et l'application de la politique d'accès GPU.

### 16.1 Détection GPU hôte

Le module `engine/gpu.py` détecte la présence d'un GPU NVIDIA via
`nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader,nounits`.

```python
@dataclass
class GpuInfo:
    detected: bool          # True si nvidia-smi retourne un GPU
    model: str              # "RTX PRO 5000", "" si absent
    vram_total_mib: int     # VRAM totale en MiB (0 si absent)
    vram_used_mib: int      # VRAM utilisée en MiB (0 si absent)

def detect_gpu() -> GpuInfo
```

Comportement :
- `nvidia-smi` absent ou échec → `GpuInfo(detected=False, ...)`
- Parsing CSV : nom, mémoire totale (MiB), mémoire utilisée (MiB)
- Un seul GPU supporté (première ligne du CSV)

### 16.2 Validation GPU

Le validateur vérifie la cohérence `gpu: true` :

1. **GPU absent** : si une machine a `gpu: true` et `detect_gpu().detected`
   est `False` → erreur de validation :
   `"Machine '{name}' requiert un GPU (gpu: true) mais aucun GPU détecté sur l'hôte"`

2. **Politique exclusive** : si `gpu_policy: exclusive` (défaut dans
   `anklume.yml`) et plusieurs machines ont `gpu: true` dans des domaines
   différents → erreur :
   `"Politique GPU exclusive : plusieurs machines GPU détectées ({names}). Utiliser gpu_policy: shared ou retirer gpu: true"`

3. **Politique shared** : si `gpu_policy: shared` et plusieurs machines
   GPU → warning (pas d'erreur)

### 16.3 Configuration globale

Nouveau champ dans `anklume.yml` :

```yaml
gpu_policy: exclusive    # exclusive (défaut) ou shared
```

Modèle :

```python
@dataclass
class GpuPolicyConfig:
    policy: str = "exclusive"  # "exclusive" ou "shared"
```

Ajouté comme champ optionnel dans `GlobalConfig` :

```python
@dataclass
class GlobalConfig:
    # ... existants ...
    gpu_policy: GpuPolicyConfig | None = None
```

Si `gpu_policy` est `None`, le défaut `exclusive` est utilisé
(toute machine GPU dans l'infra est seule autorisée).

### 16.4 Profil Incus `gpu-passthrough`

Quand un GPU est détecté et qu'au moins une machine a `gpu: true`,
le réconciliateur crée un profil `gpu-passthrough` dans chaque projet
contenant une machine GPU :

```
incus profile create gpu-passthrough --project <projet>
incus profile device add gpu-passthrough gpu gpu type=gpu gid=44 uid=0
```

Le profil est ajouté à la liste des profils de la machine :
`machine.profiles += ["gpu-passthrough"]` (avant la réconciliation).

### 16.5 Driver Incus — méthodes profil

| Méthode | Commande Incus |
|---------|---------------|
| `profile_exists(name, project)` | `incus profile list --project <p> --format json` (filtrage) |
| `profile_create(name, project)` | `incus profile create <name> --project <p>` |
| `profile_device_add(profile, device, dtype, config, project)` | `incus profile device add <profile> <device> <dtype> [k=v ...] --project <p>` |

### 16.6 Intégration au réconciliateur

Le GPU passthrough s'intègre au pipeline existant, **après** le calcul
d'adressage et **avant** la réconciliation :

```
parse → validate → assign_addresses → apply_gpu_profiles → reconcile → ...
```

La fonction `apply_gpu_profiles` :
1. Détecte le GPU (`detect_gpu()`)
2. Pour chaque domaine avec des machines `gpu: true` :
   - Ajoute `"gpu-passthrough"` aux profils de la machine
3. Retourne la `GpuInfo` (utilisée par `anklume ai status`)

Le réconciliateur crée le profil Incus lors de `create/project`
(juste après la création du projet, avant les instances).

### 16.7 Module `engine/gpu.py`

```python
@dataclass
class GpuInfo:
    detected: bool
    model: str
    vram_total_mib: int
    vram_used_mib: int

def detect_gpu() -> GpuInfo
def validate_gpu_machines(
    infra: Infrastructure,
    gpu_info: GpuInfo,
) -> list[str]  # liste d'erreurs (vide = ok)

def apply_gpu_profiles(infra: Infrastructure) -> GpuInfo
    # Détecte le GPU, enrichit machine.profiles si gpu: true
    # Retourne GpuInfo pour usage ultérieur
```

Fonctions pures (sauf `detect_gpu` qui appelle subprocess).

## 17. Rôles Ansible IA

Rôles embarqués dans `provisioner/roles/` pour le provisioning des
services IA de base. Ils suivent le pattern des rôles existants
(base, desktop, dev-tools) : tâches Ansible standards, variables
configurables via `defaults/main.yml` et surchargeables dans
`domains/*.yml` via le champ `vars:`.

### 17.1 Rôle `ollama_server`

Installe et configure un serveur Ollama pour l'inférence LLM.

**Variables** (dans `defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `ollama_port` | `11434` | Port d'écoute |
| `ollama_host` | `0.0.0.0` | Adresse d'écoute |
| `ollama_default_model` | `""` | Modèle à pull au provisioning (vide = aucun) |
| `ollama_gpu_enabled` | `true` | Activer le GPU si détecté |

**Tâches** :

1. Installer curl et ca-certificates (prérequis)
2. Installer Ollama via `curl -fsSL https://ollama.com/install.sh | sh`
   (idempotent via `creates: /usr/local/bin/ollama`)
3. Détecter le GPU (`nvidia-smi`, best-effort)
4. Créer le service systemd `/etc/systemd/system/ollama.service`
   - `OLLAMA_HOST` configuré via les variables
   - `OLLAMA_GPU_ENABLED=1` si GPU détecté et `ollama_gpu_enabled: true`
5. Activer, démarrer le service, attendre qu'il soit prêt (`/api/tags`)
6. Pull du modèle par défaut (si `ollama_default_model` défini)

**Handlers** : `Redémarrer Ollama` (triggered par changement de config)

**Exemple domaine** :
```yaml
machines:
  gpu-server:
    description: "Serveur LLM avec GPU"
    gpu: true
    roles: [base, ollama_server]
    vars:
      ollama_default_model: "qwen2:0.5b"
      ollama_port: 11434
```

### 17.2 Rôle `stt_server`

Installe et configure un serveur Speaches (STT — Speech-to-Text).
API OpenAI-compatible (`/v1/audio/transcriptions`).

**Variables** (dans `defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `stt_port` | `8000` | Port d'écoute |
| `stt_host` | `0.0.0.0` | Adresse d'écoute |
| `stt_model` | `base` | Modèle Whisper |
| `stt_language` | `fr` | Langue de transcription |
| `stt_device` | `auto` | Device (`auto`, `cuda`, `cpu`) |
| `stt_compute_type` | `auto` | Type de calcul (`auto`, `float16`, `int8`) |

**Tâches** :

1. Installer les dépendances système (python3, ffmpeg, git)
2. Installer `uv` (gestionnaire de paquets Python)
3. Cloner Speaches depuis GitHub
4. Installer via `uv sync`
5. Détecter le GPU (`nvidia-smi`, best-effort)
6. Calculer device et compute_type automatiquement :
   - GPU détecté → `cuda` + `float16`
   - GPU absent → `cpu` + `int8`
7. Créer le service systemd `/etc/systemd/system/speaches.service`
8. Activer, démarrer, attendre (`/v1/models`)

**Coexistence GPU** : Speaches et Ollama coexistent sur le même GPU.
Le flag `stt_device: auto` détecte le GPU indépendamment d'Ollama.

**Handlers** : `Redémarrer Speaches`

**Exemple domaine** :
```yaml
machines:
  gpu-server:
    description: "Serveur LLM + STT"
    gpu: true
    roles: [base, ollama_server, stt_server]
    vars:
      ollama_default_model: "qwen2:0.5b"
      stt_model: "base"
      stt_language: "fr"
```

### 17.3 Structure des rôles

```
provisioner/roles/
  base/           # Phase 5 — paquets essentiels, locale
  desktop/        # Phase 5 — KDE, outils GUI
  dev-tools/      # Phase 5 — Python, git, build-essential
  ollama_server/  # Phase 10b — serveur LLM Ollama
    defaults/main.yml
    tasks/main.yml
    handlers/main.yml
  stt_server/     # Phase 10b — serveur STT Speaches
    defaults/main.yml
    tasks/main.yml
    handlers/main.yml
```

## 18. Domaine ai-tools et CLI IA

### 18.1 Domaine ai-tools dans `anklume init`

`anklume init` génère un domaine `ai-tools.yml` d'exemple en plus du
domaine principal (pro/work). Le domaine est commenté par défaut
pour éviter les erreurs si aucun GPU n'est disponible.

Fichier `domains/ai-tools.yml` (généré) :
```yaml
# Domaine ai-tools — services IA (GPU, LLM, STT)
# Décommenter si un GPU est disponible sur l'hôte.
description: "Services IA"
trust_level: trusted
enabled: false

machines:
  gpu-server:
    description: "Serveur LLM et STT avec GPU"
    type: lxc
    gpu: true
    roles: [base, ollama_server, stt_server]
    vars:
      ollama_default_model: ""
      stt_language: "fr"
```

Le champ `enabled: false` évite les erreurs GPU au premier `apply`.
L'utilisateur active le domaine quand il est prêt.

### 18.2 Politiques réseau IA

Le fichier `policies.yml` généré inclut des exemples commentés pour
l'accès aux services IA :

```yaml
policies: []
  # - from: pro
  #   to: ai-tools
  #   ports: [11434]
  #   description: "Pro accède à Ollama"
  # - from: pro
  #   to: ai-tools
  #   ports: [8000]
  #   description: "Pro accède à Speaches (STT)"
```

### 18.3 CLI `anklume ai`

Groupe de sous-commandes pour la gestion des services IA.

```
anklume ai status    # État des services IA
```

### 18.4 `anklume ai status`

Affiche un diagnostic complet des services IA :

```
GPU:
  Détecté : oui (NVIDIA RTX PRO 5000)
  VRAM : 512 / 24576 MiB

Ollama:
  État : actif (http://10.100.3.1:11434)
  Modèles chargés : qwen2:0.5b (3.2 GiB)

STT (Speaches):
  État : actif (http://10.100.3.1:8000)
```

Si un service est injoignable : `État : injoignable`.
Si aucun GPU : `Détecté : non`.

L'URL des services est dérivée du domaine `ai-tools` :
- L'IP du `gpu-server` dans le domaine `ai-tools` (après adressage)
- Les ports proviennent des variables ou des defaults des rôles

### 18.5 Module `engine/ai.py`

```python
@dataclass
class AiServiceStatus:
    name: str           # "ollama" ou "stt"
    reachable: bool
    url: str
    detail: str         # info supplémentaire (modèles, version)

@dataclass
class AiStatus:
    gpu: GpuInfo
    services: list[AiServiceStatus]

def compute_ai_status(infra: Infrastructure) -> AiStatus
```

La détection des services utilise des requêtes HTTP vers les endpoints
connus (best-effort, timeout court). Pas de dépendance sur Incus.

## 19. Push-to-talk STT (hôte KDE)

Raccourci clavier sur l'hôte pour dicter du texte via Speaches.
Le texte transcrit est collé dans la fenêtre active.
KDE Plasma Wayland uniquement.

### 19.1 Script push-to-talk

`host/stt/push-to-talk.sh` — mode toggle Meta+S :
- 1er appui : démarre l'enregistrement (`pw-record`)
- 2e appui : arrête, envoie à Speaches, colle le résultat

**Flux** :
```
Meta+S (1er) → pw-record /tmp/anklume-stt.wav
Meta+S (2e)  → kill pw-record
             → curl -F file=@/tmp/anklume-stt.wav $STT_API_URL/v1/audio/transcriptions
             → wl-copy <texte>
             → paste dans fenêtre active
```

**Détection fenêtre active** via `kdotool getactivewindow getwindowclassname` :
- Classe terminal (konsole, Alacritty, kitty, foot, wezterm)
  → `wtype -M ctrl -M shift -k v` (paste terminal)
- Autre application → `wtype -M ctrl -k v` (paste standard)

**Notifications** : `notify-send` pour début/fin/erreur.

**Nettoyage** : fichier temporaire supprimé via trap.

### 19.2 Support AZERTY

`host/stt/azerty-type.py` — frappe de texte via `wtype` avec support
des caractères AZERTY. Utilisé quand le paste n'est pas fiable.

Fonctionnalités :
- Lecture du texte sur stdin, frappe caractère par caractère via `wtype`
- Accents (é, è, ê, à, ù, ç), dead keys (^, ¨)
- Gère les caractères spéciaux (shift, altgr)

### 19.3 Mode streaming

`host/stt/streaming.py` — transcription en temps réel :
- Chunks audio ~3s envoyés en continu
- Diff mot-à-mot pour éviter les doublons
- Filtrage des hallucinations Whisper ("sous-titres", "merci")
- Détection de silence (RMS < seuil), timeouts de sécurité

### 19.4 CLI `anklume stt`

```
anklume stt setup     # Installe les dépendances hôte + raccourci KDE
anklume stt status    # État du service STT (santé endpoint)
```

**`anklume stt setup`** vérifie et installe :
- `pw-record` (PipeWire)
- `wtype` (frappe Wayland)
- `wl-copy` / `wl-paste` (presse-papiers Wayland)
- `kdotool` (interaction fenêtres KDE)
- `jq` (parsing JSON)
- `notify-send` (notifications)
- Raccourci KDE Meta+S via `kwriteconfig6`

**`anklume stt status`** vérifie :
- Endpoint STT joignable
- Dépendances hôte installées

### 19.5 Configuration

Variables d'environnement (dans `~/.config/anklume/stt.env`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `STT_API_URL` | `http://10.100.3.1:8000` | URL du serveur Speaches |
| `STT_MODEL` | `base` | Modèle Whisper |
| `STT_LANGUAGE` | `fr` | Langue de transcription |

### 19.6 Structure

```
host/stt/
  push-to-talk.sh    # Script toggle Meta+S
  azerty-type.py     # Frappe AZERTY via wtype
  streaming.py       # Transcription streaming temps réel
```

## 20. Gestion VRAM et accès exclusif

Commandes CLI pour libérer la VRAM GPU et basculer l'accès
exclusif entre domaines. Empêche les conflits GPU quand
plusieurs domaines utilisent des services IA.

### 20.1 Flush VRAM

`anklume ai flush` — libère toute la VRAM GPU occupée.

**Étapes** :
1. Lister les modèles Ollama chargés (`GET /api/ps`)
2. Décharger chaque modèle (`POST /api/generate` avec `keep_alive: 0`)
3. Arrêter `llama-server` si actif (via `incus exec ... systemctl stop`)
4. Rapporter le résultat (modèles déchargés, VRAM libérée)

```python
@dataclass
class FlushResult:
    """Résultat d'un flush VRAM."""
    models_unloaded: list[str]
    llama_server_stopped: bool
    vram_before_mib: int
    vram_after_mib: int
```

**Erreurs** : si Ollama est injoignable, log warning et continue.
Le flush est best-effort (chaque étape indépendante).

### 20.2 Switch accès GPU

`anklume ai switch <domaine>` — bascule l'accès exclusif GPU.

**Étapes** :
1. Vérifier que le domaine cible existe et est activé
2. Flush VRAM (appel à `flush_vram`)
3. Écrire le fichier d'état avec le nouveau domaine
4. Log de l'opération

```
anklume ai switch pro
→ Flush VRAM : 2 modèles déchargés, llama-server arrêté
→ Accès GPU : pro (précédent : ai-tools)
→ Fichier d'état mis à jour
```

### 20.3 Fichier d'état

`/var/lib/anklume/ai-access.json` — trace quel domaine a accès au GPU.

```json
{
  "domain": "ai-tools",
  "timestamp": "2026-03-08T14:30:00",
  "previous": null
}
```

**Lecture** : `read_ai_access()` retourne le domaine courant (ou `None`).
**Écriture** : `write_ai_access(domain)` met à jour le fichier.
Si le répertoire `/var/lib/anklume/` n'existe pas, il est créé.

### 20.4 Politique d'accès

Champ `ai_access_policy` dans `anklume.yml` :

```yaml
schema_version: 1
ai_access_policy: exclusive   # exclusive | open
```

- **`exclusive`** (défaut) : un seul domaine accède au GPU à la fois.
  `anklume ai switch` requis pour basculer.
- **`open`** : tous les domaines autorisés accèdent librement.
  `anklume ai switch` désactivé (erreur si appelé).

### 20.5 Signatures du module

```python
# engine/ai.py (ajouts)

@dataclass
class FlushResult:
    models_unloaded: list[str]
    llama_server_stopped: bool
    vram_before_mib: int
    vram_after_mib: int

@dataclass
class AiAccessState:
    domain: str | None
    timestamp: str
    previous: str | None

def flush_vram(infra: Infrastructure) -> FlushResult
def read_ai_access(state_path: Path | None = None) -> AiAccessState
def write_ai_access(domain: str, *, state_path: Path | None = None) -> AiAccessState
def switch_ai_access(infra: Infrastructure, target_domain: str) -> AiAccessState

# models.py (ajout)
@dataclass
class GlobalConfig:
    ai_access_policy: str = "exclusive"  # "exclusive" | "open"
```

### 20.6 CLI

```
anklume ai flush     # Libérer la VRAM GPU
anklume ai switch <domaine>  # Basculer l'accès GPU
anklume ai status    # (existant) Affiche aussi l'accès courant
```

## 21. Interfaces de chat

Rôles Ansible embarqués pour déployer des interfaces de chat web
connectées aux services IA du domaine. Open WebUI (connexion
directe à Ollama) et LobeChat (multi-providers).

### 21.1 Rôle `open_webui`

Open WebUI — interface web pour interagir avec Ollama.

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `open_webui_port` | `3000` | Port HTTP |
| `open_webui_ollama_url` | `http://localhost:11434` | URL du serveur Ollama |
| `open_webui_data_dir` | `/opt/open-webui/data` | Répertoire de données |

**Tâches** (`tasks/main.yml`) :
1. Installer les dépendances système (`python3`, `pip`)
2. Installer Open WebUI via pip (`open-webui`)
3. Créer le répertoire de données
4. Configurer le service systemd (`OLLAMA_BASE_URL`, port)
5. Démarrer et activer le service
6. Attendre que le service soit prêt (health check)

**Handler** : `restart open-webui`.

### 21.2 Rôle `lobechat`

LobeChat — client de chat multi-providers (Ollama local, OpenRouter
cloud).

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `lobechat_port` | `3210` | Port HTTP |
| `lobechat_ollama_url` | `http://localhost:11434` | URL Ollama |
| `lobechat_data_dir` | `/opt/lobechat/data` | Répertoire de données |

**Tâches** (`tasks/main.yml`) :
1. Installer Node.js (via NodeSource)
2. Cloner LobeChat depuis GitHub
3. Installer les dépendances et build
4. Configurer le service systemd
5. Démarrer et activer le service
6. Attendre que le service soit prêt

**Handler** : `restart lobechat`.

### 21.3 Machines dans `anklume init`

Le template `ai-tools.yml` généré par `anklume init` inclut
des machines commentées pour les interfaces de chat :

```yaml
# ai-webui:
#   description: "Interface web Ollama (Open WebUI)"
#   type: lxc
#   roles: [base, open_webui]
#   vars:
#     ollama_host: "gpu-server"
#     ollama_port: 11434
```

Les politiques réseau commentées incluent l'accès aux ports
des interfaces de chat.

### 21.4 Détection des services

Ajout dans `_SERVICE_DEFS` (`engine/ai.py`) pour la détection
automatique par `anklume ai status` :

```python
ROLE_OPEN_WEBUI = "open_webui"
ROLE_LOBECHAT = "lobechat"
_DEFAULT_OPEN_WEBUI_PORT = 3000
_DEFAULT_LOBECHAT_PORT = 3210
```

Les services Open WebUI et LobeChat sont détectés automatiquement
sur les machines ayant les rôles correspondants, avec health check
sur le endpoint racine (`/`).

## 22. Proxy de sanitisation LLM

Moteur de détection et remplacement de données sensibles
avant envoi à un LLM externe. Module Python (`engine/sanitizer.py`)
+ rôle Ansible proxy HTTP.

### 22.1 Patterns détectés

| Catégorie | Exemples | Description |
|-----------|----------|-------------|
| IPs privées RFC 1918 | `10.x.x.x`, `192.168.x.x`, `172.16-31.x.x` | Adresses IP internes |
| Ressources Incus | Projets, bridges, instances | Noms extraits de l'infra |
| FQDNs internes | `*.internal`, `*.local`, `*.corp` | Domaines réseau privé |
| Credentials | Bearer tokens, clés API | Patterns `key=...`, `token=...` |

### 22.2 Modes de remplacement

- **`mask`** : remplacement par un placeholder lisible et indexé.
  `10.120.0.5` → `[IP_REDACTED_1]`, `pro-dev` → `[INSTANCE_REDACTED_1]`

- **`pseudonymize`** : remplacement cohérent dans une session.
  Même valeur d'entrée produit toujours le même pseudonyme.
  `10.120.0.5` → `10.ZONE.1.5`

### 22.3 Module `engine/sanitizer.py`

```python
@dataclass
class Replacement:
    """Un remplacement effectué par le sanitizer."""
    original: str
    replaced: str
    category: str       # "ip", "resource", "fqdn", "credential"
    position: tuple[int, int]  # (start, end) dans le texte original

@dataclass
class SanitizeResult:
    """Résultat d'une sanitisation."""
    text: str
    replacements: list[Replacement]

def sanitize(
    text: str,
    *,
    infra: Infrastructure | None = None,
    mode: str = "mask",
) -> SanitizeResult

def desanitize(
    text: str,
    replacements: list[Replacement],
) -> str
```

`sanitize()` détecte et remplace toutes les données sensibles.
`desanitize()` restaure les valeurs originales (pour interpréter
la réponse du LLM).

### 22.4 Rôle `llm_sanitizer`

Proxy HTTP (port 8089) qui intercepte les requêtes vers les
APIs LLM cloud. Sanitise les prompts, désanitise les réponses.

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `sanitizer_port` | `8089` | Port du proxy |
| `sanitizer_mode` | `mask` | Mode : `mask`, `pseudonymize` |
| `sanitizer_upstream_url` | `` | URL du LLM cible |
| `sanitizer_log_dir` | `/var/log/anklume/sanitizer` | Logs d'audit |

### 22.5 Champ `ai_sanitize` dans le domaine

```yaml
# domains/pro.yml
machines:
  dev:
    roles: [base]
    vars:
      ai_sanitize: true
```

- `false` (défaut) : sanitisation désactivée
- `true` : requêtes cloud passent par le proxy
- `always` : sanitisation active même pour les LLM locaux

## 23. OpenClaw — assistant IA par domaine

Assistant autonome qui monitore l'infrastructure et interagit
via des canaux de communication. Un OpenClaw par domaine,
respecte les frontières réseau.

> **Modernisé en §28** — le rôle `openclaw_server` utilise désormais
> npm + daemon natif au lieu de pip/venv. Voir §28 pour les détails.

### 23.1 Rôle `openclaw_server`

Voir §28.1 pour la version actuelle (TypeScript, npm, daemon natif).

### 23.2 Configuration dans le domaine

```yaml
ai-assistant:
  description: "Assistant IA OpenClaw"
  type: lxc
  roles: [base, admin_bootstrap, openclaw_server]
  vars:
    openclaw_channels: [telegram]
    openclaw_llm_provider: ollama
```

### 23.3 Détection du service

Ajout dans `_SERVICE_DEFS` (`engine/ai.py`) :

```python
ROLE_OPENCLAW_SERVER = "openclaw_server"
_DEFAULT_OPENCLAW_PORT = 8090
```

`anklume ai status` affiche l'état d'OpenClaw automatiquement.

## 24. Développement assisté par IA

Outils CLI et rôles pour intégrer les LLM dans le workflow
de développement.

### 24.1 `anklume ai test`

Boucle automatique : exécuter les tests, analyser les erreurs
via un LLM, proposer ou appliquer des corrections.

```python
@dataclass
class AiTestConfig:
    """Configuration de la boucle test IA."""
    backend: str = "ollama"   # "ollama" | "claude"
    mode: str = "dry-run"     # "dry-run" | "auto-apply" | "auto-pr"
    max_retries: int = 3
    model: str = ""

@dataclass
class AiTestResult:
    """Résultat d'une itération de la boucle."""
    iteration: int
    tests_passed: bool
    errors: list[str]
    fixes_proposed: list[str]
    fixes_applied: bool

def run_ai_test_loop(
    config: AiTestConfig,
    *,
    project_dir: Path | None = None,
) -> list[AiTestResult]
```

**Modes** :
- `dry-run` (défaut) : analyse + propositions, sans modification
- `auto-apply` : applique les corrections automatiquement
- `auto-pr` : crée une PR avec les corrections

**Backends** :
- `ollama` : LLM local via Ollama API
- `claude` : Claude API (nécessite `ANTHROPIC_API_KEY`)

### 24.2 Rôle `code_sandbox`

Sandbox isolé pour exécution de code généré par LLM.
Réseau restreint, filesystem éphémère.

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `sandbox_timeout` | `60` | Timeout d'exécution (secondes) |
| `sandbox_network` | `false` | Accès réseau |
| `sandbox_ephemeral` | `true` | Filesystem éphémère |

### 24.3 Rôle `opencode_server`

Serveur de coding IA headless.

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `opencode_port` | `8091` | Port HTTP |
| `opencode_ollama_host` | `localhost` | Hôte Ollama |
| `opencode_data_dir` | `/opt/opencode/data` | Données persistantes |

### 24.4 CLI

```
anklume ai test [--backend ollama|claude] [--mode dry-run|auto-apply] [--max-retries N]
```

## 25. Routage LLM — choix local/externe + sanitisation

Mécanisme de sélection du backend LLM (local Ollama, API cloud,
abonnement) avec routage conditionnel via le proxy de sanitisation.
Chaque machine choisit son backend, le sanitizer s'interpose
automatiquement quand requis.

### 25.1 Philosophie

Le POC avait trois modes d'accès aux LLM :
1. **Local** — Ollama sur le réseau interne (gratuit, privé)
2. **API cloud** — OpenAI, Anthropic, etc. (payant à l'usage)
3. **Abonnement** — OpenRouter, Together, etc. (payant mensuel)

Les modes 2 et 3 utilisent tous le format OpenAI-compatible.
Le routage se résume donc à deux familles de backends :
- `local` → Ollama (protocole Ollama natif)
- `openai` → toute API OpenAI-compatible (OpenAI, OpenRouter,
  Groq, Together, Mistral, vLLM distant, etc.)
- `anthropic` → API Claude (format Messages distinct)

Quand les données sortent du réseau local (backends `openai`
et `anthropic`), le proxy de sanitisation s'interpose pour
protéger les données sensibles.

### 25.2 Configuration machine

Les variables LLM se déclarent dans `vars:` de chaque machine.
Les rôles consommateurs (OpenClaw, LobeChat, Open WebUI)
lisent ces variables résolues.

```yaml
# domains/pro.yml
machines:
  assistant:
    description: "Assistant IA pro"
    type: lxc
    roles: [base, openclaw_server]
    vars:
      llm_backend: openai
      llm_api_url: "https://openrouter.ai/api/v1"
      llm_api_key: "sk-or-..."
      llm_model: "anthropic/claude-sonnet-4-20250514"
      ai_sanitize: true
```

| Variable | Défaut | Description |
|----------|--------|-------------|
| `llm_backend` | `local` | Backend LLM : `local`, `openai`, `anthropic` |
| `llm_api_url` | `""` | URL de l'API (requis si backend externe) |
| `llm_api_key` | `""` | Clé API (requis si backend externe) |
| `llm_model` | `""` | Modèle à utiliser (optionnel, défaut du provider) |
| `ai_sanitize` | `false` | `false`, `true` (externe only), `always` |

### 25.3 Backends supportés

| Backend | `llm_api_url` | Format API | Exemples |
|---------|---------------|------------|----------|
| `local` | ignoré | Ollama natif | Ollama local |
| `openai` | requis | OpenAI-compatible | OpenAI, OpenRouter, Groq, Together, Mistral, vLLM |
| `anthropic` | requis | Messages API | Claude API |

Pour `local`, l'URL Ollama est résolue automatiquement depuis
l'infrastructure (même domaine : `localhost`, cross-domaine :
IP de la machine `ollama_server`).

### 25.4 Routage et sanitisation

Le module `engine/llm_routing.py` résout l'endpoint effectif
pour chaque machine au moment du provisioning.

```
                                        ┌─────────────┐
llm_backend: local ──────────────────── │   Ollama     │
                                        └─────────────┘

                        ai_sanitize:    ┌─────────────┐    ┌─────────────┐
llm_backend: openai ──── true ────────► │  Sanitizer   │───►│  Cloud API   │
                    │                   └─────────────┘    └─────────────┘
                    │   ai_sanitize:    ┌─────────────┐
                    └─── false ────────►│  Cloud API   │
                                        └─────────────┘

                        ai_sanitize:    ┌─────────────┐    ┌─────────────┐
llm_backend: local ──── always ────────►│  Sanitizer   │───►│   Ollama     │
                                        └─────────────┘    └─────────────┘
```

Règles de routage :
1. `llm_backend: local` + `ai_sanitize: false` → Ollama direct
2. `llm_backend: local` + `ai_sanitize: true` → Ollama direct
   (true = externe seulement, local exempt)
3. `llm_backend: local` + `ai_sanitize: always` → Sanitizer → Ollama
4. `llm_backend: openai|anthropic` + `ai_sanitize: false` → Cloud direct
5. `llm_backend: openai|anthropic` + `ai_sanitize: true` → Sanitizer → Cloud
6. `llm_backend: openai|anthropic` + `ai_sanitize: always` → Sanitizer → Cloud

### 25.5 Module `engine/llm_routing.py`

```python
LLM_BACKENDS = {"local", "openai", "anthropic"}
AI_SANITIZE_VALUES = {"false", "true", "always"}

@dataclass
class LlmEndpoint:
    """Endpoint LLM résolu pour une machine."""
    backend: str       # "local", "openai", "anthropic"
    url: str           # URL effective (Ollama, cloud, ou sanitizer)
    api_key: str       # Clé API (vide pour local)
    model: str         # Modèle sélectionné
    sanitized: bool    # Passe par le proxy sanitizer
    upstream_url: str  # URL réelle derrière le sanitizer (vide si pas sanitisé)

def resolve_llm_endpoint(
    machine: Machine,
    domain: Domain,
    infra: Infrastructure,
) -> LlmEndpoint:
    """Résout l'endpoint LLM effectif pour une machine.

    Raises:
        ValueError: configuration invalide (backend inconnu,
                    URL manquante, sanitizer introuvable).
    """

def find_sanitizer_url(
    domain: Domain,
    infra: Infrastructure,
) -> str | None:
    """Trouve l'URL du proxy sanitizer dans le domaine ou l'infra.

    Cherche d'abord dans le même domaine, puis dans tous les
    domaines activés.
    """

def find_ollama_url(
    domain: Domain,
    infra: Infrastructure,
) -> str:
    """Trouve l'URL Ollama accessible depuis le domaine.

    Cherche d'abord dans le même domaine (localhost),
    puis dans l'infra.
    """

def enrich_llm_vars(infra: Infrastructure) -> Infrastructure:
    """Enrichit les vars des machines avec les endpoints résolus.

    Ajoute `llm_effective_url`, `llm_effective_key`,
    `llm_effective_model`, `llm_effective_backend` aux machines
    qui ont un rôle consommateur LLM.

    Appelé dans le pipeline apply, avant la génération host_vars.
    """
```

Les rôles consommateurs LLM sont identifiés par une constante :
```python
LLM_CONSUMER_ROLES = {
    "openclaw_server",
    "lobechat",
    "open_webui",
    "opencode_server",
}
```

### 25.6 Enrichissement dans le pipeline apply

```
domains/*.yml
    │
    ▼
parse_project()
    │
    ▼
enrich_llm_vars()    ◄── NOUVEAU : résout les endpoints
    │
    ▼
generate_host_vars()  ── les vars enrichies sont transmises
    │
    ▼
ansible-playbook
```

`enrich_llm_vars()` ajoute à chaque machine consommatrice :

| Variable injectée | Description |
|---|---|
| `llm_effective_url` | URL à contacter (sanitizer ou direct) |
| `llm_effective_key` | Clé API à utiliser (vide si local) |
| `llm_effective_model` | Modèle résolu |
| `llm_effective_backend` | Backend résolu (`local`, `openai`, `anthropic`) |

### 25.7 Mise à jour du rôle `llm_sanitizer`

Le rôle existant reçoit une variable supplémentaire auto-remplie :

```yaml
# defaults/main.yml
sanitizer_port: 8089
sanitizer_mode: mask
sanitizer_upstream_url: ""      # auto-rempli par enrich_llm_vars
sanitizer_log_dir: /var/log/anklume/sanitizer
sanitizer_audit: true           # NOUVEAU : log d'audit des sanitisations
```

Le service systemd du sanitizer transmet `SANITIZER_UPSTREAM_URL`
qui pointe vers le vrai backend LLM (Ollama ou cloud).

### 25.8 Mise à jour des rôles consommateurs

Chaque rôle consommateur lit `llm_effective_url` en priorité,
avec fallback sur sa variable spécifique existante.

**OpenClaw** (`openclaw_server/defaults/main.yml`) :
```yaml
openclaw_port: 8090
openclaw_ollama_host: localhost        # fallback si llm_effective_url absent
openclaw_ollama_port: 11434
openclaw_llm_backend: "{{ llm_effective_backend | default('local') }}"
openclaw_llm_url: "{{ llm_effective_url | default('') }}"
openclaw_llm_api_key: "{{ llm_effective_key | default('') }}"
openclaw_llm_model: "{{ llm_effective_model | default('') }}"
```

Le service systemd passe les variables d'environnement :
```ini
Environment=OPENCLAW_LLM_BACKEND={{ openclaw_llm_backend }}
Environment=OPENCLAW_LLM_URL={{ openclaw_llm_url }}
Environment=OPENCLAW_LLM_API_KEY={{ openclaw_llm_api_key }}
Environment=OPENCLAW_LLM_MODEL={{ openclaw_llm_model }}
```

**LobeChat** (`lobechat/defaults/main.yml`) :
```yaml
lobechat_ollama_url: "http://localhost:11434"  # fallback
lobechat_llm_backend: "{{ llm_effective_backend | default('local') }}"
lobechat_llm_url: "{{ llm_effective_url | default('') }}"
lobechat_llm_api_key: "{{ llm_effective_key | default('') }}"
```

### 25.9 Validation

Le validateur vérifie :
1. `llm_backend` ∈ `{"local", "openai", "anthropic"}` (sinon erreur)
2. `ai_sanitize` ∈ `{"false", "true", "always"}` (sinon erreur)
3. Si `llm_backend` externe → `llm_api_url` requis (sinon erreur)
4. Si `ai_sanitize: true|always` → au moins une machine avec rôle
   `llm_sanitizer` dans l'infra (sinon warning)
5. Si `llm_api_key` présent → ne pas logger/afficher la valeur

### 25.10 Exemples de configuration

**Scénario 1 : tout local (défaut)**
```yaml
# domains/ai-tools.yml
machines:
  gpu-server:
    roles: [base, ollama_server, stt_server]
    gpu: true

# domains/pro.yml
machines:
  assistant:
    roles: [base, openclaw_server]
    vars:
      openclaw_ollama_host: "10.100.3.1"
```

Résultat : OpenClaw contacte Ollama directement. Pas de sanitisation.

**Scénario 2 : LLM cloud + sanitisation**
```yaml
# domains/pro.yml
machines:
  sanitizer:
    description: "Proxy de sanitisation LLM"
    type: lxc
    roles: [base, llm_sanitizer]

  assistant:
    description: "Assistant IA pro"
    type: lxc
    roles: [base, openclaw_server]
    vars:
      llm_backend: openai
      llm_api_url: "https://api.openai.com/v1"
      llm_api_key: "sk-..."
      llm_model: "gpt-4o"
      ai_sanitize: true
```

Résultat : OpenClaw → sanitizer (port 8089) → OpenAI.
Le sanitizer redacte IPs, FQDNs, credentials, noms Incus.

**Scénario 3 : OpenRouter (abonnement) + sanitisation**
```yaml
machines:
  assistant:
    roles: [base, openclaw_server]
    vars:
      llm_backend: openai
      llm_api_url: "https://openrouter.ai/api/v1"
      llm_api_key: "sk-or-..."
      llm_model: "anthropic/claude-sonnet-4-20250514"
      ai_sanitize: true
```

**Scénario 4 : sanitisation même en local**
```yaml
machines:
  assistant:
    roles: [base, openclaw_server]
    vars:
      ai_sanitize: always
```

Résultat : même les requêtes vers Ollama passent par le sanitizer.

## 26. CLI opérationnelle

Commandes essentielles pour l'opérationnel quotidien : inspection
des instances, gestion des domaines, opérations snapshot avancées,
état réseau et supervision LLM.

### 26.1 Gestion des instances

#### `anklume instance list`

Tableau combinant état déclaré (YAML) et état réel (Incus) pour
chaque instance de l'infrastructure.

```
NOM                 DOMAINE   TYPE  ÉTAT       IP
pro-dev             pro       lxc   Running    10.100.1.2
pro-desktop         pro       vm    Stopped    10.100.1.3
perso-web           perso     lxc   Absent     10.100.2.2
ai-tools-gpu-server ai-tools  lxc   Running    10.100.3.1

4 instance(s) — 2 running, 1 arrêtée, 1 absente
```

Colonnes : nom complet, domaine, type (lxc/vm), état Incus
(Running/Stopped/Absent), IP déclarée.

#### `anklume instance exec <instance> -- <cmd>`

Exécute une commande dans une instance via `incus exec`.
L'instance est résolue par son nom complet (`domaine-machine`).

```bash
anklume instance exec pro-dev -- apt update
anklume instance exec pro-dev -- bash
```

Erreur si l'instance est absente ou le nom inconnu.

#### `anklume instance info <instance>`

Détails d'une instance : configuration déclarée, état réel,
snapshots existants.

```
pro-dev
  Domaine     : pro
  Type        : lxc
  État        : Running
  IP          : 10.100.1.2
  Trust level : semi-trusted
  GPU         : non
  Rôles       : base, openssh_server
  Profils     : default
  Éphémère    : non
  Snapshots   : anklume-pre-20250101-120000, anklume-post-20250101-120001
```

Erreur si le nom est inconnu dans les domaines déclarés.

### 26.2 Gestion des domaines

#### `anklume domain list`

Tableau récapitulatif de tous les domaines (actifs et désactivés).

```
NOM       ÉTAT      TRUST-LEVEL    MACHINES  ÉPHÉMÈRE
pro       activé    semi-trusted   3         non
perso     activé    trusted        2         non
ai-tools  désactivé admin          1         non

3 domaine(s) — 2 activé(s), 1 désactivé
```

#### `anklume domain check <nom>`

Valide un domaine isolément : parsing + validation du fichier
`domains/<nom>.yml`. Utile pour vérifier un fichier en cours
d'édition sans déployer.

```bash
anklume domain check pro
# → pro : valide (3 machines)

anklume domain check pro
# → pro : 2 erreur(s)
#   machines.dev: nom invalide ...
```

#### `anklume domain exec <nom> -- <cmd>`

Exécute une commande dans toutes les instances running d'un domaine.
Best-effort : continue si une instance échoue.

```bash
anklume domain exec pro -- apt update
# pro-dev : OK
# pro-desktop : erreur (Stopped)
```

#### `anklume domain status <nom>`

État détaillé d'un seul domaine : projet, réseau, instances, IPs.
Équivalent de `anklume status` filtré sur un domaine.

```
pro:
  Projet : oui    Réseau : oui
  pro-dev          lxc   Running    10.100.1.2   [ok]
  pro-desktop      vm    Stopped    10.100.1.3   [arrêtée]

1/2 instances running
```

### 26.3 Snapshots avancés

#### `anklume snapshot delete <instance> <snapshot>`

Supprime un snapshot spécifique. Erreur si instance ou snapshot
inconnu.

```bash
anklume snapshot delete pro-dev anklume-pre-20250101-120000
# Snapshot 'anklume-pre-20250101-120000' supprimé de pro-dev.
```

#### `anklume snapshot rollback <instance> <snapshot>`

Rollback destructif : restaure le snapshot ET supprime tous les
snapshots créés après celui-ci (cleanup des états intermédiaires).

```bash
anklume snapshot rollback pro-dev anklume-pre-20250101-120000
# Restauration de 'anklume-pre-20250101-120000' sur pro-dev.
# 3 snapshot(s) postérieur(s) supprimé(s).
```

Séquence :
1. Arrêter l'instance si running
2. Restaurer le snapshot
3. Supprimer les snapshots postérieurs (par date `created_at`)
4. Redémarrer l'instance si elle était running

### 26.4 État réseau

#### `anklume network status`

Vue réseau combinant l'état déclaré et l'état réel Incus.

```
DOMAINE   BRIDGE     SUBNET         GATEWAY       ÉTAT
pro       net-pro    10.100.1.0/24  10.100.1.1    actif
perso     net-perso  10.100.2.0/24  10.100.2.1    actif
ai-tools  net-ai     10.100.3.0/24  10.100.3.1    absent

nftables : table inet anklume présente (12 règles)
```

Affiche aussi l'état de la table nftables anklume si elle existe.

### 26.5 Supervision LLM

#### `anklume llm status`

Vue dédiée backend LLM : configuration par machine, modèles
chargés, VRAM.

```
GPU : NVIDIA RTX PRO 5000 — 2048 / 24576 MiB

MACHINE            BACKEND   SANITISÉ  URL
pro-assistant      openai    oui       http://10.100.1.5:8089
ai-tools-chat      local     non       http://10.100.3.1:11434

Ollama : actif (llama3.2:3b chargé)
```

Combine les informations de `compute_ai_status()` (GPU, services)
avec `resolve_llm_endpoint()` (backends configurés par machine).

#### `anklume llm bench`

Benchmark d'inférence sur le backend Ollama local.
Envoie un prompt court, mesure tokens/seconde et latence.

```
Modèle   : llama3.2:3b
Prompt   : "Bonjour, comment ça va ?"
Tokens   : 42
Durée    : 1.23s
Vitesse  : 34.1 tokens/s
```

Options :
- `--model <nom>` — modèle à benchmarker (défaut : premier modèle chargé)
- `--prompt <texte>` — prompt personnalisé

### 26.6 Mise à jour de la table des commandes CLI (§6)

```
### Gestion des instances

| Commande | Description |
|----------|-------------|
| `anklume instance list` | Tableau des instances (nom, domaine, état, IP, type) |
| `anklume instance exec <inst> -- <cmd>` | Exécuter dans une instance |
| `anklume instance info <inst>` | Détails d'une instance |

### Gestion des domaines

| Commande | Description |
|----------|-------------|
| `anklume domain list` | Tableau des domaines |
| `anklume domain check <nom>` | Valider un domaine isolément |
| `anklume domain exec <nom> -- <cmd>` | Exécuter dans toutes les instances |
| `anklume domain status <nom>` | État détaillé d'un domaine |

### Snapshots

| Commande | Description |
|----------|-------------|
| `anklume snapshot delete <inst> <snap>` | Supprimer un snapshot |
| `anklume snapshot rollback <inst> <snap>` | Rollback destructif |

### Réseau

| Commande | Description |
|----------|-------------|
| `anklume network status` | État réseau (bridges, IPs, nftables) |

### LLM

| Commande | Description |
|----------|-------------|
| `anklume llm status` | Vue dédiée backends LLM |
| `anklume llm bench` | Benchmark inférence |
```

### 26.7 Modules engine

#### `engine/ops.py` — Opérations d'inspection

Fonctions pures (sauf lecture Incus via driver) pour les requêtes
d'inspection opérationnelle.

```python
@dataclass
class InstanceInfo:
    """Informations complètes d'une instance."""
    name: str            # nom complet (pro-dev)
    domain: str          # nom du domaine
    machine_type: str    # lxc/vm
    state: str           # Running/Stopped/Absent
    ip: str | None       # IP déclarée
    trust_level: str     # trust level du domaine
    gpu: bool            # flag GPU
    ephemeral: bool      # flag éphémère
    roles: list[str]     # rôles Ansible
    profiles: list[str]  # profils Incus
    snapshots: list[str] # noms des snapshots

@dataclass
class DomainInfo:
    """Informations récapitulatives d'un domaine."""
    name: str
    enabled: bool
    trust_level: str
    machine_count: int
    ephemeral: bool

@dataclass
class NetworkInfo:
    """État réseau d'un domaine."""
    domain: str
    bridge: str
    subnet: str | None
    gateway: str | None
    exists: bool         # bridge présent dans Incus

@dataclass
class NetworkStatus:
    """État réseau complet."""
    networks: list[NetworkInfo]
    nftables_present: bool
    nftables_rule_count: int

def list_instances(
    infra: Infrastructure,
    driver: IncusDriver,
    nesting_context: NestingContext | None = None,
) -> list[InstanceInfo]:
    """Liste toutes les instances avec état réel combiné."""

def get_instance_info(
    infra: Infrastructure,
    driver: IncusDriver,
    instance_name: str,
    nesting_context: NestingContext | None = None,
) -> InstanceInfo | None:
    """Détails complets d'une instance."""

def list_domains(infra: Infrastructure) -> list[DomainInfo]:
    """Liste tous les domaines (actifs et inactifs)."""

def compute_network_status(
    infra: Infrastructure,
    driver: IncusDriver,
    nesting_context: NestingContext | None = None,
) -> NetworkStatus:
    """État réseau complet."""
```

#### `engine/llm_ops.py` — Opérations LLM

```python
@dataclass
class LlmMachineStatus:
    """État LLM d'une machine consommatrice."""
    name: str          # nom complet
    backend: str       # local/openai/anthropic
    sanitized: bool
    url: str

@dataclass
class LlmStatus:
    """État complet LLM."""
    gpu: GpuInfo
    machines: list[LlmMachineStatus]
    ollama_status: str    # actif/injoignable
    ollama_models: list[str]

@dataclass
class BenchResult:
    """Résultat d'un benchmark LLM."""
    model: str
    prompt: str
    tokens: int
    duration_s: float
    tokens_per_s: float

def compute_llm_status(infra: Infrastructure) -> LlmStatus:
    """Vue LLM dédiée."""

def run_llm_bench(
    infra: Infrastructure,
    *,
    model: str = "",
    prompt: str = "Bonjour, comment ça va ?",
) -> BenchResult:
    """Benchmark d'inférence Ollama."""
```

#### Ajouts à `engine/snapshot.py`

```python
def rollback_snapshot(
    driver: IncusDriver,
    instance: str,
    project: str,
    snapshot_name: str,
) -> int:
    """Rollback destructif : restaure et supprime les snapshots postérieurs.

    Returns:
        Nombre de snapshots postérieurs supprimés.
    """
```

## 27. Sanitiser avancé

Enrichissement du moteur de sanitisation (§22) avec de nouveaux
patterns, détection NER optionnelle, templates Jinja2 pour le rôle,
commande CLI dry-run et audit logging.

### 27.1 Patterns supplémentaires

Nouvelles catégories ajoutées à `engine/sanitizer.py` :

| Catégorie | Pattern | Exemples | Placeholder mask |
|-----------|---------|----------|-----------------|
| `mac` | `([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}` | `AA:BB:CC:DD:EE:FF` | `[MAC_REDACTED_N]` |
| `socket` | Chemins `/run/`, `/var/run/`, `*.sock`, `*.socket` | `/var/run/incus.sock` | `[SOCKET_REDACTED_N]` |
| `incus_cmd` | `incus (exec\|launch\|start\|stop\|delete\|config) ...` | `incus exec pro-dev -- bash` | `[INCUS_CMD_REDACTED_N]` |

Pseudonymes correspondants :
- `mac` → `00:00:00:00:00:NN`
- `socket` → `/run/redacted-N.sock`
- `incus_cmd` → `incus [COMMAND_N]`

### 27.2 Détection NER optionnelle

Backends NER en complément des regex (détection d'entités nommées) :

1. **GLiNER** (préféré) — modèle léger, labels personnalisés
2. **spaCy** (fallback) — `fr_core_news_sm` pour entités PER/ORG/LOC

**Fallback gracieux** : si aucun backend NER disponible, regex seul.
Les entités détectées par NER utilisent la catégorie `"ner"` et le
placeholder `[NER_REDACTED_N]`.

```python
NER_BACKENDS = {"gliner", "spacy"}

def detect_ner_backend() -> str | None:
    """Détecte le backend NER disponible (gliner > spacy > None)."""

def ner_extract(text: str, backend: str) -> list[tuple[int, int, str]]:
    """Extrait les entités via NER. Retourne [(start, end, entity_text)]."""
```

La fonction `sanitize()` accepte un nouveau paramètre optionnel
`ner: bool = False`. Si `True`, les entités NER sont ajoutées aux
matches regex.

### 27.3 Commande CLI `anklume llm sanitize`

Dry-run de sanitisation depuis le terminal :

```bash
# Texte en argument
anklume llm sanitize "Connexion à 10.100.1.1 via pro-dev"

# Pipe stdin
echo "token=sk-abc123" | anklume llm sanitize -

# Options
anklume llm sanitize --mode pseudonymize "texte"
anklume llm sanitize --ner "texte avec Jean Dupont"
anklume llm sanitize --json "texte"  # sortie JSON
```

**Sortie par défaut** :
```
Texte sanitisé :
  Connexion à [IP_REDACTED_1] via [RESOURCE_REDACTED_1]

Remplacements (2) :
  ip         : 10.100.1.1     → [IP_REDACTED_1]
  resource   : pro-dev        → [RESOURCE_REDACTED_1]
```

**Sortie JSON** (`--json`) :
```json
{
  "text": "Connexion à [IP_REDACTED_1] via [RESOURCE_REDACTED_1]",
  "replacements": [
    {"original": "10.100.1.1", "replaced": "[IP_REDACTED_1]",
     "category": "ip", "position": [13, 23]},
    ...
  ]
}
```

### 27.4 Audit logging

Trace des redactions dans un fichier de log (JSON-lines).

```python
@dataclass
class AuditEntry:
    """Une entrée d'audit de sanitisation."""
    timestamp: str          # ISO 8601
    mode: str               # mask | pseudonymize
    categories: dict[str, int]  # {"ip": 2, "credential": 1}
    total_redactions: int

def audit_log(
    result: SanitizeResult,
    *,
    mode: str,
    log_path: Path | None = None,
) -> AuditEntry:
    """Écrit une entrée d'audit et la retourne.

    log_path: chemin du fichier d'audit (défaut: /var/log/anklume/sanitizer/audit.jsonl).
    """
```

Variables du rôle `llm_sanitizer` :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `sanitizer_audit` | `true` | Activer l'audit logging |
| `sanitizer_audit_log_path` | `/var/log/anklume/sanitizer/audit.jsonl` | Chemin du log |
| `sanitizer_categories` | `all` | Catégories actives (`all` ou liste) |

### 27.5 Templates Jinja2 du rôle

Le rôle `llm_sanitizer` génère ses fichiers de configuration
depuis des templates :

- `templates/config.yml.j2` — configuration du proxy
  (port, mode, upstream, audit, log_path)
- `templates/patterns.yml.j2` — catégories de patterns activables
  (ip, mac, fqdn, credential, socket, incus_cmd, resource, ner)

Chaque catégorie est activable/désactivable via
`sanitizer_categories` (liste ou `"all"`).

```yaml
# defaults/main.yml
sanitizer_categories: all  # ou [ip, mac, credential, fqdn]
sanitizer_audit_log_path: /var/log/anklume/sanitizer/audit.jsonl
```

### 27.6 Module `engine/sanitizer.py` — ajouts

```python
# Nouveaux patterns
_MAC = re.compile(r"\b([0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})\b")
_SOCKET = re.compile(r"(/(?:var/)?run/[\w./-]+\.sock(?:et)?|/tmp/[\w./-]+\.sock(?:et)?)")
_INCUS_CMD = re.compile(
    r"(incus\s+(?:exec|launch|start|stop|delete|config|copy|move|snapshot)"
    r"\s+[^\n;|&]+)"
)

def sanitize(
    text: str,
    *,
    infra: Infrastructure | None = None,
    mode: str = "mask",
    ner: bool = False,
    categories: set[str] | None = None,  # None = toutes
) -> SanitizeResult:
    """..."""

def audit_log(
    result: SanitizeResult,
    *,
    mode: str,
    log_path: Path | None = None,
) -> AuditEntry:
    """..."""

def detect_ner_backend() -> str | None:
    """..."""

def ner_extract(text: str, backend: str) -> list[tuple[int, int, str]]:
    """..."""
```

### 27.7 Intégration CLI

Ajout dans `cli/__init__.py` :

```python
@llm_app.command("sanitize")
def llm_sanitize(
    text: str = typer.Argument(None, help="Texte à sanitiser (- pour stdin)"),
    mode: str = typer.Option("mask", help="Mode : mask, pseudonymize"),
    ner: bool = typer.Option(False, help="Activer la détection NER"),
    json_output: bool = typer.Option(False, "--json", help="Sortie JSON"),
) -> None:
    """Dry-run de sanitisation."""
```

Implémentation dans `cli/_llm.py` : `run_llm_sanitize()`.

## 28. Rôle OpenClaw modernisé et admin_bootstrap

Phase 16 — mise à jour du rôle `openclaw_server` pour l'OpenClaw
actuel (TypeScript, npm, daemon natif) et ajout du rôle
`admin_bootstrap` pour la première configuration machine.

### 28.1 Rôle `openclaw_server` modernisé

OpenClaw est désormais une application TypeScript installée via npm.
Le daemon systemd est créé par OpenClaw lui-même via `openclaw onboard`.
Le rôle Ansible ne réinvente pas la configuration — il délègue à
la CLI native d'OpenClaw.

**Installation** :

```
npm install -g openclaw@<version>
```

**Daemon** :

```
openclaw onboard --install-daemon
```

Cette commande crée le workspace (`~/.openclaw/workspace`), installe
le service systemd, et configure les défauts.

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `openclaw_version` | `latest` | Version npm à installer |
| `openclaw_user` | `openclaw` | Utilisateur système dédié |
| `openclaw_channels` | `[]` | Canaux : `telegram`, `signal`, `matrix` |
| `openclaw_llm_provider` | `ollama` | Provider LLM natif OpenClaw |
| `openclaw_llm_model` | `""` | Modèle LLM (vide = défaut provider) |
| `openclaw_port` | `8090` | Port HTTP API (inchangé) |

Les variables `llm_effective_*` issues du routage §25 sont mappées
vers les variables OpenClaw natives :

| Variable routage | Variable OpenClaw |
|------------------|-------------------|
| `llm_effective_backend` | `openclaw_llm_provider` |
| `llm_effective_url` | `OPENCLAW_LLM_URL` (env) |
| `llm_effective_key` | `OPENCLAW_LLM_API_KEY` (env) |
| `llm_effective_model` | `openclaw_llm_model` |

**Tâches** :

1. Créer l'utilisateur système `openclaw` (avec home dir)
2. Installer Node.js 20.x (si absent)
3. Installer OpenClaw via npm global (`openclaw@{{ openclaw_version }}`)
4. Exécuter `openclaw onboard --install-daemon` (en tant que
   `openclaw_user`, crée workspace + service systemd)
5. Déployer l'override systemd pour les variables d'environnement
   LLM (`/etc/systemd/system/openclaw.service.d/llm.conf`)
6. Démarrer et activer le service
7. Health check `/health` (port `openclaw_port`)

**Override systemd** (template `llm.conf.j2`) :

```ini
[Service]
Environment=OPENCLAW_LLM_URL={{ openclaw_llm_url }}
Environment=OPENCLAW_LLM_API_KEY={{ openclaw_llm_api_key }}
Environment=OPENCLAW_LLM_PROVIDER={{ openclaw_llm_provider }}
Environment=OPENCLAW_LLM_MODEL={{ openclaw_llm_model }}
Environment=OPENCLAW_PORT={{ openclaw_port }}
```

L'override ne remplace pas l'unit file créée par `onboard` —
il ajoute les variables d'environnement spécifiques à l'infra.

**Handler** : `restart openclaw` (inchangé).

### 28.2 Rôle `admin_bootstrap`

Première configuration d'une machine fraîche : locale, timezone,
paquets de base, mise à jour système. Rôle généraliste applicable
à toute instance, pas spécifique IA.

**Variables** (`defaults/main.yml`) :

| Variable | Défaut | Description |
|----------|--------|-------------|
| `bootstrap_locale` | `fr_FR.UTF-8` | Locale système |
| `bootstrap_timezone` | `Europe/Paris` | Timezone |
| `bootstrap_packages` | `[vim, htop, tree, jq, unzip]` | Paquets utilitaires |
| `bootstrap_upgrade` | `true` | Lancer `apt upgrade` |

**Tâches** :

1. Mettre à jour le cache APT
2. Mettre à jour les paquets (`apt upgrade`, si `bootstrap_upgrade`)
3. Configurer la locale (`locale-gen`)
4. Configurer la timezone (`timedatectl`)
5. Installer les paquets utilitaires

**Différence avec le rôle `base`** : le rôle `base` installe les
prérequis pour qu'Ansible fonctionne (curl, ca-certificates, sudo,
locales). Le rôle `admin_bootstrap` configure la machine pour un
usage confortable (timezone, vim, htop, upgrade). Ils sont
complémentaires : `roles: [base, admin_bootstrap, ...]`.

### 28.3 Configuration dans le domaine

```yaml
machines:
  ai-assistant:
    description: "Assistant IA OpenClaw"
    type: lxc
    roles: [base, admin_bootstrap, openclaw_server]
    vars:
      openclaw_channels: [telegram]
      openclaw_llm_provider: ollama
      bootstrap_timezone: "Europe/Paris"
```

### 28.4 Détection du service

Le `_SERVICE_DEFS` dans `engine/ai.py` reste inchangé :
port 8090, health path `/health`, rôle `openclaw_server`.

### 28.5 Mise à jour du template init

Le template `anklume init` inclut `ai-assistant` (commenté)
dans le domaine `ai-tools` avec les rôles
`[base, admin_bootstrap, openclaw_server]`.

### 28.6 Intégration routage LLM

Le module `llm_routing.py` continue de traiter `openclaw_server`
comme un `LLM_CONSUMER_ROLE`. La fonction `enrich_llm_vars()`
enrichit les variables de la machine, qui sont ensuite mappées
vers les variables d'environnement OpenClaw dans l'override systemd.

## 29. Portails et transferts

Communication hôte ↔ conteneur sans compromettre l'isolation.
Quatre fonctionnalités complémentaires : transfert de fichiers,
partage de presse-papiers, conteneurs jetables, et import d'infra
existante.

### 29.1 File portals — transfert de fichiers

Transfert de fichiers entre l'hôte et les conteneurs via la
CLI `incus file push/pull`. Le portail respecte les frontières
de projet Incus : chaque instance est identifiée par son nom
complet (`domaine-machine`) et résolue vers son projet.

#### Commandes CLI

```
anklume portal push <instance> <chemin_local> [chemin_distant]
anklume portal pull <instance> <chemin_distant> [chemin_local]
anklume portal list <instance> [chemin_distant]
```

**`push`** : envoie un fichier local vers l'instance.
- `chemin_distant` : défaut `/tmp/` (le fichier garde son nom)
- Vérifie que le fichier local existe
- Vérifie que l'instance existe dans l'infra

**`pull`** : récupère un fichier depuis l'instance.
- `chemin_local` : défaut `.` (répertoire courant)
- Vérifie que l'instance existe dans l'infra

**`list`** : liste les fichiers d'un répertoire distant.
- `chemin_distant` : défaut `/root/`
- Affiche : nom, type, taille, permissions

#### Sorties

```
# push
Envoyé : rapport.pdf → pro-dev:/tmp/rapport.pdf (42 Ko)

# pull
Récupéré : pro-dev:/var/log/syslog → ./syslog (128 Ko)

# list
NOM                TYPE        TAILLE    PERMISSIONS
rapport.pdf        fichier     42 Ko     -rw-r--r--
backup/            répertoire  -         drwxr-xr-x
```

#### Driver Incus — méthodes fichier

```python
def file_push(
    self,
    instance: str,
    project: str,
    local_path: str,
    remote_path: str,
) -> None:
    """Push un fichier via incus file push."""
    self._run([
        "file", "push", local_path,
        f"{instance}{remote_path}",
        "--project", project,
    ])

def file_pull(
    self,
    instance: str,
    project: str,
    remote_path: str,
    local_path: str,
) -> None:
    """Pull un fichier via incus file pull."""
    self._run([
        "file", "pull",
        f"{instance}{remote_path}",
        local_path,
        "--project", project,
    ])
```

#### Module `engine/portal.py`

```python
@dataclass
class PortalEntry:
    """Entrée dans un répertoire distant."""
    name: str
    entry_type: str     # "file" | "directory" | "link"
    size: int           # octets (-1 si inconnu)
    permissions: str    # ex: "-rw-r--r--"

@dataclass
class TransferResult:
    """Résultat d'un transfert fichier."""
    instance: str
    local_path: str
    remote_path: str
    size: int           # octets transférés

def push_file(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    local_path: str,
    remote_path: str = "/tmp/",
) -> TransferResult:
    """Envoie un fichier vers une instance."""

def pull_file(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    remote_path: str,
    local_path: str = ".",
) -> TransferResult:
    """Récupère un fichier depuis une instance."""

def list_remote(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
    remote_path: str = "/root/",
) -> list[PortalEntry]:
    """Liste les entrées d'un répertoire distant."""
```

Chaque fonction résout d'abord l'instance vers son projet via
`resolve_instance_project()`. Erreur si l'instance est inconnue.

### 29.2 Clipboard sharing — presse-papiers hôte ↔ conteneur

Pipe le contenu du presse-papiers hôte vers/depuis un conteneur.
Utilise `wl-paste`/`wl-copy` côté hôte (Wayland KDE Plasma) et
un fichier temporaire dans le conteneur.

#### Commande CLI

```
anklume instance clipboard <instance> --push    # hôte → conteneur
anklume instance clipboard <instance> --pull    # conteneur → hôte
```

**`--push`** (défaut) :
1. Lit le presse-papiers hôte via `wl-paste`
2. Écrit le contenu dans `/tmp/.anklume-clipboard` du conteneur
   via `file_push`
3. Affiche le nombre de caractères transférés

**`--pull`** :
1. Lit `/tmp/.anklume-clipboard` du conteneur via `instance_exec`
2. Écrit sur le presse-papiers hôte via `wl-copy`
3. Affiche le nombre de caractères transférés

#### Module `engine/clipboard.py`

```python
CLIPBOARD_PATH = "/tmp/.anklume-clipboard"

@dataclass
class ClipboardResult:
    """Résultat d'une opération presse-papiers."""
    direction: str        # "push" | "pull"
    instance: str
    content_length: int   # caractères transférés

def clipboard_push(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
) -> ClipboardResult:
    """Copie le presse-papiers hôte vers le conteneur."""

def clipboard_pull(
    driver: IncusDriver,
    infra: Infrastructure,
    instance: str,
) -> ClipboardResult:
    """Copie le contenu du conteneur vers le presse-papiers hôte."""

def read_host_clipboard() -> str:
    """Lit le presse-papiers hôte via wl-paste."""

def write_host_clipboard(text: str) -> None:
    """Écrit sur le presse-papiers hôte via wl-copy."""
```

#### Modification du driver

Ajout du paramètre `input` à `instance_exec` pour supporter
le pipe de données vers stdin :

```python
def instance_exec(
    self,
    instance: str,
    project: str,
    command: list[str],
    *,
    input: str | None = None,
) -> subprocess.CompletedProcess:
    """Exécute une commande dans une instance.

    Args:
        input: données à envoyer sur stdin de la commande.
    """
```

### 29.3 Disposable containers — conteneurs jetables

Conteneurs éphémères pour des tâches ponctuelles. Lancement rapide,
shell interactif, destruction automatique à la sortie.

#### Commandes CLI

```
anklume disp <image>                # shell interactif
anklume disp <image> -- <cmd>       # exécuter une commande
anklume disp --list                 # lister les conteneurs jetables actifs
anklume disp --cleanup              # détruire tous les conteneurs jetables
```

**Shell interactif** :
1. Crée un conteneur `disp-XXXX` (suffixe hex aléatoire 4 chars)
2. Démarre le conteneur
3. Ouvre un shell via `incus exec` (process remplacé, stdin/stdout
   directs vers le terminal)
4. À la sortie du shell, détruit le conteneur

**Exécution unique** :
1. Crée et démarre le conteneur
2. Exécute la commande via `instance_exec`
3. Affiche stdout/stderr
4. Détruit le conteneur

**Listing** : affiche les conteneurs `disp-*` en cours.

**Cleanup** : détruit tous les conteneurs `disp-*`.

#### Module `engine/disposable.py`

```python
DISP_PREFIX = "disp-"
DISP_PROJECT = "default"

@dataclass
class DispContainer:
    """Conteneur jetable."""
    name: str
    image: str
    project: str = DISP_PROJECT
    status: str = "Running"

def generate_disp_name() -> str:
    """Génère un nom unique disp-XXXX (4 hex)."""

def launch_disposable(
    driver: IncusDriver,
    image: str,
    *,
    project: str = DISP_PROJECT,
) -> DispContainer:
    """Crée et démarre un conteneur jetable."""

def list_disposables(
    driver: IncusDriver,
    *,
    project: str = DISP_PROJECT,
) -> list[DispContainer]:
    """Liste les conteneurs jetables actifs."""

def destroy_disposable(
    driver: IncusDriver,
    name: str,
    *,
    project: str = DISP_PROJECT,
) -> None:
    """Arrête et détruit un conteneur jetable."""

def cleanup_disposables(
    driver: IncusDriver,
    *,
    project: str = DISP_PROJECT,
) -> int:
    """Détruit tous les conteneurs jetables. Retourne le nombre supprimé."""
```

#### Shell interactif

Le shell interactif utilise `os.execvp` pour remplacer le processus
Python par `incus exec`. Cela donne un vrai terminal interactif
avec support des signaux, redimensionnement, etc.

```python
import os
os.execvp("incus", [
    "incus", "exec", name, "--project", project, "--", "bash",
])
```

Le nettoyage du conteneur est assuré par un `atexit` handler
ou un `try/finally` qui appelle `destroy_disposable` avant
l'exec. Comme `execvp` remplace le process, le cleanup est
fait dans un fork préalable.

Alternative : utiliser `subprocess.run` sans `capture_output`
(stdin/stdout/stderr hérités du terminal parent), puis détruire
après la fin du process.

### 29.4 Import infrastructure existante

Scanne un Incus déjà configuré et génère les fichiers
`domains/*.yml` correspondants. Permet d'adopter anklume sur
une infrastructure existante.

#### Commande CLI

```
anklume setup import [--dir <répertoire>]
```

**Flux** :
1. Scanner les projets Incus (hors `default`)
2. Pour chaque projet : scanner les réseaux et instances
3. Mapper vers le format domaine anklume :
   - Projet → domaine
   - Réseau `net-*` → subnet (déduit du config CIDR)
   - Instance → machine (nom déduit en retirant le préfixe projet)
4. Générer les fichiers `domains/<projet>.yml`
5. Afficher un récapitulatif

**Limitations** :
- Les rôles Ansible ne sont pas détectés (config manuelle)
- Les trust levels ne sont pas déduits (défaut `semi-trusted`)
- Le `anklume.yml` existant est préservé (créé si absent)

#### Module `engine/import_infra.py`

```python
@dataclass
class ScannedInstance:
    """Instance détectée dans Incus."""
    name: str
    status: str
    instance_type: str    # "container" | "virtual-machine"
    project: str

@dataclass
class ScannedDomain:
    """Domaine reconstitué depuis un projet Incus."""
    project: str
    network: str | None
    subnet: str | None
    instances: list[ScannedInstance]

@dataclass
class ImportResult:
    """Résultat d'un import."""
    domains: list[ScannedDomain]
    files_written: list[str]

def scan_incus(driver: IncusDriver) -> list[ScannedDomain]:
    """Scanne les projets Incus et reconstruit les domaines."""

def generate_domain_files(
    domains: list[ScannedDomain],
    output_dir: Path,
) -> list[str]:
    """Génère les fichiers domains/*.yml depuis le scan.

    Returns:
        Liste des chemins de fichiers écrits.
    """

def import_infrastructure(
    driver: IncusDriver,
    output_dir: Path,
) -> ImportResult:
    """Scan complet + génération de fichiers."""
```

### 29.5 Intégration CLI

#### Nouveau groupe `portal`

```python
# cli/__init__.py
portal_app = typer.Typer(help="Transfert de fichiers hôte ↔ conteneur.")
app.add_typer(portal_app, name="portal")

@portal_app.command("push")
def portal_push(instance, local_path, remote_path="/tmp/")

@portal_app.command("pull")
def portal_pull(instance, remote_path, local_path=".")

@portal_app.command("list")
def portal_list(instance, path="/root/")
```

#### Extension `instance clipboard`

```python
@instance_app.command("clipboard")
def instance_clipboard(instance, push=True, pull=False)
```

#### Commande `disp`

```python
@app.command("disp")
def disp(image=None, cmd=None, list_all=False, cleanup=False)
```

#### Nouveau groupe `setup`

```python
setup_app = typer.Typer(help="Configuration et import.")
app.add_typer(setup_app, name="setup")

@setup_app.command("import")
def setup_import(dir=".")
```

#### Fichiers CLI

| Fichier | Fonctions |
|---------|-----------|
| `cli/_portal.py` | `run_portal_push`, `run_portal_pull`, `run_portal_list` |
| `cli/_instance.py` | `run_instance_clipboard` (ajout) |
| `cli/_disp.py` | `run_disp` |
| `cli/_setup.py` | `run_setup_import` |

### 29.6 Tests

| Module | Tests | Couverture |
|--------|-------|-----------|
| `test_portal.py` | push, pull, list, instance inconnue, fichier absent | engine/portal.py |
| `test_clipboard.py` | push, pull, wl-paste/wl-copy mock, erreurs | engine/clipboard.py |
| `test_disposable.py` | launch, list, destroy, cleanup, nommage | engine/disposable.py |
| `test_import_infra.py` | scan, generate, projets vides, noms machines | engine/import_infra.py |
| `test_driver_file.py` | file_push, file_pull, instance_exec input | incus_driver.py |
| `test_cli_phase17.py` | registration des commandes portal, disp, setup | cli/__init__.py |

### 29.7 Mise à jour des commandes CLI (§6)

```
### Portails et transferts

| Commande | Description |
|----------|-------------|
| `anklume portal push <inst> <local> [remote]` | Envoyer un fichier |
| `anklume portal pull <inst> <remote> [local]` | Récupérer un fichier |
| `anklume portal list <inst> [path]` | Lister fichiers distants |
| `anklume instance clipboard <inst>` | Presse-papiers hôte ↔ conteneur |
| `anklume disp <image>` | Conteneur jetable (shell interactif) |
| `anklume disp --list` | Lister les conteneurs jetables |
| `anklume setup import` | Importer une infra Incus existante |
```
