# Vision : integration de l'IA dans anklume

> Traduction francaise de [`vision-ai-integration.md`](vision-ai-integration.md). En cas de divergence, la version anglaise fait foi.

**Date** : 2026-02-23
**Statut** : Brouillon -- consolidation des discussions de conception, en attente de formalisation dans le ROADMAP

## 1. Contexte et motivation

anklume fournit une compartimentation de type QubesOS en utilisant Incus et Ansible.
Aujourd'hui, les outils d'IA (Claude Code, Ollama, OpenClaw) sont utilises pendant le
developpement mais ne sont pas traites comme des citoyens de premiere classe de
l'infrastructure compartimentee. Ce document propose une vision ou l'IA est integree
dans anklume avec les memes garanties d'isolation que tout le reste.

Trois besoins convergents motivent cette vision :

1. **Flux de travail de developpement** : Claude Code + GPU local doivent fonctionner
   ensemble de maniere transparente, sans middleware proxy complexe.
2. **Assistant personnel/professionnel** : Un agent IA permanent (OpenClaw) qui vit
   au sein de l'infrastructure, la surveille et respecte les frontieres entre domain.
3. **Confidentialite** : Lorsque les requetes IA quittent le perimetre local (API LLM
   cloud), les donnees d'infrastructure sensibles doivent etre anonymisees. C'est
   critique pour les environnements professionnels ou la topologie reseau, les noms
   de machines et les donnees clients ne doivent jamais atteindre des serveurs tiers.

## 2. Principes de conception

1. **Local par defaut, cloud par exception.** Le GPU local traite 80-90% des taches
   IA. Les LLM cloud n'interviennent que lorsque la complexite du raisonnement depasse
   les capacites des modeles locaux.
2. **L'isolation est structurelle, pas applicative.** Les frontieres de securite sont
   imposees par les bridges reseau Incus et les regles nftables, pas par des listes
   d'autorisation/refus au niveau applicatif (qui ont des bugs de contournement documentes).
3. **L'IA est un citoyen du domain.** Une instance IA (OpenClaw, Claude Code) dans le
   domain `pro` ne voit que le domain `pro`. Elle ne peut pas acceder a `perso` ou
   `sandbox` -- le reseau l'empeche, pas un drapeau de configuration.
4. **La sanitization protege ce qui sort.** Les donnees restent brutes a l'interieur
   du perimetre local. L'anonymisation ne s'applique que lorsqu'une requete sort vers
   une API cloud. Le proxy se situe a la frontiere, pas a l'interieur de chaque container.
5. **L'humain controle l'escalade.** L'escalade automatique du local vers le cloud est
   limitee a un routage deterministe base sur le type de tache. L'escalade basee sur
   un score de confiance est explicitement rejetee comme non fiable.

## 3. Architecture a trois couches

### Couche 1 : Flux de travail de developpement (Claude Code)

L'outil quotidien du developpeur. Pas d'OpenClaw implique.

| Composant | Role |
|---|---|
| **Claude Code** | Orchestrateur principal (terminal/IDE) |
| **claude-code-router** | Route les taches de fond vers Ollama automatiquement via `ANTHROPIC_BASE_URL` |
| **mcp-ollama-coder** | Outils MCP pour la delegation explicite vers le GPU local (generer, reviewer, corriger, tester) |
| **LLM sanitizer** (optionnel) | Anonymise les donnees quand Claude Code communique avec l'API cloud |

Depuis Ollama v0.14 (janvier 2026), Ollama implemente nativement l'API Anthropic Messages.
Combine avec `claude-code-router`, cela resout le probleme initial (utiliser le GPU local
depuis Claude Code) sans aucun proxy personnalise.

Le proxy existant `mcp-anklume-dev.py` est retire dans cette vision. Ses outils MCP
utiles (incus_exec, operations git, etc.) peuvent etre conserves sous forme de serveur
MCP leger, sans le routage compatible OpenAI, la gestion de sessions, le changement de
cerveau et le transfert de credentials qui le rendaient complexe.

### Couche 2 : Assistant IA par domain (OpenClaw)

Un agent permanent qui vit au sein de l'infrastructure.

**Changement cle : une instance OpenClaw par domain, pas centralisee.**

