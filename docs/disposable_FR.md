# Instances Jetables

> Traduction francaise de [`disposable.md`](disposable.md). En cas de divergence, la version anglaise fait foi.

anklume supporte les instances a la demande, auto-detruites, en
utilisant le drapeau natif `--ephemeral` d'Incus. Les instances jetables
sont ideales pour les taches ponctuelles, les tests de logiciels non
fiables et les bacs a sable temporaires.

## Fonctionnement

Les instances jetables utilisent le drapeau `--ephemeral` d'Incus au
lancement. Quand une instance ephemere est arretee, Incus la detruit
automatiquement et recupere tout le stockage. Aucun nettoyage manuel
n'est necessaire.

Le nom de l'instance est genere automatiquement avec un horodatage :
`disp-AAAAMMJJ-HHMMSS`.

## Demarrage rapide

```bash
# Lancer une instance jetable et ouvrir un shell
make disp

# Lancer avec une image specifique
make disp IMAGE=images:alpine/3.20

# Lancer dans un domaine/projet specifique
make disp DOMAIN=sandbox

# Executer une commande puis detruire
make disp CMD="apt update && apt upgrade -y"

# Lancer en tant que VM (au lieu d'un conteneur)
make disp VM=1
```

Ou utiliser le script directement :

```bash
scripts/disp.sh                                    # Lancer + ouvrir un shell
scripts/disp.sh --image images:alpine/3.20         # Image differente
scripts/disp.sh --domain sandbox                   # Dans un projet specifique
scripts/disp.sh --cmd "apt update && apt upgrade"  # Commande puis destruction
scripts/disp.sh --console                          # Attacher la console
scripts/disp.sh --no-attach                        # Instance en arriere-plan
scripts/disp.sh --vm                               # Lancer une VM
```

## Options

| Option | Description |
|--------|-------------|
| `--image IMAGE` | Image OS (defaut : depuis `infra.yml` ou `images:debian/13`) |
| `--domain DOMAIN` | Projet/domaine Incus (defaut : `default`) |
| `--cmd CMD` | Executer CMD dans l'instance, puis arreter (auto-destruction) |
| `--console` | Attacher la console au lieu du shell |
| `--no-attach` | Lancer sans s'attacher (arriere-plan) |
| `--vm` | Lancer en tant que VM KVM au lieu d'un conteneur LXC |
| `-h, --help` | Afficher l'aide |

## Image par defaut

Le script lit `default_os_image` depuis `infra.yml` (ou `infra/base.yml`
en mode repertoire) pour determiner l'image par defaut. Si aucun
`infra.yml` n'est trouve, il se rabat sur `images:debian/13`.

## Modes de fonctionnement

### Shell interactif (defaut)

```bash
scripts/disp.sh
```

Lance l'instance et attache un shell bash (se rabat sur sh si bash
n'est pas disponible). Quand vous quittez le shell, l'instance est
arretee et auto-detruite.

### Mode commande

```bash
scripts/disp.sh --cmd "curl -sL https://example.com | sha256sum"
```

Lance l'instance, execute la commande et arrete l'instance
(auto-destruction). Utile pour les taches ponctuelles.

### Mode console

```bash
scripts/disp.sh --console
```

Attache la console Incus (console serie). Detacher avec `Ctrl+a q`.

### Mode arriere-plan

```bash
scripts/disp.sh --no-attach
```

Lance l'instance sans s'attacher. Le script affiche le nom de
l'instance et les instructions de connexion. Arretez l'instance pour
la detruire.

## Notes de securite

- Les instances jetables sont executees dans le projet `default` sauf
  si un `--domain` est specifie. Utilisez `--domain` pour les placer
  dans un domaine avec l'isolation reseau appropriee.
- Les instances ephemeres sont completement detruites a l'arret —
  aucune donnee ne persiste.
- Si vous devez conserver des fichiers, copiez-les avec `incus file pull`
  avant d'arreter l'instance.
- Le mode VM (`--vm`) offre une isolation plus forte que les conteneurs
  LXC.
- Le nom de l'instance inclut un horodatage, facilitant l'identification
  du moment de creation de chaque instance jetable.

## Cible Makefile

```makefile
make disp [IMAGE=...] [CMD=...] [DOMAIN=...] [VM=1]
```

| Variable | Defaut | Description |
|----------|--------|-------------|
| `IMAGE` | Depuis `infra.yml` | Image OS a utiliser |
| `CMD` | *(aucun)* | Commande a executer puis detruire |
| `DOMAIN` | `default` | Projet/domaine Incus |
| `VM` | *(non defini)* | Definir a `1` pour le mode VM |

## Depannage

### "Cannot connect to the Incus daemon"

Verifiez qu'Incus est installe et en cours d'execution :

```bash
incus version
systemctl status incus
```

Si vous executez depuis un conteneur, assurez-vous que le socket Incus
est monte.

### "Project not found"

Le domaine specifie doit exister en tant que projet Incus. Listez les
projets disponibles :

```bash
incus project list
```

### Instance non detruite apres l'arret

Verifiez que l'instance a ete creee avec `--ephemeral` :

```bash
incus info <nom-instance> | grep Ephemeral
```

Si `Ephemeral: false`, l'instance n'a pas ete creee avec le drapeau
`--ephemeral`.
