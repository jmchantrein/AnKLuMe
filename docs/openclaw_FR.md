# OpenClaw — Assistant IA auto-heberge

> **Note** : La version anglaise (`docs/openclaw.md`) fait reference en cas
> de divergence.

AnKLuMe integre [OpenClaw](https://github.com/openclaw/openclaw), un
assistant IA open-source et auto-heberge qui se connecte aux plateformes
de messagerie (Telegram, WhatsApp, Signal, Discord, etc.) et pilote
plusieurs backends LLM.

Faire tourner OpenClaw dans AnKLuMe apporte l'isolation reseau, un acces
controle aux messageries, et la delegation vers des LLM locaux pour les
requetes sensibles.

## Architecture

```
Hote
+-- Container : openclaw              (projet ai-tools)
|   +-- Daemon OpenClaw (Node.js)
|   +-- Bridges messagerie (Telegram, etc.)
|   +-- Connecte au proxy sur anklume-instance
|
+-- Container : anklume-instance       (projet anklume)
|   +-- Proxy compatible OpenAI (:9090)
|   +-- Claude Code CLI (cerveau pour les modes anklume/assistant)
|   +-- API REST pour les outils d'infrastructure
|
+-- Container : ollama                 (projet ai-tools)
    +-- llama-server (:8081)
    +-- Inference acceleree GPU
    +-- qwen2.5-coder:32b (code) / qwen3:30b-a3b (chat)
```

### Pourquoi Claude Code tourne sur anklume-instance et non dans openclaw

Question naturelle : pourquoi Ada n'execute-t-elle pas ses commandes
directement dans son conteneur `openclaw` ? Pourquoi passer par
`incus exec openclaw` depuis `anklume-instance` ?

La raison est le **modele de licence de Claude Code CLI**. Les modes
Claude (anklume et assistant) utilisent Claude Code CLI, qui necessite
un abonnement Anthropic valide (plan Max). Claude Code s'authentifie
via des tokens OAuth stockes dans `~/.claude/`. Ces credentials vivent
sur `anklume-instance` (synchronises depuis l'hote) car ce conteneur
est le plan de controle AnKLuMe — il a le socket Incus, le depot git
et Ansible.

Faire tourner Claude Code directement dans `openclaw` necessiterait de
dupliquer les credentials OAuth, le contexte projet (CLAUDE.md, SPEC.md)
et le socket Incus dans un second conteneur. Cela :
- Doublerait la surface de synchronisation des credentials
- Casserait le principe de plan de controle unique (ADR-004)
- Exposerait le socket Incus dans un conteneur qui a acces a internet
  et aux bridges de messagerie (risque de securite)

A la place, le proxy sur `anklume-instance` sert de pont : il recoit
les requetes compatibles OpenAI depuis OpenClaw, les traduit en appels
Claude Code CLI, et renvoie les reponses. Claude Code tourne avec
`--allowedTools` qui l'autorisent a executer des commandes dans
`openclaw` via `incus exec openclaw --project ai-tools`. Ainsi :
- Les credentials restent uniquement sur `anklume-instance`
- Le socket Incus n'est pas expose au conteneur connecte a internet
- Ada peut agir en root dans `openclaw` (installer des paquets,
  editer des fichiers, utiliser git) via le pont `incus exec`

Si une version future utilise l'API Claude directement (au lieu de
Claude Code CLI), l'execution native d'OpenClaw pourrait gerer les
commandes dans `openclaw` sans l'indirection `incus exec` — mais au
prix de la perte du contexte projet et des credits du plan Max.

## Modes de cerveau

OpenClaw supporte trois modes de cerveau commutables. L'utilisateur peut
changer a tout moment en envoyant "passe en mode anklume", "switch to
local", etc.

| Mode | Backend | Description |
|------|---------|-------------|
| **anklume** | Claude Code (Opus) | Expert AnKLuMe : infra, Ansible, Incus, reseau |
| **assistant** | Claude Code (Opus) | Assistant general polyvalent (persona Ada) |
| **local** | qwen3:30b-a3b (MoE) | LLM local gratuit et rapide via llama-server sur GPU |

### Comment fonctionne la commutation

1. L'utilisateur envoie "mode local" sur Telegram
2. OpenClaw transmet le message au proxy
3. Le LLM inclut un marqueur `[SWITCH:local]` dans sa reponse
4. Le proxy detecte le marqueur et :
   - Met a jour la config OpenClaw pour le nouveau backend
   - Change le modele llama-server si necessaire (coder vs chat)
   - Redemarre OpenClaw
   - Envoie un message de reveil sur Telegram confirmant le nouveau mode

### Commutation de modele llama-server

Les modes Claude utilisent `qwen2.5-coder:32b` (optimise pour les taches
de code via MCP). Le mode local utilise `qwen3:30b-a3b` (MoE avec 3B
parametres actifs, rapide, bon en conversation). Les deux modeles tournent
en services systemd mutuellement exclusifs (`llama-server.service` et
`llama-server-chat.service` avec directives `Conflicts=`).

## Suivi de consommation

Le proxy suit l'utilisation cumulative de Claude Code (cout, tokens) par
session. Quand l'utilisateur demande sa consommation ("combien j'ai
consomme ?"), le proxy injecte les statistiques directement dans le
contexte du LLM. L'assistant les presente naturellement.

Les statistiques incluent :
- Cout total en USD depuis le demarrage du proxy
- Compteurs de tokens (entree/sortie)
- Utilisation du cache (lecture et creation)
- Repartition par session (openclaw-anklume vs openclaw-assistant)

Note : le quota global du plan Max n'est pas accessible par API. Seuls
les couts par session du proxy sont suivis.

## API du proxy

Le proxy sur `anklume-instance:9090` expose :

### Endpoint compatible OpenAI
- `POST /v1/chat/completions` — utilise par OpenClaw comme backend LLM
- Supporte le streaming (SSE) et les reponses non-streaming
- Persistance de session via Claude Code `--resume`

### Outils d'infrastructure (REST)
- `/api/git_status`, `/api/git_log`, `/api/git_diff`
- `/api/make_target`, `/api/run_tests`, `/api/lint`
- `/api/incus_list`, `/api/incus_exec`, `/api/read_file`
- `/api/claude_chat`, `/api/claude_sessions`, `/api/claude_code`
- `/api/switch_brain`, `/api/usage`

### Outils web (delegues au conteneur openclaw)
- `/api/web_search` — API Brave Search (`{"query": "...", "count": 5}`)
- `/api/web_fetch` — Recuperer et extraire le texte d'une URL (`{"url": "..."}`)

### Auto-gestion
- `/api/self_upgrade` — Verifier/appliquer les mises a jour du framework

### Workflow de developpement

Ada travaille directement dans son conteneur `openclaw` (ou elle est root)
via `/api/incus_exec` avec `instance: openclaw`. Le conteneur a acces a
internet, l'imbrication Incus (`security.nesting=true`), et un clone git
d'AnKLuMe dans `/root/AnKLuMe/`. Cela permet le developpement complet,
les tests et la creation de PR sans creer de conteneurs supplementaires.

## Auto-amelioration

Ada dispose de deux boucles d'auto-amelioration, toutes deux operant
de maniere autonome depuis son conteneur sandboxe :

### Evolution du persona

OpenClaw stocke l'identite et les connaissances d'Ada dans des fichiers
workspace editables (`~/.openclaw/workspace/`). Ada peut les modifier
elle-meme pour affiner son comportement au fil des sessions :

| Fichier | Ce qu'Ada peut faire evoluer |
|---------|-----------------------------|
| `SOUL.md` | Personnalite, ton, valeurs, opinions |
| `AGENTS.md` | Instructions operationnelles, documentation des outils |
| `TOOLS.md` | Notes locales, references API, carte de l'infrastructure |
| `MEMORY.md` | Connaissances curees a long terme |
| `memory/YYYY-MM-DD.md` | Notes de session quotidiennes pour la continuite |

Quand Ada apprend quelque chose d'utile pendant une conversation (un
nouveau pattern, une preference utilisateur, un insight de debug), elle
peut le persister dans ses fichiers memoire. Au fil du temps, son
persona et sa base de connaissances evoluent par l'experience accumulee
— sans intervention manuelle.