```
Domain pro       -> OpenClaw "pro"      (trust: trusted)
  - Sees only pro containers and network
  - Mode: local-first (Ollama, cloud fallback)
  - Heartbeat: monitors pro services
  - Channel: Telegram (or Signal, WhatsApp...)

Domain perso     -> OpenClaw "perso"    (trust: trusted)
  - Sees only perso containers and network
  - Mode: local (Ollama only, nothing leaves)
  - Heartbeat: personal reminders, perso service health
  - Channel: Telegram

Domain sandbox   -> OpenClaw "sandbox"  (trust: disposable)
  - Tests risky skills, untrusted prompts
  - Mode: local (never cloud for sandbox)
  - No heartbeat (ephemeral)
  - If compromised, destroy and recreate
```

Chaque instance communique directement avec Ollama (decouverte automatique sur l'IP du
container GPU) pour le mode local. Aucun proxy intermediaire necessaire.

**Fonctionnalites OpenClaw a exploiter (actuellement inutilisees) :**

| Fonctionnalite | Cas d'utilisation |
|---|---|
| Heartbeat (toutes les 30 min) | Surveillance proactive de l'infrastructure par domain |
| Cron | Rapports programmes, taches de maintenance, declenchement de snapshots |
| Memory + RAG | Accumuler les connaissances operationnelles par domain (recherche hybride SQLite) |
| Multi-agent | Agent de surveillance infra + agent assistant personnel |
| Skills (personnalises) | Competences d'automatisation specifiques a anklume (PAS de ClawHub tiers, sauf en sandbox) |
| Sessions spawn | Sous-taches isolees sans polluer la session principale |

**Patron de surveillance par heartbeat :**

A chaque cycle de heartbeat, l'agent OpenClaw du domain :

1. Execute des sondes (statut des container, espace disque, sante des services, diff de scan reseau)
2. Transmet les resultats a Ollama local (triage : normal / suspect / critique)
3. Si anomalie detectee -> alerte l'utilisateur via Telegram + escalade cloud optionnelle
4. Si routine -> enregistre en memoire, pas de notification

Cela implemente le patron "IDS a deux niveaux" issu de la recherche academique :
surveillance continue legere en local, analyse lourde uniquement en cas d'escalade.

### Couche 3 : Proxy de sanitization LLM

Un service dans le domain anklume qui anonymise les donnees d'infrastructure avant
qu'elles n'atteignent une API LLM cloud.

**Architecture :**

```
Container in domain pro
  -> LLM request (raw data: real IPs, hostnames, FQDNs)
      -> anklume-sanitizer (domain anklume, admin zone)
          -> Detects and tokenizes:
             - IPs (RFC1918 ranges, client ranges)
             - Hostnames, FQDNs (*.internal, *.corp, *.local)
             - Service names, database names
             - Credentials, tokens, API keys
             - Network topology indicators
          -> Forwards anonymized content to cloud API
          -> Receives response
          -> De-tokenizes response (token -> real value)
          -> Returns to requesting container
          -> Logs everything locally (audit trail)
```

**Pourquoi l'IaC est ideal pour la sanitization :** Dans les playbooks Ansible, presque
tout ce qui est sensible sont des identifiants (noms de machines, IP, ports, domaines),
pas la logique elle-meme. Un template nginx est identique que le serveur s'appelle
`prod-web-01.acme.corp` ou `server_A`. L'anonymisation degrade tres peu la qualite
des reponses pour ce cas d'usage.

**Implementations candidates** (a evaluer, pas a construire de zero) :

| Projet | Langage | Points forts |
|---|---|---|
| LLM Sentinel | Go | 80+ types PII, support Anthropic |
| LLM Guard | Python | Base NER (BERT), coffre-fort de tokens |
| Privacy Proxy (Ogou) | Python | 30+ patterns regex, zero-trust |

Aucun de ces outils ne comprend les donnees specifiques a l'IaC (noms de projets Incus,
noms de bridges, IP de la convention d'adressage anklume). anklume ajouterait des
patrons de detection specifiques a l'IaC par-dessus une base eprouvee.

**Integration transparente :** Le sanitizer expose un endpoint compatible Anthropic.
Les container l'atteignent via `ANTHROPIC_BASE_URL=http://anklume-sanitizer:8080`.
Claude Code, OpenClaw ou tout outil supportant `ANTHROPIC_BASE_URL` fonctionne
sans modification.

## 4. Integration dans infra.yml

### Nouveaux champs au niveau du domain

```yaml
domains:
  pro:
    trust_level: trusted
    ai_provider: local-first       # local | cloud | local-first
    ai_sanitize: true              # false | true (= cloud-only) | always
    machines:
      pro-dev:
        type: lxc
        roles: [base_system]
      pro-gateway:
        type: lxc
        roles: [base_system, network_gateway]
```

