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

- [x] Tests de nesting (LXC dans LXC, 2 niveaux = cas d'usage réel, 5 niveaux = benchmark de robustesse)
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

## Phase 15 — Sanitiser avancé ✅

Enrichissement du moteur de sanitisation : nouveaux patterns,
NER optionnel, templates Jinja2, CLI dry-run et audit logging.

- [x] SPEC §27 détaillé (patterns, NER, CLI, audit, templates, intégration)
- [x] Patterns supplémentaires dans `engine/sanitizer.py` :
  - MAC addresses (`AA:BB:CC:DD:EE:FF`) — catégorie `mac`
  - Sockets Unix (`/var/run/*.sock`, `/run/*_socket`) — catégorie `socket`
  - Commandes Incus (`incus exec|launch|stop|...`) — catégorie `incus_cmd`
- [x] Filtrage par catégories (`categories={"ip", "mac"}` ou `None` = toutes)
- [x] NER optionnel (GLiNER > spaCy > regex seul) :
  - `detect_ner_backend()` — détection automatique
  - `ner_extract()` — extraction d'entités nommées
  - `sanitize(..., ner=True)` — activation
  - Fallback gracieux si aucun backend disponible
- [x] `anklume llm sanitize <texte>` — dry-run CLI :
  - `--mode mask|pseudonymize`
  - `--ner` (activer NER)
  - `--json` (sortie JSON structurée)
  - `-` pour stdin
- [x] Audit logging (`AuditEntry` dataclass + `audit_log()`) :
  - JSON-lines, création auto des répertoires parents
  - Comptage par catégorie, timestamp ISO 8601
  - `sanitizer_audit_log_path` configurable
- [x] Templates Jinja2 pour le rôle `llm_sanitizer` :
  - `templates/config.yml.j2` — configuration proxy
  - `templates/patterns.yml.j2` — catégories activables
  - Defaults enrichis (`sanitizer_audit_log_path`, `sanitizer_categories`)
  - Tasks mises à jour (déploiement via `ansible.builtin.template`)
- [x] Tests unitaires : 42 nouveaux tests (patterns, catégories, NER,
  audit, CLI, rôle templates)
- [x] 774 tests unitaires au total, zéro régression
  (7 E2E dnsmasq préexistants)

## Phase 16 — Rôle OpenClaw modernisé ✅

Rôle `openclaw_server` mis à jour pour l'OpenClaw actuel
(TypeScript, npm, daemon natif). Nouveau rôle `admin_bootstrap`.

- [x] Installation via `npm install -g openclaw@latest`
- [x] Daemon systemd via `openclaw onboard --install-daemon`
- [x] Configuration workspace `~/.openclaw/workspace`
- [x] Variables : `openclaw_version`, `openclaw_channels`, `openclaw_llm_provider`
- [x] Template systemd override `llm.conf.j2` (variables LLM)
- [x] Rôle `admin_bootstrap` — première configuration machine
  (locale, timezone, packages de base, mise à jour)
- [x] Template `anklume init` mis à jour (ai-assistant commenté)
- [x] SPEC §28 rédigée, §23 mise à jour
- [x] Tests unitaires : 31 nouveaux tests (openclaw + admin_bootstrap)
- [x] 805 tests unitaires au total, zéro régression
  (7 E2E dnsmasq préexistants)

## Phase 17 — Portails et transferts ✅

Communication hôte ↔ conteneur sans compromettre l'isolation.

- [x] SPEC §29 détaillé (portails fichiers, clipboard, disposable, import)
- [x] Driver Incus : `file_push`, `file_pull`, `instance_exec` avec `input`
- [x] `engine/portal.py` — push/pull/list fichiers hôte ↔ conteneur
  - PortalEntry, TransferResult dataclasses
  - Résolution instance → projet via `resolve_instance_project()`
  - Parse `ls -la` pour listing distant
- [x] `engine/clipboard.py` — presse-papiers hôte ↔ conteneur
  - `wl-paste`/`wl-copy` côté hôte (Wayland)
  - Fichier `/tmp/.anklume-clipboard` dans le conteneur
  - ClipboardResult dataclass
- [x] `engine/disposable.py` — conteneurs jetables
  - Nommage `disp-XXXX` (4 hex aléatoires)
  - launch, list, destroy, cleanup
  - DispContainer dataclass
- [x] `engine/import_infra.py` — import infrastructure Incus existante
  - Scan projets, réseaux, instances
  - Génération `domains/*.yml`
  - ScannedDomain, ScannedInstance, ImportResult dataclasses
- [x] CLI : `anklume portal push/pull/list`
- [x] CLI : `anklume instance clipboard --push/--pull`
- [x] CLI : `anklume disp <image> [--list] [--cleanup]`
- [x] CLI : `anklume setup import [--dir]`
- [x] Tests unitaires : 72 nouveaux tests (portal, clipboard, disposable,
  import, driver file, CLI registration)
- [x] 875 tests unitaires au total, zéro régression
  (8 E2E/nesting préexistants)

## Phase 18 — Opérations avancées ✅

- [x] SPEC §30 détaillé (golden images, Tor gateway, tmux console, doctor)
- [x] Golden images — `anklume golden create/list/delete`
  - `engine/golden.py` — GoldenImage, create/list/delete, résolution instance
  - Driver Incus : `IncusImage`, `image_publish`, `image_list`, `image_delete`, `image_alias_exists`
  - CLI : `_golden.py` — `run_golden_create`, `run_golden_list`, `run_golden_delete`
- [x] Tor gateway — VM routeur transparent Tor
  - `engine/tor.py` — TorGateway, `find_tor_gateways`, `validate_tor_config`
  - Rôle Ansible `tor_gateway` (tasks, defaults, templates torrc.j2 + nftables-tor.conf.j2, handlers)
  - CLI : `_tor.py` — `run_tor_status`
- [x] tmux console — console colorée par domaine
  - `engine/console.py` — ConsolePane, ConsoleConfig, `build_console_config`, `launch_console`
  - Couleurs par trust level (admin=rouge, trusted=bleu, semi-trusted=jaune, untrusted=orange, disposable=gris)
  - CLI : `_console.py` — `run_console`, options `--detach` et filtrage par domaine
- [x] Doctor/health check — `anklume doctor` (diagnostic auto + fix)
  - `engine/doctor.py` — CheckResult, DoctorReport, checks (incus, nft, ansible, gpu, domains, networks, golden)
  - CLI : `_doctor.py` — `run_doctor_cmd`, options `--fix` et `--json`
- [x] Tests unitaires : 74 nouveaux tests (golden, tor, console, doctor, CLI registration)
- [x] 949 tests unitaires au total, zéro régression
  (8 E2E/GPU préexistants)

## Phase 19 — Qualité et distribution ✅

- [x] SPEC §31-34 détaillé (CI/CD, i18n, telemetry, documentation)
- [x] CI/CD — GitHub Actions (`.github/workflows/ci.yml`)
  - Jobs : `lint` (ruff check + format), `shellcheck`, `test` (pytest), `build` (uv build)
  - Triggers : push, pull_request
- [x] i18n — internationalisation (§32)
  - `i18n/__init__.py` — `t()`, `set_locale()`, `get_locale()`
  - Catalogues YAML : `fr.yml`, `en.yml` (mêmes clés)
  - Détection locale : `ANKLUME_LANG` > `LANG` > `fr`
  - Interpolation `{variable}`, fallback clé brute
- ~~Telemetry — métriques d'usage opt-in (§33)~~ — supprimée (YAGNI, code mort jamais câblé)
- [x] Documentation — MkDocs (§34)
  - `mkdocs.yml` — Material theme, navigation manuelle
  - `docs/index.md` — page d'accueil avec démarrage rapide
- [x] Tests unitaires : 67 nouveaux tests (i18n, telemetry, CI/CD, MkDocs, CLI)
- [x] 1016 tests unitaires au total, zéro régression
  (7 E2E dnsmasq préexistants)

## Phase 20 — Environnement de développement ✅

Génération automatique de domaines de dev via `anklume dev env`.

- [x] SPEC §35 détaillé (CLI, rôle, module, LXC vs VM, preset, tests)
- [x] `engine/dev_env.py` — DevEnvConfig, generate_dev_domain, generate_dev_policies
  - Génération YAML domaine complet depuis config
  - Politiques réseau pour accès LLM (Ollama, STT)
  - Preset `anklume_self_dev_config()` pour auto-développement
- [x] Rôle Ansible `dev_env` (embarqué) — outillage moderne
  - uv, Node.js, ripgrep, fd, fzf, lazygit, direnv
  - Claude Code CLI, aider (optionnels)
  - Configuration git, utilisateur non-root, paquets extras
- [x] `anklume dev env <name>` — commande CLI Typer
  - `--type lxc|vm`, `--gpu`, `--llm`, `--claude-code`
  - `--mount nom=/chemin` (répétable), `--memory`, `--cpu`
  - `--preset anklume` — self-dev avec toute la chaîne
  - `--llm-backend local|openai|anthropic` — choix du backend LLM
  - `--llm-model <model>` — modèle par défaut
  - `--sanitize false|true|always` — proxy de sanitisation LLM
- [x] Routage LLM intégré (cohérent avec §25 llm_routing.py)
  - Backend local → `ollama_default_model` dans les vars
  - Backend cloud → `llm_backend`, `llm_api_url`, `llm_api_key`, `llm_model`
  - Politiques réseau intelligentes (Ollama distant seulement si pas de GPU local)
- [x] Sanitisation intégrée (cohérent avec §22/27 sanitizer)
  - `--sanitize true|always` → machine `sanitizer` dédiée dans le domaine
  - Rôle `llm_sanitizer` avec mode mask + audit activé
  - Var `ai_sanitize` injectée dans la machine dev
- [x] Tests unitaires : 65 tests (config, domaines, LLM backends,
  sanitisation, politiques, preset, rôle, CLI, validations)
- [x] 1172 tests au total, zéro régression

## Phase 21 — Tests réels en VM KVM ✅

Mécanisme de tests réels dans une VM KVM isolée — anklume teste anklume.
ADR-024.

- [x] `engine/e2e_real.py` — orchestrateur (génération domaine, push source,
  exec pytest, collecte résultats)
  - E2eRealConfig, E2eRealResult dataclasses
  - `generate_e2e_project()` — projet anklume temporaire avec VM sandbox
  - `wait_for_vm_ready()` — attente boot cloud-init
  - `push_source_to_vm()` — tar + file_push + extraction
  - `install_deps_in_vm()` — uv sync dans la VM
  - `run_tests_in_vm()` — pytest via incus exec
- [x] Rôle Ansible `e2e_runner` (embarqué) — provisionne la VM
  - Incus + init minimal, uv, Python, nftables, Ansible, tmux
- [x] `anklume dev test-real` — commande CLI Typer
  - `--keep` conserver la VM après les tests
  - `--filter/-k` filtre pytest
  - `--verbose/-v` sortie complète
  - `--memory`, `--cpu`, `--timeout` configuration VM
- [x] `tests/test_e2e_real.py` — 15 classes de tests marqués `@pytest.mark.real`
  - Driver CRUD réel (projet, réseau, instance, exec)
  - Snapshots (create, list, restore, rollback)
  - Réconciliateur (apply, idempotence, restart)
  - Destroy (protection ephemeral, --force)
  - Status (déclaré vs réel)
  - Nftables (déploiement, vérification nft list)
  - Nesting (injection fichiers de contexte /etc/anklume/)
  - Portal (push/pull fichier)
  - Disposable (lancement, cleanup)
  - Golden images (publish, list, delete)
  - Import infrastructure (scan projets existants)
  - Doctor (diagnostic Incus)
  - Network status (bridges réels)
  - Provisioner Ansible (rôle base réel)
  - Console tmux (build config)
- [x] Tests unitaires : 21 tests (config, génération, parsing, rôle, CLI)
- [x] 22 tests réels E2E marqués `@real` (exécutés dans la VM)
- [x] 1204 tests unitaires au total, zéro régression
  (2 E501 pré-existants dans test_gui.py)

## Phase 22 — TUI interactif ✅

Éditeur visuel en mode terminal (Textual) pour les domaines et politiques.

- [x] SPEC §37 détaillé (architecture, modules, CLI, raccourcis, sérialisation, tests)
- [x] ADR-026 dans ARCHITECTURE.md
- [x] `tui/app.py` — Application Textual master-detail avec onglets
  - Layout : Header + TabbedContent (Domaines, Politiques) + Footer
  - Bindings : Ctrl+S sauver, Ctrl+Q quitter, a/d ajouter/supprimer
  - Sauvegarde YAML (domaines + politiques)
- [x] `tui/widgets/domain_tree.py` — Arbre Tree[NodeData] coloré par trust-level
- [x] `tui/widgets/domain_form.py` — Formulaire domaine (description, trust, enabled, ephemeral)
- [x] `tui/widgets/machine_form.py` — Formulaire machine (type, IP, GPU, GUI, rôles, weight)
  - Détection automatique des rôles Ansible via `BUILTIN_ROLES_DIR`
- [x] `tui/widgets/yaml_preview.py` — Preview YAML live (omission valeurs par défaut)
  - `domain_to_dict()`, `machine_to_dict()` — sérialisation publique
- [x] `tui/widgets/policy_table.py` — Table DataTable + formulaire inline
- [x] `tui/styles/app.tcss` — Thème CSS (trust-level colors, layout, validation)
- [x] `cli/_tui.py` — Point d'entrée CLI avec dépendance optionnelle Textual
- [x] Commande `anklume tui [--project]`
- [x] Documentation MkDocs : `docs/guide/tui.md`
- [x] CLI reference : commande tui ajoutée à `docs/cli/index.md`
- [x] Tests unitaires : 36 tests (sérialisation, parsing, CLI, rôles, NodeData)
- [x] 1240+ tests unitaires au total, zéro régression

## Phase 23 — Workspace layout déclaratif (GUI "tmuxp")

Layout déclaratif du bureau graphique : chaque machine GUI déclare
son bureau virtuel, sa position et son autostart. `anklume workspace load`
restaure l'environnement identique à chaque fois. Gestion de la grille
de bureaux virtuels KDE via DBus.

- [ ] SPEC §36 détaillé (workspace config, grille, kwinrulesrc, CLI, séquence)
- [ ] ADR-025 dans ARCHITECTURE.md
- [ ] `engine/workspace.py` — WorkspaceEntry, WorkspaceLayout, compute_grid_needs,
  resolve_desktop_index, parse_workspace
- [ ] `cli/_workspace.py` — backend KDE (kwinrulesrc + DBus VirtualDesktopManager)
  - `ensure_virtual_desktops()` — crée les desktops manquants
  - `resolve_desktop_uuids()` — mapper [col,row] → UUID
  - `install_workspace_rules()` — kwinrulesrc (desktop + position + couleur trust)
  - `launch_workspace_apps()` — lance les apps via `run_instance_gui()`
- [ ] `anklume workspace load [domaine]` — restaure le layout complet
- [ ] `anklume workspace status` — affiche layout déclaré vs réel
- [ ] `anklume workspace grid` — affiche la grille actuelle
- [ ] `anklume workspace grid --add-cols N --add-rows N` — étend la grille
- [ ] `anklume workspace grid --set CxR` — force la grille
- [ ] Modèle : `WorkspaceConfig` dans Machine, parsing + validation
- [ ] Fusion kwinrulesrc : workspace + couleur trust dans la même règle
- [ ] Tests unitaires : workspace engine + CLI registration + validation
- [ ] Tests réels : grille DBus, kwinrulesrc, lancement apps

## Phase 24 — Audit de cohérence codebase (deep review 1M tokens) ✅

Analyse approfondie de l'ensemble de la codebase en exploitant le
contexte 1M tokens. Objectif : détecter les incohérences, code mort,
duplications, divergences spec/code, et consolider la qualité avant
le passage en production.

- [x] Lecture exhaustive de tous les modules `engine/`, `cli/`, `provisioner/`
- [x] Vérification cohérence SPEC.md ↔ code (§1-§37)
- [x] Vérification cohérence ARCHITECTURE.md (ADRs) ↔ implémentation
- [x] Audit des rôles Ansible embarqués (15 rôles) : tasks, defaults, templates
- [x] Détection de code mort, imports inutilisés, fonctions non appelées
- [x] Détection de duplications cross-modules (patterns copiés-collés)
- [x] Vérification que tous les tests existants passent (1240+ tests)
- [x] Identification des écarts entre bootstrap.sh, quickstart.sh, _setup.py
- [x] Consolidation des fonctions utilitaires dupliquées (find_repo_root, etc.)
- [x] Audit des modèles de données (dataclasses) : champs inutilisés, types incohérents
- [x] Vérification couverture i18n (clés fr.yml ↔ en.yml)
- [x] Corrections et tests pour chaque problème trouvé
  - Fix `test_tui.py` : `pytest.importorskip("textual")` pour dépendance optionnelle
  - Fix `sanitizer.py` : type annotation `callable` → `Callable[[int], str]`
  - 277 tests OK, 3 skipped, ruff propre, zéro régression
- [x] Audit approfondi : 28 CLI modules, 4 provisioner modules, 15 rôles Ansible,
  SPEC.md (37 sections), ARCHITECTURE.md (26 ADRs), scripts shell, TUI, tests
  - SPEC ↔ code : 99% aligné, §6 (table CLI) incomplète
  - ADRs : 100% respectés (26/26)
  - Rôles Ansible : 3 sans defaults, handlers en français, variables externes non documentées
  - TUI : gestion d'erreurs insuffisante (I/O, widget crashes)
  - Scripts shell : duplication confirmée, race conditions push-to-talk.sh
  - Tous les problèmes identifiés → Phase 26

## Phase 25 — Showcase fonctionnel + validation fresh install en VM

Rendre le showcase 100% fonctionnel pour un utilisateur final.
Tests interactifs dans le tmux partagé, corrections itératives,
puis validation complète sur une fresh install simulée en VM KVM.

### 25a — Showcase fonctionnel (tmux partagé) ✅

Tester chaque fonctionnalité du showcase en tant que jmc :

- [x] `ank init showcase` + `ank apply all` — déploiement complet
  - 5 domaines, 20 instances, 56 actions, 0 erreur
- [x] Vérifier chaque domaine : vault, pro, perso, ai-tools, sandbox
- [x] `ank status` — 20/20 instances running, état cohérent
- [x] `ank snapshot create` / `ank snapshot list` / `ank snapshot restore`
- [x] `ank network rules` / `ank network deploy` / `ank network status`
- [x] `ank instance list` / `ank instance exec` / `ank instance info`
- [x] `ank domain list` / `ank domain status`
- [x] `ank portal push/pull` — transfert fichiers OK
- [x] `ank disp` — conteneurs jetables (fix bash→sh fallback)
- [x] `ank doctor` — 15/15 checks OK (GPU RTX PRO 5000 détecté)
- [x] `ank ai status` — GPU + services détectés
- [x] `ank resource show` — allocation proportionnelle correcte
- [x] `ank destroy` — 3 éphémères supprimées, 17 protégées
- [x] `ank destroy --force` — 17 instances, nettoyage complet
- [x] Correction itérative de 5 bugs + tests :
  1. `limits.memory.soft` → `limits.memory` + `limits.memory.enforce=soft`
  2. `incus profile show --format json` → `incus query /1.0/profiles/...`
  3. Proxy GUI PipeWire : `_push_gui_tmpfiles` via tmpfiles.d avant start
  4. Cascade d'erreurs réconciliateur : par instance au lieu du domaine
  5. `ank disp` : fallback `sh` si `bash` absent (Alpine)

### 25b — Validation fresh install en VM KVM ✅

VM KVM Arch Linux (images:archlinux/cloud, 8 CPUs, 16 GB RAM)
avec Incus nested. Validation du cycle complet.

- [x] Créer une VM KVM Arch Linux via Incus
  - `images:archlinux/cloud` avec nesting activé
  - Bridge `incusbr0` + NAT
- [x] Installer Incus + AnKLuMe dans la VM
  - Résolution conflit iptables/iptables-nft (Arch)
  - subuid/subgid pour conteneurs unprivileged
  - `incus admin init --minimal`
  - `uv tool install` avec `SETUPTOOLS_SCM_PRETEND_VERSION`
- [x] Exécuter le showcase complet dans la VM
  - `ank init showcase` + adaptation (pas de GPU)
  - `ank apply all --no-provision` : 50/51 actions OK
  - 19/20 instances running (1 arrêtée = profil audio sans PipeWire)
  - `ank status`, `ank destroy --force` : 20 instances supprimées, 0 erreur
- [x] Finding nftables : `policy drop` bloquait les bridges non-anklume
  → ADR-027, `network_passthrough` (défaut false), CLI enable/disable
- [x] Tests showcase dry-run ajoutés (test_e2e.py, 8 tests)
  - init, parse, validate, addressing, nftables, dry-run, trust-levels, policies
- [x] Tests showcase réels ajoutés (test_e2e_real.py, 3 tests @real)
  - apply + status, snapshot cycle, destroy avec protection
- [ ] Validation complète bootstrap.sh avec ZFS — reporté (nécessite
  disques dédiés)

## Phase 26 — Consolidation (améliorations identifiées en Phase 24)

Corrections de fond issues de l'audit de cohérence. Aucun n'est
bloquant, mais chaque point améliore la maintenabilité.

### ~~26a — Câbler la télémétrie~~ — Supprimée (YAGNI)

Code mort supprimé : `engine/telemetry.py`, `cli/_telemetry.py`,
`AuditEntry`/`audit_log()` dans sanitizer.py, feature flags `experimental`.

### 26b — Factoriser les scripts shell (bootstrap / quickstart) ✅

- [x] Extraire `host/lib/common.sh` (couleurs, check_root, info/warn/error/step)
- [x] Extraire `host/lib/nvidia.sh` (BLACKWELL_IDS, detect_gpu, install_standard, install_blackwell)
- [x] Sourcer ces libs depuis bootstrap.sh, quickstart.sh et faime/postinst.sh
- [x] PKG_INSTALL converti en array bash (plus de word-splitting)
- [x] Fonctions imbriquées extraites en top-level (_resolve_disk_path, _ensure_dataset)
- [x] postinst.sh : `uv tool install` → wrapper `uv run` + ajout check_root
- [ ] Extraire `host/lib/shell-setup.sh` (aliases, completion) — reporté
- [ ] Consolider `_find_anklume_root()` et `_find_project_root()` — reporté

### 26c — Étendre la couverture i18n

Les catalogues `fr.yml` / `en.yml` sont synchronisés (25 clés) mais
90%+ des strings CLI sont encore hardcodées en français.

- [ ] Ajouter les clés manquantes pour les commandes principales
      (snapshot, network, instance, domain, doctor, console, portal)
- [ ] Remplacer les `typer.echo("...")` hardcodés par `typer.echo(t("..."))`
- [ ] Ajouter les messages d'erreur courants au catalogue
- [ ] Test de couverture : vérifier que toutes les clés fr existent en en

### 26d — Consolider les rôles Ansible ✅

- [x] `meta/main.yml` créé pour les 16 rôles (galaxy_info, platforms, dependencies)
- [x] Tags ajoutés à toutes les tâches (install/configure/service)
- [x] Handlers renommés en anglais (ollama, stt, tor_gateway)
- [x] `defaults/main.yml` pour base, desktop, dev-tools (packages paramétrisables)
- [x] `changed_when` conditionnel (stt, e2e_runner, ollama — register + check output)
- [x] `failed_when` amélioré (GPU rc check, `ignore_errors` pip, health check warnings)
- [x] git config → `community.general.git_config` (dev_env)
- [x] Rôle `nodejs/` partagé, référencé via meta dependencies (lobechat, openclaw, dev_env)
- [x] open_webui pip dans virtualenv `/opt/open-webui/venv`
- [ ] Documenter les variables externes `llm_effective_*` — reporté
- [ ] Standardiser templates .j2 vs config inline — reporté

### 26e — Robustifier le TUI ✅

- [x] try-except OSError sur les I/O fichier dans `tui/app.py` `action_save()`
- [x] Guard `is_mounted` dans `DomainForm` et `MachineForm` (load/apply)
- [x] `_clamp_weight()` avec bornes [1, 1000] dans `machine_form.py`
- [x] `contextlib.suppress(OSError)` dans `action_delete_node()` (était FileNotFoundError)
- [x] Tests unitaires : 14 nouveaux tests (weight clamping, form mounted guard)

### 26f — Mettre à jour SPEC §6 ✅

- [x] §6 mis à jour : 76 commandes dans 17 catégories
  (ajout : portails, golden, IA, STT, Tor, workspace, setup, télémétrie,
  rollback, migrate, doctor, disp, console, instance gui/clipboard,
  network passthrough, llm sanitize, dev env/test-real/molecule)

### 26g — Audit global + sécurité + CI hardening ✅

Audit approfondi par technologie (Python, Ansible, Bash, GitHub Actions,
nftables/sécurité, tests/docs) — 5 critiques, 27 importants, 29 suggestions.

- [x] Passphrase ZFS masquée (`openssl -pass fd:3`)
- [x] Actions GitHub épinglées par SHA + permissions `contents: read`
- [x] Règles nftables DNAT prerouting pour routage transparent Tor
- [x] `ports: "all"` respecte le champ `protocol` (meta l4proto)
- [x] Validation `_validate_name()` dans IncusDriver
- [x] Sanitizer enrichi (SSH keys, AWS creds, IPv6, JSON credentials)
- [x] Path traversal renforcé dans portal.py
- [x] Warnings log : nesting privilégié (L2+), GPU shared mode
- [x] Validation dict dans parser (non-dict YAML → ParseError propre)
- [x] CI : matrice Python 3.11+3.12, cache uv, timeouts, persist-credentials
- [x] Workflow `security.yml` (ruff S + pip-audit hebdomadaire)
- [x] `dependabot.yml` (github-actions + pip)
- [x] Ruff étendu C4/SIM/PIE, pyright basic, pytest-cov
- [x] Tests parametrize, edge cases YAML/nftables, coverage dans CI
- [x] mkdocstrings + référence API (`docs/reference/api.md`)

### 26h — Infrastructure safety + DX Claude Code ✅

Protections contre les régressions après `git pull` et optimisations
pour l'auto-évolution LLM du projet.

- [x] nftables intégré dans le pipeline `apply` (plus de `network deploy` séparé)
- [x] `anklume rollback` — restaure les snapshots pre-apply de toutes les instances
- [x] `anklume doctor --drift` — détecte les écarts YAML vs état Incus réel
- [x] `anklume migrate` — placeholder pour migrations de `schema_version`
- [x] `requires_anklume` dans anklume.yml — vérifie la version minimum du tool
- ~~Feature flags `experimental:` dans anklume.yml~~ — supprimés (YAGNI, jamais utilisés)
- [x] Hook PreToolUse commit-bloquant (pytest doit passer avant `git commit`)
- [x] Hook PreToolUse protection fichiers critiques (CLAUDE.md, SPEC, pyproject)
- [x] Hook PostToolUse `ruff format` ajouté
- [x] CLAUDE.md : trigger table (14 mappings source→test), gotchas (6 pièges),
      règle de régression obligatoire
- [x] Skill `/catchup` pour rattraper le contexte après `/clear`
- [x] Coverage ratcheting (`scripts/coverage-ratchet.sh` + `.coverage-threshold`)
- [x] CHANGELOG.md (Keep a Changelog format)

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
