# Roadmap anklume

## Phase 1 — Squelette et spécifications ✅

- [x] Archiver le prototype (branche `poc` sur GitHub)
- [x] Reset main avec squelette propre
- [x] CLAUDE.md, SPEC.md, ARCHITECTURE.md rédigés
- [x] CLI Typer avec sous-commandes (apply all/domain, dev, instance)
- [x] `anklume init` produit le format docker-compose-like
- [x] Skills Claude Code (architect, simplify, reviewer, lint, test)
- [x] Cycle d'itération dans CLAUDE.md (démarrage de session)
- [x] Analyse critique architecture + mise à jour docs (nesting POC,
      resource policy, snapshots, dry-run, schema versioning, stateless)

## Phase 2 — Moteur PSOT ✅

- [x] Parser les fichiers domaine (`domains/*.yml`)
- [x] Valider (noms, IPs, trust levels, contraintes)
- [x] Calcul d'adressage automatique
- [x] Vérification `schema_version` + migration
- [x] Tests unitaires exhaustifs pour le moteur (80 tests)

## Phase 3 — Incus driver ✅

- [x] `engine/incus_driver.py` — wrapper typé autour de subprocess
- [x] Réconciliateur (`engine/reconciler.py`) — diff désiré vs réel
- [x] Créer projets Incus depuis les domaines
- [x] Créer réseaux (bridges) avec adressage
- [x] Créer instances (LXC/VM)
- [x] Réconciliation stateless (lire état Incus → comparer → appliquer)
- [x] `--dry-run` (afficher le plan sans appliquer)
- [x] `anklume apply all` / `anklume apply domain <nom>` fonctionnels
- [x] Tests E2E pytest (7 scénarios) + BDD E2E behave (8 scénarios)

## Phase 4 — Snapshots ✅

- [x] `IncusSnapshot` dataclass + méthodes driver (create, list, restore, delete)
- [x] Module `engine/snapshot.py` — logique métier snapshots
- [x] Snapshots automatiques pré/post-apply (intégrés au pipeline)
- [x] `anklume snapshot create [instance] [--name X]`
- [x] `anklume snapshot list [instance]`
- [x] `anklume snapshot restore <instance> <snapshot>`
- [x] Tests unitaires : 27 tests snapshot + 7 tests driver snapshot
- [x] SPEC.md §10 détaillé (nommage, CLI, résolution, driver)

## Phase 5 — Provisioner Ansible ✅

- [x] SPEC §11 détaillé (inventaire, playbook, connexion, rôles, CLI)
- [x] `provisioner/inventory.py` — génération inventaire YAML par domaine
- [x] `provisioner/playbook.py` — génération site.yml + host_vars
- [x] `provisioner/runner.py` — exécution ansible-playbook via subprocess
- [x] Plugin de connexion `anklume_incus` (incus exec, sans dépendance externe)
- [x] Rôles embarqués (base, desktop, dev-tools)
- [x] Support `ansible_roles_custom/` utilisateur (prioritaire sur builtin)
- [x] `--no-provision` flag sur `anklume apply`
- [x] Intégré au pipeline apply (après snapshots post-apply)
- [x] Tests unitaires : 39 tests provisioner
- [x] 205 tests unitaires au total, zéro régression

## Phase 6 — Réseau et sécurité nftables ✅

- [x] Parser `policies.yml` (existant depuis Phase 2 — parser.py + validator.py)
- [x] SPEC §12 détaillé (philosophie, structure nftables, résolution cibles, CLI)
- [x] `engine/nftables.py` — génération ruleset nftables (drop-all + allow sélectif)
- [x] Résolution de cibles : domaine (bridge), machine (bridge + IP), host (commentaire)
- [x] Support : bidirectionnel, UDP, ports "all", domaines désactivés
- [x] `anklume network rules` — affiche le ruleset sur stdout
- [x] `anklume network deploy` — applique via `nft -f`
- [x] Tests unitaires : 30 tests nftables
- [x] 233 tests unitaires au total, zéro régression

## Phase 7 — Nesting Incus ✅

