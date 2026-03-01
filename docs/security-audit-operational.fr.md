> La version anglaise fait foi en cas de divergence.

# Audit de securite -- Modele operationnel

**Date** : 2026-02-26
**Perimetre** : Architecture, frontieres de confiance, flux operationnels, modele d'isolation.
Il ne s'agit pas d'un audit au niveau du code (pas de revue ligne par ligne des implementations).
**Methodologie** : Revue documentaire (SPEC, ARCHITECTURE, ADR, documents operationnels)
croisee avec le modele de menaces declare.

---

## Resume executif

Le modele operationnel d'anklume est fondamentalement solide. L'architecture suit
les principes de defense en profondeur avec plusieurs couches d'isolation (namespaces
Incus, nftables, projets Incus, gestion par socket). Le schema d'adressage IP par
zone de confiance (ADR-038) et la separation du plan de controle (socket Incus) et
du plan de donnees (bridges reseau) sont des choix de conception robustes.

Cependant, plusieurs schemas architecturaux introduisent des risques allant de
**MEDIUM** a **CRITICAL** selon le contexte de deploiement. Les constats ci-dessous
sont classes par severite.

---

## FINDING-01 : Socket Incus = acces total (CRITICAL)

### Description

`anklume-instance` a le socket Incus de l'hote monte en lecture/ecriture. Ce socket
fournit un **acces root non authentifie et sans restriction** a l'ensemble du daemon
Incus. Tout processus a l'interieur d'`anklume-instance` capable d'ecrire sur
`/var/run/incus/unix.socket` peut :

- Creer/supprimer/modifier N'IMPORTE quel conteneur ou VM dans TOUS les projets
- Executer des commandes arbitraires en root dans N'IMPORTE quelle instance (`incus exec`)
- Lire/ecrire N'IMPORTE quel fichier dans N'IMPORTE quelle instance (`incus file`)
- Modifier la configuration reseau, les profils, le stockage
- Obtenir effectivement le root sur l'hote (via la creation d'un conteneur privilegie)

### Pourquoi c'est important

L'ensemble du modele de securite repose sur la fiabilite d'`anklume-instance`.
Si ce conteneur est compromis (role Ansible malveillant, attaque de chaine
d'approvisionnement sur une dependance pip, role Galaxy compromis depuis
`roles_vendor/`, ou une vulnerabilite dans le proxy OpenClaw), l'attaquant
contourne TOUTES les frontieres d'isolation instantanement.

### Facteurs de risque

- Le proxy OpenClaw (`docs/openclaw.md`) expose des endpoints API REST
  dont `/api/incus_exec` et `/api/incus_list` -- ce sont des surfaces
  d'attaque accessibles par le reseau, adossees au socket tout-puissant
- Claude Code s'execute avec `bypassPermissions` dans le lanceur d'agents,
  et le proxy transmet les commandes des messages Telegram vers l'infrastructure
- Les roles Galaxy (`roles_vendor/`) sont du code tiers s'executant a l'interieur
  du conteneur qui a acces au socket
- Les dependances `pip install` (PyYAML, libtmux, mcp, etc.) s'executent dans
  le meme domaine de confiance que le socket

### Recommandations

1. **Socket en LECTURE SEULE quand c'est possible** : pour les operations qui ne
   font que consulter l'etat (`incus list`, `incus info`), envisager un proxy en
   lecture seule ou des certificats TLS Incus a granularite fine avec une portee
   restreinte au projet. Incus supporte les certificats client confines a un
   projet depuis la v6.0.
2. **Separer le proxy** : deplacer le proxy OpenClaw hors d'`anklume-instance`
   dans son propre conteneur avec un certificat Incus a portee limitee (pas le
   socket brut). Le proxy n'a besoin que d'`incus exec` sur des instances
   specifiques.
3. **Segmentation reseau d'anklume-instance** : le modele actuel n'accorde aucune
   exception nftables speciale a anklume-instance (bien), mais le proxy OpenClaw
   cree un chemin reseau depuis internet (Telegram) vers le conteneur detenteur
   du socket. Envisager une revue dediee de la politique reseau pour ce chemin.
