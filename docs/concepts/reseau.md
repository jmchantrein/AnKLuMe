# Réseau et isolation

## Isolation par défaut

Tout le trafic inter-domaines est **bloqué par défaut** via nftables.
Les exceptions sont déclarées explicitement dans `policies.yml`.

```mermaid
graph TD
    subgraph "Domaine pro"
        P1[pro-dev]
        P2[pro-desktop]
    end
    subgraph "Domaine perso"
        S1[perso-web]
    end
    subgraph "Domaine ai-tools"
        A1[gpu-server]
    end

    P1 <-->|"✅ même domaine"| P2
    P1 -.-x|"❌ bloqué par défaut"| S1
    P1 -->|"✅ policy : port 11434"| A1

    style P1 fill:#eab308,color:#000
    style P2 fill:#eab308,color:#000
    style S1 fill:#eab308,color:#000
    style A1 fill:#22c55e,color:#fff
```

## Architecture réseau

Chaque domaine obtient son propre bridge réseau :

```mermaid
graph TB
    subgraph Hôte
        NFT[nftables]
    end

    subgraph "net-pro (10.120.0.0/24)"
        GW1[".254 — passerelle"]
        M1["pro-dev .1"]
        M2["pro-desktop .2"]
    end

    subgraph "net-perso (10.120.1.0/24)"
        GW2[".254 — passerelle"]
        M3["perso-web .1"]
    end

    subgraph "net-ai-tools (10.110.0.0/24)"
        GW3[".254 — passerelle"]
        M4["gpu-server .1"]
    end

    NFT -.-> GW1
    NFT -.-> GW2
    NFT -.-> GW3

    style NFT fill:#ef4444,color:#fff
    style GW1 fill:#6366f1,color:#fff
    style GW2 fill:#6366f1,color:#fff
    style GW3 fill:#6366f1,color:#fff
```

## Politiques réseau

Les exceptions au blocage par défaut sont déclarées dans `policies.yml` :

```yaml
policies:
  - from: pro
    to: ai-tools
    ports: [11434, 3000]
    description: "Pro accède à Ollama et Open WebUI"

  - from: host
    to: shared-dns
    ports: [53]
    protocol: udp
    bidirectional: false
    description: "DNS local"
```

### Champs

| Champ | Défaut | Description |
|---|---|---|
| `from` | requis | Domaine, machine, ou `host` |
| `to` | requis | Domaine ou machine |
| `ports` | requis | Liste de ports ou `all` |
| `protocol` | `tcp` | `tcp` ou `udp` |
| `bidirectional` | `false` | Qui peut initier la connexion |
| `description` | requis | Justification de la politique |

### Bidirectional

- `false` (défaut) — seul `from` peut initier vers `to`
- `true` — les deux parties peuvent initier la connexion

## Commandes réseau

```bash
# Générer les règles nftables (stdout)
anklume network rules

# Appliquer les règles sur l'hôte
anklume network deploy

# État réseau (bridges, IPs, nftables actives)
anklume network status
```

## Génération nftables

anklume génère un ruleset nftables complet :

1. **Drop-all** — tout le trafic inter-domaines est bloqué
2. **Allow sélectif** — une règle par politique déclarée
3. Les cibles sont résolues : domaine → bridge, machine → bridge + IP
