# Journal des Decisions

> Traduction francaise de [`decisions-log.md`](decisions-log.md). En cas de divergence, la version anglaise fait foi.

Decisions d'implementation autonomes prises durant les Phases 7+.
Lisez ce fichier pour comprendre les choix faits sans revue humaine.

Pour les decisions au niveau de l'architecture, voir [ARCHITECTURE.md](ARCHITECTURE.md)
(ADR-001 a ADR-019).

---

## Phase 7 : Documentation + Publication

### D-001 : Structure du repertoire des exemples

**Probleme** : Le ROADMAP liste les exemples comme des fichiers plats
(`examples/student-sysadmin.infra.yml`) mais dit aussi "chaque exemple accompagne
d'un README". Des fichiers plats + README seraient desordres.

**Decision** : Utiliser des sous-repertoires par exemple :
```
examples/
+-- README.md                    # Vue d'ensemble de tous les exemples
+-- student-sysadmin/
|   +-- infra.yml
|   +-- README.md
+-- teacher-lab/
|   +-- infra.yml
|   +-- README.md
...
```

**Justification** : KISS -- un repertoire = un cas d'usage autonome. Compatible git.

### D-002 : Tous les fichiers infra.yml d'exemples doivent passer la validation PSOT

**Probleme** : Les exemples sont de la documentation mais aussi executables. Des
exemples morts sont pires que pas d'exemples.

**Decision** : Ajouter un test pytest qui valide chaque `examples/*/infra.yml` contre
la fonction `validate()` de `scripts/generate.py`. Cela garantit que les exemples
restent valides a mesure que le generateur evolue.

**Justification** : TDD -- si les exemples cassent, les tests le detectent.

### D-003 : Violations ansible-lint preexistantes

**Probleme** : `make lint` echoue a cause de violations preexistantes dans
ollama_server, open_webui et incus_snapshots (command-instead-of-module,
risky-shell-pipe, var-naming[read-only]). Ce ne sont pas des problemes de la Phase 7.

**Decision** : Les noter mais ne pas les corriger dans la branche Phase 7. La Phase 7
se concentre sur la documentation/les exemples. Les violations de lint sont suivies
pour une passe de correction future.

### D-004 : Synchronisation de README_FR.md

**Probleme** : L'ADR-011 exige que la traduction francaise soit synchronisee.
La Phase 7 ajoute une documentation significative.

**Decision** : Mettre a jour README_FR.md pour correspondre aux modifications de
README.md. Les nouveaux documents (quickstart, lab-tp, gpu-llm) sont en anglais
uniquement selon l'ADR-011 -- pas de fichiers de traduction francaise separes pour
les guides (README_FR.md couvre uniquement le README principal).

### D-005 : Nombre de lignes de documentation vs regle des 200 lignes

**Probleme** : CLAUDE.md stipule "Pas de fichier de plus de 200 lignes" (KISS).
Le guide gpu-llm.md fait 275 lignes. Mais les documents existants du projet
depassent deja cela : SPEC.md (337), ARCHITECTURE.md (352), ROADMAP.md (777).

**Decision** : La regle des 200 lignes s'applique aux fichiers de code (roles,
scripts, playbooks). Les fichiers de documentation en sont exemptes lorsque le
contenu est coherent et qu'un decoupage nuirait a la lisibilite. gpu-llm.md
couvre un seul sujet (configuration GPU+LLM) et le decouper creerait une charge
de navigation inutile.

**Justification** : KISS s'applique a la complexite, pas au nombre brut de lignes
pour de la prose.

### D-006 : Patron .gitignore pour infra.yml dans les exemples

**Probleme** : `.gitignore` avait `infra.yml` comme patron global, ce qui ignorait
aussi `examples/*/infra.yml`. Les fichiers infra des exemples doivent etre commites.

**Decision** : Changer les patrons de `.gitignore` de globaux a ancres a la racine :
`infra.yml` -> `/infra.yml`, `inventory/` -> `/inventory/`, etc. Cela ignore les
fichiers specifiques a l'utilisateur a la racine mais autorise les fichiers d'exemples
dans les sous-repertoires.

