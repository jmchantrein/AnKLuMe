# Integration Bureau

> Note : la version anglaise ([`desktop-integration.md`](desktop-integration.md)) fait reference en cas de divergence.

anklume fournit une integration avec les environnements de bureau pour
les utilisateurs de stations de travail. Les codes couleur par domaine
dans les terminaux et gestionnaires de fenetres donnent un retour visuel
instantane sur le domaine de securite en cours -- le meme modele que les
bordures colorees de QubesOS.

## Demarrage rapide

```bash
make console                    # Console tmux avec panneaux colores
make domain-exec I=pro-dev TERMINAL=1  # Terminal colore par domaine
make clipboard-to I=pro-dev     # Presse-papier hote -> conteneur
make clipboard-from I=pro-dev   # Presse-papier conteneur -> hote
make desktop-config             # Generer les configs Sway/foot/.desktop
make dashboard                  # Dashboard web sur http://localhost:8888
```

## Console tmux (Phase 19a)

La console tmux genere automatiquement une session depuis `infra.yml`
avec des panneaux colores par domaine :

```bash
make console          # Creer et attacher
make console KILL=1   # Recreer la session
make console DRY_RUN=1  # Previsualiser sans creer
```

Les couleurs sont definies **cote serveur** via `select-pane -P 'bg=...'`
-- les conteneurs ne peuvent pas usurper leur identite visuelle (meme
modele de securite que les bordures colorees dom0 de QubesOS).

| Niveau de confiance | Couleur | Code tmux |
|---------------------|---------|-----------|
| admin | Bleu fonce | colour17 |
| trusted | Vert fonce | colour22 |
| semi-trusted | Jaune fonce | colour58 |
| untrusted | Rouge fonce | colour52 |
| disposable | Magenta fonce | colour53 |

Reconnexion : `tmux attach -t anklume`

## Transfert de presse-papier

Partage controle du presse-papier entre l'hote et les conteneurs.
Chaque transfert est une **action explicite de l'utilisateur** -- pas
de synchronisation automatique entre domaines.

```bash
# Presse-papier hote -> conteneur
make clipboard-to I=pro-dev
scripts/clipboard.sh copy-to pro-dev --project pro

# Presse-papier conteneur -> hote
make clipboard-from I=pro-dev
scripts/clipboard.sh copy-from pro-dev --project pro
```

### Fonctionnement

- Utilise `wl-copy`/`wl-paste` (Wayland) ou `xclip`/`xsel` (X11) sur l'hote
- Transfert via `incus file push`/`pull` vers `/tmp/anklume-clipboard`
- Compatible avec les outils MCP `clipboard_get`/`clipboard_set` (Phase 20c)
- Auto-detection du serveur d'affichage et du backend presse-papier

### Modele de securite

- Chaque transfert est une decision consciente de l'utilisateur
- Pas de daemon, pas de synchronisation en arriere-plan, pas de pont automatique
- Chaque direction est une commande separee -- lecture et ecriture sont explicites
- Le conteneur ne peut pas declencher de lectures du presse-papier hote

## Wrapper domain-exec

Lance des commandes dans les conteneurs avec le contexte du domaine :

```bash
# Shell interactif dans le conteneur
make domain-exec I=pro-dev

# Fenetre terminal coloree
make domain-exec I=pro-dev TERMINAL=1

# Executer une commande specifique
scripts/domain-exec.sh pro-dev -- htop

# Terminal colore avec commande specifique
scripts/domain-exec.sh pro-dev --terminal -- firefox
```

### Variables d'environnement

Le wrapper definit ces variables dans le conteneur :

| Variable | Description |
|----------|-------------|
| `ANKLUME_DOMAIN` | Nom du domaine (ex. `pro`) |
| `ANKLUME_TRUST_LEVEL` | Niveau de confiance (ex. `trusted`) |
| `ANKLUME_INSTANCE` | Nom de l'instance (ex. `pro-dev`) |

### Mode terminal