4. **Auditer les dependances pip** : epingler toutes les dependances pip avec des
   hash dans `requirements.txt` pour prevenir les attaques de chaine
   d'approvisionnement sur le conteneur qui detient la cle maitresse.

---

## FINDING-02 : Proxy OpenClaw -- Pont Internet-vers-Infrastructure (HIGH)

### Description

L'architecture `openclaw.md` cree un chemin direct :

```
Telegram (internet) → OpenClaw (projet ai-tools) → proxy (anklume-instance) → socket Incus → N'IMPORTE quel conteneur
```

Le proxy sur `anklume-instance:9090` accepte des appels API compatibles OpenAI et
les traduit en invocations CLI de Claude Code. Claude Code s'execute alors avec un
acces aux outils, incluant `incus exec` sur des conteneurs arbitraires. Le proxy
expose egalement des endpoints REST (`/api/incus_exec`, `/api/make_target`, etc.)
qui interagissent directement avec l'infrastructure.

### Pourquoi c'est important

- Un attaquant qui compromet le conteneur OpenClaw (qui a un acces internet
  et des passerelles de messagerie) peut envoyer des requetes forgees au proxy
- L'injection de prompts via des messages Telegram pourrait tromper Claude Code
  pour qu'il execute des commandes d'infrastructure destructrices
- La restriction `--allowedTools` sur Claude Code est un controle au niveau
  applicatif, pas une frontiere au niveau du noyau -- elle peut etre contournee
  par des sequences d'utilisation d'outils forgees
- La liste de blocage pour les operations dangereuses (`flush`, `nftables-deploy`)
  est une liste de refus, pas une liste d'autorisation -- les nouvelles commandes
  dangereuses ne seront pas bloquees

### Recommandations

1. **Inverser le modele de securite** : utiliser une liste d'autorisation (seules
   les operations connues comme sures) au lieu d'une liste de blocage pour les
   endpoints API du proxy
2. **Authentification sur le proxy** : le proxy sur `:9090` devrait exiger une
   authentification (cle API, TLS mutuel) meme pour les appels intra-reseau
3. **Limitation de debit et journalisation des requetes** : journaliser chaque
   appel `incus_exec` avec les arguments complets dans un journal en ajout seul
   situe hors du conteneur
4. **Envisager de retirer `incus_exec` du proxy** : si l'agent OpenClaw n'a
   besoin de gerer que son propre conteneur, limiter le proxy a ce seul conteneur
   plutot que d'exposer l'execution inter-conteneurs

---

## FINDING-03 : Montage de credentials avec permissions lisibles par tous (HIGH)

### Description

D'apres `docs/openclaw.md` :

> **Requirement** : The host credentials file must be world-readable
> (`chmod 644`) because Incus UID mapping maps the host user to
> `nobody:nogroup` inside the container.

Les credentials OAuth de Claude Code (`~/.claude/.credentials.json`) sont rendues
lisibles par tous sur l'hote pour permettre au conteneur de les lire a travers le
peripherique disque Incus avec decalage d'UID.

### Pourquoi c'est important

- N'importe quel processus sur l'hote peut lire ces credentials
- N'importe quel autre conteneur avec un peripherique disque pointant vers le
  repertoire personnel de l'utilisateur hote peut y acceder
- Les jetons OAuth pour le plan Anthropic Max donnent acces a l'API Claude
  avec le compte de facturation de l'utilisateur
- Le fichier de credentials peut contenir des jetons de rafraichissement accordant
  un acces de longue duree

### Recommandations

1. **Utiliser Incus idmap avec raw.idmap** : au lieu de permissions lisibles par
   tous, configurer `raw.idmap` sur le conteneur pour faire correspondre l'UID
   de l'hote a l'UID root du conteneur. Cela permet des permissions `0600` sur
   l'hote tandis que le root du conteneur peut toujours lire le fichier.
2. **Renouveler et limiter la portee des jetons** : si possible, utiliser une cle
   API a portee limitee plutot qu'un fichier de credentials OAuth pour le service
   proxy
3. **Monter les credentials en lecture seule avec un wrapper** : injecter le
   jeton via une variable d'environnement plutot qu'un montage de fichier

---

## FINDING-04 : Surface d'evasion des conteneurs LXC (MEDIUM)

### Description

