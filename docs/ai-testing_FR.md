# Tests et Developpement Assistes par IA

> Traduction francaise de [`ai-testing.md`](ai-testing.md). En cas de divergence, la version anglaise fait foi.

AnKLuMe supporte optionnellement la correction de tests et le developpement
autonome assistes par IA. Un backend LLM analyse les echecs de tests, propose
des corrections, et les applique optionnellement -- le tout dans le cadre
des garde-fous de securite du projet.

## Modes

| Mode | Valeur | Backend | Description |
|------|--------|---------|-------------|
| Aucun | `none` | -- | Tests Molecule standards, pas d'IA (defaut) |
| Local | `local` | Ollama | LLM local via l'API Ollama |
| Distant | `remote` | Claude API | API cloud avec cle Anthropic |
| Claude Code | `claude-code` | CLI | Claude Code en mode autonome |
| Aider | `aider` | CLI | Aider connecte a Ollama ou une API |

Definissez le mode via une variable d'environnement ou un fichier de configuration :

```bash
export ANKLUME_AI_MODE=local
make ai-test
```

## Demarrage rapide

### Mode test + correction

Executez les tests Molecule et laissez un LLM corriger les echecs :

```bash
# Execution a blanc (defaut) : afficher les corrections proposees sans les appliquer
make ai-test AI_MODE=local

# Appliquer les corrections automatiquement
make ai-test AI_MODE=local DRY_RUN=false

# Tester un seul role
make ai-test-role R=base_system AI_MODE=claude-code
```

### Mode developpement

Laissez un LLM implementer une tache de maniere autonome :

```bash
# Execution a blanc : montrer ce que le LLM ferait
make ai-develop TASK="Add a monitoring role" AI_MODE=claude-code

# Appliquer les changements et executer les tests
make ai-develop TASK="Add a monitoring role" AI_MODE=claude-code DRY_RUN=false
```

## Configuration

### Variables d'environnement

| Variable | Defaut | Description |
|----------|--------|-------------|
| `ANKLUME_AI_MODE` | `none` | Selection du backend IA |
| `ANKLUME_AI_DRY_RUN` | `true` | Afficher les corrections sans les appliquer |
| `ANKLUME_AI_AUTO_PR` | `false` | Creer automatiquement les PRs en cas de succes |
| `ANKLUME_AI_MAX_RETRIES` | `3` | Nombre maximum de tentatives de correction par role |
| `ANKLUME_AI_OLLAMA_URL` | `http://homelab-ai:11434` | URL de l'API Ollama |
| `ANKLUME_AI_OLLAMA_MODEL` | `qwen2.5-coder:32b` | Modele Ollama |
| `ANTHROPIC_API_KEY` | -- | Cle API pour le mode distant |
| `ANKLUME_AI_LOG_DIR` | `logs` | Repertoire des journaux de session |

### Fichier de configuration (optionnel)

Creez `anklume.conf.yml` a la racine du projet :

```yaml
ai:
  mode: none
  ollama_url: "http://homelab-ai:11434"
  ollama_model: "qwen2.5-coder:32b"
  anthropic_api_key: ""
  max_retries: 3
  auto_pr: false
  dry_run: true
```

Les variables d'environnement ont priorite sur le fichier de configuration.

## Garde-fous de securite

AnKLuMe privilegie la securite maximale par defaut :

| Garde-fou | Defaut | Description |
|-----------|--------|-------------|
| `dry_run` | `true` | Le LLM propose, l'humain applique |
| `auto_pr` | `false` | L'humain cree la PR manuellement |
| Tentatives max | 3 | Empeche les boucles de correction infinies |
| Journalisation | Toujours | Transcription complete pour audit |
| Bac a sable | Phase 12 | Incus-in-Incus isole l'execution |

### Modele de confiance progressive

1. Commencer avec `dry_run=true` -- examiner chaque correction proposee
2. Activer `dry_run=false` quand on a confiance dans le backend
3. Activer `auto_pr=true` pour des flux de travail totalement autonomes
4. Utiliser le bac a sable Incus-in-Incus (Phase 12) pour l'isolation

