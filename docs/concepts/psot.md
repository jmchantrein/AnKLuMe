# Modèle PSOT — Source de vérité stateless

PSOT = **Primary Source of Truth**. Les fichiers `domains/*.yml` sont
la source de vérité primaire. Incus est la source de vérité secondaire
(état réel).

## Principe

```mermaid
graph LR
    YAML["domains/*.yml<br/>(état désiré)"] -->|anklume apply| R[Réconciliateur]
    Incus["Incus<br/>(état réel)"] -->|interrogation| R
    R -->|diff| Plan[Plan d'actions]
    Plan -->|exécution| Incus

    style YAML fill:#6366f1,color:#fff
    style R fill:#3b82f6,color:#fff
    style Incus fill:#10b981,color:#fff
```

- **Pas de state file** — le système est stateless par design
- **Idempotent** — relancer `apply` produit le même résultat
- **Git-friendly** — les fichiers domaine sont commités dans git

## Pipeline `anklume apply`

```mermaid
flowchart TD
    A[Lire anklume.yml + domains/*.yml] --> B[Vérifier schema_version]
    B --> C[Valider noms, IPs, contraintes]
    C --> D[Calculer adressage automatique]
    D --> E[Interroger Incus — état réel]
    E --> F[Réconcilier — calculer le diff]
    F --> G{--dry-run ?}
    G -->|oui| H[Afficher le plan]
    G -->|non| I[Snapshots pré-apply]
    I --> J[Exécuter le plan]
    J --> K[Snapshots post-apply]
    K --> L{--no-provision ?}
    L -->|non| M[Provisioning Ansible]
    L -->|oui| N[Rapport final]
    M --> N

    style A fill:#6366f1,color:#fff
    style F fill:#3b82f6,color:#fff
    style J fill:#10b981,color:#fff
    style M fill:#8b5cf6,color:#fff
```

## Réconciliation

Le réconciliateur compare l'état désiré avec l'état réel et produit
un plan d'actions ordonnées :

1. Créer les projets Incus manquants
2. Créer les réseaux (bridges) manquants
3. Créer les instances manquantes
4. Démarrer les instances arrêtées

### Actions

| Verbe | Ressource | Quand |
|---|---|---|
| `create` | projet, réseau, instance | Manquant dans Incus |
| `start` | instance | Existe mais arrêtée |
| `skip` | tout | Déjà dans l'état voulu |

### Best-effort

En cas d'échec partiel (domaine 3/5 échoue) :

- Les domaines indépendants continuent
- Le rapport final indique les succès et échecs
- Un `apply` suivant reprend depuis l'état réel (idempotent)

## Dry-run

```bash
anklume apply all --dry-run
```

Affiche le plan sans l'exécuter :

```
[dry-run] Domaine pro :
  + Créer projet : pro
  + Créer réseau : net-pro (10.120.0.254/24)
  + Créer instance : pro-dev (lxc, images:debian/13)
  + Démarrer instance : pro-dev
```
