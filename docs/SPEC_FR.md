# SPEC.md -- Specification anklume

> Note : la version anglaise ([`SPEC.md`](SPEC.md)) fait reference en cas de divergence.

## 1. Vision

anklume est un framework declaratif de cloisonnement d'infrastructure.
Il fournit une isolation de type QubesOS en utilisant les fonctionnalites
natives du noyau Linux (KVM/LXC), avec des capacites IA integrees
optionnelles.

L'utilisateur decrit son infrastructure dans un seul fichier YAML
(`infra.yml`), execute `make sync && make apply`, et obtient des
environnements isoles, reproductibles et jetables. anklume abstrait
la complexite des technologies sous-jacentes (Incus, Ansible, nftables)
derriere un format declaratif haut niveau -- maitriser ces outils est
benefique mais pas requis.

**Principe de conception : minimiser la friction UX.** Chaque interaction
avec le framework -- du premier bootstrap aux operations quotidiennes --
doit necessiter le moins d'etapes, de decisions et de prerequis
possible. Des valeurs par defaut sensees eliminent la configuration
quand l'utilisateur n'a pas d'opinion. Les messages d'erreur expliquent
quoi faire, pas seulement ce qui a echoue. Les formats sont choisis
pour une compatibilite maximale (ex. ISO hybride pour les images live,
disposition Ansible standard pour les fichiers generes).

Le framework est livre avec des valeurs par defaut suivant les
conventions d'entreprise :
- Adressage IP par niveau de confiance (`10.<zone>.<seq>.<host>`)
  encodant la posture de securite directement dans les adresses IP
- Conventions de nommage des domaines alignees avec les pratiques
  professionnelles de segmentation reseau
- Toutes les valeurs par defaut sont configurables pour les
  environnements personnalises

Optionnellement, anklume integre des assistants IA dans
l'infrastructure cloisonnee :
- Assistants IA par domaine respectant les frontieres reseau
- Inference LLM locale (GPU) avec fallback cloud optionnel
- Anonymisation automatique des donnees sensibles quittant le
  perimetre local

Concu pour :
- Les **administrateurs systemes** cloisonnant leur poste de travail
- Les **etudiants** apprenant l'administration systeme dans un
  environnement sur, reproductible, qui reproduit les conventions
  d'entreprise (classes IP, nommage, segmentation reseau)
- Les **enseignants** deployant des TPs reseau pour N etudiants
- Les **utilisateurs avances** voulant une isolation type QubesOS
  sans les contraintes QubesOS
- Les **utilisateurs soucieux de leur vie privee** ayant besoin de
  contourner des restrictions internet ou de router le trafic via
  des passerelles isolees (Tor, VPN)
- Toute personne voulant des outils IA qui respectent les frontieres
  de domaine et la confidentialite des donnees

## 2. Concepts cles

### Domaine
Un domaine = un sous-reseau isole + un projet Incus + N instances.
Chaque domaine devient :
- Un groupe d'inventaire Ansible
- Un bridge reseau (`net-<domaine>`)
- Un projet Incus (isolation par espace de noms)
- Un fichier `group_vars/<domaine>.yml`

Ajouter un domaine = ajouter une section dans `infra.yml` + `make sync`.

### Instance (machine)
Un container LXC ou une machine virtuelle KVM. Definie dans un domaine
dans `infra.yml`. Chaque instance devient un hote Ansible dans le groupe
de son domaine, avec des variables dans `host_vars/<instance>.yml`.

### Profil
Une configuration Incus reutilisable (GPU, imbrication, limites de
ressources). Defini au niveau du domaine dans `infra.yml`, applique aux
instances qui le referencent.

### Snapshot
Un etat sauvegarde d'une instance. Supporte : individuel, par lot
(domaine entier), restauration, suppression.

## 3. Modele de source de verite (PSOT)

