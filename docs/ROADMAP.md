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

### 10a — GPU passthrough et profils

- [ ] SPEC §16 détaillé (GPU : détection, profils, politique, validation)
- [ ] `engine/gpu.py` — détection GPU hôte via `nvidia-smi`
  (présence, modèle, VRAM totale/utilisée)
- [ ] Validation du flag `gpu: true` sur les machines
  - Erreur si `gpu: true` et aucun GPU détecté sur l'hôte
- [ ] Profil Incus `nvidia-compute` : création automatique si GPU détecté
  - Device `gpu` de type `gpu` avec `gid`/`uid` appropriés
- [ ] Politique GPU (`gpu_policy` dans `anklume.yml`) :
  - `exclusive` (défaut) : une seule instance GPU à la fois, erreur sinon
  - `shared` : plusieurs instances partagent le GPU, warning
- [ ] Intégration au réconciliateur (profil GPU ajouté à l'instance)
- [ ] Driver Incus : `profile_create`, `profile_exists`, `profile_list`
- [ ] Tests unitaires : détection, validation, profils, politique

### 10b — Rôles Ansible IA de base

- [ ] Rôle `ollama_server` (embarqué dans `provisioner/roles/`)
  - Installation via `https://ollama.com/install.sh`
  - Détection GPU runtime (`nvidia-smi`), fallback CPU
  - Service systemd, port configurable (défaut 11434)
  - Pull automatique d'un modèle par défaut au provisioning
  - *POC : `roles/ollama_server/` → adapté en rôle embarqué*
- [ ] Rôle `stt_server` — Speaches (embarqué)
  - Installation via `uv` depuis les sources
  - API OpenAI-compatible (`/v1/audio/transcriptions`)
  - GPU float16 si disponible, fallback int8 CPU
  - Service systemd, port configurable (défaut 8000)
  - Coexistence avec Ollama sur le même GPU
  - *POC : `roles/stt_server/` → adapté en rôle embarqué*
- [ ] Tests unitaires : génération inventaire/playbook avec rôles IA

### 10c — Domaine ai-tools et accès réseau

- [ ] Exemple de domaine `ai-tools` dans `anklume init`
  - `gpu-server` : `gpu: true`, rôles `[base, ollama_server, stt_server]`
- [ ] Politiques réseau pour l'accès IA :
  - Accès depuis d'autres domaines vers Ollama (port 11434)
  - Accès depuis l'hôte vers les services IA
- [ ] Sous-commande `anklume ai` (groupe CLI)
- [ ] `anklume ai status` — état des services IA :
  - GPU détecté (modèle, VRAM totale/utilisée)
  - Ollama running, modèles chargés (`/api/ps`)
  - STT running
  - Domaine ayant accès actuellement

### 10d — Push-to-talk STT (hôte KDE)

Raccourci clavier sur l'hôte pour dicter du texte via Speaches.
Le texte transcrit est collé dans la fenêtre active.
KDE Plasma Wayland uniquement dans un premier temps.

- [ ] Script push-to-talk (`host/stt/push-to-talk.sh`)
  - Meta+S (Super+S) en mode toggle :
    1er appui → démarre l'enregistrement (`pw-record`)
    2e appui → arrête, envoie à Speaches, colle le résultat
  - Notification desktop (`notify-send`) : début/fin/erreur
  - Nettoyage des fichiers temporaires (signal handlers)
  - *POC : `host/stt/stt-push-to-talk.sh` → adapté*
- [ ] Détection de la fenêtre active via KWin D-Bus
  - Terminal détecté → Ctrl+Shift+V (paste terminal)
  - Autre application → Ctrl+V (paste standard)
  - Liste des classes terminales (Konsole, Alacritty, kitty, etc.)
- [ ] Support clavier AZERTY (`host/stt/azerty-type.py`)
  - Frappe via `ydotool key` avec keycodes Linux
  - Accents (é, è, ê, à, ù), dead keys (^, ¨)
  - Shift et AltGr pour caractères spéciaux
  - *POC : `host/stt/stt-azerty-type.py` → adapté*
- [ ] Mode streaming temps réel (`host/stt/streaming.py`)
  - Chunks audio ~3s, transcription incrémentale
  - Diff mot-à-mot pour éviter les doublons
  - Filtrage des hallucinations Whisper ("sous-titres", "merci")
  - Détection de silence (RMS), timeouts de sécurité
  - *POC : `host/stt/stt-streaming.py` → adapté*
- [ ] `anklume stt setup` — installe les dépendances hôte
  (`pw-record`, `ydotool`, `wl-copy`, `wl-paste`, `jq`)
  et configure le raccourci KDE (Meta+S)
- [ ] `anklume stt status` — état du service STT, santé endpoint
- [ ] Configuration : `STT_API_URL`, `STT_MODEL`, `STT_LANGUAGE` (défaut `fr`)
- [ ] Tests unitaires : parsing réponse API, détection terminal, AZERTY

### 10e — Gestion VRAM et accès exclusif

- [ ] `engine/ai.py` — logique métier IA (flush, switch, état)
- [ ] `anklume ai flush` — décharge tous les modèles Ollama,
  arrête llama-server si actif (libère la VRAM)
  - *POC : script bash inline → module Python*
- [ ] `anklume ai switch <domaine>` — bascule l'accès exclusif GPU :
  1. Flush VRAM
  2. Mise à jour nftables (bloquer ancien domaine, autoriser nouveau)
  3. Redémarrage services GPU
  4. Log de l'opération
  - *POC : `scripts/ai-switch.sh` → `engine/ai.py` + CLI*
- [ ] Fichier d'état `/var/lib/anklume/ai-access-current`
- [ ] Champ `ai_access_policy` dans `anklume.yml` :
  - `exclusive` (défaut) : un seul domaine accède à ai-tools
  - `open` : tous les domaines autorisés peuvent accéder
- [ ] Tests unitaires : flush, switch, politique d'accès

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

### 11a — Interfaces de chat

- [ ] Rôle `open_webui` (embarqué)
  - Interface web pour Ollama (port 3000)
  - Connexion automatique au serveur Ollama du domaine
  - *POC : `roles/open_webui/` → rôle embarqué*
- [ ] Rôle `lobechat` (embarqué)
  - Support multi-providers (Ollama local, OpenRouter cloud)
  - Port configurable (défaut 3210)
  - *POC : `roles/lobechat/` → rôle embarqué*
- [ ] Machines optionnelles dans le domaine `ai-tools` :
  ```yaml
  ai-webui:
    roles: [base, open_webui]
    vars: { ollama_host: "gpu-server", ollama_port: 11434 }
  ```
- [ ] Politiques réseau : accès navigateur depuis les domaines autorisés

### 11b — Proxy de sanitisation LLM

Anonymise les données sensibles avant envoi à un LLM externe.
Protège contre les fuites d'IPs internes, credentials, noms
de ressources Incus.

- [ ] `engine/sanitizer.py` — moteur de détection et remplacement
  - IPs privées (RFC 1918, zones anklume 10.1xx)
  - Ressources Incus (projets, bridges, instances)
  - FQDNs internes (*.internal, *.corp, *.local)
  - Credentials (bearer tokens, clés API, patterns `key=...`)
  - Identifiants Ansible (group_vars, host_vars)
  - *POC : `roles/llm_sanitizer/` → module Python + rôle*
- [ ] Modes de remplacement :
  - `mask` : `10.120.0.5` → `10.ZONE.SEQ.HOST`
  - `pseudonymize` : remplacement cohérent dans une session
- [ ] Rôle `llm_sanitizer` (embarqué) — proxy HTTP (port 8089)
  - Intercepte les requêtes vers les APIs LLM cloud
  - Audit log des données sanitisées
- [ ] Champ `ai_sanitize` dans le domaine :
  - `false` (défaut pour local), `true`, `always`
- [ ] Tests unitaires : patterns de détection, modes de remplacement

### 11c — OpenClaw — assistant IA par domaine

Assistant autonome qui monitore et interagit avec l'infrastructure.
Un OpenClaw par domaine, respecte les frontières réseau.

- [ ] Rôle `openclaw_server` (embarqué)
  - Self-hosted, SQLite pour mémoire + RAG
  - Channels : Telegram, Signal (configurables via `vars:`)
  - Heartbeat monitoring (intervalle configurable, défaut 30 min)
  - Cron scheduling pour les tâches récurrentes
  - *POC : `roles/openclaw_server/` → rôle embarqué*
- [ ] Configuration dans le domaine :
  ```yaml
  ai-assistant:
    roles: [base, openclaw_server]
    vars:
      openclaw_channels: [telegram]
      openclaw_heartbeat_interval: 30m
      openclaw_ollama_host: "gpu-server"
  ```
- [ ] Politiques réseau : accès à Ollama depuis le domaine assistant
- [ ] Tests unitaires : génération config OpenClaw

### 11d — Développement assisté par IA

Outils pour utiliser les LLM dans le workflow de développement
d'anklume lui-même et des projets utilisateur.

- [ ] `anklume ai test` — boucle test + analyse LLM + fix
  - Modes : dry-run (défaut), auto-apply, auto-PR
  - Backends LLM : Ollama (local), Claude API (remote)
  - Max retries configurable (défaut 3)
  - Session logging complet
  - *POC : `scripts/ai-test-loop.sh` → commande CLI Python*
- [ ] Rôle `code_sandbox` (embarqué)
  - Sandbox isolé pour exécution de code généré par LLM
  - Réseau restreint, filesystem éphémère
  - *POC : `roles/code_sandbox/` → rôle embarqué*
- [ ] Rôle `opencode_server` (embarqué)
  - Serveur de coding IA headless
  - *POC : `roles/opencode_server/` → rôle embarqué*
- [ ] Tests unitaires : boucle de test, génération sandbox

### Reporté (post-Phase 11)
- Live ISO — OS immuable + persistance chiffrée ZFS/BTRFS (`live/`)
- Plateforme web (`platform/`)
- Labs éducatifs (`labs/`)
- Gestion distante via SSH (optionnel)
- Internationalisation (i18n)

### Contraintes Live ISO à respecter dès le core
- Chemins de données configurables
- Storage Incus sur volume chiffré (ZFS pool / BTRFS subvolume)
- `anklume apply all` idempotent (survit aux redémarrages)
- Compatible avec tout mode de boot (installé ou live)
