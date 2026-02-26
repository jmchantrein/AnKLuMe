# Images de Référence et Modèles

> Note : En cas de divergence, la version anglaise (`golden-images.md`)
> fait foi.

anklume prend en charge les images de référence (golden images) —
des modèles d'instances pré-provisionnés qui peuvent être clonés
efficacement pour créer de nouvelles instances. Cela permet une
création rapide d'instances et une gestion centralisée des mises à jour.

## Fonctionnement

Une image de référence est simplement une instance Incus avec un
snapshot nommé `pristine`. Le flux de travail est :

1. **Créer** : Provisionner une instance avec les rôles souhaités,
   l'arrêter et créer un snapshot `pristine`
2. **Dériver** : Cloner le snapshot pour créer de nouvelles instances
   via `incus copy` (CoW sur ZFS/Btrfs)
3. **Publier** (optionnel) : Exporter le snapshot en image Incus
   réutilisable, référençable dans `infra.yml` via `os_image`

```
┌──────────────────┐       incus copy       ┌──────────────────┐
│ pro-dev          │  ──────────────────────▶│ pro-dev-clone    │
│ (image ref.)     │     (CoW sur ZFS/Btrfs) │ (dérivée)        │
│                  │                          │                  │
│ snap: pristine   │       incus publish      │                  │
│                  │  ──────────────────────▶ local:golden-pro  │
└──────────────────┘       (image Incus)                        │
```

## Efficacité du Copy-on-Write (CoW)

Avec les backends de stockage ZFS ou Btrfs, `incus copy` crée un
clone CoW du snapshot. Cela signifie :

- **Création instantanée** : la copie est quasi immédiate
- **Utilisation disque minimale** : seules les différences par rapport
  au modèle consomment de l'espace
- **Instances indépendantes** : les modifications du clone n'affectent
  pas le modèle, et inversement

Sur le backend `dir`, `incus copy` effectue une copie complète
(plus lent, utilise tout l'espace disque).

Vérifier votre backend de stockage :

```bash
incus storage list
```

## Démarrage rapide

### 1. Provisionner et créer une image de référence

```bash
# Déployer l'instance avec ses rôles d'abord
anklume domain apply

# Créer l'image de référence (arrêt + snapshot pristine)
anklume golden create pro-dev
```

### 2. Dériver de nouvelles instances

```bash
# Créer un clone depuis l'image de référence
anklume golden derive pro-dev pro-dev-v2

# Démarrer le clone
incus start pro-dev-v2 --project pro
```

### 3. Publier en image réutilisable (optionnel)

```bash
# Publier l'image de référence en image Incus locale
anklume golden publish pro-dev --alias golden-pro

# Utiliser dans infra.yml
# machines:
#   new-instance:
#     os_image: "golden-pro"
```

### 4. Lister les images de référence

```bash
anklume golden list                  # Tous les projets
anklume golden list --project admin    # Projet spécifique
```

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `anklume golden create <nom>` | Arrêter l'instance + créer le snapshot pristine |
| `anklume golden derive <nom> <nouveau>` | Copie CoW depuis pristine |
| `anklume golden publish <nom> --alias <alias>` | Publier en image Incus |
| `anklume golden list` | Lister les instances avec snapshot pristine |

Toutes les cibles acceptent un paramètre optionnel `PROJECT=<projet>`
pour spécifier le projet Incus (détecté automatiquement si omis).

## Propagation des profils

Quand vous modifiez un profil Incus, toutes les instances utilisant
ce profil sont automatiquement mises à jour (comportement natif Incus).
Cela signifie :

- Les images de référence et leurs instances dérivées partagent les profils
- Mettre à jour un profil se propage à toutes les instances dérivées
- Pas besoin de re-dériver après un changement de profil

C'est particulièrement utile pour les limites de ressources, les
configurations de périphériques et les paramètres réseau gérés via
les profils.

## Exemples de flux de travail

### Modèle d'environnement de développement

```bash
# 1. Provisionner un environnement de développement
anklume domain apply pro

# 2. Installer des outils supplémentaires manuellement
incus exec pro-dev --project pro -- apt install -y vim tmux git

# 3. Créer l'image de référence
anklume golden create pro-dev

# 4. Dériver pour chaque développeur
anklume golden derive pro-dev pro-alice
anklume golden derive pro-dev pro-bob
```

### Déploiement de TP pour étudiants

```bash
# 1. Créer une instance de référence pour le TP
anklume domain apply lab

# 2. En faire une image de référence
anklume golden create lab-reference

# 3. Dériver N instances étudiantes
for i in $(seq 1 20); do
    anklume golden derive lab-reference "lab-student-${i}"
done
```

### Cycle de mise à jour

```bash
# 1. Démarrer l'image de référence
incus start pro-dev --project pro

# 2. Appliquer les mises à jour
incus exec pro-dev --project pro -- apt update && apt upgrade -y

# 3. Re-créer l'image de référence (remplace le snapshot pristine)
anklume golden create pro-dev

# 4. Dériver des instances fraîches depuis le modèle mis à jour
anklume golden derive pro-dev pro-dev-updated
```

## Dépannage

### « Instance not found »

Vérifier que l'instance existe et contrôler le projet :

```bash
incus list --all-projects | grep <nom>
```

### L'instance dérivée a une mauvaise configuration réseau

Les instances dérivées conservent la même IP que le modèle. Modifier
l'IP avant de démarrer :

```bash
incus config device override <instance> eth0 ipv4.address=<nouvelle-ip> --project <projet>
```

### Copie complète au lieu du CoW

Si l'utilisation disque est anormalement élevée après la dérivation,
vérifier votre backend de stockage. Le CoW ne fonctionne que sur
ZFS et Btrfs :

```bash
incus storage list
# Chercher "driver: zfs" ou "driver: btrfs"
```

### La publication échoue avec « snapshot not found »

S'assurer que l'instance a un snapshot `pristine` :

```bash
incus snapshot list <instance> --project <projet>
```

Sinon, le créer d'abord :

```bash
anklume golden create <instance>
```
