# Golden images

Publier des instances configurées comme images réutilisables.

## Principe

```mermaid
flowchart LR
    I["Instance configurée<br/>pro-dev"] -->|"anklume golden create"| G["Golden image<br/>pro-dev-golden"]
    G -->|"os_image:"| N["Nouvelles instances"]

    style I fill:#3b82f6,color:#fff
    style G fill:#eab308,color:#000
    style N fill:#10b981,color:#fff
```

## Commandes

```bash
# Publier une instance comme image
anklume golden create pro-dev
anklume golden create pro-dev --alias mon-image-dev

# Lister les golden images
anklume golden list

# Supprimer une golden image
anklume golden delete mon-image-dev
```

## Usage

Une fois créée, la golden image peut être utilisée comme `os_image`
dans un fichier domaine :

```yaml
machines:
  dev-clone:
    description: "Clone de l'environnement de dev"
    type: lxc
    os_image: mon-image-dev
```
