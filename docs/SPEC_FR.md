# SPEC.md -- Specification AnKLuMe

> Traduction francaise de [`SPEC.md`](SPEC.md). En cas de divergence, la version anglaise fait foi.

## 1. Vision

AnKLuMe est un framework declaratif de cloisonnement d'infrastructure.
Il fournit une isolation de type QubesOS en utilisant les fonctionnalites
natives du noyau Linux (KVM/LXC), orchestrees par l'utilisateur via
Ansible et Incus.

L'utilisateur decrit son infrastructure dans un seul fichier YAML (`infra.yml`),
execute `make sync && make apply`, et obtient des environnements isoles,
reproductibles et jetables.

Concu pour :
- Les administrateurs systemes qui veulent cloisonner leur poste de travail
- Les enseignants deployant des TPs reseau pour N etudiants
- Les utilisateurs avances qui veulent une isolation de type QubesOS sans les contraintes de QubesOS

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
Un container LXC ou une machine virtuelle KVM. Definie dans un domaine dans `infra.yml`.
Chaque instance devient un hote Ansible dans le groupe de son domaine, avec des
variables dans `host_vars/<instance>.yml`.

### Profil
Une configuration Incus reutilisable (GPU, imbrication, limites de ressources). Defini au
niveau du domaine dans `infra.yml`, applique aux instances qui le referencent.

