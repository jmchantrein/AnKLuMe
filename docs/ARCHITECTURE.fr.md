# ARCHITECTURE.md -- Registre des Decisions d'Architecture

> Note : la version anglaise ([`ARCHITECTURE.md`](ARCHITECTURE.md)) fait reference en cas de divergence.

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

**Consequence** : Pour ajouter une machine, editer `infra.yml` + `anklume sync`. Pour
personnaliser davantage, editer les fichiers generes en dehors des sections gerees.

---

## ADR-003 : Tags Ansible pour le ciblage, pas d'extra-vars

**Contexte** : Une iteration precedente utilisait `-e target_domains=[...]`.

**Decision** : Utiliser les mecanismes Ansible standards : `--tags` pour les types
de ressources, `--limit` pour les domaines. Combinables.

**Consequence** : Pas de logique de filtrage personnalisee dans les playbooks.

---

## ADR-004 : Minimiser les modifications de l'hote

**Contexte** : L'hote fait tourner Incus mais doit rester aussi intact que
possible. La regle originale ("ne jamais modifier l'hote") s'est averee trop
stricte en pratique : les regles nftables doivent etre appliquees sur le noyau
de l'hote, et certains prerequis logiciels doivent etre installes directement.

**Decision** : L'hote n'est pas dans l'inventaire Ansible. Ansible s'execute
dans `anklume-instance` avec le socket Incus monte. Les modifications de
l'hote doivent etre evitees autant que possible. Quand c'est necessaire
(nftables, prerequis logiciels), elles sont faites directement si c'est
plus KISS/DRY et ne compromet pas la securite globale.

**Consequence** : L'hote n'est pas gere par Ansible mais peut recevoir des
modifications ciblees manuelles ou scriptees quand les contraintes d'isolation
l'exigent (ex. `anklume network deploy`).

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

## ADR-008 : Noms de machine globalement uniques

**Decision** : Les noms de machine sont globalement uniques, pas seulement dans leur
domaine. Le generateur valide cette contrainte.

---

## ADR-009 : Developpement pilote par la documentation et les comportements

**Contexte** : Le code ecrit avant les specs et les tests tend a diverger de
l'intention. Les tests ecrits apres le code decrivent ce que le code fait, pas
ce qu'il devrait faire. Une matrice comportementale (anciennement ADR-033)
et des tests de style BDD fournissent a la fois un suivi de couverture et
une documentation vivante.

**Decision** : Le flux de travail de developpement suit un ordre strict :
1. Ecrire/mettre a jour la documentation et la specification
2. Ecrire les tests comportementaux (style Given/When/Then) decrivant
   le comportement attendu depuis la spec -- pas depuis le code existant
3. Implementer jusqu'a ce que les tests passent (Molecule pour les roles,
   pytest pour le generateur)
4. Valider (`anklume dev lint`)
5. Revue (agent de revue)
6. Commiter seulement quand tout passe

Les tests comportementaux servent de documentation vivante. Ils sont
organises dans une matrice comportementale (`tests/behavior_matrix.yml`)
avec trois niveaux de profondeur par capacite. Chaque cellule a un
identifiant unique (ex. `DL-001`). Les tests referencent leur cellule
de matrice via des commentaires `# Matrix: DL-001`.

Les tests bases sur les proprietes (Hypothesis, `tests/test_properties.py`)
completent les tests comportementaux pour les invariants du generateur :
idempotence, pas de doublons d'IPs, marqueurs managed presents, coherence
de la detection d'orphelins.

Quand on rattrape du code existant, les tests doivent etre ecrits depuis
les specs, pas retro-concus depuis l'implementation.

**Consequence** : Pas de code sans specification et test correspondants.
La couverture est mesurable et auditable via la matrice comportementale.

---

## ADR-010 : Generateur Python -- preferer la bibliotheque standard, autoriser les dependances de qualite

**Decision** : `scripts/generate.py` utilise PyYAML et la bibliotheque
standard Python comme fondation. Si une bibliotheque open-source/libre bien
maintenue evite de reinventer la roue, elle peut etre ajoutee. Pas de
frameworks lourds ni de moteurs de templates externes. Le seuil pour
ajouter une dependance : elle doit etre activement maintenue, resoudre un
vrai probleme mieux que la stdlib, et ne pas introduire de dependances
transitives excessives.