### ai_provider

Controle ou les requetes LLM de ce domain sont routees.

| Valeur | Comportement |
|---|---|
| `local` | Toutes les requetes vont a Ollama. Rien ne quitte la machine. |
| `cloud` | Toutes les requetes vont a l'API cloud (via sanitizer si `ai_sanitize` est defini). |
| `local-first` | Ollama traite la requete. Si le type de tache necessite un raisonnement de niveau cloud, bascule vers le cloud (via sanitizer si `ai_sanitize` est defini). |

Defaut : `local` (securise par defaut -- rien ne sort sauf configuration explicite).

### ai_sanitize

Controle si les requetes LLM sont anonymisees avant de quitter le perimetre local.

| Valeur | Comportement |
|---|---|
| `false` | Pas de sanitization. A utiliser pour les domain sandbox, personnels ou en local uniquement. |
| `true` | Sanitization quand la requete va vers une API cloud. Les requetes locales restent brutes. C'est le defaut quand `ai_provider` est `cloud` ou `local-first`. |
| `always` | Sanitization meme pour les requetes locales. Pour les exigences strictes de conformite/audit. |

Defaut : `false` quand `ai_provider: local`, `true` sinon.

Le sanitizer journalise chaque requete a destination du cloud avec : texte anonymise
envoye, reponse recue, correspondance token-valeur (stockee localement), horodatage,
domain source. Cette piste d'audit prouve que les outils IA n'ont pas expose de donnees
sensibles -- utile pour les contrats clients et la conformite.

### Strategie d'escalade ai_provider (mode local-first)

L'escalade du local vers le cloud utilise deux mecanismes :

**1. Routage statique par type de tache (pour les taches automatisees -- heartbeat, cron) :**

| Type de tache | Routage | Raison |
|---|---|---|
| Analyse syntaxique, reformatage, inventaire | Local | Structurel, pas de raisonnement necessaire |
| Triage d'alertes (normal/suspect) | Local | Classification simple |
| Resume de capture/scan | Local | Condensation, pas analyse |
| Generation de code/playbook | Local | Les modeles codeurs 32B sont suffisants |
| Correlation multi-sources | Cloud | Raisonnement en chaine longue necessaire |
| Forensique, analyse d'incident | Cloud | Connaissance approfondie des protocoles necessaire |
| Evaluation d'architecture | Cloud | Jugement expert multi-criteres |
| Rapports pour la direction/les clients | Cloud | Redaction nuancee requise |

**2. Escalade explicite de l'utilisateur (pour les conversations) :**

L'utilisateur dit "escalade" / "analyse ca plus en profondeur" / "demande a Claude".
L'agent bascule du local vers le cloud pour cet echange specifique.

**Explicitement rejete : l'auto-escalade basee sur un score de confiance.** Les modeles
locaux (7-32B) ne sont pas fiables pour estimer leur propre confiance. Un modele qui
hallucine le fait avec conviction. L'escalade automatique basee sur l'incertitude
auto-declaree produirait a la fois des faux positifs (appels cloud inutiles) et des
faux negatifs (hallucinations confiantes restant en local).

## 5. Conventions de nommage

### Domain anklume (zone admin)

Les services d'infrastructure qui necessitent une visibilite inter-domain vivent
dans le domain anklume. Les noms de container sont prefixes `anklume-` :

| Service | Nom du container | Role |
|---|---|---|
| Admin/controleur | `anklume-instance` | Ansible, git, orchestration (existant) |
| Pare-feu | `anklume-firewall` | Routage inter-domain nftables |
| Surveillance | `anklume-monitoring` | Metriques d'infrastructure, alertes |
| Sauvegarde | `anklume-backup` | Gestion de snapshots inter-domain |
| Sanitizer | `anklume-sanitizer` | Proxy d'anonymisation LLM |

**Regle de placement :** Si un service a besoin de voir au-dela de son propre domain
pour fonctionner, il va dans anklume. Si c'est un service accede par d'autres domain
via network_policies, il obtient son propre domain.

### Domain shared (services partages)

Services accessibles par plusieurs domain via network_policies. Ils n'ont pas besoin
de visibilite inter-domain -- les autres domain se connectent a eux, pas l'inverse.

```yaml
  shared:
    trust_level: trusted
    machines:
      shared-print:
        type: lxc
        roles: [base_system, cups_server]
      shared-dns:
        type: lxc
        roles: [base_system, dns_cache]
```

