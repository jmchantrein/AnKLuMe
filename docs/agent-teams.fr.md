# Claude Code Agent Teams -- Developpement Autonome

> Traduction francaise de [`agent-teams.md`](agent-teams.md). En cas de divergence, la version anglaise fait foi.

anklume supporte le developpement et les tests entierement autonomes en
utilisant Claude Code Agent Teams. Plusieurs instances de Claude Code
travaillent en parallele dans un bac a sable Incus-in-Incus, avec une
supervision humaine au niveau de la fusion des PRs.

## Architecture

```
+----------------------------------------------------------------+
| Container : anklume (Incus-in-Incus, Phase 12)                  |
| security.nesting: true                                          |
| CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1                          |
| --dangerously-skip-permissions (sur : bac a sable isole)       |
|                                                                 |
|  Claude Code Agent Teams                                        |
|                                                                 |
|  Chef d'equipe : orchestrateur                                  |
|  +-- lit le ROADMAP / description de la tache                   |
|  +-- decompose le travail en liste de taches partagee           |
|  +-- assigne les taches aux coequipiers                         |
|  +-- synthetise les resultats, cree la PR                       |
|                                                                 |
|  Coequipier "Builder" : implementation de fonctionnalites       |
|  Coequipier "Tester" : tests continus                           |
|  Coequipier "Reviewer" : qualite du code et conformite ADR      |
|                                                                 |
|  Incus imbrique (les cibles de test Molecule s'executent ici)   |
+----------------------------------------------------------------+
```

## Demarrage rapide

### Prerequis

1. Container runner (Phase 12) : `anklume dev runner create`
2. Claude Code installe dans le runner : `make agent-runner-setup`
3. Cle API Anthropic : `export ANTHROPIC_API_KEY=sk-ant-...`

### Mode correction

Corriger les tests Molecule en echec de maniere autonome :

```bash
# Corriger tous les roles
anklume ai agent-fix

# Corriger un role specifique
anklume ai agent-fix R=base_system
```

### Mode developpement

Implementer une fonctionnalite de maniere autonome :

```bash
anklume ai agent-develop TASK="Add monitoring role with Prometheus node exporter"
```

## Installation

### 1. Creer le container runner

```bash
anklume dev runner create     # Cree le bac a sable Incus-in-Incus
```

### 2. Installer Claude Code dans le runner

```bash
make agent-runner-setup
```

Cela execute le role `dev_agent_runner` dans le container runner :
- Installe Node.js 22 et tmux
- Installe le CLI Claude Code globalement
- Configure les parametres de Claude Code (permissions, flag Agent Teams)
- Deploie le script de hook d'audit
- Configure l'identite git

### 3. Definir votre cle API

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Modes operationnels

### Mode correction (`anklume ai agent-fix`)

```
1. Lancer Claude Code dans le container runner
2. Executer molecule test pour tous les roles (ou ceux specifies)
3. En cas d'echec : lancer les coequipiers Fixer + Tester
4. Le Fixer analyse les journaux + le code source, applique la correction
5. Le Tester re-execute les tests apres chaque correction
6. Boucler jusqu'au succes ou au nombre max de tentatives (3)
7. Commiter les corrections, creer optionnellement une PR
```

### Mode developpement (`anklume ai agent-develop TASK="..."`)

```
1. Lancer Claude Code avec la description de la tache
2. L'agent lit ROADMAP.md et CLAUDE.md
3. Lance les coequipiers Builder, Tester et Reviewer
4. Le Builder implemente, le Tester valide, le Reviewer verifie
5. Iterer jusqu'a ce que tous approuvent
6. Commiter sur la branche feature, creer une PR
```

## Modele de permissions

| Couche | Controle |
|--------|----------|
| Bac a sable | Incus-in-Incus = isolation totale |
| Claude Code | bypassPermissions (sur dans le bac a sable) + hook d'audit |
| Flux git | Les agents travaillent sur des branches feature/fix, jamais main |
| Porte humaine | Fusion de la PR = decision humaine |

Le principe cle : autonomie complete dans le bac a sable, approbation
humaine a la frontiere de la production (fusion de la PR).

## Hook d'audit

Chaque invocation d'outil est journalisee par le hook d'audit PreToolUse :

```bash
# Consulter le journal d'audit
cat logs/agent-session-20260212.jsonl | jq .
```

Chaque entree contient :
- Horodatage
- Nom de l'outil (Edit, Bash, Read, etc.)
- Arguments de l'outil

## Configuration du role

| Variable | Defaut | Description |
|----------|--------|-------------|
| `dev_agent_runner_node_version` | `22` | Version de Node.js |
| `dev_agent_runner_permissions_mode` | `bypassPermissions` | Mode Claude Code |
| `dev_agent_runner_git_user` | `anklume Agent` | Auteur des commits git |
| `dev_agent_runner_git_email` | `agent@anklume.local` | Email des commits git |
| `dev_agent_runner_enable_teams` | `true` | Activer Agent Teams |
| `dev_agent_runner_audit_hook` | `true` | Activer la journalisation d'audit |

## Considerations de cout

Les Agent Teams consomment plus de tokens que les sessions individuelles :

| Mode | Cout estime |
|------|------------|
| `agent-fix` (un role) | ~3-8 $ |
| `agent-fix` (tous les roles) | ~15-40 $ |
| `agent-develop` (petite tache) | ~20-60 $ |
| `agent-develop` (phase complete) | ~50-150 $ |

Utilisez `agent-fix` pour les corrections ciblees (cout inferieur) et
`agent-develop` pour l'implementation complete de fonctionnalites (cout
superieur, valeur superieure).

## Relation avec la Phase 13

La Phase 13 (`ai-test-loop.sh`, `ai-develop.sh`) fournit une assistance IA
legere et agnostique du backend via des scripts shell. La Phase 15 fournit
un developpement autonome a pleine puissance via Claude Code Agent Teams.

| Fonctionnalite | Phase 13 | Phase 15 |
|----------------|----------|----------|
| Backends | Ollama, Claude API, Claude Code, Aider | Claude Code uniquement |
| Multi-agent | Non | Oui (Agent Teams) |
| Edition directe de fichiers | Seulement Claude Code + Aider | Oui |
| Isolation par bac a sable | Optionnelle | Requise |
| Cout | Faible a moyen | Moyen a eleve |
| Niveau d'autonomie | Tache unique, agent unique | Multi-taches, equipe |

Les deux phases coexistent. Utilisez la Phase 13 pour les corrections rapides
et la Phase 15 pour les taches de developpement complexes.

## Depannage

### Runner introuvable

```bash
anklume dev runner create     # Creer le container bac a sable
```

### Claude Code non installe

```bash
make agent-runner-setup  # Installer Claude Code dans le runner
```

### Cle API non definie

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Agent Teams ne fonctionne pas

Verifiez le flag de fonctionnalite :

```bash
incus exec anklume -- cat /root/.claude/settings.json | jq .env
```

Devrait afficher `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"`.
