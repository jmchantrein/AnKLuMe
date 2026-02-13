# ARCHITECTURE.md -- Registre des Decisions d'Architecture

> Traduction francaise de [`ARCHITECTURE.md`](ARCHITECTURE.md). En cas de divergence, la version anglaise fait foi.

Chaque decision est numerotee et definitive sauf si explicitement remplacee.
Claude Code doit respecter ces decisions sans les remettre en question.

---

## ADR-001 : L'inventaire Ansible reflete l'infrastructure reelle

**Contexte** : Une iteration precedente utilisait un dossier personnalise `domains/`
avec `include_vars` + `find`. C'etait une reinvention de `group_vars`.

**Decision** : L'inventaire Ansible est le miroir de l'infrastructure reelle.
Chaque domaine = un groupe Ansible. Chaque container/VM = un hote dans son groupe.
Variables dans `group_vars/<domaine>.yml` et `host_vars/<machine>.yml`.

**Consequence** : Mecanismes Ansible natifs uniquement. Pas de chargement dynamique personnalise.

---

## ADR-002 : Modele PSOT -- infra.yml est la Source de Verite Primaire

**Contexte** : Editer manuellement inventory + group_vars + host_vars est fastidieux.

**Decision** : `infra.yml` est la Source de Verite Primaire (PSOT). Le generateur
produit l'arborescence de fichiers Ansible avec des sections gerees. Les fichiers
generes sont la Source de Verite Secondaire -- librement editables en dehors des
sections gerees. Les deux doivent etre commites dans git.

**Consequence** : Pour ajouter une machine, editer `infra.yml` + `make sync`. Pour
personnaliser davantage, editer les fichiers generes en dehors des sections gerees.

---

## ADR-003 : Tags Ansible pour le ciblage, pas d'extra-vars

**Contexte** : Une iteration precedente utilisait `-e target_domains=[...]`.

**Decision** : Utiliser les mecanismes Ansible standards : `--tags` pour les types
de ressources, `--limit` pour les domaines. Combinables.

**Consequence** : Pas de logique de filtrage personnalisee dans les playbooks.

---

## ADR-004 : Pas d'hyperviseur dans l'inventaire

**Contexte** : L'hote fait tourner Incus mais n'est pas gere par Ansible.

**Decision** : Ansible s'execute dans un container d'administration avec le socket
Incus monte. La Phase 1 cible `localhost`. La Phase 2 cible les instances via le
plugin de connexion `community.general.incus`.

**Consequence** : L'hote n'apparait jamais dans l'inventaire.

---

## ADR-005 : Incus via CLI, pas de modules Ansible natifs

**Contexte** : Les modules `community.general.lxd_*` sont casses avec Incus.
Aucun module `incus_*` stable n'existe.

**Decision** : Utiliser `ansible.builtin.command` + CLI `incus` + `--format json`
+ verifications d'idempotence manuelles.

**Consequence** : Chaque role d'infra implemente sa propre idempotence. Plus verbeux
mais fiable.

---

## ADR-006 : Deux phases d'execution distinctes

**Decision** :
- Phase 1 (Infra) : `hosts: localhost`, `connection: local`, tag `infra`
- Phase 2 (Provisionnement) : `hosts: all:!localhost`,
  `connection: community.general.incus`, tag `provision`

**Consequence** : `--tags infra` et `--tags provision` fonctionnent independamment.

---

## ADR-007 : GPU NVIDIA = LXC uniquement, pas de VM

**Decision** : Les instances GPU sont des containers LXC avec un profil GPU. Les modeles
LLM sont stockes dans des volumes de stockage separes. Pas de GPU pour les VMs KVM.

---

## ADR-008 : Noms de machine globalement uniques

**Decision** : Les noms de machine sont globalement uniques, pas seulement dans leur
domaine. Le generateur valide cette contrainte.

---

## ADR-009 : Developpement pilote par la specification et les tests

**Decision** : Le flux de travail de developpement est :
1. Ecrire/mettre a jour la specification
2. Ecrire les tests (Molecule pour les roles, pytest pour le generateur)
3. Implementer jusqu'a ce que les tests passent
4. Valider (`make lint`)
5. Revue (agent de revue)
6. Commiter seulement quand tout passe

**Consequence** : Pas de code sans specification et test correspondants.

---