### Contribution au framework

Ada peut aussi ameliorer le framework AnKLuMe lui-meme. Depuis son
conteneur `openclaw`, elle a un acces complet au depot git :

```
Ada sur Telegram → comprend un bug ou une amelioration
  → cree une branche dans /root/AnKLuMe/
  → implemente le correctif, lance les tests (make lint, pytest)
  → pousse et cree une PR via gh CLI
  → jmc revoit et merge
```

Cela cree une boucle recursive : l'assistant IA ameliore le framework
d'infrastructure qui heberge l'assistant IA. Combine avec la
bibliotheque d'experiences (Phase 18d) et les Agent Teams (Phase 15),
cela permet une auto-amelioration continue et auditable avec une
supervision humaine au niveau du merge.

### Ce qui rend cela sur

- **Isolation sandbox** : Ada tourne dans un conteneur LXC dedie sans
  acces aux autres domaines (pro, perso, etc.)
- **Workflow git** : tous les changements passent par des branches et
  des PR — Ada ne commite jamais directement sur main
- **Controle humain** : jmc revoit chaque PR avant la mise en production
- **Les fichiers persona sont locaux** : les modifications du workspace
  n'affectent que le comportement d'Ada, pas le framework ni les autres
  utilisateurs

## Valeur ajoutee par rapport a OpenClaw natif