Les noms de container sont prefixes `shared-`, conformement a la convention selon
laquelle les container sont prefixes par le nom de leur domain (`pro-dev`, `perso-desktop`,
`anklume-instance`, `shared-print`).

### Notes de migration

- `sys-firewall` a ete renomme en `anklume-firewall` (Phase 36)
- Exemple `sys-print` -> `shared-print` dans le domain `shared`
- Le prefixe `sys-` est retire. Les services sont soit dans `anklume` (infrastructure
  d'administration), soit dans `shared` (services partages accessibles aux utilisateurs).

## 6. Inspection reseau et surveillance de securite

### Le pipeline a trois niveaux

L'inspection reseau assistee par LLM suit un pipeline strict ou chaque niveau
ajoute de l'intelligence mais aussi du risque (exposition des donnees) :

```
LEVEL 1 — Collection (no LLM)
  tcpdump, tshark, nmap, SNMP walks, LLDP/CDP
  Output: PCAP files, XML results, MIB tables, neighbor data
      |
      v
LEVEL 2 — Local triage (LLM local, 100% confidential)
  Ollama (llama3:8b, qwen2.5-coder:32b, mistral:7b)
  Tasks: parsing, inventory, triage, summaries, basic alerts
  Cost: zero (hardware amortized), no rate limit, 24/7
  Triggered by: OpenClaw heartbeat (every 30 min) or cron
      |
      | Only cases requiring advanced reasoning
      | (+ data anonymized by sanitizer)
      v
LEVEL 3 — Deep analysis (cloud LLM, via sanitizer)
  Claude Sonnet/Opus via API
  Tasks: forensics, multi-source correlation, architecture
  evaluation, incident reports, adversarial reasoning
  Triggered by: explicit user request or task-type routing
```

### Ce que les modeles locaux gerent bien

- Analyser et structurer la sortie brute de nmap, SNMP, LLDP en JSON
- Generer des inventaires a partir de donnees de scan
- Comparer l'inventaire actuel avec la reference (detecter les changements)
- Produire des diagrammes simples (Mermaid, DOT/Graphviz)
- Trier les anomalies (normal / a investiguer / critique)
- Resumer les captures (principaux emetteurs, distribution des protocoles)
- Alertes basiques (port inhabituel, plage IP non autorisee)
- Boucle de surveillance continue (pas de cout, pas de limite de debit)

### Ce qui necessite les modeles cloud

- Reconstituer des chronologies d'intrusion a partir de multiples captures et logs
- Detecter des corruptions subtiles (timing MitM, TTL de spoofing DNS)
- Recouper donnees reseau + logs systeme + evenements applicatifs
- Analyser des protocoles rares (SCADA/Modbus, BGP, extensions TLS 1.3)
- Rediger des rapports forensiques structures pour un public non technique
- Raisonnement adversarial (identifier les techniques d'evasion)
- Evaluer une architecture par rapport aux bonnes pratiques (segmentation,
  redondance, points de defaillance uniques) sur 50+ equipements

### Ce que les LLM ne remplacent PAS

- IDS/NIDS (Suricata, Zeek, Snort) pour la detection en temps reel a haut debit
- SIEM (Splunk, Elastic) pour la correlation a grande echelle sur des mois de logs
- Scanners de vulnerabilites (Nessus, OpenVAS) pour la detection systematique de CVE
- Le jugement de l'analyste humain -- le LLM guide l'investigation, il ne conclut pas

### Specificites d'anonymisation pour les donnees reseau

Les captures reseau sont significativement plus sensibles que le code IaC. Le
sanitizer doit gerer :

| Type de donnee | Sensibilite | Methode d'anonymisation |
|---|---|---|
| IP internes et plages | Elevee | Remplacer par des IP factices coherentes |
| Topologie (qui communique avec qui) | Elevee | Anonymiser les endpoint, preserver la structure |
| Services et versions | Elevee | Generaliser les versions, conserver le type de service |
| Noms DNS internes | Elevee | Remplacer par des noms generiques |
| Contenu applicatif (HTTP, etc.) | Critique | Ne jamais envoyer le contenu, uniquement les metadonnees |
| Credentials en clair | Critique | Supprimer entierement |
| Motifs de communication | Moyenne | Preserver le timing, anonymiser les endpoint |
| Volumes de trafic | Faible | Laisser passer (statistiques agregees) |

## 7. Paysage concurrentiel

### Aucun framework existant ne combine les quatre fonctionnalites

En fevrier 2026, aucun framework IaC, plateforme ou projet open-source ne combine :

1. Infrastructure compartimentee declarative (domain isoles avec application reseau)
2. Assistant IA integre (cloud et local, conscient de la topologie d'infrastructure)
3. Proxy de sanitization LLM (anonymisation specifique a l'IaC, pas seulement du PII generique)
4. Isolation IA par domain (differentes instances IA par zone de securite)

**Chevauchements partiels existants :**

| Outil | Compartimente | IA integree | Sanitization LLM | IA par domain |
|---|---|---|---|---|
| QubesOS | Oui (meilleur de sa categorie) | Non | Non | Non |
| Pulumi Neo | Non (ressources cloud) | Oui | Non | Non |
| Spacelift Intent | Non | Oui | Non | Non |
| HashiCorp Vault+Terraform MCP | Non | Partiel | Partiel (secrets) | Non |
| Ansible Lightspeed | Non | Oui (generation de code) | Partiel (PII) | Non |
| LLM Guard / Sentinel | Non | Non | Oui (PII generique) | Non |
| Proxmox MCP ecosystem | Partiel | Oui | Non | Non |
| **anklume (cette vision)** | **Oui** | **Oui** | **Oui** | **Oui** |

**Challengers a surveiller :**

- **Pulumi Neo** : evolue vers une infrastructure agentique avec gouvernance.
  S'il ajoute LXC/KVM, l'application de l'isolation et la sanitization, le
  chevauchement augmente.
- **HashiCorp Vault MCP + Terraform MCP** : possede deja l'anonymisation RAG
  pour les secrets. Si etendu aux donnees de topologie, chevauchement partiel.
- **Proxmox MCP ecosystem** (6+ projets) : donne aux LLM l'acces aux API
  Proxmox, mais sans application de l'isolation ni politiques d'acces IA.

La combinaison est unique aujourd'hui, mais le paysage evolue vite.

### Les differenciateurs les plus forts d'anklume

- **Fonctionnalite 4 (isolation IA par domain)** est veritablement novatrice. Aucun
  outil ne fournit differentes instances IA par zone de securite avec des frontieres
  imposees par le reseau.
- **Fonctionnalite 3 appliquee a la topologie d'infrastructure** (pas seulement du
  PII generique) n'est pas traitee. Aucun outil de sanitization ne comprend les noms
  de projets Incus, les noms de bridges ou les conventions d'adressage par zone.
- La combinaison des fonctionnalites 1+2 (infra compartimentee + IA qui respecte les
  compartiments) est ce qui rend les fonctionnalites 3+4 possibles. Sans isolation
  structurelle, l'isolation IA au niveau applicatif n'est que du theatre.

## 8. Considerations de securite

### Defense en profondeur (d'apres le rapport de confidentialite IaC)

Aucune couche seule n'est suffisante. L'approche recommandee combine :

1. **Isolation de contexte** (essentiel) : depots IaC dedies avec zero secret,
   zero nom reel. Inventaires anonymises pour le travail assiste par IA.
2. **Proxy de sanitization LLM** (fortement recommande) : tokeniser IP, FQDN,
   noms de services, credentials avant les appels API cloud.
3. **Isolation reseau** (recommande) : bastion SSH avec ProxyJump. Les outils
   IA voient des alias, jamais la topologie reelle.
4. **Discipline de processus** (essentiel) : revue humaine avant tout apply/deploy.
   Documenter les conventions dans CLAUDE.md. Auditer regulierement les logs du proxy.

### Risques connus

| Risque | Severite | Mitigation |
|---|---|---|
| Fuite de topologie d'infrastructure | Elevee | Proxy de sanitization + isolation de contexte |
| Contournement des regles de refus (Claude Code) | Elevee | Isolation structurelle (Incus), pas de regles au niveau applicatif |
| Retention des donnees par le fournisseur cloud | Moyenne | Sanitization (le fournisseur ne voit que des donnees anonymisees) |
| Injection de prompt via du contenu IaC | Moyenne | Revue humaine + execution sandboxee |
| Heritage de permissions | Elevee | Utilisateur OS dedie par domain, permissions restreintes |

### Skills tiers ClawHub

L'incident ClawHavoc (fevrier 2026) a revele 341-1 184 skills malveillants dans
ClawHub. Les skills tiers doivent etre traites comme du code non fiable.

**Politique :** Les skills ClawHub sont installes UNIQUEMENT dans les domain sandbox
(`trust_level: disposable`). Les domain de production utilisent des skills personnalises
definis dans le depot anklume et deployes via des templates Ansible (patron ADR-036).

## 9. Ce que cette vision retire

| Composant | Statut | Remplacement |
|---|---|---|
| `mcp-anklume-dev.py` (proxy de 1200 lignes) | Retire | claude-code-router + mcp-ollama-coder + OpenClaw par domain |
| OpenClaw centralise dans ai-tools | Retire | Instances OpenClaw par domain |
| Changement de cerveau via modification JSON + redemarrage systemd | Retire | Connexion directe a Ollama par instance |
| Sessions Claude Code gerees par le proxy | Retire | Claude Code fonctionne en autonome avec claude-code-router |
| Montage de credentials par bind-mount du host vers anklume-instance | Retire | Claude Code s'authentifie normalement sur le host |
| Prefixe `sys-` pour les services d'infrastructure | Retire | Prefixe `anklume-` dans le domain admin, `shared-` dans le domain shared |

## 10. Ce que cette vision preserve

| Composant | Statut | Raison |
|---|---|---|
| ADR-036 (templates reproductibles) | Conserve | Excellent patron pour les instances OpenClaw par domain |
| Role Ansible `openclaw_server` | Conserve + enrichi | Etendre pour le deploiement multi-instances par domain |
| Isolation reseau Incus | Conserve | Fondation de toutes les garanties d'isolation IA |
| Outils MCP `mcp-ollama-coder` | Conserve | Claude Code delegue au GPU local via MCP |
| `ai_access_policy: exclusive` | Conserve | Isolation GPU/VRAM entre domain |
| Exception SOUL.md pour OpenClaw | Conserve | La personnalite persiste, non geree par le framework |

## 11. Phases d'implementation (a formaliser dans le ROADMAP)

Ordre approximatif, a affiner :

1. **Integration de claude-code-router** : documentation + role optionnel,
   remplace le proxy pour le flux de travail de developpement.
2. **OpenClaw par domain** : etendre le role `openclaw_server`, supporter
   plusieurs instances, une par domain dans infra.yml.
3. **Exploitation du heartbeat + cron OpenClaw** : skills personnalises pour
   la surveillance d'infrastructure par domain.
4. **Proxy de sanitization LLM** : evaluer LLM Sentinel / LLM Guard,
   ajouter des patrons specifiques a l'IaC, deployer comme `anklume-sanitizer`.
5. **Integration de l'inspection reseau** : MCP Wireshark + pipeline de triage
   local + escalade cloud a travers le sanitizer.
6. **Migration des noms** : `sys-firewall` renomme en `anklume-firewall`
   (Phase 36, fait), `sys-print` -> `shared-print` dans le domain `shared`.
7. **`ai_provider` et `ai_sanitize` dans infra.yml** : support du generateur,
   validation, documentation.

## 12. Questions ouvertes

1. **Affinement du seuil d'escalade** : Le routage statique par type de tache est
   la base. Peut-on l'ameliorer avec des heuristiques legeres (longueur de reponse,
   nombre de tokens, detection de repetition) sans tomber dans le piege du score
   de confiance ?

2. **Support MCP client dans OpenClaw** : La PR #21530 est ouverte. Une fois mergee,
   elle permettra a OpenClaw de consommer des outils MCP nativement -- potentiellement
   en remplacement du besoin d'implementations d'outils personnalises a l'interieur
   d'OpenClaw.

3. **Multi-agent au sein d'un domain** : Un domain devrait-il avoir un seul agent
   OpenClaw (qui fait tout) ou deux (un pour la surveillance, un pour l'assistance
   personnelle) ? La fonctionnalite multi-agent le supporte mais ajoute de la
   complexite.

4. **Performance du sanitizer** : Ajouter un proxy dans le chemin de requete LLM
   ajoute de la latence. Des benchmarks sont necessaires pour s'assurer que le
   surcout est acceptable pour l'utilisation interactive (objectif : < 200ms de
   latence ajoutee).

5. **Mises a jour d'OpenClaw** : OpenClaw publie plusieurs versions par semaine.
   Le role Ansible fixe une version ou utilise `@latest`. Une strategie pour les
   mises a jour securisees est necessaire (tester d'abord dans un domain sandbox ?).

6. **Container passerelle pour les reseaux clients** : Quand un domain contient
   une passerelle vers des reseaux externes (VPN/VLAN vers l'infrastructure client),
   le `ai_sanitize: true` au niveau du domain couvre tous les container y compris
   la passerelle. Devrait-on supporter des patrons d'anonymisation supplementaires
   specifiques au client, configurables dans infra.yml ?