- [x] Tests de nesting (LXC dans LXC, 5 niveaux validés)
- [x] SPEC §8 détaillé (détection, préfixes, contexte, sécurité, module)
- [x] `engine/nesting.py` — NestingContext, préfixes, sécurité, fichiers de contexte
- [x] Détection du contexte via `/etc/anklume/` (absolute_level, relative_level, vm_nested, yolo)
- [x] Préfixe de nesting (`{level:03d}-`) intégré au réconciliateur
- [x] Fichiers de contexte injectés dans les instances après démarrage
- [x] Sécurité par niveau (L0→L1 unprivileged+syscalls, L1+→L2+ privilegié)
- [x] Config explicite machine override la config nesting
- [x] `instance_exec` ajouté au driver Incus
- [x] Tests unitaires : 47 tests nesting + zéro régression réconciliateur
- [x] 280 tests unitaires au total, zéro régression

## Phase 8 — Resource policy ✅

- [x] SPEC §9 détaillé (détection, réserve, algorithme, modes, overcommit, intégration, CLI)
- [x] `engine/resources.py` — détection hardware (Incus + fallback /proc/)
- [x] Allocation proportionnelle/égale par poids (`weight`)
- [x] Réserve hôte (pourcentage ou absolu), overcommit (warning vs erreur)
- [x] Modes CPU : allowance (%) et count (vCPUs fixes)
- [x] Modes mémoire : soft (ballooning) et hard (limite stricte)
- [x] Exclusion des machines avec config explicite (par ressource)
- [x] `apply_resource_config` enrichit machine.config avant réconciliation
- [x] Tests unitaires : 44 tests resource policy
- [x] 325 tests unitaires au total, zéro régression

## Phase 9 — Status et destroy ✅

- [x] SPEC §13 détaillé (status : comparaison déclaré/réel, destroy : protection ephemeral, --force, dry-run)
- [x] `engine/status.py` — compute_status, InfraStatus, DomainStatus, InstanceStatus
- [x] `engine/destroy.py` — destroy, DestroyAction, DestroyResult, protection ephemeral
- [x] Driver Incus : `instance_config_set`, `network_delete`, `project_delete`
- [x] `anklume status` — tableau par domaine (projet, réseau, instances, sync)
- [x] `anklume destroy` — suppression avec respect ephemeral, `--force` pour tout détruire
- [x] Support nesting (préfixes) pour status et destroy
- [x] Dry-run destroy (plan sans exécuter)
- [x] Tests unitaires : 12 tests status + 18 tests destroy
- [x] 364 tests au total, zéro régression

## Phase 10 — Infrastructure IA (GPU, LLM, STT)

Fondations IA : GPU passthrough, services de base (Ollama, Speaches),
gestion VRAM et accès exclusif. Adapté du POC (branche `poc`,
domaine `ai-tools`) vers l'architecture PSOT `domains/*.yml`.

> **Adaptation POC → main** : les scripts shell (`ai-switch.sh`)
> deviennent des modules Python dans `engine/` + commandes CLI Typer.
> Les rôles Ansible passent de `roles/` racine à `provisioner/roles/`
> embarqués. La config `infra.yml` monolithique est remplacée par
> `domains/ai-tools.yml` + `anklume.yml`.

### 10a — GPU passthrough et profils ✅

- [x] SPEC §16 détaillé (GPU : détection, profils, politique, validation)
- [x] `engine/gpu.py` — détection GPU hôte via `nvidia-smi`
  (présence, modèle, VRAM totale/utilisée)
- [x] Validation du flag `gpu: true` sur les machines
  - Erreur si `gpu: true` et aucun GPU détecté sur l'hôte
- [x] Profil Incus `gpu-passthrough` : création automatique si GPU détecté
  - Device `gpu` de type `gpu` avec `gid`/`uid` appropriés
- [x] Politique GPU (`gpu_policy` dans `anklume.yml`) :
  - `exclusive` (défaut) : une seule instance GPU à la fois, erreur sinon
  - `shared` : plusieurs instances partagent le GPU, warning