### Snapshot
Un etat sauvegarde d'une instance. Supporte : individuel, par lot (domaine entier),
restauration, suppression.

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
- `infra.yml` contient la verite structurelle (quels domaines, machines, IPs, profils).
- Les fichiers Ansible generes contiennent la verite operationnelle (variables
  personnalisees, configuration supplementaire, parametres de roles ajoutes par l'utilisateur).
- Les deux doivent etre commites dans git.
- `make sync` ne reecrit que les sections `=== MANAGED ===` ; tout le reste
  est preserve.

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

Le container d'administration :
- A le socket Incus de l'hote monte en lecture/ecriture
- Contient Ansible, le depot git, et pilote tout via le CLI `incus`
- Ne modifie jamais l'hote directement

## 5. Format d'infra.yml

```yaml
# infra.yml -- Source de Verite Primaire
# Decrit l'infrastructure. Executez `make sync` apres modification.

project_name: my-infra

global:
  base_subnet: "10.100"             # Les domaines utilisent <base_subnet>.<subnet_id>.0/24
  default_os_image: "images:debian/13"
  default_connection: community.general.incus
  default_user: root

domains:
  <nom-domaine>:
    description: "A quoi sert ce domaine"
    subnet_id: <0-254>               # Doit etre unique entre tous les domaines
    ephemeral: false                  # Optionnel (defaut : false). Voir ci-dessous.
    profiles:                         # Optionnel : profils Incus supplementaires
      <nom-profil>:
        devices: { ... }
        config: { ... }
    machines:
      <nom-machine>:                # Doit etre globalement unique
        description: "Ce que fait cette machine"
        type: lxc                     # "lxc" ou "vm"
        ip: "<base_subnet>.<subnet_id>.<hote>"  # Optionnel (DHCP si omis)
        ephemeral: false              # Optionnel (defaut : herite du domaine)
        gpu: false                    # true pour activer le passthrough GPU
        profiles: [default]           # Liste de profils Incus
        config: { ... }              # Surcharges de config instance Incus
        storage_volumes: { ... }     # Optionnel : volumes dedies
        roles: [base_system]         # Roles Ansible pour le provisionnement
```

### Convention de passerelle

Chaque reseau de domaine utilise `<base_subnet>.<subnet_id>.254` comme adresse
de passerelle. Ceci est defini automatiquement par le generateur et ne peut pas
etre surcharge.

### Directive ephemere

Le booleen `ephemeral` controle si un domaine ou une machine est protege
contre la suppression accidentelle :

- **Niveau domaine** : `ephemeral: false` (defaut) protege le domaine entier.
- **Niveau machine** : surcharge la valeur du domaine pour cette machine specifique.
- **Heritage** : si non specifie sur une machine, herite de son domaine.
  Si non specifie sur un domaine, defaut a `false` (protege).

**Semantique** :
- `ephemeral: false` (protege) : toute operation de suppression (machine, reseau,
  domaine) qui detruirait cette ressource est refusee par l'outillage.
  `detect_orphans()` signale les ressources protegees mais `--clean-orphans`
  les ignore.
- `ephemeral: true` : la ressource peut etre librement creee et detruite.

### Contraintes de validation

- Noms de domaine : uniques, alphanumeriques + tiret
- Noms de machine : globalement uniques (pas seulement dans leur domaine)
- `subnet_id` : unique par domaine, plage 0-254
- IPs : globalement uniques, doivent etre dans le sous-reseau correct
- Les profils references par une machine doivent exister dans son domaine
- `ephemeral` : doit etre un booleen si present (aux niveaux domaine et machine)

## 6. Generateur (scripts/generate.py)

Lit `infra.yml` et genere/met a jour l'arborescence de fichiers Ansible.

### Fichiers generes

```
inventory/<domaine>.yml      # Hotes pour ce domaine
group_vars/all.yml           # Variables globales
group_vars/<domaine>.yml     # Variables au niveau du domaine
host_vars/<machine>.yml      # Variables specifiques a la machine
```

### Patron des sections gerees

```yaml
# === MANAGED BY infra.yml ===
# Ne modifiez pas cette section -- elle sera reecrite par `make sync`
incus_network:
  name: net-example
  subnet: 10.100.0.0/24
  gateway: 10.100.0.254
# === END MANAGED ===

# Vos variables personnalisees ci-dessous :
```

### Comportement du generateur

1. **Fichier manquant** -> cree avec la section geree + commentaires utiles
2. **Fichier existant** -> seule la section geree est reecrite, le reste est preserve
3. **Orphelins** -> listes dans un rapport, suppression interactive proposee
4. **Validation** -> toutes les contraintes verifiees avant d'ecrire un fichier

### Variables de connexion

`default_connection` et `default_user` de la section `global:` d'`infra.yml`
sont stockees dans `group_vars/all.yml` sous les noms `psot_default_connection` et
`psot_default_user` (a titre informatif uniquement). Les playbooks peuvent
referencer ces valeurs si necessaire.

Elles ne sont **PAS** produites sous la forme `ansible_connection` ou `ansible_user`
dans aucun fichier genere. Justification : les variables d'inventaire Ansible
ont priorite sur les mots-cles au niveau du play
([precedence des variables](https://docs.ansible.com/ansible/latest/reference_appendices/general_precedence.html)).
Si `ansible_connection: community.general.incus` apparaissait dans les
group_vars d'un domaine, cela surchargerait `connection: local` dans le playbook,
amenant les roles d'infrastructure a tenter de se connecter dans des containers
qui n'existent pas encore. La connexion est une preoccupation operationnelle
du playbook, pas une propriete declarative de l'infrastructure.

## 7. Roles Ansible

### Phase 1 : Infrastructure (connection: local, cible : localhost)

| Role | Responsabilite | Tags |
|------|---------------|------|
| `incus_networks` | Creer/reconcilier les bridges | `networks`, `infra` |
| `incus_projects` | Creer/reconcilier les projets + profil par defaut | `projects`, `infra` |
| `incus_profiles` | Creer les profils supplementaires (GPU, imbrication) | `profiles`, `infra` |
| `incus_storage` | Creer les volumes de stockage dedies | `storage`, `infra` |
| `incus_instances` | Creer/gerer les instances LXC + VM | `instances`, `infra` |

### Phase 2 : Provisionnement (connection: community.general.incus)

| Role | Responsabilite | Tags |
|------|---------------|------|
| `base_system` | Paquets de base, locale, fuseau horaire, utilisateur | `provision`, `base` |
| (defini par l'utilisateur) | Configuration specifique a l'application | `provision` |

### Patron de reconciliation (tous les roles d'infra)

Chaque role d'infra suit exactement ce patron en 6 etapes :
1. **Lire** l'etat actuel : `incus <ressource> list --format json`
2. **Parser** en une structure comparable
3. **Construire** l'etat desire a partir de group_vars/host_vars
4. **Creer** ce qui est declare mais manquant
5. **Mettre a jour** ce qui existe mais differe
6. **Detecter les orphelins** -- signaler, supprimer si `auto_cleanup: true`

## 8. Snapshots (scripts/snap.sh)

Operations imperatives (pas de reconciliation declarative). Encapsule `incus snapshot`.

### Interface

```bash
scripts/snap.sh create  <instance|self> [nom-snap]    # Nom par defaut : snap-YYYYMMDD-HHMMSS
scripts/snap.sh restore <instance|self> <nom-snap>
scripts/snap.sh list    [instance|self]                 # Toutes les instances si omis
scripts/snap.sh delete  <instance|self> <nom-snap>
```

### Cibles Makefile

```bash
make snap              I=<nom|self> [S=<snap>]   # Creer
make snap-restore      I=<nom|self>  S=<snap>    # Restaurer
make snap-list        [I=<nom|self>]              # Lister
make snap-delete       I=<nom|self>  S=<snap>    # Supprimer
```

### Resolution instance-vers-projet

Interroge `incus list --all-projects --format json` pour trouver quel projet
Incus contient l'instance. L'ADR-008 (noms globalement uniques) garantit une
resolution non ambigue.

### Mot-cle "self"

Lorsque `I=self`, le script utilise `hostname` pour detecter le nom de l'instance
courante. Fonctionne depuis n'importe quelle instance ayant acces au socket Incus
(typiquement le container d'administration). Echoue avec un message clair si le
nom d'hote n'est pas trouve.

### Securite de l'auto-restauration

Restaurer l'instance dans laquelle vous etes en cours d'execution tue votre session.
Le script avertit et demande une confirmation (`Type 'yes' to confirm`). Utilisez
`--force` pour ignorer le prompt (pour une utilisation scriptee).

## 9. Validateurs

Chaque type de fichier a un validateur dedie. Aucun fichier n'echappe a la validation.

| Validateur | Fichiers cibles | Verifications |
|-----------|-------------|--------|
| `ansible-lint` | `roles/**/*.yml`, playbooks | Profil production, 0 violation |
| `yamllint` | Tous les `*.yml` / `*.yaml` | Syntaxe, formatage, longueur de ligne |
| `shellcheck` | `scripts/**/*.sh` | Bonnes pratiques shell, portabilite |
| `ruff` | `scripts/**/*.py`, `tests/**/*.py` | Linting + formatage Python |
| `markdownlint` | `**/*.md` (optionnel) | Coherence Markdown |
| `ansible-playbook --syntax-check` | Playbooks | Syntaxe YAML/Jinja2 |

`make lint` execute tous les validateurs en sequence. Le CI doit tous les passer.

## 10. Flux de travail de developpement

Ce projet suit un **developpement pilote par la specification et les tests** :

1. **Specification d'abord** : Mettre a jour SPEC.md ou ARCHITECTURE.md
2. **Tests ensuite** : Molecule (roles) ou pytest (generateur)
3. **Implementation en troisieme** : Coder jusqu'a ce que les tests passent
4. **Valider** : `make lint`
5. **Revue** : Executer l'agent de revue
6. **Commiter** : Seulement quand tout passe

## 11. Pile technique

| Composant | Version | Role |
|-----------|---------|------|
| Incus | >= 6.0 LTS | Containers LXC + VMs KVM |
| Ansible | >= 2.16 | Orchestration, roles |
| community.general | >= 9.0 | Plugin de connexion `incus` |
| Molecule | >= 24.0 | Tests de roles |
| pytest | >= 8.0 | Tests du generateur |
| Python | >= 3.11 | Generateur PSOT |
| nftables | -- | Isolation inter-bridges |
| shellcheck | -- | Validation des scripts shell |
| ruff | -- | Linting Python |

## 12. Hors perimetre

Gere manuellement ou par des scripts de bootstrap de l'hote :
- Installation/configuration du pilote NVIDIA
- Configuration du noyau / mkinitcpio
- Installation du daemon Incus
- Configuration nftables de l'hote (isolation inter-bridges, NAT)
- Configuration Sway/Wayland pour le transfert d'interface graphique

Le framework AnKLuMe ne modifie PAS l'hote. Il pilote Incus via le socket.