**Justification** : Les patrons ancres git (`/patron`) ne correspondent qu'a la racine
du depot. Pas besoin de negation `!` ou de contournements avec force-add.

---

## Phase 8 : Isolation nftables Inter-Bridges

### D-007 : nftables priorite -1 (coexistence avec les chaines Incus)

**Contexte** : Incus gere ses propres chaines nftables a la priorite 0 pour le NAT
et le filtrage par bridge. Nous avons besoin de regles d'isolation qui s'executent
avant les chaines Incus sans les desactiver ni entrer en conflit.

**Decision** : Utiliser `priority -1` dans la chaine forward de la table `inet anklume`
d'AnKLuMe. Cela garantit que nos regles d'isolation sont evaluees avant les chaines
Incus. Nous ne desactivons PAS le pare-feu Incus (`security.ipv4_firewall`)
car les chaines Incus fournissent des regles NAT et DHCP par bridge utiles.

**Consequence** : AnKLuMe et les nftables d'Incus coexistent pacifiquement. Le trafic
non correspondant tombe dans les chaines Incus avec `policy accept`.

### D-008 : Deploiement en deux etapes (generation dans admin, deploiement sur l'hote)

**Contexte** : AnKLuMe s'execute dans le container admin (ADR-004 : Ansible ne
modifie pas l'hote). Cependant, les regles nftables doivent etre appliquees sur
le noyau de l'hote, pas dans un container.

**Decision** : Decouper en deux etapes :
1. `make nftables` -- s'execute dans le container admin, genere les regles vers
   `/opt/anklume/nftables-isolation.nft`
2. `make nftables-deploy` -- execute `scripts/deploy-nftables.sh` sur l'hote,
   recupere les regles depuis le container admin via `incus file pull`,
   valide la syntaxe, installe dans `/etc/nftables.d/`, et applique

**Consequence** : L'operateur peut examiner les regles generees avant le deploiement.
Le container admin n'a jamais besoin de privileges au niveau de l'hote. C'est une
exception documentee a l'ADR-004.

### D-009 : Gestion du trafic intra-bridge avec br_netfilter

**Contexte** : Lorsque `br_netfilter` est charge (requis pour que nftables voie
le trafic des bridges), le trafic intra-bridge (meme bridge, differents ports)
passe aussi par la chaine `forward`. Sans regles d'acceptation explicites,
le trafic intra-bridge entre containers du meme domaine serait rejete par
la regle de rejet inter-bridges.

**Decision** : Ajouter des regles d'acceptation explicites intra-bridge pour chaque
bridge AnKLuMe avant la regle de rejet inter-bridges :
```nft
iifname "net-admin" oifname "net-admin" accept
iifname "net-perso" oifname "net-perso" accept
...
```

**Consequence** : Les containers au sein du meme domaine peuvent communiquer librement.
Les regles sont generees dynamiquement a partir de la liste des bridges decouverts.

### D-010 : Patrons .gitignore ancres a la racine

**Contexte** : Les fichiers generes (comme les regles nftables) ne doivent pas etre
commites dans le depot. Le fichier `.gitignore` utilise des patrons ancres a la
racine (ex. `/opt/`) pour eviter d'ignorer accidentellement des fichiers dans des
sous-repertoires portant des noms similaires.

**Decision** : Utiliser des patrons ancres a la racine dans `.gitignore` dans la
mesure du possible. Pour les artefacts generes comme les regles nftables, le chemin
de sortie (`/opt/anklume/`) est dans le systeme de fichiers du container et n'apparait
pas dans le depot, donc aucune entree `.gitignore` n'est necessaire.

**Consequence** : Statut git propre. Aucun artefact genere ne fuit dans le depot.

---

## Phase 9 : Support des VMs (Instances KVM)

### D-011 : Timeouts d'attente separes pour VM vs LXC

**Contexte** : Le role `incus_instances` avait une seule boucle d'attente
(30 tentatives x 2s = 60s) pour tous les types d'instance. Les VMs mettent
10-30 secondes pour le demarrage UEFI+noyau, tandis que les containers LXC
demarrent en <2 secondes.

