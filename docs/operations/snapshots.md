# Snapshots

## Snapshots automatiques

anklume crée automatiquement des snapshots lors de `anklume apply` :

```mermaid
flowchart LR
    Pre["Snapshot pré-apply<br/>(instances existantes)"] --> Apply[Exécution du plan]
    Apply --> Post["Snapshot post-apply<br/>(instances modifiées/créées)"]

    style Pre fill:#eab308,color:#000
    style Apply fill:#3b82f6,color:#fff
    style Post fill:#22c55e,color:#fff
```

### Nommage

Format automatique : `anklume-{pre|post}-{YYYYMMDD-HHMMSS}`

## Commandes

```bash
# Snapshotter toutes les instances
anklume snapshot create

# Snapshotter une instance
anklume snapshot create pro-dev

# Snapshot avec nom personnalisé
anklume snapshot create pro-dev --name avant-migration

# Lister les snapshots
anklume snapshot list
anklume snapshot list pro-dev

# Restaurer un snapshot
anklume snapshot restore pro-dev anklume-pre-20240301-120000

# Supprimer un snapshot
anklume snapshot delete pro-dev anklume-pre-20240301-120000

# Rollback destructif (restaure + supprime les snapshots postérieurs)
anklume snapshot rollback pro-dev anklume-pre-20240301-120000
```

## Rollback destructif

`rollback` restaure un snapshot et **supprime tous les snapshots
postérieurs**. Utile pour revenir à un état connu et nettoyer
l'historique.

```mermaid
graph LR
    S1["snap-1 ✅"] --> S2["snap-2 ✅"] --> S3["snap-3 🎯<br/>rollback ici"] --> S4["snap-4 ❌"] --> S5["snap-5 ❌"]

    style S3 fill:#eab308,color:#000
    style S4 fill:#ef4444,color:#fff
    style S5 fill:#ef4444,color:#fff
```

## Protection ephemeral

Les instances avec `ephemeral: false` (défaut) ont
`security.protection.delete=true`. Les snapshots respectent
cette protection.