- [x] Intégration au réconciliateur (profil GPU ajouté à l'instance)
- [x] Driver Incus : `profile_create`, `profile_exists`, `profile_list`, `profile_device_add`
- [x] Parser : `gpu_policy` dans `anklume.yml`
- [x] Modèle : `GpuPolicyConfig` dans `GlobalConfig`
- [x] Tests unitaires : 32 tests (détection, validation, profils, politique, parser)
- [x] 387 tests au total, zéro régression

### 10b — Rôles Ansible IA de base ✅

- [x] SPEC §17 détaillé (rôles IA : variables, tâches, structure, exemples)
- [x] Rôle `ollama_server` (embarqué dans `provisioner/roles/`)
  - Installation via `https://ollama.com/install.sh`
  - Détection GPU runtime (`nvidia-smi`), fallback CPU
  - Service systemd, port configurable (défaut 11434)
  - Pull automatique d'un modèle par défaut au provisioning
- [x] Rôle `stt_server` — Speaches (embarqué)
  - Installation via `uv` depuis les sources
  - API OpenAI-compatible (`/v1/audio/transcriptions`)
  - GPU float16 si disponible, fallback int8 CPU
  - Service systemd, port configurable (défaut 8000)
  - Coexistence avec Ollama sur le même GPU
- [x] Tests unitaires : 32 tests (existence rôles, contenu, playbook, host_vars, inventaire)
- [x] 419 tests au total, zéro régression

### 10c — Domaine ai-tools et accès réseau ✅

- [x] SPEC §18 détaillé (domaine ai-tools, CLI IA, ai status, module ai.py)
- [x] Exemple de domaine `ai-tools` dans `anklume init` (désactivé par défaut)
  - `gpu-server` : `gpu: true`, rôles `[base, ollama_server, stt_server]`
- [x] Politiques réseau commentées (Ollama 11434, STT 8000)
- [x] Sous-commande `anklume ai` (groupe CLI Typer)
- [x] `anklume ai status` — état des services IA :
  - GPU détecté (modèle, VRAM totale/utilisée)
  - Ollama running, modèles chargés (`/api/ps`)
  - STT running (`/v1/models`)
- [x] Module `engine/ai.py` (compute_ai_status, _check_service)
- [x] Tests unitaires : 22 tests (ai status, check service, init ai-tools)
- [x] 441 tests au total, zéro régression

### 10d — Push-to-talk STT (hôte KDE) ✅

Raccourci clavier sur l'hôte pour dicter du texte via Speaches.
Le texte transcrit est collé dans la fenêtre active.
KDE Plasma Wayland uniquement dans un premier temps.

- [x] Script push-to-talk (`host/stt/push-to-talk.sh`)
  - Meta+S (Super+S) en mode toggle :
    1er appui → démarre l'enregistrement (`pw-record`)
    2e appui → arrête, envoie à Speaches, colle le résultat
  - Notification desktop (`notify-send`) : début/fin/erreur
  - Nettoyage des fichiers temporaires (`trap`)
- [x] Détection de la fenêtre active via `kdotool`
  - Terminal détecté → Ctrl+Shift+V (paste terminal)
  - Autre application → Ctrl+V (paste standard)
  - Classes terminales (konsole, Alacritty, kitty, foot, wezterm)
- [x] Support clavier AZERTY (`host/stt/azerty-type.py`)
  - Frappe via `wtype` avec support dead keys
  - Accents (é, è, ê, à, ù, ç), dead keys (^, ¨)
  - Circumflex et diaeresis via dead_circumflex/dead_diaeresis
- [x] Mode streaming temps réel (`host/stt/streaming.py`)
  - Chunks audio ~3s, transcription incrémentale
  - Diff mot-à-mot pour éviter les doublons
  - Filtrage des hallucinations Whisper ("sous-titres", "merci")
  - Détection de silence (RMS), timeouts de sécurité
- [x] `anklume stt setup` — vérifie les dépendances hôte
  (`pw-record`, `wtype`, `wl-copy`, `kdotool`, `jq`, `notify-send`)
  et configure le raccourci KDE Meta+S via `kwriteconfig6`
- [x] `anklume stt status` — état du service STT, dépendances, santé endpoint
- [x] Module `cli/_stt.py` — `get_stt_config()`, `check_stt_dependencies()`, `STT_DEPENDENCIES`
- [x] Configuration : `STT_API_URL`, `STT_MODEL`, `STT_LANGUAGE` (défaut `fr`)
- [x] Tests unitaires : 26 tests (scripts, contenu, config, dépendances)
- [x] 476 tests au total, zéro régression

### 10e — Gestion VRAM et accès exclusif ✅

- [x] `engine/ai.py` — `flush_vram()`, `switch_ai_access()`, `read/write_ai_access()`
  - Déchargement modèles Ollama via `POST /api/generate` avec `keep_alive: 0`
  - Arrêt llama-server via `incus exec ... systemctl stop`
  - Mesure VRAM avant/après (via `detect_gpu()`)
- [x] `anklume ai flush` — décharge tous les modèles Ollama,
  arrête llama-server si actif (libère la VRAM)
- [x] `anklume ai switch <domaine>` — bascule l'accès exclusif GPU :
  1. Valide domaine (existe, activé, politique exclusive)
  2. Flush VRAM
  3. Écriture fichier d'état
- [x] Fichier d'état `/var/lib/anklume/ai-access.json`
  - JSON : domain, timestamp, previous
  - Création auto du répertoire parent
- [x] Champ `ai_access_policy` dans `anklume.yml` + `GlobalConfig` + parser :
  - `exclusive` (défaut) : switch requis
  - `open` : switch désactivé (erreur si appelé)
- [x] `anklume ai status` affiche l'accès GPU courant
- [x] Tests unitaires : 30 tests (flush, switch, state, policy, parser, llama-server)
- [x] 506 tests au total, zéro régression

## Phase 11 — Services IA avancés

Services de haut niveau construits sur la fondation Phase 10 :
interfaces de chat, sanitisation LLM, assistant autonome,
développement assisté par IA.

> **Adaptation POC → main** : chaque service POC (Open WebUI,
> LobeChat, OpenClaw, sanitizer) était un rôle Ansible autonome.
> Ici ils deviennent des rôles embarqués dans `provisioner/roles/`
> avec des variables configurables dans `domains/*.yml` via `vars:`.
> Les scripts de développement IA (`ai-test-loop.sh`) deviennent
> des commandes CLI Python.

### 11a — Interfaces de chat ✅

- [x] SPEC §21 détaillé (rôles chat, variables, tâches, intégration init)
- [x] Rôle `open_webui` (embarqué)
  - Interface web pour Ollama (port 3000)
  - Connexion automatique au serveur Ollama du domaine
  - Service systemd, health check
- [x] Rôle `lobechat` (embarqué)
  - Support multi-providers (Ollama local, OpenRouter cloud)
  - Port configurable (défaut 3210), Node.js, service systemd
- [x] Machines optionnelles commentées dans `anklume init` (ai-webui, ai-chat)
- [x] Politiques réseau : ports 3000, 3210 dans les exemples commentés
- [x] Détection automatique par `anklume ai status` (_SERVICE_DEFS)
- [x] Tests unitaires : 39 tests (rôles, playbook, host_vars, inventaire, CLI, init)
- [x] 545 tests au total, zéro régression

### 11b — Proxy de sanitisation LLM ✅

Anonymise les données sensibles avant envoi à un LLM externe.
Protège contre les fuites d'IPs internes, credentials, noms
de ressources Incus.

- [x] SPEC §22 détaillé (patterns, modes, module, rôle, champ domaine)
- [x] `engine/sanitizer.py` — moteur de détection et remplacement
  - IPs privées RFC 1918 (10.x, 172.16-31.x, 192.168.x)
  - Ressources Incus (instances, bridges) via infra
  - FQDNs internes (*.internal, *.local, *.corp)
  - Credentials (bearer tokens, clés API, patterns key/token/password)
- [x] Modes de remplacement :
  - `mask` : placeholders indexés `[IP_REDACTED_1]`
  - `pseudonymize` : remplacement cohérent dans une session
- [x] `desanitize()` : restauration des valeurs originales
- [x] Rôle `llm_sanitizer` (embarqué) — proxy HTTP (port 8089)
- [x] Tests unitaires : 32 tests (IPs, FQDNs, credentials, resources, modes, rôle)
- [x] 577 tests au total, zéro régression

### 11c — OpenClaw — assistant IA par domaine ✅

Assistant autonome qui monitore et interagit avec l'infrastructure.
Un OpenClaw par domaine, respecte les frontières réseau.

- [x] SPEC §23 détaillé (rôle, variables, configuration, détection)
- [x] Rôle `openclaw_server` (embarqué)
  - SQLite pour données, service systemd
  - Channels configurables (telegram, signal)
  - Heartbeat monitoring (intervalle configurable, défaut 30 min)
  - Connexion Ollama configurable
- [x] Détection automatique par `anklume ai status` (_SERVICE_DEFS)
- [x] Tests unitaires : 19 tests (rôle, playbook, host_vars, service def, ai status)
- [x] 596 tests au total, zéro régression

### 11d — Développement assisté par IA ✅

Outils pour utiliser les LLM dans le workflow de développement
d'anklume lui-même et des projets utilisateur.

- [x] SPEC §24 détaillé (boucle test, rôles, CLI)
- [x] `engine/ai_dev.py` — `AiTestConfig`, `AiTestResult`, `run_ai_test_loop`
  - Modes : dry-run (défaut), auto-apply, auto-pr
  - Backends LLM : Ollama (local), Claude API (remote)
  - Max retries configurable (défaut 3)
  - Validation backend et mode
- [x] `anklume ai test` — commande CLI Typer
  - `--backend ollama|claude`, `--mode dry-run|auto-apply|auto-pr`, `--max-retries N`
- [x] Rôle `code_sandbox` (embarqué)
  - Sandbox isolé, timeout configurable, réseau restreint, filesystem éphémère
- [x] Rôle `opencode_server` (embarqué)
  - Serveur de coding IA headless (port 8091)
- [x] Tests unitaires : 23 tests (rôles, dataclasses, boucle test, CLI)
- [x] 619 tests au total, zéro régression (1 E2E GPU timeout préexistant)

## Phase 12 — STT Voxtype + tests Molecule ✅

(commit 7bbe3db)

## Phase 13 — Routage LLM et intégration sanitiser ✅

Choix du backend LLM (local Ollama, API cloud, abonnement) avec
routage conditionnel via le proxy de sanitisation. Chaque machine
choisit son backend, le sanitizer s'interpose automatiquement
quand requis.

- [x] SPEC §25 détaillé (10 sous-sections : philosophie, config, backends,
  routage, module, enrichissement, rôles, validation, exemples)
- [x] `engine/llm_routing.py` — module de routage LLM
  - `resolve_llm_endpoint()` : résout backend + sanitisation
  - `find_sanitizer_url()` : cherche le proxy (même domaine, cross-domaine)
  - `find_ollama_url()` : cherche Ollama dans l'infra
  - `enrich_llm_vars()` : enrichit les vars machines avant provisioning
  - `validate_llm_config()` : valide backend, ai_sanitize, URL, clé
- [x] Backends supportés : `local` (Ollama), `openai` (OpenAI-compatible
  incluant OpenRouter, Groq, Together, etc.), `anthropic` (Claude API)
- [x] Sanitisation conditionnelle :
  - `ai_sanitize: false` → direct
  - `ai_sanitize: true` → sanitise les requêtes externes uniquement
  - `ai_sanitize: always` → sanitise même le local
- [x] Rôle `openclaw_server` mis à jour (LLM_BACKEND, LLM_URL, LLM_API_KEY, LLM_MODEL)
- [x] Rôle `lobechat` mis à jour (llm_backend, llm_url, llm_api_key)
- [x] Rôle `llm_sanitizer` mis à jour (sanitizer_audit, upstream auto-rempli)
- [x] Pipeline apply : `enrich_llm_vars()` câblé dans `provision()`
  avant `write_host_vars()` — les vars enrichies sont transmises à Ansible
- [x] Tests unitaires : 60 tests (constantes, resolve local/externe/sanitisé,
  find sanitizer/ollama, enrich_llm_vars, rôles, host_vars, validation,
  cross-domaine, scénario OpenRouter, intégration pipeline)
- [x] 683 tests unitaires au total, zéro régression

## Phase 14 — CLI opérationnelle ✅

Commandes essentielles pour l'opérationnel quotidien.

- [x] SPEC §26 détaillé (12 commandes, dataclasses, modules engine, exemples)
- [x] `anklume instance list` — tableau (nom, domaine, état, IP, type)
- [x] `anklume instance exec <instance> -- <cmd>` — exécuter dans une instance
- [x] `anklume instance info <instance>` — détails (config, snapshots, IPs)
- [x] `anklume domain list` — tableau des domaines (état, machines, trust-level)
- [x] `anklume domain check <nom>` — valider un domaine isolément
- [x] `anklume domain exec <nom> -- <cmd>` — exécuter dans toutes les instances
- [x] `anklume domain status <nom>` — état détaillé d'un domaine
- [x] `anklume snapshot delete <instance> <snapshot>` — supprimer un snapshot
- [x] `anklume snapshot rollback <instance> <snapshot>` — rollback destructif
- [x] `anklume network status` — état réseau (bridges, IPs, nftables actives)
- [x] `anklume llm status` — vue dédiée backend LLM, modèles, VRAM
- [x] `anklume llm bench` — benchmark inference (tokens/s, latence)
- [x] `engine/ops.py` — InstanceInfo, DomainInfo, NetworkStatus + fonctions
- [x] `engine/llm_ops.py` — LlmStatus, BenchResult + compute/bench
- [x] `engine/snapshot.py` — rollback_snapshot (restaure + cleanup postérieurs)
- [x] CLI : `_instance.py`, `_domain.py`, `_llm.py` + extensions `_snapshot.py`, `_network.py`
- [x] Tests unitaires : 49 tests (ops, llm_ops, CLI registration, rollback)
- [x] 732 tests unitaires au total, zéro régression

## Phase 15 — Sanitiser avancé

Enrichir le proxy de sanitisation : NER, templates, dry-run, audit.

- [ ] NER sanitizer — backends GLiNER/spaCy en plus du regex
  - MAC addresses, noms Ansible, sockets, commandes Incus
  - Fallback gracieux si NLP indisponible
- [ ] Templates sanitizer — `patterns.yml.j2`, `config.yml.j2`
  - Catégories activables individuellement
  - Génération depuis les variables du rôle
- [ ] `anklume llm sanitize <texte>` — dry-run de sanitisation
- [ ] Audit logging — trace des redactions dans les logs
  - `sanitizer_audit_log_path` configurable

## Phase 16 — Rôle OpenClaw modernisé

Mettre à jour le rôle pour l'OpenClaw actuel (TypeScript, npm,
daemon systemd). Ne pas réinventer la configuration — OpenClaw
gère nativement ses channels, skills et providers.