L'architecture proxy d'AnKLuMe etend OpenClaw avec des capacites qui
vont au-dela de ce qu'OpenClaw fournit nativement.

### 1. Cerveau agentique (Claude Code CLI)

**OpenClaw natif** : appelle n'importe quelle API compatible OpenAI
avec un simple echange requete/reponse. Le LLM ne peut que produire
du texte.

**Avec proxy** : Claude Code CLI est un assistant de codage agentique
avec utilisation d'outils (Read, Edit, Grep, Bash). Il peut lire des
fichiers, ecrire du code, fouiller le codebase et executer des
commandes — le tout de facon autonome en un seul tour. Ada ne fait
pas que repondre aux questions — elle modifie activement le code et
gere l'infrastructure.

### 2. Orchestration inter-conteneurs

**OpenClaw natif** : ne peut executer des commandes que dans son
propre conteneur via l'outil `exec` integre.

**Avec proxy** : l'outil `incus_exec` permet a Ada d'executer des
commandes dans N'IMPORTE QUEL conteneur Incus de TOUS les projets
(avec filtres de securite). Elle peut inspecter le conteneur Ollama,
verifier l'etat reseau, gerer d'autres instances.

### 3. Commutation multi-cerveau avec gestion GPU VRAM

**OpenClaw natif** : supporte un modele a la fois, configure dans
`openclaw.json`. Changer necessite une edition manuelle et un redemarrage.

**Avec proxy** : commutation transparente entre Claude (puissant,
couteux) et les LLM locaux (gratuit, rapide) en langage naturel
("passe en mode local"). Le proxy change automatiquement les modeles
llama-server, gere la VRAM GPU et envoie un message de confirmation
sur Telegram.

### 4. Attribution des messages

**OpenClaw natif** : tous les messages viennent du meme bot. Aucun
moyen de distinguer le LLM, OpenClaw ou un gestionnaire d'erreur.

**Avec proxy** : les messages emis par le proxy sont tagues avec
`⚙️ [proxy]` pour distinguer Ada (le cerveau), le proxy (middleware)
et OpenClaw (le corps).