Le type d'instance par defaut est LXC (conteneur), pas VM. Les conteneurs LXC
partagent le noyau de l'hote. Bien qu'Incus fournisse l'isolation par namespaces,
les filtres seccomp et les profils AppArmor, la surface d'attaque conteneur-vers-hote
au niveau du noyau est significativement plus grande que celle VM-vers-hote.

anklume impose certaines restrictions :
- `security.privileged: true` interdit sans imbrication VM (ADR-020)
- Le drapeau `--YOLO` est requis pour contourner cette restriction
- `security.nesting: true` est necessaire pour Incus imbrique (augmente la surface)

### Pourquoi c'est important

- Les vulnerabilites du noyau (CVE-2024-1086, CVE-2023-32233, etc.) peuvent etre
  exploitees depuis des conteneurs non privilegies pour obtenir le root de l'hote
- Les conteneurs avec `security.nesting: true` ont une surface d'appels systeme
  plus large
- Le passthrough GPU grand public (`type: gpu`) expose le pilote noyau NVIDIA
  (une surface d'attaque massive) directement au conteneur
- Les niveaux de confiance `untrusted` et `disposable` suggerent que ces conteneurs
  executent du code non fiable, mais ils utilisent LXC par defaut

### Recommandations

1. **Definir VM par defaut pour les niveaux untrusted/disposable** : la SPEC
   recommande deja les VM pour une isolation plus forte. Envisager de definir
   `type: vm` comme valeur par defaut quand `trust_level: untrusted` ou
   `trust_level: disposable`
2. **Documenter explicitement le modele de menaces LXC** : indiquer clairement
   dans le guide d'integration que l'isolation LXC est basee sur les namespaces,
   pas sur le materiel, et qu'une vulnerabilite du noyau brise toute la
   compartimentation
3. **Durcir le profil seccomp** : envisager d'appliquer un profil seccomp plus
   strict pour les conteneurs non fiables (Incus supporte les profils seccomp
   personnalises via `raw.seccomp`)
4. **Les conteneurs GPU sont a haut risque** : le module noyau NVIDIA est une
   source frequente de CVE. Documenter le fait que le passthrough GPU en LXC
   augmente significativement la surface d'attaque par rapport aux conteneurs
   sans GPU

---

## FINDING-05 : Le vidage VRAM est au mieux un effort, pas une garantie (MEDIUM)

### Description

Le mecanisme de commutation AI (`docs/ai-switch.md`) vide la VRAM du GPU entre
les changements de domaine pour prevenir les fuites de donnees inter-domaines.
Le processus de vidage :

1. Arrete les services GPU (ollama, speaches)
2. Tue les processus GPU de calcul restants via `nvidia-smi`
3. Tente `nvidia-smi --gpu-reset` (peut ne pas etre supporte)
4. Redemarre les services GPU

### Pourquoi c'est important

- `nvidia-smi --gpu-reset` n'est pas supporte sur tous les GPU (documente)
- Tuer les processus libere leurs allocations VRAM mais ne remet pas la memoire
  a zero -- le pilote GPU peut reutiliser les pages sans les effacer
- Il n'y a pas d'etape de verification que la VRAM a effectivement ete effacee
- L'option `--no-flush` permet de sauter entierement le vidage
- Les GPU grand public n'ont pas d'isolation materielle de la memoire (pas de
  SR-IOV, pas de MIG)

### Recommandations

1. **Ajouter une etape de verification** : apres le vidage, allouer un petit
   tampon CUDA et le lire pour verifier qu'il contient des zeros (pas de donnees
   residuelles). Cela ne garantira pas que toute la VRAM est propre mais fournit
   un test de base.
2. **Documenter clairement la limitation** : indiquer que le vidage VRAM est au
   mieux un effort et ne fournit pas de garanties cryptographiques contre
   l'analyse forensique de la memoire GPU
3. **Envisager CUDA memset** : utiliser un petit programme CUDA qui alloue et
   remet a zero toute la VRAM disponible avant que les services du nouveau
   domaine demarrent
4. **Avertir sur `--no-flush`** : le drapeau devrait etre journalise avec un
   avertissement de securite, pas accepte silencieusement

---

## FINDING-06 : L'isolation nftables depend de br_netfilter (MEDIUM)

### Description