## ADR-010 : Generateur Python sans dependances externes

**Decision** : `scripts/generate.py` utilise uniquement PyYAML et la bibliotheque
standard. Pas de framework, pas de moteur de template externe.

---

## ADR-011 : Tout le contenu en anglais, traductions francaises maintenues

**Decision** : Tout le code, les commentaires, la documentation et les prompts sont
en anglais. Des traductions francaises (`*_FR.md`) sont maintenues pour tous les
fichiers de documentation, toujours synchronisees avec les versions anglaises. Cela
inclut `README_FR.md` et tous les fichiers dans `docs/` (ex. `quickstart_FR.md`,
`SPEC_FR.md`, `ARCHITECTURE_FR.md`, etc.). Chaque fichier francais inclut une note
d'en-tete indiquant que la version anglaise fait foi en cas de divergence.

---

## ADR-012 : Chaque type de fichier a un validateur dedie

**Contexte** : La qualite du code doit etre appliquee de maniere coherente sur tous
les types de fichiers.

**Decision** : Chaque type de fichier a un validateur obligatoire :
- `*.yml` / `*.yaml` -> `yamllint` + `ansible-lint` (pour les fichiers Ansible)
- `*.sh` -> `shellcheck`
- `*.py` -> `ruff`
- `*.md` -> `markdownlint` (optionnel mais recommande)

`make lint` chaine tous les validateurs. Le CI doit tous les passer. Aucun fichier
n'echappe a la validation.

**Consequence** : Les contributeurs doivent avoir tous les validateurs installes.
`make init` les installe.

---

## ADR-013 : MVP Snapshot via script shell, pas de role Ansible

**Contexte** : Le snapshot et la restauration sont des operations imperatives, ponctuelles
("prendre un snapshot maintenant", "restaurer ce snapshot maintenant"). Elles ne suivent pas
le patron de reconciliation declaratif (lire/comparer/creer/mettre a jour/orphelins)
que tous les roles d'infra utilisent. Un playbook Ansible serait une boucle for glorifiee
autour de `incus snapshot` avec un overhead inutile.

**Decision** : Le MVP snapshot est `scripts/snap.sh`, un script Bash autonome
encapsulant les commandes CLI `incus snapshot`. Il interroge Incus directement
(`incus list --all-projects`) pour resoudre les correspondances instance-vers-projet.
Supporte le mot-cle `self` pour auto-detecter l'instance courante via `hostname`.

**Consequence** : Les cibles Makefile de snapshot invoquent `scripts/snap.sh`. Valide
par `shellcheck`. Un role Ansible declaratif pourrait remplacer ceci dans une phase
future si des hooks pre/post ou de la planification sont necessaires.

---

## ADR-014 : Les reseaux vivent dans le projet Incus par defaut

**Contexte** : Les projets Incus peuvent controler si les reseaux sont specifiques
au projet ou partages. Nos projets utilisent `features.networks=false`, ce qui
signifie que les reseaux sont geres globalement dans le projet par defaut.

**Decision** : Tous les bridges de domaine sont crees dans le projet par defaut. Le
profil par defaut de chaque projet reference le bridge appropriate par son nom.

**Justification** :
- Gestion plus simple : un seul endroit pour tous les reseaux
- L'isolation nftables se fait au niveau de l'hote, pas au niveau du projet Incus
- Conforme aux recommandations upstream d'Incus pour la plupart des deploiements
- Reference : https://linuxcontainers.org/incus/docs/main/explanation/projects/

**Consequences** : Les taches Ansible liees au reseau n'utilisent pas le flag
`--project`. Les taches de profil ONT besoin de `--project` pour configurer le
profil de chaque projet.

---

## ADR-015 : Le playbook utilise hosts:all avec connection:local

**Contexte** : Toutes les commandes Incus doivent s'executer sur le controleur
Ansible (`admin-ansible`) qui a le socket Incus monte. Les autres hotes de
l'inventaire n'ont pas acces a Incus et n'existent pas encore lorsque les
roles d'infrastructure s'executent.