---

## ADR-011 : Tout le contenu en anglais, traductions francaises maintenues

**Decision** : Tout le code, les commentaires, la documentation et les prompts sont
en anglais. Des traductions francaises (`*.fr.md`) sont maintenues pour tous les
fichiers de documentation, toujours synchronisees avec les versions anglaises. Cela
inclut `README_FR.md` et tous les fichiers dans `docs/` (ex. `quickstart.fr.md`,
`SPEC.fr.md`, `ARCHITECTURE.fr.md`, etc.). Chaque fichier francais inclut une note
d'en-tete indiquant que la version anglaise fait foi en cas de divergence.

---

## ADR-012 : Chaque type de fichier a un validateur dedie

**Contexte** : La qualite du code doit etre appliquee de maniere coherente sur tous
les types de fichiers.

**Decision** : Chaque type de fichier du projet a un validateur obligatoire.
`anklume dev lint` chaine tous les validateurs. Le CI doit tous les passer. Aucun fichier
n'echappe a la validation. Zero violation toleree.

Voir SPEC-operations.md Section 9 pour le tableau complet des validateurs.

**Consequence** : Les contributeurs doivent avoir tous les validateurs installes.
`anklume setup init` les installe.

---

## ADR-013 : Operations de snapshot -- script shell + role Ansible

**Contexte** : Le snapshot et la restauration sont des operations imperatives,
ponctuelles ("prendre un snapshot maintenant", "restaurer ce snapshot maintenant").
Elles ne suivent pas le patron de reconciliation declaratif
(lire/comparer/creer/mettre a jour/orphelins) que tous les roles d'infra utilisent.

**Decision** : Deux implementations complementaires :
- `scripts/snap.sh` : script Bash autonome pour les operations de snapshot ponctuelles.
  Interroge Incus directement, supporte le mot-cle `self`. Valide par `shellcheck`.
- Role Ansible `incus_snapshots` + playbook `snapshot.yml` : gestion declarative
  des snapshots invoquee via Makefile (`anklume snapshot create`, `anklume snapshot restore`, etc.).
  Supporte les operations par lot au niveau du domaine.

**Historique** : Le MVP original (snap.sh uniquement) a ete complete par le role
Ansible en Phase 4, qui fournit une meilleure integration avec l'infrastructure
de playbooks. `scripts/snap.sh` reste disponible pour l'utilisation CLI directe.

**Consequence** : Les cibles Makefile de snapshot utilisent le role Ansible
(`snapshot.yml`). `scripts/snap.sh` est un outil autonome pour l'utilisation
ponctuelle en dehors d'Ansible.

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
Ansible (`anklume-instance`) qui a le socket Incus monte. Les autres hotes de
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

**Decision :** Le code DOIT rester conscient des VMs desormais. La variable
`instance_type` (provenant d'infra.yml `type: lxc|vm`) pilote le comportement
des roles la ou LXC et VM different. Ne pas ajouter de roles, profils ou
peripheriques specifiques aux VMs tant qu'il n'y a pas de cas d'usage concret --
garder l'abstraction minimale.

Voir SPEC-operations.md Section 7 (role `incus_instances`) pour les details
d'implementation (flag --vm, differences de profils, passthrough GPU).

**Consequence :** Tout nouveau code dans incus_instances DOIT brancher sur
`instance_type` la ou le comportement differe entre LXC et VM.

---

## ADR-018 : Politique d'acces GPU -- exclusif par defaut, partage optionnel

**Contexte :** Le passthrough GPU dans les containers LXC expose le pilote GPU
du noyau hote au container, elargissant la surface d'attaque. Lier le meme GPU
a plusieurs containers simultanement introduit des risques :
- Pas d'isolation VRAM sur les GPUs grand public (pas de SR-IOV)
- L'etat partage du pilote pourrait causer des plantages
- Tout container avec acces GPU peut potentiellement lire la memoire GPU

**Decision :**
1. **Politique par defaut : `gpu_policy: exclusive`** -- au plus une instance GPU.
2. **Surcharge optionnelle : `gpu_policy: shared`** -- permet a plusieurs instances
   de partager le GPU avec un avertissement.
3. **GPU dans les VMs :** le passthrough vfio-pci fournit une isolation au niveau
   materiel. La politique exclusive s'applique toujours (une seule VM par
   peripherique PCI sans SR-IOV).

