# Diagnostic — `anklume doctor`

Diagnostic automatique de l'environnement avec corrections optionnelles.

## Commandes

```bash
# Diagnostic
anklume doctor

# Diagnostic + corrections automatiques
anklume doctor --fix

# Sortie JSON
anklume doctor --json
```

## Checks effectués

```mermaid
graph TD
    D[anklume doctor]
    D --> C1[Incus installé et fonctionnel]
    D --> C2[nftables disponible]
    D --> C3[Ansible installé]
    D --> C4[GPU détecté]
    D --> C5[Domaines valides]
    D --> C6[Réseaux cohérents]
    D --> C7[Golden images intègres]

    C1 -->|"✅ ou ❌"| R[Rapport]
    C2 --> R
    C3 --> R
    C4 --> R
    C5 --> R
    C6 --> R
    C7 --> R

    style D fill:#6366f1,color:#fff
    style R fill:#10b981,color:#fff
```

| Check | Description | `--fix` |
|---|---|---|
| Incus | Installation et accès | — |
| nftables | Présence de `nft` | — |
| Ansible | Installation | — |
| GPU | Détection `nvidia-smi` | — |
| Domaines | Validation des fichiers YAML | — |
| Réseaux | Cohérence bridges vs domaines | Crée les bridges manquants |
| Golden images | Intégrité des images publiées | Nettoie les images orphelines |
