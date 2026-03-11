# Niveaux de confiance

Chaque domaine a un **niveau de confiance** (trust level) qui encode
sa posture de sécurité. Ce niveau est visible dans l'adressage IP.

## Les 5 niveaux

```mermaid
graph LR
    A[admin<br/>🔵 100] --> B[trusted<br/>🟢 110]
    B --> C[semi-trusted<br/>🟡 120]
    C --> D[untrusted<br/>🔴 140]
    D --> E[disposable<br/>🟣 150]

    style A fill:#3b82f6,color:#fff
    style B fill:#22c55e,color:#fff
    style C fill:#eab308,color:#000
    style D fill:#ef4444,color:#fff
    style E fill:#a855f7,color:#fff
```

| Niveau | Offset zone | 2e octet | Couleur | Usage |
|---|---|---|---|---|
| `admin` | 0 | 100 | bleu | Gestion infrastructure |
| `trusted` | 10 | 110 | vert | Services de confiance |
| `semi-trusted` | 20 | 120 | jaune | Usage quotidien (défaut) |
| `untrusted` | 40 | 140 | rouge | Logiciels tiers, tests |
| `disposable` | 50 | 150 | magenta | Éphémère, jetable |

## Adressage IP

Les IPs encodent le niveau de confiance dans le deuxième octet :

```
10.<zone_base + zone_offset>.<domain_seq>.<host>/24
```

```mermaid
graph TD
    IP["10.140.0.5"]
    O1["10"] --> O2["140"]
    O2 --> O3["0"]
    O3 --> O4["5"]

    O1 -.- N1["Réseau privé"]
    O2 -.- N2["100 + 40 = untrusted"]
    O3 -.- N3["1er domaine de la zone"]
    O4 -.- N4["5e machine"]

    style O2 fill:#ef4444,color:#fff
```

Depuis `10.140.0.5`, un admin sait immédiatement : zone 140 = 100 + 40
= **untrusted**.

### Convention d'adressage

- `.1` à `.99` — IPs statiques (machines)
- `.100` à `.199` — DHCP
- `.254` — passerelle (bridge)

### Séquencement des domaines

`domain_seq` est auto-assigné alphabétiquement dans chaque zone de
confiance. Le premier domaine `semi-trusted` obtient le sous-réseau
`10.120.0.0/24`, le deuxième `10.120.1.0/24`, etc.

## Impact sur l'isolation

Le niveau de confiance influence :

1. **L'adressage IP** — zones séparées dans l'espace d'adressage
2. **nftables** — tout trafic inter-domaines bloqué par défaut
3. **Couleur KDE** — barre de titre colorée par niveau (identité visuelle)
4. **Protection ephemeral** — `disposable` est éphémère par défaut