```
+-----------------------+     make sync     +---------------------------+
|     infra.yml         | -----------------> |  Fichiers Ansible         |
|  (Source de Verite    |                    |  (Source de Verite        |
|   Primaire)           |                    |   Secondaire)             |
|                       |                    |                           |
|  Description de       |                    |  inventory/<domaine>.yml  |
|  l'infra de haut      |                    |  group_vars/<domaine>.yml |
|  niveau : domaines,   |                    |  host_vars/<hote>.yml     |
|  machines, reseaux,   |                    |                           |
|  profils              |                    |  Les utilisateurs peuvent |
|                       |                    |  editer librement en      |
|                       |                    |  dehors des sections gerees|
+-----------------------+                    +-------------+-------------+
                                                          |
                                                     make apply
                                                          |
                                                          v
                                             +---------------------------+
                                             |    Etat Incus             |
                                             |  (bridges, projets,       |
                                             |   profils, instances)     |
                                             +---------------------------+
```

**Regles** :
- `infra.yml` contient la verite structurelle (quels domaines, machines,
  IPs, profils).
- Les fichiers Ansible generes contiennent la verite operationnelle
  (variables personnalisees, configuration supplementaire, parametres
  de roles ajoutes par l'utilisateur).
- Les deux doivent etre commites dans git.
- `make sync` ne reecrit que les sections `=== MANAGED ===` ; tout le
  reste est preserve.

## 4. Architecture de l'hote

```
+---------------------------------------------------------+
| Hote (n'importe quelle distribution Linux)              |
|  . Daemon Incus + nftables + (optionnel) GPU NVIDIA     |
|                                                          |
|  +----------+ +----------+ +----------+                  |
|  | net-aaa  | | net-bbb  | | net-ccc  |  ...            |
|  | .X.0/24  | | .Y.0/24  | | .Z.0/24  |                 |
|  +----+-----+ +----+-----+ +----+-----+                 |
|       |             |             |                       |
|  +----+----+  +-----+----+ +----+------+                 |
|  | LXC/VM  |  | LXC/VM   | | LXC/VM   |                 |
|  +---------+  +----------+ +----------+                  |
|                                                          |
|  Isolation nftables : net-X != net-Y (pas de forwarding) |
+---------------------------------------------------------+
```

Le container anklume (`anklume-instance`) :
- A le socket Incus de l'hote monte en lecture/ecriture
- Contient Ansible, le depot git, et pilote tout via le CLI `incus`
- Evite de modifier l'hote autant que possible ; quand c'est
  necessaire (nftables, prerequis logiciels), les modifications
  sont faites directement si c'est plus KISS/DRY et ne compromet
  pas la securite (ADR-004)

## 5. Format d'infra.yml

```yaml
# infra.yml -- Source de Verite Primaire
# Decrit l'infrastructure. Executez `make sync` apres modification.

project_name: my-infra

global:
  addressing:                         # Adressage IP par zone (ADR-038)
    base_octet: 10                    # Premier octet, toujours 10 (RFC 1918)
    zone_base: 100                    # Deuxieme octet de depart (defaut : 100)
    zone_step: 10                     # Ecart entre les zones (defaut : 10)
  default_os_image: "images:debian/13"
  default_connection: community.general.incus
  default_user: root
  ai_access_policy: open            # "exclusive" ou "open" (defaut : open)
  ai_access_default: pro            # Domaine avec acces initial (requis si exclusive)
  ai_vram_flush: true               # Vider la VRAM GPU au changement de domaine (defaut : true)
  nesting_prefix: true              # Prefixer les noms Incus avec le niveau d'imbrication (defaut : true)
  resource_policy:                  # Optionnel : allocation automatique CPU/memoire
    host_reserve:
      cpu: "20%"                    # Reserve pour l'hote (defaut : 20%)
      memory: "20%"                 # Reserve pour l'hote (defaut : 20%)
    mode: proportional              # proportional | equal (defaut : proportional)
    cpu_mode: allowance             # allowance (%) | count (vCPU) (defaut : allowance)
    memory_enforce: soft            # soft (ballooning) | hard (defaut : soft)
    overcommit: false               # Autoriser total > disponible (defaut : false)

domains:
  <nom-domaine>:
    description: "A quoi sert ce domaine"
    enabled: true                     # Optionnel (defaut : true). false ignore la generation.
    subnet_id: <0-254>               # Optionnel : auto-assigne alphabetiquement dans la zone
    ephemeral: false                  # Optionnel (defaut : false). Voir ci-dessous.
    trust_level: semi-trusted         # Determine la zone IP (defaut : semi-trusted)
    profiles:                         # Optionnel : profils Incus supplementaires
      <nom-profil>:
        devices: { ... }
        config: { ... }
    machines:
      <nom-machine>:                # Doit etre globalement unique
        description: "Ce que fait cette machine"
        type: lxc                     # "lxc" ou "vm"
        ip: "<bo>.<zone>.<seq>.<host>"  # Optionnel (auto-assigne si omis)
        ephemeral: false              # Optionnel (defaut : herite du domaine)
        gpu: false                    # true pour activer le passthrough GPU
        profiles: [default]           # Liste de profils Incus
        weight: 1                     # Poids d'allocation de ressources (defaut : 1)
        boot_autostart: false         # Optionnel : demarrer au boot de l'hote (defaut : false)
        boot_priority: 0             # Optionnel : ordre de demarrage 0-100 (defaut : 0)
        snapshots_schedule: "0 2 * * *"  # Optionnel : planning cron pour les auto-snapshots
        snapshots_expiry: "30d"       # Optionnel : duree de retention (ex. 30d, 24h)
        config: { ... }              # Surcharges de config instance Incus
        storage_volumes: { ... }     # Optionnel : volumes dedies
        roles: [base_system]         # Roles Ansible pour le provisionnement
```

### Convention d'adressage (ADR-038)

Les adresses IP encodent les zones de confiance dans le deuxieme octet :

```
10.<zone_base + zone_offset>.<domain_seq>.<host>/24
```

| trust_level    | zone_offset | Deuxieme octet par defaut |
|----------------|-------------|---------------------------|
| admin          | 0           | 100                       |
| trusted        | 10          | 110                       |
| semi-trusted   | 20          | 120                       |
| untrusted      | 40          | 140                       |
| disposable     | 50          | 150                       |

`domain_seq` (troisieme octet) est auto-assigne alphabetiquement dans
chaque zone, ou explicitement surcharge via `subnet_id` sur le domaine.

Reservation IP par sous-reseau /24 :
- `.1-.99` : assignation statique (machines dans infra.yml, auto-assignees)
- `.100-.199` : plage DHCP
- `.250` : monitoring (reserve)
- `.251-.253` : services d'infrastructure
- `.254` : passerelle (convention immuable)

### Convention de passerelle

Chaque reseau de domaine utilise `<base_octet>.<zone>.<seq>.254` comme
adresse de passerelle. Ceci est defini automatiquement par le generateur
et ne peut pas etre surcharge.

### Directive enabled

Le booleen optionnel `enabled` sur un domaine controle si le generateur
produit des fichiers pour celui-ci. Par defaut `true`. Quand `false`,
aucun fichier d'inventaire, group_vars ou host_vars n'est genere pour
ce domaine. Les domaines desactives participent toujours au calcul
d'adressage (leurs plages IP sont reservees) et ne sont pas signales
comme orphelins.

### Directive ephemere

Le booleen `ephemeral` controle si un domaine ou une machine est protege
contre la suppression accidentelle :

- **Niveau domaine** : `ephemeral: false` (defaut) protege le domaine
  entier.
- **Niveau machine** : surcharge la valeur du domaine pour cette machine
  specifique.
- **Heritage** : si non specifie sur une machine, herite de son domaine.
  Si non specifie sur un domaine, defaut a `false` (protege).

**Semantique** :
- `ephemeral: false` (protege) : toute operation de suppression (machine,
  reseau, domaine) qui detruirait cette ressource est refusee par
  l'outillage. `detect_orphans()` signale les ressources protegees mais
  `--clean-orphans` les ignore.
- `ephemeral: true` : la ressource peut etre librement creee et detruite.

Le role `incus_instances` propage le flag ephemere vers Incus nativement :
`ephemeral: false` definit `security.protection.delete=true` sur
l'instance, empechant la suppression via `incus delete`. `ephemeral: true`
le definit a `false`.

### Demarrage automatique

Les champs optionnels `boot_autostart` et `boot_priority` controlent le
comportement des instances au demarrage de l'hote Incus :

- `boot_autostart: true` definit `boot.autostart=true` sur l'instance,
  faisant en sorte qu'Incus la demarre automatiquement au lancement du
  daemon.
- `boot_priority` (0-100) controle l'ordre de demarrage. Les valeurs
  plus elevees demarrent en premier. Defaut : 0.

Le role `incus_instances` applique ces parametres via `incus config set`.

### Snapshots automatiques

Les champs optionnels `snapshots_schedule` et `snapshots_expiry`
activent les snapshots automatiques natifs d'Incus :

- `snapshots_schedule` est une expression cron (5 champs, ex.
  `"0 2 * * *"` pour tous les jours a 2h). Incus cree les snapshots
  automatiquement selon ce planning.
- `snapshots_expiry` est une duree de retention (ex. `"30d"`, `"24h"`,
  `"60m"`). Incus supprime automatiquement les snapshots plus anciens.

Les deux sont optionnels et independants. Le role `incus_instances`
les applique via `incus config set snapshots.schedule` et
`snapshots.expiry`.

### Prefixe d'imbrication

Le booleen optionnel `nesting_prefix` dans `global:` active le
prefixage de tous les noms de ressources Incus avec le niveau
d'imbrication. Cela evite les collisions de noms quand anklume
s'execute imbrique dans une autre instance anklume.

```yaml
global:
  nesting_prefix: false   # Desactivation (defaut : true)
```

Quand active, le generateur lit `/etc/anklume/absolute_level` (cree par
l'instance parente). Si le fichier est absent (hote physique, pas
d'imbrication), aucun prefixe n'est applique quelle que soit la
configuration. Le format du prefixe est `{level:03d}-` :

| Ressource | Sans prefixe | Avec prefixe (niveau 1) |
|-----------|-------------|------------------------|
| Projet Incus | `pro` | `001-pro` |
| Nom du bridge | `net-pro` | `001-net-pro` |
| Nom d'instance | `pro-dev` | `001-pro-dev` |

Les chemins de fichiers Ansible et les noms de groupes restent sans
prefixe (`inventory/pro.yml`, `group_vars/pro.yml`,
`host_vars/pro-dev.yml`). Le prefixe n'affecte que les noms cote Incus
stockes dans les variables (`incus_project`, `incus_network.name`,
`instance_name`). Les roles Ansible consomment ces variables de maniere
transparente.

Quand `nesting_prefix: false`, aucun prefixe n'est applique. C'est
utile quand anklume s'execute directement sur un hote physique sans
imbrication.

### Niveaux de confiance

Le champ optionnel `trust_level` indique la posture de securite et les
exigences d'isolation d'un domaine. C'est principalement utilise par le
generateur de console (Phase 19a) pour l'identification visuelle des
domaines par code couleur (style QubesOS), mais peut aussi informer de
futures decisions de controle d'acces et de politique.

Valeurs valides :
- **`admin`** : Domaine administratif avec acces systeme complet (bleu)
- **`trusted`** : Charges de travail de production, donnees personnelles (vert)
- **`semi-trusted`** : Developpement, tests, navigation a faible risque (jaune)
- **`untrusted`** : Logiciels non fiables, navigation risquee (rouge)
- **`disposable`** : Bacs a sable ephemeres, taches ponctuelles (magenta)

Si omis, aucun niveau de confiance n'est assigne et le domaine n'a pas
de code couleur specifique dans la console.

Le generateur propage `trust_level` vers `domain_trust_level` dans
`group_vars/<domaine>.yml`. Les roles et outils peuvent lire cette
variable pour adapter leur comportement selon la posture de confiance
du domaine.

### Contraintes de validation

- Noms de domaine : uniques, alphanumeriques + tiret
- Noms de machine : globalement uniques (pas seulement dans leur domaine)
- `enabled` : doit etre un booleen si present (defaut : true)
- `subnet_id` : optionnel avec `addressing:` (auto-assigne) ; unique
  dans la meme zone de confiance, plage 0-254
- IPs : globalement uniques, doivent etre dans le bon sous-reseau
  (auto-assignees dans la plage `.1-.99` quand omises en mode
  `addressing:`)
- `addressing.base_octet` : doit etre 10 (RFC 1918)
- `addressing.zone_base` : doit etre 0-245 (defaut : 100)
- `addressing.zone_step` : doit etre un entier positif (defaut : 10)
- Les profils references par une machine doivent exister dans son domaine
- Politique GPU (`gpu_policy: exclusive` par defaut) : au plus une
  instance avec `gpu: true` ou un peripherique GPU dans un profil. Si
  compteur > 1 et politique != `shared` -> erreur. Si compteur > 1 et
  politique == `shared` -> avertissement. Les instances VM avec GPU
  necessitent IOMMU (Phase 9+)
- `ephemeral` : doit etre un booleen si present (aux niveaux domaine et
  machine)
- `trust_level` : doit etre l'un de `admin`, `trusted`, `semi-trusted`,
  `untrusted`, `disposable` (si present)
- `weight` : doit etre un entier positif si present (defaut : 1)
- `boot_autostart` : doit etre un booleen si present
- `boot_priority` : doit etre un entier 0-100 si present (defaut : 0)
- `snapshots_schedule` : doit etre une expression cron valide (5 champs)
  si present
- `snapshots_expiry` : doit etre une chaine de duree (ex. `30d`, `24h`,
  `60m`) si present
- `ai_access_policy` : doit etre `exclusive` ou `open`
- `resource_policy.mode` : doit etre `proportional` ou `equal` (si
  present)
- `resource_policy.cpu_mode` : doit etre `allowance` ou `count` (si
  present)
- `resource_policy.memory_enforce` : doit etre `soft` ou `hard` (si
  present)
- `nesting_prefix` : doit etre un booleen si present (defaut : true)
- `resource_policy.overcommit` : doit etre un booleen (si present)
- `resource_policy.host_reserve.cpu` et `.memory` : doivent etre `"N%"`
  ou un nombre positif (si present)
- `shared_volumes_base` : doit etre un chemin absolu si present
  (defaut : `/srv/anklume/shares`)
- Noms de volumes `shared_volumes` : DNS-safe
  (`^[a-z0-9]([a-z0-9-]*[a-z0-9])?$`)
- `shared_volumes.*.source` et `.path` : doivent etre des chemins absolus
- `shared_volumes.*.shift` : doit etre un booleen si present (defaut :
  true)
- `shared_volumes.*.propagate` : doit etre un booleen si present
  (defaut : false)
- `shared_volumes.*.consumers` : doit etre un mapping non vide ; les
  cles doivent etre des noms de domaine ou machine connus ; les valeurs
  doivent etre `"ro"` ou `"rw"`
- Collision de noms de peripheriques : `sv-<nom>` ne doit pas entrer en
  collision avec les peripheriques declares par l'utilisateur sur un
  consommateur
- Unicite des chemins : deux volumes ne peuvent pas monter au meme
  `path` sur la meme machine consommatrice
- Quand `ai_access_policy: exclusive` :
  - `ai_access_default` est requis et doit referencer un domaine connu
  - `ai_access_default` ne peut pas etre `ai-tools` lui-meme
  - Un domaine `ai-tools` doit exister
  - Au plus une `network_policy` peut cibler `ai-tools` comme destination

### Conventions de nommage

Les noms de machines suivent le schema `<domaine>-<role>`. Deux
domaines ont une signification speciale :

**Domaine `anklume`** (infrastructure/admin) :
- Niveau de confiance : `admin`
- Machines prefixees `anklume-`
- Objectif : infrastructure du framework (orchestration, firewall)
- Exemples : `anklume-instance`, `anklume-firewall`

**Domaine `shared`** (services partages) :
- Niveau de confiance : `semi-trusted`
- Machines prefixees `shared-`
- Objectif : services accessibles depuis plusieurs domaines via
  `network_policies` (impression, DNS, VPN)
- Exemples : `shared-print`, `shared-dns`, `shared-vpn`

**Autres domaines** : schema standard `<domaine>-<role>` :
- `pro-dev`, `perso-desktop`, `ai-gpu`, `torgw-proxy`

Le prefixe `sys-` est retire. Les declarations legacy `sys-firewall`
sont toujours acceptees pour la retrocompatibilite (voir ci-dessous).

### Auto-creation de anklume-firewall (firewall_mode: vm)

Quand `global.firewall_mode` est defini a `vm`, le generateur cree
automatiquement une machine `anklume-firewall` dans le domaine anklume
si elle n'est pas deja declaree. Cette etape d'enrichissement
(`enrich_infra()`) s'execute apres la validation mais avant la
generation de fichiers. La machine auto-creee utilise :
- type : `vm`, ip : `<base_octet>.<zone>.<anklume_seq>.253`
- config : `limits.cpu: "2"`, `limits.memory: "2GiB"`
- roles : `[base_system, firewall_router]`
- ephemeral : `false`

Si l'utilisateur declare `anklume-firewall` explicitement (dans
n'importe quel domaine), sa definition a la priorite et aucune
auto-creation ne se produit. Pour la retrocompatibilite, une
declaration `sys-firewall` empeche egalement l'auto-creation.
Si `firewall_mode` est `vm` mais qu'aucun domaine `anklume`
n'existe, le generateur quitte avec une erreur.

### Politique de securite (containers privilegies)

Le generateur applique une politique de securite basee sur le contexte
d'imbrication :

- **`security.privileged: true`** est interdit sur les containers LXC
  quand `vm_nested` est `false` (c.-a-d. aucune VM n'existe dans la
  chaine au-dessus de l'instance anklume courante). Seules les VMs
  fournissent une isolation materielle suffisante pour les charges de
  travail privilegiees.
- Le flag `vm_nested` est auto-detecte au bootstrap via
  `systemd-detect-virt` et propage a toutes les instances enfants.
- Un flag `--YOLO` contourne cette restriction (avertissements au lieu
  d'erreurs).

Le contexte d'imbrication est stocke dans `/etc/anklume/` sous forme de
fichiers individuels :
- `absolute_level` -- profondeur d'imbrication depuis l'hote physique reel
- `relative_level` -- profondeur d'imbrication depuis la frontiere VM la
  plus proche (reinitialisee a 0 a chaque VM)
- `vm_nested` -- `true` si une VM existe quelque part dans la chaine
  parente
- `yolo` -- `true` si le mode YOLO est active

Ces fichiers sont crees par le **parent** quand il instancie les enfants,
pas par le bootstrap de l'enfant lui-meme.

### Politiques reseau

Par defaut, tout le trafic inter-domaines est bloque. La section
`network_policies` declare des exceptions selectives :

```yaml
network_policies:
  - description: "Pro domain accesses AI services"
    from: pro                    # Source : nom de domaine ou de machine
    to: ai-tools                 # Destination : nom de domaine ou de machine
    ports: [3000, 8080]          # Ports TCP/UDP
    protocol: tcp                # tcp ou udp

  - description: "Host accesses Ollama"
    from: host                   # Mot-cle special : l'hote physique
    to: gpu-server               # Machine specifique
    ports: [11434]
    protocol: tcp

  - description: "Full connectivity between dev and staging"
    from: dev
    to: staging
    ports: all                   # Tous les ports, tous les protocoles
    bidirectional: true          # Regles dans les deux sens
```

Mots-cles speciaux :
- Nom de domaine -> sous-reseau entier de ce domaine
- Nom de machine -> IP unique de cette machine
- `host` -> la machine hote physique
- `ports: all` -> tous les ports et protocoles
- `bidirectional: true` -> cree des regles dans les deux sens

Le generateur valide que chaque `from` et `to` reference un nom de
domaine, un nom de machine connu, ou le mot-cle `host`. Chaque regle
correspond a une regle nftables `accept` avant le `drop` general.

### Politique d'allocation de ressources

La section optionnelle `resource_policy` dans `global:` active
l'allocation automatique de CPU et memoire aux instances basee sur
les ressources detectees de l'hote.

```yaml
global:
  resource_policy:              # absent = pas d'auto-allocation
    host_reserve:
      cpu: "20%"                # Reserve pour l'hote (defaut : 20%)
      memory: "20%"             # Reserve pour l'hote (defaut : 20%)
    mode: proportional          # proportional | equal (defaut : proportional)
    cpu_mode: allowance         # allowance (%) | count (vCPU) (defaut : allowance)
    memory_enforce: soft        # soft (ballooning) | hard (defaut : soft)
    overcommit: false           # Autoriser total > disponible (defaut : false)
```

Definir `resource_policy: {}` ou `resource_policy: true` active
l'allocation avec toutes les valeurs par defaut : 20% de reserve hote,
distribution proportionnelle, mode CPU allowance, application memoire
soft.

**Reserve hote** : Un pourcentage fixe (ou une valeur absolue) des
ressources hote reservees pour le systeme d'exploitation et le daemon
Incus. Les instances ne peuvent pas utiliser cette reserve.

**Modes de distribution** :
- `proportional` : Chaque machine recoit des ressources proportionnelles
  a son `weight` (poids par defaut : 1). Une machine avec `weight: 3`
  recoit trois fois les ressources d'une machine avec `weight: 1`.
- `equal` : Toutes les machines recoivent la meme part quel que soit
  le poids.

**Modes CPU** :
- `allowance` : Definit `limits.cpu.allowance` en pourcentage. Permet
  un partage flexible du CPU via le scheduler CFS.
- `count` : Definit `limits.cpu` comme un nombre fixe de vCPUs. Dedie
  des coeurs aux instances.

**Application memoire** :
- `soft` : Ajoute `limits.memory.enforce: "soft"` (ballooning memoire
  cgroups v2). Les instances peuvent temporairement depasser leur limite
  quand la memoire de l'hote est disponible. Les VMs utilisent
  nativement virtio-balloon.
- `hard` : Comportement par defaut d'Incus -- limite memoire stricte.

**Overcommit** : Quand `false` (defaut), le generateur produit une
erreur si la somme de toutes les ressources allouees (auto + explicites)
depasse le pool disponible. Quand `true`, un avertissement est emis a
la place.

**Poids des machines** :

```yaml
machines:
  heavy-worker:
    weight: 3               # Recoit 3x la part des machines a poids par defaut
    type: lxc
  light-worker:
    type: lxc               # Poids par defaut : 1
```

Les machines avec des `limits.cpu`, `limits.cpu.allowance`, ou
`limits.memory` explicites dans leur `config:` sont exclues de
l'auto-allocation pour cette ressource mais comptees dans le total
d'overcommit. Le generateur ne surcharge jamais la configuration
explicite.

**Detection** : Les ressources de l'hote sont detectees via
`incus info --resources` (prefere) ou `/proc/cpuinfo` +
`/proc/meminfo` (fallback). Si la detection echoue, l'allocation
de ressources est ignoree avec un avertissement.

### Volumes partages

La section optionnelle de haut niveau `shared_volumes:` declare des
repertoires de l'hote partages avec des consommateurs (machines ou
domaines entiers) via des peripheriques disque Incus.

```yaml
global:
  shared_volumes_base: /mnt/anklume-data/shares  # Defaut : /srv/anklume/shares

shared_volumes:
  docs:
    source: /mnt/anklume-data/shares/docs  # Optionnel, defaut : <base>/<nom>
    path: /shared/docs                      # Optionnel, defaut : /shared/<nom>
    shift: true                             # Optionnel, defaut : true
    propagate: false                        # Optionnel, defaut : false
    consumers:
      pro: ro            # Domaine -> toutes les machines du domaine en ro
      pro-dev: rw        # Machine -> surcharge en rw pour cette machine
      ai-tools: ro       # Un autre domaine
```

**Champs** :
- `source` : chemin absolu sur l'hote vers le repertoire. Defaut :
  `<shared_volumes_base>/<nom_volume>`.
- `path` : chemin de montage dans les consommateurs. Defaut :
  `/shared/<nom_volume>`.
- `shift` : activer le shifting idmap (`shift=true` sur le peripherique
  disque Incus). Defaut : `true`. Necessaire pour que les containers non
  privilegies accedent aux fichiers possedes par l'hote.
- `propagate` : si `true`, le volume est aussi monte dans les instances
  ayant `security.nesting=true` dans leur config, permettant aux
  instances anklume imbriquees de re-declarer le volume. Defaut : `false`.
- `consumers` : mapping de noms de domaine ou machine vers un mode
  d'acces (`ro` ou `rw`). Les entrees au niveau machine surchargent
  les entrees au niveau domaine pour cette machine specifique.

**Mecanisme** : Le generateur resout `shared_volumes` en peripheriques
disque Incus injectes dans `instance_devices` dans les host_vars de
chaque consommateur. Aucun nouveau role Ansible n'est necessaire -- le
role `incus_instances` existant gere les peripheriques disque
arbitraires.

- Nommage des peripheriques : `sv-<nom_volume>` (le prefixe `sv-` evite
  les collisions avec les peripheriques declares par l'utilisateur).
- Resolution des consommateurs : un nom de domaine s'etend a toutes les
  machines du domaine ; un nom de machine cible cette machine
  specifiquement ; l'acces au niveau machine surcharge l'acces au niveau
  domaine pour la meme machine.
- Fusion : les peripheriques `sv-*` sont ajoutes aux cotes des
  `instance_devices` declares par l'utilisateur. La validation empeche
  les collisions de noms.

**Imbrication croisee** : `propagate: true` monte le volume dans les
instances avec imbrication activee. L'anklume enfant peut alors
re-declarer le volume avec `source:` pointant vers le chemin de montage
propage. Il n'y a pas de propagation recursive automatique -- chaque
niveau d'imbrication doit declarer explicitement ses volumes.

**Repertoires hote** : `make shares` cree les repertoires cote hote
pour tous les volumes partages declares. `global.shared_volumes_base`
definit le chemin de base (defaut : `/srv/anklume/shares`).

### infra.yml en tant que repertoire

Pour les grands deploiements, `infra.yml` peut etre remplace par un
repertoire `infra/` :

```
infra/
├── base.yml                 # project_name + parametres globaux
├── domains/
│   ├── anklume.yml          # Un fichier par domaine
│   ├── ai-tools.yml
│   ├── pro.yml
│   └── perso.yml
└── policies.yml             # network_policies
```

Le generateur auto-detecte le format :
- Si `infra.yml` existe -> mode fichier unique (retro-compatible)
- Si `infra/` existe -> fusionne `base.yml` + `domains/*.yml` (tries
  alphabetiquement) + `policies.yml`

Les deux formats produisent une sortie identique apres fusion.

---

Pour les details operationnels (generateur, roles, snapshots,
validateurs, flux de travail de developpement, pile technique,
bootstrap et tests), voir
[SPEC-operations.md](SPEC-operations.md).