D'apres `docs/network-isolation.md` :

> If `br_netfilter` is not loaded, bridge traffic bypasses nftables entirely.

L'ensemble du modele d'isolation reseau (regles DROP inter-domaines) depend du
module noyau `br_netfilter` charge et de `net.bridge.bridge-nf-call-iptables`
defini a 1.

### Pourquoi c'est important

- Si `br_netfilter` n'est pas charge (ce qui est le defaut sur de nombreuses
  distributions Linux), tout le trafic inter-domaines est silencieusement autorise
- Les regles nftables sembleront chargees (`nft list table inet anklume` les
  affiche) mais elles n'ont aucun effet -- un faux sentiment de securite
- Il n'y a pas de verification documentee dans `anklume domain apply` ou
  `anklume network deploy` qui verifie que `br_netfilter` est charge
- Une mise a jour du noyau ou une reconfiguration systeme pourrait decharger
  le module

### Recommandations

1. **Verification prealable obligatoire** : `anklume network deploy` et
   `bootstrap.sh` devraient verifier que `br_netfilter` est charge et que
   `bridge-nf-call-iptables=1`, en echouant avec une erreur claire si ce
   n'est pas le cas
2. **Persister le module** : ajouter `br_netfilter` a `/etc/modules-load.d/`
   et le parametre sysctl a `/etc/sysctl.d/` lors du bootstrap
3. **Surveillance en temps reel** : le monitoring heartbeat (Phase 38) devrait
   verifier periodiquement que `br_netfilter` est toujours charge
4. **Documenter cette dependance en evidence** : pas seulement dans le
   depannage -- dans la documentation principale du modele de securite

---

## FINDING-07 : Le deploiement nftables en deux etapes cree une fenetre temporelle (LOW-MEDIUM)

### Description

Les regles nftables sont generees a l'interieur du conteneur (`anklume network rules`)
puis deployees sur l'hote (`anklume network deploy`). Entre `anklume domain apply`
(qui cree de nouveaux domaines/bridges) et `anklume network rules && anklume network deploy`
(qui met a jour les regles d'isolation), il existe une fenetre ou les nouveaux bridges
existent sans regles d'isolation.

### Pourquoi c'est important

- Les nouveaux domaines crees par `anklume domain apply` sont immediatement
  joignables par le reseau depuis les autres domaines jusqu'a la mise a jour
  des regles nftables
- La documentation mentionne l'execution de `anklume network rules && anklume network deploy`
  apres l'ajout de domaines, mais c'est une etape manuelle
- La cible `anklume domain apply` ne regenere pas automatiquement les nftables

### Recommandations

1. **Integrer nftables dans le flux d'application** : `anklume domain apply` devrait
   automatiquement lancer `anklume network rules` apres les modifications d'infrastructure
2. **Refus par defaut sur les nouveaux bridges** : envisager une regle nftables
   permanente qui refuse tout le trafic inter-bridges pour les bridges correspondant
   a `net-*` qui ne sont pas explicitement autorises, plutot que d'enumerer les
   bridges connus
3. **Documenter la fenetre temporelle** : indiquer explicitement dans le modele
   de securite que les nouveaux domaines ne sont pas isoles tant que les nftables
   ne sont pas redeployees

---

## FINDING-08 : Les instances jetables utilisent le projet `default` par defaut (LOW-MEDIUM)

### Description

D'apres `docs/disposable.md` :

> Disposable instances run in the `default` project unless a `--domain` is specified.

### Pourquoi c'est important

- Le projet `default` d'Incus n'a pas de regles d'isolation nftables (seuls les
  bridges prefixes `net-*` sont isoles)
- Une instance jetable dans le projet par defaut partage le bridge par defaut
  avec le trafic de gestion d'Incus lui-meme
- Si un utilisateur lance `anklume instance disp` sans `DOMAIN=`, la charge de
  travail non fiable s'execute sans isolation de domaine
- Cela contredit le principe selon lequel les instances jetables sont destinees
  aux charges de travail non fiables

### Recommandations

1. **Definir un domaine jetable dedie par defaut** : creer un domaine `disposable`
   dans `infra.yml` et l'utiliser comme defaut pour `anklume instance disp`