## Configuration des backends

### Local (Ollama)

Necessite une instance Ollama accessible depuis le container admin :

```bash
# Verifier la connectivite
curl http://homelab-ai:11434/api/tags

# Definir le mode
export ANKLUME_AI_MODE=local
export ANKLUME_AI_OLLAMA_URL=http://homelab-ai:11434
export ANKLUME_AI_OLLAMA_MODEL=qwen2.5-coder:32b
```

### Distant (Claude API)

Necessite une cle API Anthropic :

```bash
export ANKLUME_AI_MODE=remote
export ANTHROPIC_API_KEY=sk-ant-...
```

### Claude Code CLI

Necessite que Claude Code soit installe :

```bash
npm install -g @anthropic-ai/claude-code
export ANKLUME_AI_MODE=claude-code
```

Claude Code opere directement sur les fichiers (pas d'extraction de patch necessaire).
Il lit CLAUDE.md pour les conventions du projet.

### Aider

Necessite Aider installe avec un backend Ollama :

```bash
pip install aider-chat
export ANKLUME_AI_MODE=aider
export ANKLUME_AI_OLLAMA_MODEL=qwen2.5-coder:32b
```

## Journaux de session

Chaque session IA produit un fichier journal dans `logs/` :

```
logs/
+-- ai-test-20260212-143022.log          # Transcription de session
+-- ai-test-20260212-143022-base_system-molecule.log  # Sortie des tests
+-- ai-test-20260212-143022-base_system-context.txt   # Contexte envoye au LLM
+-- ai-test-20260212-143022-response.patch            # Reponse du LLM
```

Les journaux ne sont pas commites dans git (ajouter `logs/` a `.gitignore`).

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `make ai-test` | Executer les tests + correction IA (tous les roles) |
| `make ai-test-role R=<nom>` | Test + correction IA pour un role |
| `make ai-develop TASK="..."` | Developpement autonome |

Surcharger les parametres IA via les variables Make :

```bash
make ai-test AI_MODE=local DRY_RUN=false MAX_RETRIES=5
```

## Fonctionnement

### Boucle de test (ai-test-loop.sh)

```
1. Executer molecule test pour chaque role
2. Si le test passe -> role suivant
3. Si le test echoue -> construire le contexte (journal + code source)
4. Envoyer le contexte au backend LLM
5. Le LLM retourne une correction (patch ou modification directe de fichier)
6. Appliquer la correction (si pas en mode a blanc)
7. Re-tester
8. Boucler jusqu'au succes ou au nombre max de tentatives
9. Commiter les corrections reussies
10. Creer optionnellement une PR
```

### Developpement (ai-develop.sh)

```
1. Creer une branche feature (feature/<slug-tache>)
2. Construire le contexte projet (CLAUDE.md + ROADMAP.md + tache)
3. Envoyer au backend LLM
4. Le LLM implemente la tache
5. Executer la suite de tests (pytest + molecule)
6. Si les tests echouent -> reessayer (envoyer le contexte d'echec)
7. Boucler jusqu'au succes ou au nombre max de tentatives
8. Commiter et creer optionnellement une PR
```

## Depannage

### "AI_MODE=none: no automatic fix attempted"

Comportement attendu quand aucun backend IA n'est configure. Definissez
`ANKLUME_AI_MODE` sur un backend valide.

### Connexion Ollama refusee

Verifiez que l'URL Ollama est accessible depuis l'endroit ou vous executez `make ai-test` :

```bash
curl http://homelab-ai:11434/api/tags
```

Si vous executez depuis le container admin, assurez-vous que le domaine homelab
est accessible (necessite l'acces reseau admin->homelab).

### Claude Code introuvable

Installez globalement :

```bash
npm install -g @anthropic-ai/claude-code
```

### Le patch ne s'applique pas proprement

Le patch genere par le LLM peut ne pas correspondre exactement a l'etat actuel
du fichier. En mode a blanc, le patch est sauvegarde pour examen manuel. Verifiez :

```bash
cat logs/ai-test-*-response.patch
```