Avec `--terminal`, le wrapper ouvre une nouvelle fenetre terminal avec :
- Titre de fenetre : `[domaine] instance` (ex. `[pro] pro-dev`)
- Couleur de fond correspondant au niveau de confiance du domaine
- Terminaux supportes : foot (Wayland), alacritty, xterm

## Integration environnement de bureau

Generer des extraits de configuration pour les environnements de bureau :

```bash
make desktop-config             # Genere toutes les configurations
python3 scripts/desktop_config.py --sway    # Sway/i3 uniquement
python3 scripts/desktop_config.py --foot    # Terminal foot uniquement
python3 scripts/desktop_config.py --desktop # Entrees .desktop uniquement
```

Les fichiers sont generes dans le repertoire `desktop/`.

### Sway/i3

La configuration generee colorise les bordures de fenetres par domaine :

```
# Dans ~/.config/sway/config (ou config.d/anklume.conf)
default_border pixel 3
for_window [title="^\[admin\]"] border pixel 3
for_window [title="^\[admin\]"] client.focused #3333ff #3333ff #ffffff #3333ff
for_window [title="^\[pro\]"] border pixel 3
for_window [title="^\[pro\]"] client.focused #33cc33 #33cc33 #ffffff #33cc33
```

Les fenetres sont identifiees par patron de titre (defini par
`domain-exec.sh`) ou par patron `app_id` (defini par le mode
`--terminal`).

### Terminal foot

Les profils generes fournissent des fonds colores par domaine :

```ini
# foot --override 'colors.background=#0a0a2a'   # admin (bleu fonce)
# foot --override 'colors.background=#0a1a0a'   # pro (vert fonce)
```

### Entrees .desktop

Fichiers `.desktop` generes pour le lancement rapide depuis les menus
d'applications :

```
~/.local/share/applications/
├── anklume-anklume-instance.desktop
├── anklume-pro-dev.desktop
└── anklume-perso-desktop.desktop
```

Chaque entree lance `domain-exec.sh` avec `--terminal` pour l'instance
correspondante.

## Dashboard Web

Statut de l'infrastructure en direct dans un navigateur :

```bash
make dashboard              # http://localhost:8888
make dashboard PORT=9090    # Port personnalise
make dashboard HOST=0.0.0.0 # Ecouter sur toutes les interfaces
```

### Fonctionnalites

- Statut des instances en temps reel (auto-refresh toutes les 5s via htmx)
- Cartes d'instances colorees par domaine avec badges de niveau de confiance
- Liste des reseaux avec informations de sous-reseau
- Visualisation des politiques reseau
- Aucune dependance Python externe (stdlib `http.server` + htmx CDN)

### Endpoints API

| Endpoint | Description |
|----------|-------------|
| `GET /` | Page principale du dashboard |
| `GET /api/status` | JSON : instances, reseaux, politiques |
| `GET /api/infra` | JSON : infra.yml parse |
| `GET /api/html` | Fragment HTML pour les mises a jour htmx |

### Securite

- **Lecture seule** -- le dashboard ne modifie pas l'infrastructure
- **Local uniquement** par defaut (lie a `127.0.0.1`)
- Utiliser `HOST=0.0.0.0` pour exposer sur le reseau (a utiliser avec precaution)
- Pas d'authentification -- s'appuyer sur le controle d'acces au niveau reseau

## Schema de couleurs

Tous les outils d'integration bureau partagent le meme mapping
niveau de confiance -> couleur :

| Niveau de confiance | Bordure (vif) | Fond (sombre) | Description |
|---------------------|---------------|---------------|-------------|
| admin | `#3333ff` | `#0a0a2a` | Acces systeme complet |
| trusted | `#33cc33` | `#0a1a0a` | Production, personnel |
| semi-trusted | `#cccc33` | `#1a1a0a` | Developpement, tests |
| untrusted | `#cc3333` | `#1a0a0a` | Logiciels risques |
| disposable | `#cc33cc` | `#1a0a1a` | Bacs a sable ephemeres |

Les couleurs sont configurables via `trust_level` dans `infra.yml`
(voir SPEC.md).