2. **Avertir lors de l'utilisation du projet `default`** : afficher un avertissement
   quand aucun `--domain` n'est specifie, indiquant que l'instance n'a pas
   d'isolation reseau
3. **Documenter l'implication en matiere de securite** : le document `disposable.md`
   mentionne cela en passant mais devrait souligner l'impact sur la securite

---

## FINDING-09 : Roles Galaxy dans la frontiere de confiance (LOW-MEDIUM)

### Description

L'ADR-045 introduit des roles Galaxy installes dans `roles_vendor/` depuis
`requirements.yml`. Ces roles s'executent a l'interieur d'`anklume-instance`
pendant `anklume domain apply`, avec acces au socket Incus.

### Pourquoi c'est important

- Les roles Galaxy sont du code tiers sans revue de securite formelle
- Un role Galaxy malveillant ou compromis pourrait exfiltrer des secrets,
  creer des conteneurs avec des portes derobees, ou modifier les regles nftables
- `roles_vendor/` est dans le gitignore -- le code reellement execute n'est pas
  suivi dans le controle de version
- `anklume setup init` installe la derniere version correspondante, qui pourrait etre
  une version compromise publiee apres le `requirements.yml` initial

### Recommandations

1. **Epingler les roles Galaxy a des versions exactes** (pas `>=`) : dans
   `requirements.yml`, utiliser des versions exactes pour empecher le
   telechargement d'une nouvelle version compromise
2. **Committer `roles_vendor/` dans git** : bien que cela augmente la taille du
   depot, cela fournit une piste d'audit et empeche les mises a jour silencieuses.
   Alternativement, generer et committer des checksums
3. **Revoir les roles Galaxy avant adoption** : documenter un processus de revue
   pour l'ajout de nouveaux roles Galaxy, similaire a npm audit

---

## FINDING-10 : Agent Teams avec bypassPermissions (LOW)

### Description

D'apres `docs/agent-teams.md` :

> `--dangerously-skip-permissions` (safe: isolated sandbox)

Les Agent Teams Claude Code s'executent avec toutes les permissions contournees
a l'interieur du bac a sable Incus-dans-Incus.

### Pourquoi c'est important

- Le bac a sable est une VM (ADR-029), fournissant une isolation materielle -- bien
- Cependant, les agents ont un acces reseau pour les appels API (ANTHROPIC_API_KEY)
- Une injection de prompt dans le code source en cours de traitement pourrait amener
  l'agent a exfiltrer la cle API ou d'autres secrets via des appels reseau
- Le hook d'audit journalise les invocations d'outils mais ne peut pas empecher
  les actions malveillantes en temps reel

### Recommandations

1. **Restreindre le reseau du bac a sable** : n'autoriser que les connexions
   sortantes vers les endpoints de l'API Anthropic (api.anthropic.com), bloquer
   toute autre sortie
2. **Renouveler les cles API** : utiliser une cle API a duree limitee et a portee
   restreinte pour les sessions d'agents plutot qu'une cle a longue duree de vie
3. **Revoir le journal d'audit dans le cadre de la revue de PR** : exiger que
   le JSONL d'audit soit joint ou reference dans la PR pour revue humaine

---

## FINDING-11 : Sanitizer LLM -- Architecture a deux niveaux (LOW)

### Description

Le sanitizer LLM (Phase 39, ADR-044) est concu comme une architecture de
detection **a deux niveaux** (`docs/vision-ai-integration.md`) :

1. **Niveau 1 -- Patterns regex specifiques a l'IaC** (implemente dans
   `roles/llm_sanitizer/templates/patterns.yml.j2`) : regex curees ciblant
   les identifiants specifiques a anklume (IP de zones de confiance, noms
   de ressources Incus, bridges, FQDN, credentials, chemins Ansible,
   adresses MAC, sorties de scan reseau).