### 5. Sync automatique des credentials via bind-mount

**OpenClaw natif** : ne gere pas les credentials OAuth pour des CLIs
externes.

**Avec proxy** : les credentials Claude Code de l'hote sont montes en
bind-mount dans le conteneur. La fraicheur du token est automatique.

### 6. Suivi des couts et de l'utilisation

**OpenClaw natif** : ne suit pas les couts des API LLM.

**Avec proxy** : accumule les couts, compteurs de tokens et utilisation
du cache par session Claude Code. L'assistant presente les stats
naturellement quand l'utilisateur pose la question.

### 7. API REST d'infrastructure

**OpenClaw natif** : dispose d'outils exec et navigateur.

**Avec proxy** : endpoints REST types et filtres pour git, make, incus,
lint et tests — avec liste noire pour les operations dangereuses.

### 8. Recherche web deleguee a travers les frontieres reseau

**OpenClaw natif** : dispose d'une recherche Brave integree.

**Avec proxy** : delegue `web_search` et `web_fetch` au conteneur
`openclaw` (qui a acces a internet), tandis que `anklume-instance`
reste hors ligne. Cela maintient l'isolation reseau.

### 9. Capacite d'auto-mise a jour

**OpenClaw natif** : `openclaw update` se met a jour lui-meme.

**Avec proxy** : l'outil `self_upgrade` peut verifier et appliquer les
mises a jour du framework AnKLuMe, re-synchroniser la configuration
et re-provisionner le conteneur openclaw — depuis un message Telegram.

### 10. Sessions persistantes multi-tours

**OpenClaw natif** : chaque tour d'agent est un appel API frais.

**Avec proxy** : maintient des sessions Claude Code persistantes via
`--resume`, permettant des conversations multi-tours ou le cerveau
conserve le contexte complet du codebase entre les messages.

### Tableau recapitulatif

| Capacite | OpenClaw natif | Avec proxy AnKLuMe |
|----------|---------------|-------------------|
| Cerveau LLM | Completion textuelle API | Codage agentique (outils) |
| Portee des commandes | Son conteneur uniquement | Tout conteneur Incus |
| Changement de modele | Edition manuelle config | Langage naturel + auto-redemarrage |
| Origine des messages | Opaque | Tague (`[proxy]`) |
| Credentials | Manuel | Bind-mount (auto) |
| Suivi des couts | Non | Stats par session |
| Outils d'infra | exec uniquement | git, make, incus, lint, tests |
| Recherche web | Native (meme conteneur) | Deleguee (isolation reseau) |
| Auto-mise a jour | OpenClaw uniquement | Framework + conteneur |
| Memoire de session | Par tour | Persistante (--resume) |

## Deploiement

