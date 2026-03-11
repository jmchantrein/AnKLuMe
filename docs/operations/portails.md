# Portails et transferts

Communication hôte ↔ conteneur sans compromettre l'isolation.

## Transfert de fichiers

```mermaid
graph LR
    H[Hôte] -->|"anklume portal push"| C[Conteneur]
    C -->|"anklume portal pull"| H

    style H fill:#3b82f6,color:#fff
    style C fill:#10b981,color:#fff
```

```bash
# Envoyer un fichier vers un conteneur
anklume portal push pro-dev ./rapport.pdf /home/user/

# Récupérer un fichier
anklume portal pull pro-dev /home/user/output.txt ./

# Lister les fichiers
anklume portal list pro-dev /home/user/
```

## Presse-papiers

Transfert du presse-papiers entre l'hôte (Wayland) et un conteneur :

```bash
# Hôte → conteneur
anklume instance clipboard --push pro-dev

# Conteneur → hôte
anklume instance clipboard --pull pro-dev
```

Utilise `wl-paste`/`wl-copy` côté hôte et un fichier temporaire
dans le conteneur.

## Conteneurs jetables

Conteneurs éphémères pour des tâches ponctuelles :

```bash
# Lancer un conteneur jetable
anklume disp images:debian/13

# Lister les conteneurs jetables
anklume disp --list

# Supprimer tous les conteneurs jetables
anklume disp --cleanup
```

Nommage : `disp-XXXX` (4 caractères hexadécimaux aléatoires).

## Import d'infrastructure existante

Scanner une infrastructure Incus existante et générer les fichiers
`domains/*.yml` correspondants :

```bash
anklume setup import
anklume setup import --dir mon-infra/
```

Scanne les projets, réseaux et instances Incus et produit une
configuration anklume prête à l'emploi.
