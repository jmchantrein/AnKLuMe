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

## Gestion des credentials

Le proxy sur `anklume-instance` utilise Claude Code CLI qui necessite
des credentials OAuth valides. Un timer systemd (`anklume-sync-creds.timer`)
synchronise les credentials depuis l'hote toutes les 2 heures :

```bash
# Installer le timer de synchronisation (sur l'hote)
host/boot/sync-claude-credentials.sh --install

# Synchronisation manuelle
host/boot/sync-claude-credentials.sh
```

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

Le token OAuth a expire. Lancer le script de synchronisation sur l'hote :

```bash
host/boot/sync-claude-credentials.sh
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