**Decision** : Le playbook `site.yml` utilise `hosts: all` avec
`connection: local`. Chaque hote fournit ses variables generees par le PSOT
(domaine, configuration reseau, configuration d'instance). Toutes les commandes
s'executent localement sur le controleur via le socket Incus. Aucun `run_once`
n'est utilise -- chaque hote execute les roles independamment.

**Pourquoi pas `run_once`** : Avec `run_once: true`, un seul hote par play
execute chaque tache. Puisque chaque hote a des variables pour son propre domaine,
cela signifie que seules les ressources d'un domaine sont creees. Retirer `run_once`
permet a chaque hote de creer les ressources de son domaine, avec l'idempotence
garantie par le patron de reconciliation (verifier si existe -> ignorer).

**Pourquoi pas `delegate_to`** : Puisque TOUTES les taches s'executent localement
(pas juste certaines), `connection: local` est plus propre que `delegate_to: localhost`
sur chaque tache. La documentation Ansible recommande `connection: local` lorsque
le play entier cible une API locale.

**Concurrence** : Avec `forks > 1`, deux hotes du meme domaine pourraient
tenter de creer le meme projet simultanement. Le patron de reconciliation
gere cela gracieusement (le second hote voit que la ressource existe deja).
Pour une execution strictement sequentielle, `serial: 1` peut etre active.

---

## ADR-016 : Disposition standard des repertoires Ansible avec le playbook a la racine

**Contexte** : Le plugin `host_group_vars` d'Ansible charge les fichiers de variables
depuis des chemins relatifs au fichier du playbook ou a la source d'inventaire. Avec le
playbook dans `playbooks/site.yml`, Ansible cherchait dans `playbooks/group_vars/`
au lieu du `group_vars/` reel a la racine du projet, rendant toutes les variables
generees par le PSOT indefinies.

**Decision** : Adopter la disposition standard des repertoires Ansible avec `site.yml`
a la racine du projet, aux cotes de `group_vars/`, `host_vars/`, `inventory/`,
et `roles/`.

**Reference** : https://docs.ansible.com/ansible/2.9/user_guide/playbooks_best_practices.html#directory-layout

**Consequence** : La resolution des variables fonctionne correctement par defaut.
La disposition correspond a ce que les utilisateurs Ansible attendent d'un projet standard.

---

## ADR-017 : Abstraction du type d'instance -- LXC maintenant, pret pour les VMs plus tard

**Contexte :** Toutes les instances actuelles sont des containers LXC. Cependant, certains
cas d'usage necessitent des VMs KVM : isolation plus forte (GPU avec vfio-pci, charges
de travail non fiables), personnalisation complete du noyau, ou execution de systemes
non-Linux.

**Decision :** La variable `instance_type` (provenant d'infra.yml `type: lxc|vm`)
est presente dans host_vars mais le role `incus_instances` traite actuellement toutes
les instances comme des containers LXC. Le code DOIT rester conscient des VMs desormais :

1. **infra.yml supporte deja `type: lxc|vm`** -- pas de changement de schema necessaire
2. **Role incus_instances :** la commande `incus launch` doit passer `--vm`
   quand `instance_type == 'vm'`. C'est le SEUL changement necessaire pour la
   creation basique de VM. Toute la logique de reconciliation (surcharge de peripherique,
   config IP, attente de demarrage) fonctionne de maniere identique.
3. **Profils :** Les instances VM peuvent necessiter des profils par defaut differents
   (ex. `agent.nic.enp5s0.mode` pour la config reseau dans les VMs). C'est une
   preoccupation Phase 8+.
4. **GPU dans les VMs :** Necessite un passthrough vfio-pci + groupes IOMMU, ce qui est
   significativement plus complexe que le passthrough GPU LXC. Reporte a la Phase 9+.
5. **Plugin de connexion :** Les VMs utilisent `incus exec` tout comme les containers LXC,
   donc le plugin de connexion `community.general.incus` fonctionne pour les deux.

**Consequence :** Tout nouveau code dans incus_instances DOIT brancher sur
`instance_type` la ou le comportement differe entre LXC et VM. Aujourd'hui la
seule difference est le flag `--vm` sur `incus launch`. Les phases futures
ajouteront des profils, peripheriques et configuration de demarrage specifiques aux VMs.

**Ce qu'il ne faut PAS faire maintenant :** Ne pas ajouter de roles, profils ou
peripheriques specifiques aux VMs tant qu'il n'y a pas de cas d'usage concret.
Garder l'abstraction minimale.

---

## ADR-018 : Politique d'acces GPU -- exclusif par defaut, partage optionnel

**Contexte :** Le passthrough GPU dans les containers LXC expose le pilote GPU
du noyau hote au container, elargissant la surface d'attaque. Lier le meme GPU
a plusieurs containers simultanement introduit des risques :
- Pas d'isolation VRAM sur les GPUs grand public (pas de SR-IOV)
- L'etat partage du pilote pourrait causer des plantages
- Tout container avec acces GPU peut potentiellement lire la memoire GPU

**Decision :**
1. **Politique par defaut : `gpu_policy: exclusive`** -- le generateur PSOT
   valide qu'au plus UNE instance dans tous les domaines a un peripherique GPU.
   Si plusieurs instances declarent `gpu: true`, le generateur echoue avec un
   message clair.
2. **Surcharge optionnelle : `gpu_policy: shared`** -- defini dans `infra.yml`
   `global.gpu_policy: shared` pour permettre a plusieurs instances de partager
   le GPU. Le generateur emet un avertissement mais ne produit pas d'erreur.
3. **GPU dans les VMs :** Quand `instance_type: vm` a un acces GPU, il utilise
   le passthrough vfio-pci qui fournit une isolation au niveau materiel. La
   politique exclusive s'applique toujours par defaut (une seule VM peut posseder
   un peripherique PCI), mais le mode `shared` n'est pas pertinent pour les VMs
   (on ne peut pas partager un peripherique PCI entre VMs sans SR-IOV).