Voir SPEC.md Contraintes de validation pour les regles de validation du generateur.

**Consequence :** Sur par defaut. Les utilisateurs qui savent ce qu'ils font peuvent
opter explicitement pour l'acces GPU partage.

---

## ADR-019 : Resilience du socket proxy anklume-instance au demarrage

**Contexte :** Le peripherique proxy de `anklume-instance` mappe le socket
Incus de l'hote vers `/var/run/incus/unix.socket` dans le container. Au
redemarrage, `/var/run/` (tmpfs) est vide et le bind du proxy echoue.

**Decision :** Un service systemd oneshot cree `/var/run/incus/` tot dans
la sequence de demarrage, avant que le peripherique proxy ne demarre.

**Pourquoi pas `raw.lxc` :** `lxc.hook.pre-start` s'execute sur l'HOTE,
pas dans le container -- entre en conflit avec l'ADR-004. Un service systemd
dans le container est autonome et portable.

Voir SPEC-operations.md Section 12 pour le fichier d'unite systemd.

**Consequence :** `anklume-instance` survit aux redemarrages sans intervention
manuelle. S'applique uniquement a `anklume-instance`.

---

## ADR-020 : LXC privilegie interdit au premier niveau d'imbrication + contexte d'imbrication

**Contexte** : Les containers LXC avec `security.privileged: true` partagent
le noyau hote avec des capacites elevees. Chaque niveau d'imbrication a
aussi besoin de connaitre sa position dans la hierarchie pour la prise de
decision.

**Decision** : Au premier niveau d'imbrication (directement sous l'hote
physique ou sous un LXC non privilegie), `security.privileged=true` est
interdit pour les containers LXC. Seules les VMs fournissent une isolation
materielle suffisante (noyau separe, IOMMU) pour les charges de travail
privilegiees.

