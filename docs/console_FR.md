# Console tmux — Isolation Visuelle des Domaines (style QubesOS)

> **Note** : Ce document est une traduction de `console.md`. En cas de divergence,
> la version anglaise fait autorité.

anklume génère automatiquement une session tmux depuis `infra.yml` avec
des volets colorés reflétant les niveaux de confiance des domaines, offrant
une isolation visuelle similaire aux bordures colorées de QubesOS.

## Démarrage rapide

```bash
anklume console              # Lancer la console tmux
anklume console --dry-run    # Prévisualiser sans créer la session
anklume console --kill       # Forcer la recréation (tuer la session existante)
```

Ou utiliser le script directement :

```bash
python3 scripts/console.py
python3 scripts/console.py --dry-run
python3 scripts/console.py --kill
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│ session tmux "anklume"                                   │
│ ┌─────────────┐ ┌──────────┐ ┌──────────────────┐      │
│ │ volet bg:bleu│ │ bg:vert  │ │ bg:jaune         │      │
│ │ admin-ctrl   │ │ pro-dev  │ │ perso-desktop    │      │
│ │ incus exec...│ │          │ │                  │      │
│ └─────────────┘ └──────────┘ └──────────────────┘      │
│ [0:admin]  [1:pro]  [2:perso]  [3:homelab]              │
└─────────────────────────────────────────────────────────┘
```

Chaque domaine devient une fenêtre tmux. Chaque machine du domaine devient
un volet dans cette fenêtre. Les couleurs d'arrière-plan des volets sont
définies **côté serveur** par tmux, pas par le conteneur — cela signifie
que les conteneurs ne peuvent pas usurper leur identité visuelle (même
modèle de sécurité que les bordures dom0 de QubesOS).

## Couleurs des niveaux de confiance

| Niveau de confiance | Couleur | Cas d'usage |
|-------------------|---------|-------------|
| `admin` | Bleu foncé (`colour17`) | Domaines administratifs avec accès système complet |
| `trusted` | Vert foncé (`colour22`) | Charges de production, données personnelles |
| `semi-trusted` | Jaune foncé (`colour58`) | Développement, tests, navigation à faible risque |
| `untrusted` | Rouge foncé (`colour52`) | Logiciels non fiables, navigation risquée |
| `disposable` | Magenta foncé (`colour53`) | Bacs à sable éphémères, tâches ponctuelles |

Les couleurs sont définies dans `scripts/console.py` via les dictionnaires
`TRUST_COLORS` et `TRUST_LABELS`.

## Configuration

### Niveau de confiance explicite dans infra.yml

Ajouter `trust_level` à n'importe quel domaine :

```yaml
domains:
  admin:
    description: "Administration"
    subnet_id: 0
    trust_level: admin
    machines:
      sa-admin:
        type: lxc
        ip: "10.100.0.10"

  lab:
    description: "Environnement de laboratoire"
    subnet_id: 1
    trust_level: disposable
    machines:
      lab-web:
        type: lxc
        ip: "10.100.1.10"
```

### Niveau de confiance auto-inféré

Si `trust_level` n'est pas défini, la console l'infère avec ces heuristiques :

1. **Le nom du domaine contient "admin"** → `admin`
2. **`ephemeral: true`** → `disposable`
3. **Par défaut** → `trusted`

Exemple :

```yaml
domains:
  admin:          # Inféré: admin (nom contient "admin")
    subnet_id: 0
    machines: { ... }

  lab:            # Inféré: disposable (ephemeral: true)
    subnet_id: 1
    ephemeral: true
    machines: { ... }

  pro:            # Inféré: trusted (par défaut)
    subnet_id: 2
    machines: { ... }
```

## Reconnexion

La console crée une session tmux persistante nommée `anklume` (configurable
via `--session-name`). Si vous vous détachez ou si votre connexion SSH
tombe, reconnectez-vous avec :

```bash
tmux attach -t anklume
```

Si la session existe déjà, `anklume console` s'y attache au lieu d'en créer
une nouvelle.

## Recréation

Pour forcer la recréation de la session (par exemple, après avoir
ajouté/supprimé des domaines) :

```bash
anklume console --kill
```

Cela tue la session existante et en crée une nouvelle.

## Options de ligne de commande

```bash
python3 scripts/console.py [OPTIONS] [infra_file]

Options:
  infra_file              Chemin vers infra.yml ou infra/ (défaut: auto-détection)
  --dry-run               Afficher la configuration sans créer la session
  --attach                S'attacher à la session après création (défaut)
  --no-attach             Ne pas s'attacher à la session après création
  --session-name NAME     Nom de la session tmux (défaut: anklume)
  --prefix TOUCHE         Touche prefix tmux pour la session (défaut: C-a)
  --kill                  Tuer la session existante avant d'en créer une nouvelle
```

## tmux imbriqué (touche prefix)

La console anklume utilise **`Ctrl-a`** comme touche prefix (au lieu du
`Ctrl-b` par défaut). Cela évite les conflits avec tmux à l'intérieur des
conteneurs :

- **`Ctrl-a`** contrôle la session **extérieure** anklume (changer de
  fenêtre, de volet)
- **`Ctrl-b`** passe directement aux sessions tmux **intérieures** dans
  les conteneurs