- [ ] Installation via `npm install -g openclaw@latest`
- [ ] Daemon systemd via `openclaw onboard --install-daemon`
- [ ] Configuration workspace `~/.openclaw/workspace`
- [ ] Variables : `openclaw_version`, `openclaw_channels`, `openclaw_llm_provider`
- [ ] Rôle `admin_bootstrap` — première configuration machine
  (locale, timezone, packages de base, mise à jour)

## Phase 17 — Portails et transferts

Communication hôte ↔ conteneur sans compromettre l'isolation.

- [ ] File portals — transfert fichiers hôte ↔ conteneur
  (`anklume portal push/pull/list`)
- [ ] Clipboard sharing — copier/coller hôte ↔ conteneur
  (`anklume instance clipboard <instance>`)
- [ ] Disposable containers — workflow conteneurs éphémères
  (`anklume disp <image>` — lance, utilise, détruit)
- [ ] Import infra existante — importer depuis un Incus déjà configuré
  (`anklume setup import`)

## Phase 18 — Opérations avancées

- [ ] Golden images — `anklume golden create/derive/publish`
- [ ] Tor gateway — VM routeur transparent Tor
- [ ] tmux console — console colorée par domaine
- [ ] Doctor/health check — `anklume doctor` (diagnostic auto + fix)