**Decision** : Decouper l'attente en taches specifiques au type avec des
valeurs par defaut configurables : LXC garde 30x2s=60s, les VMs obtiennent
60x2s=120s. Les variables sont prefixees par le role (`incus_instances_vm_retries`,
etc.) selon les conventions du projet.

**Consequence** : Les VMs ont un temps de demarrage adequat sans ralentir les
deploiements LXC.

### D-012 : Attente de l'incus-agent comme tache separee

**Contexte** : Apres qu'une VM atteint le statut "Running", l'`incus-agent`
dans le systeme invite a encore besoin de secondes pour s'initialiser. Sans
l'agent, `incus exec` et le plugin de connexion `community.general.incus`
echouent, cassant la phase de provisionnement.

**Decision** : Ajouter une tache dediee "attente de l'incus-agent" qui
interroge `incus exec <vm> -- true` avec `failed_when: false` + boucle `until`.
S'execute uniquement pour les VMs (`when: instance_type == 'vm'`).

**Consequence** : La phase de provisionnement se connecte de maniere fiable aux VMs.
Pas d'impact sur le flux de travail des containers LXC.

### D-013 : Validation du type d'instance sans application de ressources minimales

**Contexte** : Le ROADMAP mentionne "Contraintes VM (memoire minimale, CPU minimal)"
mais les valeurs par defaut d'Incus (1 vCPU, 1 Gio) fonctionnent pour la plupart
des systemes Linux legers. Imposer des minimums dans le generateur ajouterait de
la complexite pour un benefice marginal.

**Decision** : Valider que `type` est `lxc` ou `vm` (erreur sur les valeurs
invalides). NE PAS imposer de ressources minimales -- les valeurs par defaut
d'Incus sont adequates et les utilisateurs peuvent surcharger via `config:`
dans infra.yml.

**Justification** : KISS -- le generateur valide la structure, pas la politique.
Les recommandations de ressources appartiennent a la documentation (`docs/vm-support.md`),
pas au code.

### D-014 : Exemple VM dans sandbox-isolation

**Contexte** : Besoin d'un exemple pratique montrant la coexistence VM+LXC.
L'exemple sandbox-isolation est le choix naturel puisque les VMs fournissent une
isolation plus forte pour les charges de travail non fiables.

**Decision** : Ajouter `sbx-vm` (type: vm, 2 vCPU, 2 Gio) aux cotes de l'existant
`sbx-test` (type: lxc) dans l'exemple sandbox-isolation. README mis a jour avec les
exigences materielles et la comparaison d'isolation.

---

## Phase 10 : Gestion Avancee du GPU

### D-015 : Validation de la politique GPU dans le generateur (ADR-018)

**Contexte** : L'ADR-018 specifie une politique GPU exclusive/partagee mais la
validation n'etait pas implementee dans le generateur.

**Decision** : Implementer l'application de la politique GPU dans `validate()` :
- Compter les instances GPU via le flag `gpu: true` ET la detection de peripheriques de profil
- `exclusive` (defaut) : erreur si >1 instance GPU
- `shared` : pas d'erreur, mais `get_warnings()` emet un avertissement
- Une valeur `gpu_policy` invalide declenche une erreur de validation

La detection de peripheriques de profil scanne les profils au niveau du domaine
references par la machine pour trouver tout peripherique avec `type: gpu`. Cela
capture l'acces GPU direct (`gpu: true`) et indirect (via profil).

### D-016 : get_warnings() comme fonction separee

**Contexte** : Les avertissements (non fatals) ne doivent pas bloquer `make sync`
mais doivent etre visibles pour l'utilisateur. Changer le type de retour de
`validate()` casserait la compatibilite descendante avec les tests existants.

**Decision** : Ajouter `get_warnings(infra)` comme fonction separee qui retourne
une liste de chaines d'avertissement. Appelee dans `main()` apres que la validation
passe. Les avertissements sont affiches sur stderr avec le prefixe `WARNING:`.