C'est essentiel pour les administrateurs système qui utilisent tmux dans
leur workflow quotidien à l'intérieur des conteneurs qu'ils gèrent.

Pour utiliser un prefix différent :

```bash
python3 scripts/console.py --prefix C-q     # Utiliser Ctrl-q
python3 scripts/console.py --prefix C-b     # Prefix standard (pas de confort imbriqué)
```

## Commandes des volets

Chaque volet exécute `incus exec <machine> --project <domain> -- bash`,
ce qui vous donne un shell à l'intérieur de la machine. Toute la communication
passe par le socket Incus (pas le réseau), donc le domaine admin n'a pas
besoin de règles d'accès réseau spéciales.

## Étiquettes de bordure des volets

Chaque volet a une étiquette de bordure affichant `[domain] machine-name`.
Ceci est défini côté serveur par tmux et ne peut pas être usurpé par le
conteneur.

Exemple :

```
┌────────────────────────────┐
│ [admin] sa-admin           │
│ root@sa-admin:~#           │
│                            │
└────────────────────────────┘
```

## Dispositions

Les fenêtres avec plusieurs volets utilisent la disposition `tiled`, qui
distribue les volets uniformément. Vous pouvez changer la disposition après
création avec les raccourcis tmux standards :

- `Ctrl-a Espace` — parcourir les dispositions
- `Ctrl-a Alt-1` — even-horizontal
- `Ctrl-a Alt-2` — even-vertical
- `Ctrl-a Alt-5` — tiled (défaut)

## Navigation

La session anklume utilise `Ctrl-a` comme prefix (voir ci-dessus) :

| Action | Session anklume | tmux interne (dans le conteneur) |
|--------|----------------|----------------------------------|
| Changer de fenêtre | `Ctrl-a 0`, `Ctrl-a 1`, ... | `Ctrl-b 0`, `Ctrl-b 1`, ... |
| Fenêtre suivante | `Ctrl-a n` | `Ctrl-b n` |
| Fenêtre précédente | `Ctrl-a p` | `Ctrl-b p` |
| Changer de volet | `Ctrl-a o` ou `Ctrl-a <flèche>` | `Ctrl-b o` |
| Détacher | `Ctrl-a d` | `Ctrl-b d` |

## Dépannage

### "Session 'anklume' already exists"

Comportement attendu — la console s'attache à la session existante.
Utiliser `KILL=1` pour forcer la recréation.

### Les couleurs des volets ne s'affichent pas

Vérifier que votre terminal supporte 256 couleurs :

```bash
echo $TERM    # Devrait être "screen-256color" ou "tmux-256color" dans tmux
```

Sinon, le définir dans votre `~/.tmux.conf` :

```
set -g default-terminal "tmux-256color"
```

### "incus exec" échoue dans le volet

Vérifier que la machine existe et est en cours d'exécution :

```bash
incus list --all-projects
```

Si la machine n'existe pas encore, exécuter `anklume domain apply` pour créer
l'infrastructure.

### Impossible de s'attacher à la session

Si `tmux attach -t anklume` échoue avec "session not found", la session
a été tuée ou tmux a été redémarré. Exécuter `anklume console` pour la recréer.

### Les étiquettes de bordure des volets ne s'affichent pas

Les étiquettes de bordure des volets nécessitent tmux >= 3.0. Vérifier
votre version :

```bash
tmux -V    # Devrait être "tmux 3.0" ou supérieur
```

Sur les anciennes versions de tmux, la console fonctionne mais les
étiquettes de bordure ne sont pas affichées.

## Exemples

### Utilisation standard

```bash
# Créer et s'attacher à la console
anklume console

# Détacher
Ctrl-a d

# Reconnecter plus tard
tmux attach -t anklume
```

### Prévisualisation en mode dry-run

```bash
anklume console --dry-run
```

Sortie :

```
Session: anklume
  Window [0] admin (trust: admin, color: dark blue)
    Pane: sa-admin → incus exec sa-admin --project admin -- bash
  Window [1] lab (trust: disposable, color: dark magenta)
    Pane: sa-db → incus exec sa-db --project lab -- bash
    Pane: sa-web → incus exec sa-web --project lab -- bash
```

### Nom de session personnalisé

```bash
python3 scripts/console.py --session-name mon-infra
tmux attach -t mon-infra
```

### Création non-interactive

```bash
python3 scripts/console.py --no-attach
# Session créée mais pas attachée — s'attacher plus tard si nécessaire
```

## Dépendances

- Python 3.11+
- `pip install libtmux` (installé via `anklume setup init`)
- tmux >= 3.0 (pour les étiquettes de bordure des volets)

## Modèle de sécurité

Les couleurs sont définies **côté serveur** par tmux en utilisant
`select-pane -P 'bg=...'`. Les conteneurs ne peuvent pas changer la couleur
d'arrière-plan de leur volet ou l'étiquette de bordure, empêchant l'usurpation
visuelle. Cela correspond au modèle de sécurité de QubesOS où les bordures
colorées sont dessinées par dom0 (l'hyperviseur), pas par les invités VM.

Les commandes des volets exécutent `incus exec` via le socket Incus, pas via
le réseau. Pas de clés SSH, pas de trafic réseau entre admin et les domaines.
