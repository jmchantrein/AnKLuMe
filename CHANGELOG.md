# Changelog

Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/).

## [Non publié]

### Supprimé
- refactor: télémétrie supprimée (YAGNI) — code mort jamais câblé
- refactor: feature flags `experimental` supprimés — jamais utilisés
- refactor: AuditEntry/audit_log supprimés du sanitizer — jamais appelés

### Modifié
- docs: repositionnement — outil IaC pour IA sécurisée + enseignement
- docs: suppression des références QubesOS — anklume n'est pas un OS sécurisé
- docs: clarification isolation LXC vs VM (KVM = hyperviseur type 1)
- docs: nesting 2 niveaux = usage réel, 5 niveaux = benchmark
- docs: cas d'usage IA : agents isolés, sanitisation, GPU local

### Sécurité
- fix: passphrase ZFS masquée via openssl fd:3 (plus visible dans /proc)
- fix: actions GitHub épinglées par SHA + permissions contents:read
- feat: règles nftables DNAT pour routage transparent Tor
- feat: validation noms dans IncusDriver (_validate_name)
- feat: sanitizer enrichi (SSH keys, AWS creds, IPv6, JSON credentials)
- fix: path traversal renforcé dans portal.py
- fix: ports="all" respecte le champ protocol dans nftables

### Ajouté
- feat: `anklume rollback` — restaure les snapshots pre-apply de toutes les instances
- feat: `anklume doctor --drift` — détecte les écarts YAML vs état Incus réel
- feat: nftables déployé automatiquement en fin d'apply
- feat: warning GPU shared mode et nesting privilégié
- feat: CI matrice Python 3.11+3.12, cache uv, timeouts, dependabot
- feat: workflow security.yml (ruff S + pip-audit hebdomadaire)
- feat: mkdocstrings + référence API
- feat: hook commit-bloquant (pytest doit passer avant git commit)
- feat: CLAUDE.md trigger table + gotchas + règle de régression

### Amélioré
- refactor: Bash DRY — host/lib/common.sh + host/lib/nvidia.sh (~400 lignes dédupl.)
- refactor: 16 rôles Ansible consolidés (meta, tags, handlers EN, nodejs partagé)
- refactor: ruff étendu C4/SIM/PIE, pyright basic, pytest-cov
- refactor: tests parametrize, edge cases YAML/nftables