**Justification** : DRY -- la logique de scan des instances GPU est dupliquee entre
`validate()` et `get_warnings()` mais elles servent des objectifs differents
(erreurs vs avertissements). KISS l'emporte sur DRY ici puisque l'alternative
(tuple de retour partage) changerait l'API.

### D-017 : GPU VM documente mais pas applique

**Contexte** : Le ROADMAP mentionne le GPU dans les VMs via vfio-pci. Cependant,
vfio-pci necessite une configuration IOMMU au niveau de l'hote qu'AnKLuMe ne peut
pas valider depuis l'interieur du container admin.

**Decision** : Documenter la configuration GPU VM dans `docs/gpu-advanced.md` mais
ne pas ajouter de validation a l'execution pour IOMMU. Le generateur applique la
politique exclusive quel que soit le type d'instance. Les profils GPU VM utilisent
la syntaxe de peripherique `pci:` documentee par Incus upstream.

**Justification** : KISS -- la detection IOMMU est une preoccupation de l'hote, pas
une preoccupation d'infra.yml. L'ADR-004 (pas d'hyperviseur dans l'inventaire)
signifie que nous ne pouvons pas verifier IOMMU depuis le container admin.

---

## Phase 11 : VM Pare-feu Dediee

### D-018 : Architecture a deux roles pour la VM pare-feu

**Contexte** : La VM pare-feu necessite a la fois une configuration d'infrastructure
(profil multi-NIC) et un provisionnement (nftables dans la VM). Ceux-ci s'executent
dans des phases de playbook differentes avec des types de connexion differents.

**Decision** : Decouper en deux roles :
- `incus_firewall_vm` : Role d'infrastructure (connection: local). Decouvre les
  bridges, cree un profil `firewall-multi-nic` avec une carte reseau par bridge
  de domaine, attache a la VM sys-firewall.
- `firewall_router` : Role de provisionnement (connection: community.general.incus).
  S'execute dans la VM : active le forwarding IP, installe nftables, deploie les
  regles d'isolation via un template Jinja2.

**Justification** : Correspond a l'architecture en deux phases (ADR-006). L'infrastructure
cree la topologie, le provisionnement configure l'interieur de la VM.

### D-019 : Le bridge admin toujours en eth0

**Contexte** : La VM pare-feu a besoin d'une carte reseau par bridge de domaine.
Le bridge admin doit etre previsible pour les regles nftables.

**Decision** : Le role `incus_firewall_vm` trie les bridges avec `net-admin`
toujours en premier (eth0). Les autres bridges sont tries alphabetiquement et
assignes eth1, eth2, etc. Le template nftables utilise cet ordonnancement pour
identifier l'interface admin.

**Consequence** : Les regles de pare-feu peuvent referencer `eth0` comme l'interface
admin sans configuration. L'ajout de nouveaux domaines ajoute automatiquement de
nouvelles cartes reseau.

### D-020 : Validation de firewall_mode dans le generateur PSOT

**Contexte** : infra.yml supporte `global.firewall_mode: host|vm`. Les valeurs
invalides doivent etre detectees tot par `make sync`, pas au moment du deploiement.

**Decision** : Ajouter la validation de `firewall_mode` a `validate()` dans
generate.py. Valeurs valides : `host` (defaut) et `vm`. Les valeurs invalides
produisent une erreur de validation. Le generateur n'impose pas qu'une machine
`sys-firewall` existe quand le mode `vm` est defini -- c'est la responsabilite
de l'operateur.

**Justification** : KISS -- le generateur valide les valeurs, pas la topologie de
deploiement. Verifier l'existence de sys-firewall couplerait le generateur aux
preoccupations au niveau des roles.

### D-021 : Defense en profondeur -- les modes hote + VM peuvent coexister

**Contexte** : La Phase 8 fournit une isolation nftables au niveau de l'hote.
La Phase 11 ajoute un routage de pare-feu au niveau VM. Doivent-ils etre
mutuellement exclusifs ?