2. **Niveau 2 -- Detection basee sur ML/NER** (prevu) : integration avec
   une base eprouvee comme LLM Guard (NER via BERT, 30+ types d'entites)
   ou LLM Sentinel (80+ types de PII). Ces outils gerent la detection
   semantique que les regex ne peuvent pas couvrir.

Le document de vision indique : "None of these understand IaC-specific data
[...] anklume would add IaC-specific detection patterns on top of a
proven base."

### Etat actuel

Seul le Niveau 1 (regex) est implemente. Le Niveau 2 (ML/NER) est prevu mais
pas encore deploye. Avec uniquement le Niveau 1 actif :

- Les patterns regex ne peuvent pas detecter les fuites d'informations
  semantiques (par exemple, decrire la topologie de l'infrastructure en langage
  naturel sans utiliser les IP ou noms reels)
- Les nouveaux patterns d'identifiants non couverts par les regex passeront
  au travers
- Le sanitizer s'execute a l'interieur du conteneur du domaine -- si le
  conteneur est compromis, le sanitizer peut etre contourne
- Le mode de remplacement `pseudonymize` utilise des correspondances
  coherentes -- un attaquant observant plusieurs requetes pourrait correler
  les pseudonymes

### Recommandations

1. **Prioriser l'integration du Niveau 2** : ajouter la detection basee sur
   NER (LLM Guard ou equivalent) comblerait le manque de detection semantique
   que les regex seules ne peuvent pas adresser
2. **Etendre proactivement les patterns du Niveau 1** : quand de nouveaux
   identifiants d'infrastructure sont ajoutes (par exemple, noms de services
   MCP), ajouter les patterns correspondants a `patterns.yml.j2`
3. **Journaliser les metriques de contournement** : suivre quel pourcentage
   de requetes ont zero redactions -- une chute soudaine pourrait indiquer
   un nouveau type d'identifiant qui fuit
4. **L'architecture a deux niveaux est la bonne conception** : regex pour les
   identifiants specifiques a l'IaC (rapide, pas de faux positifs) + ML pour
   la detection generale de PII/semantique (couverture large) est une approche
   en couches pertinente

---

## FINDING-12 : Pas de verification d'integrite des fichiers Ansible generes (LOW)

### Description

Les fichiers Ansible generes (`group_vars/`, `host_vars/`, `inventory/`) sont
la source de verite secondaire. Les utilisateurs peuvent les modifier en dehors
des sections gerees. `anklume domain apply` execute ce qui se trouve dans ces fichiers.

### Pourquoi c'est important

- Un attaquant qui obtient un acces en ecriture a ces fichiers (par exemple, via
  un editeur compromis, une fusion git malveillante, ou une attaque de chaine
  d'approvisionnement) peut injecter des taches Ansible arbitraires
- Les sections gerees sont regenerees par `anklume sync`, mais les sections
  utilisateur sont preservees -- une charge malveillante dans les sections
  utilisateur persisterait
- Il n'y a pas de verification de signature ou de checksum des fichiers generes
  avant `anklume domain apply`

### Recommandations

1. **Integrite basee sur git** : exiger un `git status` propre avant
   `anklume domain apply` (ou au moins avertir sur les modifications non
   committees des fichiers generes)
2. **Checksums des sections gerees** : le generateur pourrait inclure un hash
   du contenu de la section geree que `anklume domain apply` verifie avant
   l'execution
3. **C'est acceptable pour le public cible** : anklume cible des administrateurs
   systeme et des utilisateurs avances qui gerent leurs propres depots git. Le
   risque est faible dans le modele de deploiement prevu.

---

## Proprietes de securite positives

L'audit a identifie plusieurs proprietes de securite solides qui doivent etre
preservees :

1. **Gestion par socket, pas de SSH** : utiliser le socket Incus au lieu de SSH
   elimine une classe entiere d'attaques (gestion des cles SSH, sshd expose sur
   le reseau, force brute). C'est un avantage significatif.

2. **Pas d'exception nftables speciale pour anklume** : le domaine anklume n'a
   pas de privileges reseau au-dela des autres domaines. Le trafic de gestion
   passe par le socket, pas par le reseau. C'est correct et ne devrait jamais
   changer.

3. **Restriction LXC privilegie (ADR-020)** : exiger une frontiere VM pour les
   conteneurs privilegies est une posture de securite forte. La trappe de secours
   `--YOLO` est correctement documentee comme un outil reserve a la formation.

4. **nftables en defense en profondeur** : le firewalling au niveau de l'hote et
   au niveau de la VM peuvent coexister, garantissant que la compromission d'une
   couche ne brise pas l'isolation.