## Phase 19 — Qualité et distribution

- [ ] CI/CD — GitHub Actions (lint, ruff, pytest, shellcheck)
- [ ] Documentation — MkDocs, docs fr/en par fonctionnalité
- [ ] i18n — traductions fr.yml, mécanisme gettext
- [ ] Telemetry — métriques d'usage opt-in (`anklume telemetry on/off`)

### En réflexion

- **MCP services** — canal de communication contrôlé pour les instances
  isolées (trust-level `untrusted`). Socket local côté hôte, le
  serveur MCP filtre les requêtes selon la politique. Permet de lire
  des métadonnées (statut, services, snapshots) sans ouvrir de port
  réseau. Valeur de sécurité réelle, mérite spécification dédiée.
- **Desktop integration** — fichiers `.desktop` par instance avec
  couleur trust-level, générés par `anklume apply`. Minimaliste
  ou rien — pas d'usine à gaz.

### Écarté

- ~~Live ISO~~ — hors scope (OS immuable séparé)
- ~~`anklume llm switch`~~ — le routage §25 suffit, pas de bascule runtime
- ~~Rôle `firewall_router`~~ — remplacé par nftables natif
- ~~Rôles Ansible infra (`incus_*`)~~ — géré par le réconciliateur Python
- ~~Labs éducatifs~~ — hors scope
- ~~Plateforme web / dashboard~~ — hors scope
- ~~Modes (user/student/dev)~~ — complexité inutile
- ~~Accessibility~~ — hors scope
- ~~Examples~~ — les docs suffisent