**Regles de validation pour le generateur PSOT (scripts/generate.py) :**
- Compter les instances avec `gpu: true` ou avec un profil contenant un peripherique `gpu`
- Si compte > 1 et `global.gpu_policy` != `shared` -> erreur
- Si compte > 1 et `global.gpu_policy` == `shared` -> avertissement
- Si une instance VM a `gpu: true` -> valider que l'hote a IOMMU active (Phase 9+)

**Consequence :** Sur par defaut. Les utilisateurs qui savent ce qu'ils font peuvent
opter explicitement pour l'acces GPU partage.

---

## ADR-019 : Resilience du socket proxy admin-ansible au demarrage

**Contexte :** Le container `admin-ansible` a un peripherique proxy Incus qui
mappe le socket Incus de l'hote (`/var/lib/incus/unix.socket`) vers
`/var/run/incus/unix.socket` dans le container. Lorsque le container est
redemarre, le repertoire `/var/run/` est ephemere (tmpfs) et le
sous-repertoire `/var/run/incus/` n'existe pas encore quand le peripherique
proxy tente de se lier, causant l'echec du demarrage du container avec :

```
Error: Failed to listen on /var/run/incus/unix.socket:
listen unix /var/run/incus/unix.socket: bind: no such file or directory
```

Le contournement actuel est manuel : retirer le peripherique proxy, demarrer le
container, creer le repertoire, re-ajouter le peripherique proxy. Cela doit etre
automatise.

**Decision :** Ajouter un service systemd oneshot dans le container `admin-ansible`
qui cree `/var/run/incus/` avant que le peripherique proxy ne demarre. Ce service
s'execute tot au demarrage (`Before=network.target`, `After=local-fs.target`).

Implementation dans le role `base_admin` (ou provisionnement pour admin-ansible) :

```ini
# /etc/systemd/system/incus-socket-dir.service
[Unit]
Description=Create Incus socket directory for proxy device
DefaultDependencies=no
Before=network.target
After=local-fs.target

[Service]
Type=oneshot
ExecStart=/bin/mkdir -p /var/run/incus
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
```

**Pourquoi pas `raw.lxc` :** Le hook `lxc.hook.pre-start` s'execute sur l'HOTE,
pas dans le container. Bien qu'il puisse creer le repertoire dans le rootfs du
container, il necessite de connaitre le chemin du rootfs et s'execute en root
sur l'hote -- ce qui entre en conflit avec notre principe que Ansible ne modifie
pas l'hote (ADR-004). Un service systemd dans le container est autonome et portable.

**Portee :** Cette correction s'applique UNIQUEMENT a `admin-ansible`. Les autres
containers n'ont pas le peripherique proxy et ne sont pas affectes.

**Consequence :** `admin-ansible` survit aux redemarrages sans intervention manuelle.
Le service systemd est idempotent (mkdir -p).