### Prerequis
- AnKLuMe deploye avec le domaine `ai-tools`
- Ollama ou llama-server en fonctionnement avec un modele charge
- Un token de bot Telegram (via [@BotFather](https://t.me/BotFather))

### Role Ansible

Le role `openclaw_server` installe et configure OpenClaw :

```yaml
# Dans infra.yml
domains:
  ai-tools:
    subnet_id: 10
    machines:
      openclaw:
        type: lxc
        ip: "10.100.10.40"
        roles: [base_system, openclaw_server]
```

### Configuration manuelle (apres deploiement du role)

```bash
# Dans le container openclaw
incus exec openclaw --project ai-tools -- bash

# Lancer l'onboarding (interactif)
cd ~/.openclaw && openclaw onboard

# Configurer le canal Telegram
# Suivre les invites pour entrer le token du bot et l'ID utilisateur

# Demarrer le daemon
openclaw start
```

## Fichiers de configuration

Dans le conteneur `openclaw` :

| Fichier | Role |
|---------|------|
| `~/.openclaw/openclaw.json` | Config principale (modele, provider, canaux) |
| `~/.openclaw/agents/main/SOUL.md` | Definition du persona (identite, ton, langue) |
| `~/.openclaw/agents/main/AGENTS.md` | Manuel operationnel avec sections par mode |

### Structure de AGENTS.md

Le fichier `AGENTS.md` utilise des marqueurs de mode (`[ALL MODES]`,
`[ANKLUME MODE]`, `[ASSISTANT MODE]`, `[LOCAL MODE]`) pour organiser le
contenu par mode de cerveau. OpenClaw envoie le fichier entier au backend
LLM actif, et le LLM ne suit que les sections pertinentes pour son mode :

| Marqueur | Contenu |
|----------|---------|
| `[ALL MODES]` | Architecture, internals OpenClaw, commutation, outils web, limitations |
| `[ANKLUME MODE]` | Workflow de dev, API REST infra, incus_exec, auto-upgrade, sessions Claude Code |
| `[ASSISTANT MODE]` | Comportement assistant general, suivi de consommation |
| `[LOCAL MODE]` | Outils natifs OpenClaw (exec, browser, cron), skills |

## Gestion des credentials

Le proxy sur `anklume-instance` utilise Claude Code CLI qui necessite
des credentials OAuth valides. Les credentials sont partages via un
bind-mount Incus depuis l'hote vers le conteneur :

```bash
# Le bind-mount est configure comme un device disk Incus :
incus config device add anklume-instance claude-creds disk \
  source=/home/user/.claude/.credentials.json \
  path=/root/.claude/.credentials.json \
  readonly=true shift=true
```

Le conteneur lit directement le fichier de credentials de l'hote —
pas de timer de synchronisation, pas de copie, pas de delai. Quand
Claude Code renouvelle le token OAuth sur l'hote, le conteneur voit
le nouveau token immediatement.

**Prerequis** : Le fichier de credentials de l'hote doit etre lisible
par tous (`chmod 644`) car le mapping UID d'Incus mappe l'utilisateur
hote vers `nobody:nogroup` dans le conteneur.

**Limitation** : Les tokens OAuth expirent toutes les ~12 heures. Si
Claude Code n'est pas utilise de maniere interactive sur l'hote pendant
plus de 12 heures, le token expire et Ada perd l'acces aux modes Claude.
Pour retablir l'acces, lancer `claude` une fois sur l'hote (le token se
renouvelle automatiquement au demarrage) — le bind-mount rend le token
frais disponible instantanement.

Quand le token expire, le proxy renvoie un message tague `⚙️ [proxy]`
expliquant comment le renouveler, plutot qu'une erreur opaque.

## Depannage

### Ada ne repond pas sur Telegram

1. Verifier qu'OpenClaw tourne :
   ```bash
   incus exec openclaw --project ai-tools -- pgrep -f openclaw
   ```

2. Verifier que le proxy tourne :
   ```bash
   incus exec anklume-instance --project anklume -- pgrep -f mcp-anklume-dev
   ```

3. Consulter les logs du proxy :
   ```bash
   incus exec anklume-instance --project anklume -- tail -20 /tmp/proxy.log
   ```

### Erreur d'authentification Claude Code

Le token OAuth a expire. Lancer Claude Code en mode interactif sur
l'hote pour renouveler le token — le bind-mount le rend disponible
instantanement dans le conteneur :

```bash
claude
# (le token se renouvelle automatiquement, puis quitter)
```

### Le mode local est lent

Verifier quel service llama-server est actif :

```bash
incus exec ollama --project ai-tools -- systemctl status llama-server-chat
```

Le modele qwen3:30b-a3b MoE devrait etre rapide (~3B parametres actifs).

### La commutation de cerveau n'envoie pas de message de reveil

Verifier qu'OpenClaw a redemarre apres la commutation :

```bash
incus exec openclaw --project ai-tools -- pgrep -f openclaw
```

Le message de reveil est envoye via l'API Telegram Bot directement par
le proxy, avec un delai (6s pour les modes Claude, 15s pour le mode local
pour permettre le chargement du modele).