Le contexte d'imbrication est stocke sous forme de fichiers individuels
dans `/etc/anklume/` (crees par le **parent**, pas l'enfant). Des fichiers
individuels plutot qu'une configuration structuree car ils sont trivialement
lisibles depuis le shell, Ansible ou Python sans dependance de parsing.

Le flag `--YOLO` contourne les restrictions de securite (avertissements
au lieu d'erreurs) pour les contextes de TP/formation.

Voir SPEC.md section "Politique de securite" pour la liste complete des
fichiers, les formules de propagation et les regles de validation.

**Consequence** : Sur par defaut. Les containers privilegies ne sont autorises
que dans une frontiere d'isolation VM. Le contexte d'imbrication permet
de futures decisions tenant compte de la hierarchie. (Absorbe l'ancien
ADR-028.)

---

## ADR-021 : Politiques reseau -- communication inter-domaines declarative

**Contexte** : La Phase 8 bloque tout le trafic inter-domaines. Il n'y a
aucun mecanisme pour autoriser selectivement l'acces a des services
specifiques entre domaines (ex. services IA depuis plusieurs domaines).

**Decision** : Ajouter une section `network_policies:` a infra.yml -- une
liste plate de regles d'autorisation inspiree des Consul Intentions. Par
defaut : tout le trafic inter-domaines est DROP. Chaque regle ajoute un
`accept` avant le `drop`.

Voir SPEC.md "Politiques reseau" pour la syntaxe complete et les exemples.

**Consequence** : Active l'acces aux services inter-domaines tout en
maintenant l'isolation par defaut. Les regles sont generees a la fois
dans le nftables de l'hote (Phase 8) et le nftables de la firewall VM
(Phase 11). Auditable : la description de chaque regle apparait comme
commentaire nftables.

---

## ADR-022 : Priorite nftables -1 -- coexistence avec les chaines Incus

**Contexte** : Incus gere ses propres chaines nftables a la priorite 0 pour
le NAT et le filtrage par bridge. anklume a besoin de regles d'isolation qui
s'executent avant les chaines Incus sans les desactiver ni entrer en conflit.

**Decision** : Utiliser `priority -1` dans la chaine forward de la table
`inet anklume` d'anklume. anklume et Incus nftables coexistent paisiblement
dans des tables separees. Le trafic non-correspondant passe aux chaines
Incus avec `policy accept`.

**Consequence** : Aucune interference avec le NAT, DHCP ou les regles par
bridge d'Incus. L'isolation anklume est evaluee en premier.

---

## ADR-023 : Deploiement nftables en deux etapes (anklume -> hote)

**Contexte** : anklume s'execute dans le container anklume (ADR-004) mais
les regles nftables doivent etre appliquees sur le noyau de l'hote.

**Decision** : Decouper en deux etapes :
1. `anklume network rules` -- s'execute dans le container anklume, genere les regles
2. `anklume network deploy` -- s'execute sur l'hote, recupere les regles
   depuis anklume, valide et applique

**Consequence** : L'operateur revoit les regles avant de deployer. Le
container anklume n'a jamais besoin de privileges au niveau hote. Exception
documentee a l'ADR-004.

---

## ADR-024 : Firewall VM -- architecture a deux roles

**Contexte** : La firewall VM a besoin d'une configuration d'infrastructure
(profil multi-NIC sur l'hote) et d'un provisionnement (nftables dans la VM).
Ceux-ci s'executent dans differentes phases du playbook avec des types de
connexion differents.

**Decision** : Decouper en deux roles :
- `incus_firewall_vm` : Role d'infrastructure (connection: local). Cree le
  profil multi-NIC.
- `firewall_router` : Role de provisionnement (connection: incus). Configure
  le forwarding IP + nftables dans la VM.

**Consequence** : Correspond a l'architecture en deux phases (ADR-006).

---

## ADR-025 : Defense en profondeur -- les modes hote + firewall VM coexistent

**Contexte** : La Phase 8 fournit l'isolation nftables au niveau hote. La
Phase 11 ajoute une firewall VM. Doivent-ils etre mutuellement exclusifs ?

**Decision** : Les deux modes coexistent pour une securite en couches. Le
nftables de l'hote bloque le forwarding direct entre bridges. La firewall
VM route le trafic autorise et journalise les decisions. Meme si la
firewall VM est compromise, les regles hote empechent toujours le trafic
direct entre bridges.

**Consequence** : L'operateur peut choisir hote seul, VM seule, ou les deux.

---

## ADR-026 : Bridge anklume -- pas d'exception dans les regles nftables

**Contexte** : Le container anklume communique avec toutes les instances via
le socket Incus (ADR-004), pas via le reseau. Ansible utilise
`community.general.incus` qui appelle `incus exec` via le socket.

**Decision** : Le bridge anklume n'a pas de regle accept speciale dans
nftables. Tous les domaines (y compris anklume) sont traites de maniere
egale pour l'isolation reseau. `ping` depuis `anklume-instance` vers
d'autres domaines echoue (comportement attendu).

**Consequence** : Isolation plus forte. Le trafic de gestion admin passe
par le socket Incus (`incus exec`), qui est le chemin correct et prevu.
`anklume-instance` n'a pas besoin d'acces reseau pour gerer les autres
instances.

---

## ADR-029 : dev_test_runner en VM (pas en LXC)

**Contexte** : Tester anklume dans anklume necessitait des containers LXC
privilegies, en conflit avec l'ADR-020. L'imbrication triple causait des
problemes AppArmor sur Debian 13.

**Decision** : Le test runner (`anklume-test`) est une VM. Dans la VM,
anklume se bootstrap comme sur un hote vierge. Les tests s'executent
aux niveaux 1 et 2 dans le noyau de la VM -- pas d'interference AppArmor
depuis l'hote.

**Consequence** : Demarrage plus lent (~30s) mais isole materiellement.
Triple imbrication eliminee. L'environnement de test correspond
exactement a la production.

---

## ADR-030 : Support du repertoire infra/ aux cotes d'infra.yml

**Contexte** : Un seul `infra.yml` devient difficile a gerer pour les
grands deploiements (20+ domaines).

**Decision** : Le generateur accepte les deux formats avec auto-detection.
Voir SPEC.md "infra.yml en tant que repertoire" pour la disposition du
repertoire.

**Consequence** : Scalable pour les grands deploiements. Git-friendly.
100% retro-compatible.

---

## ADR-031 : Protection des donnees utilisateur pendant les mises a jour

**Contexte** : anklume est distribue comme un depot git. Les mises a jour
du framework ne doivent pas detruire la configuration utilisateur, les
roles personnalises ni les personnalisations des fichiers generes.

**Decision** : Protection multi-couches :
1. Classification explicite des fichiers : framework (ecrase), config
   utilisateur (jamais touche), genere (sections gerees), runtime (jamais
   touche)
2. Repertoire `roles_custom/` (gitignore) avec priorite dans `roles_path`
3. `anklume upgrade` avec detection de conflits et creation de `.bak`
4. Marqueur de version pour verification de compatibilite

**Consequence** : Les utilisateurs ne perdent jamais de donnees pendant
les mises a jour. Les roles personnalises et les configurations survivent
aux mises a jour du framework.

---

## ADR-032 : Acces reseau exclusif aux outils IA avec flush VRAM

**Contexte** : Plusieurs domaines pourraient acceder simultanement a
ai-tools, creant un risque de fuite de donnees inter-domaines via la
VRAM GPU. Les GPUs grand public n'ont pas de SR-IOV, donc la VRAM est
partagee entre tous les processus utilisant le GPU.

**Decision** : Ajouter un mode `ai_access_policy: exclusive` a infra.yml.
Quand active, un seul domaine a la fois peut acceder a ai-tools. Le
changement de domaine vide atomiquement la VRAM et met a jour les regles
nftables.

Voir SPEC.md Contraintes de validation pour les regles de validation du
generateur. Voir docs/ai-switch.md pour la procedure operationnelle de
basculement.

**Consequence** : Isolation VRAM appliquee au niveau operationnel. Fuite
de donnees inter-domaines via la memoire GPU empechee par le vidage entre
les changements de domaine.

---

## ADR-035 : Cache d'images partage entre niveaux d'imbrication

**Contexte** : Chaque daemon Incus (hote et imbrique) telecharge les
images OS independamment depuis internet. La VM dev_test_runner (Phase 12)
re-telecharge toutes les images, gaspillant bande passante et temps.

**Decision** : Pre-exporter les images depuis l'hote, monter en lecture
seule dans les VMs imbriquees, importer localement.

Pourquoi ne pas monter le systeme de fichiers hote directement : casse
l'isolation. Pourquoi ne pas utiliser l'hote comme remote Incus : necessite
reseau + TLS + configuration d'authentification.

Voir SPEC-operations.md Section 15 pour le flux complet.

**Consequence** : Pas d'acces internet necessaire pour les telechargements
d'images Incus imbriquees. Bootstrap de sandbox plus rapide. Le montage
en lecture seule preserve l'isolation.

---

## ADR-036 : Les connaissances operationnelles des agents doivent etre reproductibles par le framework

**Contexte** : Les agents OpenClaw s'executent dans des containers Incus.
Si le container est detruit, toutes les connaissances operationnelles sont
perdues a moins qu'elles proviennent du framework.

**Decision** : Le depot git anklume est la **seule source de verite** pour
les connaissances operationnelles des agents. Tous les fichiers agents
sont des templates Jinja2 deployes avec `force: true` a chaque
`anklume domain apply`. Les agents NE DOIVENT PAS modifier leurs fichiers
operationnels directement -- ils suivent le flux de travail de
developpement standard (editer le template, tester, PR, merger, appliquer).

Exception : `SOUL.md` (personnalite) appartient a l'agent et est
`.gitignore`.

Voir SPEC-operations.md pour la liste des fichiers templates et les regles
de deploiement.

**Consequence** : Tout agent peut etre entierement reproduit a partir du
framework seul (moins la personnalite). Detruire et reconstruire un
container restaure la pleine capacite operationnelle.

---

## ADR-040 : Reconnaitre les outils et dependances externes

**Contexte** : anklume est un framework d'assemblage (principe 9 : "pas de
roue reinventee"). Il orchestre de nombreux outils open-source externes
mais ne les credite pas toujours explicitement. Les utilisateurs et
contributeurs doivent savoir de quoi le framework depend et pouvoir
trouver la documentation de chaque outil.

**Decision** : Maintenir une section CREDITS dans README.md listant chaque
outil externe qu'anklume utilise, avec un lien vers chaque projet. La
liste est organisee par categorie (infrastructure, provisionnement,
IA/ML, qualite, developpement). Quand une nouvelle dependance est ajoutee
au framework, son entree doit etre ajoutee a la section CREDITS dans le
meme commit.

**Consequence** : Les contributeurs connaissent toujours le graphe complet
des dependances. Les projets externes recoivent une attribution appropriee.
Les utilisateurs peuvent verifier la compatibilite des licences. La section
CREDITS sert de reference rapide pour la pile technologique.

---

## ADR-039 : Volumes partages via bind mounts de l'hote

**Contexte** : Les utilisateurs ont besoin de partager des repertoires
entre machines de differents domaines (ex. documents partages, datasets
pour les outils IA). Les volumes de stockage personnalises Incus ne
peuvent pas couvrir plusieurs projets, donc le partage inter-projets
necessite un mecanisme different.

**Decision** : Utiliser des bind mounts de l'hote (peripheriques disque
Incus avec `source` pointant vers un repertoire hote) injectes par le
generateur dans les host_vars des consommateurs. Le generateur resout les
declarations `shared_volumes` dans `infra.yml` en peripheriques disque
`sv-<nom>` fusionnes avec les `instance_devices` de chaque consommateur.

**Pourquoi des bind mounts hote, pas des volumes personnalises Incus** :
Les volumes de stockage Incus appartiennent a un seul projet.
L'attachement inter-projets necessite des appels manuels
`incus storage volume attach` avec `--target-project`, ce qui est fragile
et mal documente. Les bind mounts hote fonctionnent nativement entre tous
les projets et sont l'approche recommandee pour les donnees partagees dans
la documentation Incus.

**Convention de nommage** : Les peripheriques injectes utilisent le prefixe
`sv-` pour eviter les collisions avec les peripheriques declares par
l'utilisateur. Le generateur valide qu'aucun peripherique utilisateur
n'utilise le prefixe `sv-`.

**Consequence** : Les volumes partages sont entierement declaratifs.
Ajouter un consommateur est un changement d'une ligne dans `infra.yml`.
Le role `incus_instances` existant gere les peripheriques de maniere
transparente -- pas de nouveau role necessaire.

---

## ADR-038 : Convention d'adressage IP par niveau de confiance

**Contexte** : Le schema d'adressage original (`10.100.<subnet_id>.0/24`
avec des subnet_ids sequentiels assignes manuellement) ne fournit aucune
information semantique. Un administrateur ne peut pas determiner la
posture de securite d'un domaine a partir de son adresse IP seule.
L'allocation manuelle est sujette aux erreurs et ne suit pas les bonnes
pratiques de segmentation reseau.

**Decision** : Encoder les zones de confiance dans le deuxieme octet IP :
`10.<zone_base + zone_offset>.<domain_seq>.<host>/24`. Le champ
`base_subnet` est remplace par `addressing`.

Voir SPEC.md "Convention d'adressage" pour le tableau complet des zones,
les reservations IP, le format de configuration et les regles de
validation. Voir docs/addressing-convention.md pour la documentation
complete.

**Pourquoi pas `11.x.x.x`** : `11.0.0.0/8` est un espace d'adresses
public (US DoD). Fuites DNS, fuites de paquets -- disqualifie le
framework.

**Pourquoi zone_base=100** : evite `10.0-60.x.x` utilise par les VPNs
d'entreprise, les routeurs domestiques et les orchestrateurs de
containers. `10.1xx` est un marqueur visuel pour le trafic anklume.

**Consequence** : Les adresses IP sont lisibles par l'humain. A partir de
`10.140.0.5`, un admin sait immediatement : zone 140 = 100+40 = untrusted.
