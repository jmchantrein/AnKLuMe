# anklume

**Framework déclaratif de compartimentalisation d'infrastructure.**

Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.
Provisioning des instances via Ansible (intégré, optionnel pour l'utilisateur).

```mermaid
graph LR
    A[domains/*.yml] -->|anklume apply| B[Incus]
    A -->|anklume apply| C[Ansible]
    B --> D[Projets]
    B --> E[Réseaux]
    B --> F[Instances LXC/VM]
    C --> G[Provisioning]

    style A fill:#6366f1,color:#fff
    style B fill:#3b82f6,color:#fff
    style C fill:#8b5cf6,color:#fff
```

## Principe

Décrivez vos domaines en YAML. Lancez `anklume apply all`. Obtenez des
environnements isolés et reproductibles.

```yaml
# domains/pro.yml
description: "Environnement professionnel"
trust_level: semi-trusted

machines:
  dev:
    description: "Développement"
    type: lxc
    roles: [base, dev-tools]

  desktop:
    description: "Bureau KDE"
    type: lxc
    gpu: true
    roles: [base, desktop]
```

## Démarrage rapide

```bash
# Installer
uv tool install anklume

# Créer un projet
anklume init mon-infra
cd mon-infra

# Déployer
anklume apply all

# Vérifier
anklume status
```

## Fonctionnalités

| Fonctionnalité | Description |
|---|---|
| **Isolation par domaines** | Un projet Incus + sous-réseau + nftables par domaine |
| **PSOT stateless** | Réconciliation sans state file — YAML + Incus = source de vérité |
| **GPU passthrough** | Accès exclusif ou partagé au GPU (Ollama, STT, LLM) |
| **Provisioning Ansible** | Rôles embarqués + rôles custom utilisateur |
| **Snapshots automatiques** | Pré/post-apply, rollback destructif |
| **Nesting Incus** | Conteneurs dans conteneurs (5 niveaux validés) |
| **Réseau nftables** | Drop-all par défaut, politiques déclaratives |
| **Push-to-talk STT** | Dictée vocale via Speaches (KDE Wayland) |
| **Portails fichiers** | Transfert hôte ↔ conteneur sans compromettre l'isolation |
| **Golden images** | Publier des instances comme images réutilisables |

## Architecture

```mermaid
graph TB
    subgraph Hôte Linux
        CLI[CLI Typer]
        Engine[Engine Python]
        Prov[Provisioner Ansible]
    end

    subgraph Incus
        subgraph "Domaine admin"
            A1[admin-mgmt]
        end
        subgraph "Domaine pro"
            P1[pro-dev]
            P2[pro-desktop]
        end
        subgraph "Domaine ai-tools"
            AI1["gpu-server 🎮"]
        end
    end

    NFT[nftables]

    CLI --> Engine
    Engine -->|subprocess| Incus
    Engine --> Prov
    Prov -->|ansible-playbook| Incus
    NFT -.->|isolation| Incus

    style CLI fill:#6366f1,color:#fff
    style Engine fill:#3b82f6,color:#fff
    style Prov fill:#8b5cf6,color:#fff
    style NFT fill:#ef4444,color:#fff
```
