# Nesting Incus

Support du nesting LXC pour les architectures multi-niveaux :
conteneurs dans conteneurs, jusqu'à 5 niveaux validés.

## Principe

```mermaid
graph TD
    L0["L0 — Hôte physique"]
    L1["L1 — Conteneur LXC"]
    L2["L2 — Conteneur dans conteneur"]
    L3["L3 — Niveau 3"]

    L0 -->|"unprivileged + syscalls"| L1
    L1 -->|"privileged (sûr dans unprivileged)"| L2
    L2 -->|"privileged"| L3

    style L0 fill:#3b82f6,color:#fff
    style L1 fill:#6366f1,color:#fff
    style L2 fill:#8b5cf6,color:#fff
    style L3 fill:#a855f7,color:#fff
```

## Contexte de nesting

Au démarrage, anklume détecte son niveau dans la hiérarchie via les
fichiers `/etc/anklume/` :

| Fichier | Description | Exemple L1 |
|---|---|---|
| `absolute_level` | Profondeur absolue (0 = hôte) | `1` |
| `relative_level` | Reset à 0 après frontière VM | `1` |
| `vm_nested` | VM dans la chaîne d'ancêtres | `false` |
| `yolo` | Override des checks de sécurité | `false` |

## Préfixe de nesting

Quand `nesting.prefix: true` (défaut) et `absolute_level > 0`, les
ressources Incus sont préfixées pour éviter les collisions :

| Ressource | Hôte (L0) | Niveau 1 | Niveau 2 |
|---|---|---|---|
| Projet | `pro` | `001-pro` | `002-pro` |
| Bridge | `net-pro` | `001-net-pro` | `002-net-pro` |
| Instance | `pro-dev` | `001-pro-dev` | `002-pro-dev` |

Format : `{level:03d}-`

À L0, aucun préfixe — il sert uniquement aux niveaux imbriqués.

## Sécurité par niveau

```mermaid
graph LR
    L0["L0 → L1"] -->|"unprivileged<br/>+ nesting<br/>+ syscalls intercept"| L1[Conteneur L1]
    L1P["L1+ → L2+"] -->|"privileged<br/>+ nesting"| L2[Conteneur L2+]

    style L0 fill:#3b82f6,color:#fff
    style L1 fill:#10b981,color:#fff
    style L1P fill:#6366f1,color:#fff
    style L2 fill:#10b981,color:#fff
```

| Niveau courant | Configuration des instances créées |
|---|---|
| L0 (hôte) | `security.nesting=true`, `security.syscalls.intercept.mknod=true`, `security.syscalls.intercept.setxattr=true` |
| L1+ (conteneur) | `security.nesting=true`, `security.privileged=true` |

L2+ : conteneurs privilegiés à l'intérieur de conteneurs unprivileged —
sûr par design (recommandation stgraber).

## Fichiers de contexte

Chaque instance créée reçoit 4 fichiers dans `/etc/anklume/` pour que
le prochain niveau puisse détecter son contexte. L'injection est
best-effort (continue si l'instance refuse les commandes).

## Configuration

```yaml
# anklume.yml
nesting:
  prefix: true    # préfixer les ressources par niveau (défaut)
```