**Decision** : Les deux modes peuvent coexister pour une securite en couches. Les
nftables de l'hote bloquent le forwarding direct bridge-a-bridge. La VM pare-feu
route le trafic autorise et journalise les decisions. Meme si la VM pare-feu est
compromise, les regles de l'hote empechent toujours le trafic direct inter-bridges.

**Consequence** : Documente dans `docs/firewall-vm.md`. L'operateur peut choisir
hote seul, VM seule, ou les deux. Aucun code n'impose l'exclusivite.

---

## Phase 13 : Tests et Developpement Assistes par LLM

### D-022 : Orchestrateur en script shell (pas de framework Python)

**Contexte** : Le systeme de tests assistes par IA doit orchestrer l'execution
des tests, les requetes LLM et l'application des corrections. Pourrait etre
implemente comme un framework Python, un role Ansible ou des scripts shell.

**Decision** : Utiliser des scripts Bash simples (`ai-test-loop.sh`, `ai-develop.sh`)
avec un assistant de configuration partage (`ai-config.sh`). L'orchestrateur charge
l'assistant de configuration et dispatch vers des fonctions specifiques au backend.

**Justification** : KISS -- les scripts shell sont le choix naturel pour orchestrer
des outils CLI (molecule, claude, aider, curl). Pas de nouvelles dependances Python.
Correspond au patron existant (`run-tests.sh`, `deploy-nftables.sh`).

### D-023 : Valeurs par defaut securitaires (dry_run=true, auto_pr=false)

**Contexte** : Les modifications de code generees par IA comportent des risques.
Le systeme doit etre sur a executer sans effets secondaires inattendus.

**Decision** : Privileger la securite maximale par defaut :
- `dry_run=true` : le LLM propose les corrections, l'humain examine et applique
- `auto_pr=false` : l'humain cree la PR manuellement
- Tentatives max : 3 (empeche les boucles infinies)
- Journalisation complete des sessions (toujours activee)

**Consequence** : Les utilisateurs doivent explicitement opter pour les operations
destructives. Confiance progressive : dry_run -> no-dry-run -> auto_pr.

### D-024 : Variables d'environnement plutot que fichier de configuration

**Contexte** : Le ROADMAP specifie a la fois `anklume.conf.yml` et des variables
d'environnement pour la configuration. Besoin de regles de precedence claires.

**Decision** : Les variables d'environnement ont priorite sur les valeurs du
fichier de configuration, qui ont priorite sur les valeurs par defaut. Le fichier
de configuration est optionnel (`anklume.conf.yml`), parse avec un one-liner Python
utilisant PyYAML (deja une dependance du projet). Le fichier de configuration est
gitignore car il peut contenir des cles API.

**Justification** : Les variables d'environnement fonctionnent partout (CI, containers,
scripts). Le fichier de configuration est une commodite pour le developpement local.

### D-025 : Strategies de correction specifiques au backend

**Contexte** : Les differents backends IA ont des capacites differentes. Ollama
et l'API Claude retournent du texte (patchs), tandis que Claude Code et Aider
operent directement sur les fichiers.

**Decision** : Deux strategies de correction :
- **Basee sur les patchs** (Ollama, Claude API) : le LLM retourne un diff unifie,
  le script l'applique avec `patch -p1`
- **Modification directe** (Claude Code, Aider) : l'outil CLI modifie les fichiers
  directement, le script invoque simplement l'outil avec le bon contexte

**Consequence** : Claude Code et Aider sont plus capables (peuvent parcourir les
fichiers, mieux comprendre le contexte) mais necessitent leur CLI installe.
Le mode Ollama/API fonctionne avec juste `curl`.

---

## Phase 14 : Service de Reconnaissance Vocale (STT)

### D-026 : Speaches plutot que faster-whisper brut

**Contexte** : Besoin d'un serveur API pour le STT. Options : bibliotheque Python
faster-whisper brute, faster-whisper-server, Speaches, OWhisper.

**Decision** : Utiliser Speaches (anciennement faster-whisper-server) comme couche
API. Il fournit un point d'acces `/v1/audio/transcriptions` compatible OpenAI
qu'Open WebUI consomme directement. Un seul pip install, pas de Docker ni
d'orchestration complexe necessaire.