5. **Modele de securite des couleurs tmux** : les couleurs de panneaux definies
   cote serveur (pas par le conteneur) empechent l'usurpation visuelle -- meme
   principe que les bordures dom0 de QubesOS.

6. **Deploiement nftables en deux etapes** : separer la generation du deploiement
   donne a l'operateur un temps de revue et evite au conteneur d'avoir besoin
   de privileges au niveau de l'hote.

7. **Remplacement atomique des nftables** : le pattern `delete table; create table`
   garantit l'absence de trou dans la couverture des regles pendant les mises a jour.

8. **Adressage IP par zone de confiance (ADR-038)** : encoder les niveaux de
   confiance dans les adresses IP fournit une identification visuelle immediate
   et permet des regles de pare-feu basees sur les zones.

9. **Protection ephemerisme (ADR-042)** : `anklume flush` respectant
   `security.protection.delete` empeche la destruction accidentelle des
   instances importantes.

10. **Reproductibilite des agents (ADR-036)** : toute la connaissance
    operationnelle des agents reproduite depuis des templates git garantit
    qu'aucun etat cache ne s'accumule.

---

## Matrice recapitulative

| Constat | Severite | Exploitabilite | Impact | Statut |
|---------|----------|----------------|--------|--------|
| FINDING-01 : Socket Incus = acces total | CRITICAL | Medium | Compromission totale | Risque accepte (Phase 44a) |
| FINDING-02 : Pont OpenClaw internet-vers-infra | HIGH | Medium | Execution arbitraire | Risque accepte (Phase 44a) |
| FINDING-03 : Credentials lisibles par tous | HIGH | Low | Vol de jetons | Phase 44b |
| FINDING-04 : LXC pour charges non fiables | MEDIUM | Low-Medium | Evasion de conteneur | Phase 44c |
| FINDING-05 : Vidage VRAM au mieux un effort | MEDIUM | Low | Fuite de donnees inter-domaines | Phase 44d |
| FINDING-06 : Dependance a br_netfilter | MEDIUM | Low | Echec d'isolation silencieux | Phase 44e |
| FINDING-07 : Fenetre temporelle nftables | LOW-MEDIUM | Low | Trou d'isolation temporaire | Phase 44f |
| FINDING-08 : Projet par defaut pour les jetables | LOW-MEDIUM | Low | Pas d'isolation | Phase 44g |
| FINDING-09 : Roles Galaxy dans la frontiere de confiance | LOW-MEDIUM | Low | Chaine d'approvisionnement | Phase 44h |
| FINDING-10 : Agent Teams contournant les permissions | LOW | Very Low | Exfiltration de cle API | Phase 44i |
| FINDING-11 : Sanitizer LLM Niveau 2 pas encore deploye | LOW | Low | Fuite de donnees | Prevu |
| FINDING-12 : Pas de verification d'integrite des fichiers | LOW | Very Low | Injection de configuration | Phase 44j |

---

## Priorite des recommandations

Tous les constats actionnables sont suivis dans la **Phase 44** du ROADMAP.

### Immediat (avant le deploiement en production)

1. Verifier `br_netfilter` dans le bootstrap et nftables-deploy (Phase 44e)
2. Epingler les versions des roles Galaxy exactement (Phase 44h)
3. Corriger les permissions des credentials avec `raw.idmap` (Phase 44b)
4. Documenter les risques acceptes pour le socket et le proxy (Phase 44a)

### Court terme (prochain cycle de developpement)

5. Integrer la regeneration nftables dans `anklume domain apply` (Phase 44f)
6. Empecher les instances jetables dans le projet par defaut (Phase 44g)
7. Ajouter un avertissement pour les conteneurs LXC non fiables (Phase 44c)
8. Ajouter une etape de verification de la VRAM (Phase 44d)

### Long terme (evolution architecturale)

9. Limiter l'acces Incus via des certificats TLS confines a un projet (FINDING-01)
10. Restreindre le reseau du bac a sable des agents aux sorties API uniquement (Phase 44i)
11. Avertissement d'integrite des fichiers generes (Phase 44j)

---

*Cet audit couvre le modele operationnel tel que documente. Un audit complementaire
au niveau du code devrait verifier que les proprietes de securite declarees sont
correctement implementees.*