**Justification** : KISS -- un seul `pip install speaches` donne a la fois
faster-whisper et le serveur API. La compatibilite OpenAI signifie pas de code
d'integration personnalise pour Open WebUI.

### D-027 : Mode GPU partage requis pour STT + Ollama

**Contexte** : Le STT et Ollama ont tous deux besoin d'un acces GPU pour des
performances acceptables. Ils fonctionnent dans des containers separes.

**Decision** : Documenter que `gpu_policy: shared` est requis lorsque les
containers STT et Ollama ont tous deux acces au GPU. Le generateur valide
deja cela (Phase 10, ADR-018). Recommander la quantification `int8_float16`
pour le STT afin de reduire la pression VRAM.

**Consequence** : Les utilisateurs optent explicitement pour le GPU partage.
La competition VRAM est un compromis connu documente dans `docs/stt-service.md`.

### D-028 : Modele telecharge a la premiere requete

**Contexte** : Les modeles Whisper sont volumineux (1-6 Go). Les pre-telecharger
pendant le provisionnement ralentirait le deploiement et pourrait echouer sur les
reseaux lents.

**Decision** : Laisser Speaches telecharger le modele a la premiere requete de
transcription (son comportement par defaut). Le service demarre immediatement et
telecharge de maniere asynchrone. Cela correspond au comportement d'Ollama avec
`ollama pull`.

**Justification** : KISS -- pas de tache de telechargement personnalisee dans le
role Ansible. Le modele est mis en cache apres le premier telechargement.

---

## Phase 15 : Claude Code Agent Teams

### D-029 : Architecture bac a sable d'abord

**Contexte** : Les Agent Teams avec `--dangerously-skip-permissions` et le mode
`bypassPermissions` donnent a Claude Code un acces complet au systeme. C'est
dangereux sur une machine de production mais sur dans un bac a sable
Incus-in-Incus qui ne peut pas atteindre les ressources de production.

**Decision** : Les Agent Teams s'executent UNIQUEMENT dans le container bac a sable
Phase 12. Les scripts `agent-fix.sh` et `agent-develop.sh` verifient que le container
runner existe et injectent la cle API a l'execution. Le role `dev_agent_runner`
configure le bac a sable avec les permissions appropriees et les hooks d'audit.

**Justification** : Defense en profondeur -- isolation au niveau OS (Incus) +
permissions au niveau application (Claude Code) + portes au niveau flux de travail
(fusion PR) + journalisation d'audit (hook PreToolUse).

### D-030 : Scripts separes de la Phase 13

**Contexte** : La Phase 13 a `ai-test-loop.sh` et `ai-develop.sh` pour des flux
de travail IA legers. La Phase 15 utilise Claude Code Agent Teams pour une
orchestration multi-agents complete.

**Decision** : Garder les scripts des Phases 13 et 15 separes. Les scripts
Phase 13 s'executent localement avec des backends enfichables (Ollama, API, CLI).
Les scripts Phase 15 necessitent un bac a sable Incus-in-Incus + CLI Claude Code
+ cle API. Differents niveaux de complexite pour differents cas d'usage.

**Consequence** : Les utilisateurs choisissent le bon outil pour la tache. Phase 13
pour les corrections rapides (cout faible), Phase 15 pour le developpement complexe
(cout superieur, capacite superieure).

### D-031 : Hook d'audit PreToolUse pour la responsabilite

**Contexte** : Les Agent Teams peuvent executer de nombreux outils de maniere
autonome. Pour un audit a posteriori, chaque invocation d'outil doit etre journalisee.

**Decision** : Deployer `agent-audit-hook.sh` comme hook PreToolUse dans le container
runner. Il journalise chaque appel d'outil (nom, arguments, horodatage) dans un
fichier JSONL dans `logs/`. Le hook est optionnel mais active par defaut.

**Justification** : Responsabilite -- trace complete de ce que les agents ont fait.
Le format JSONL permet un filtrage et une analyse faciles.

---
