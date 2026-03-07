# anklume

Framework déclaratif de compartimentalisation d'infrastructure.

Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.

## Installation

```bash
# Prérequis : uv (https://docs.astral.sh/uv/getting-started/installation/)
curl -LsSf https://astral.sh/uv/install.sh | sh

git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe
uv sync
```

## Démarrage rapide

```bash
uv run anklume init mon-infra
cd mon-infra
vim domains/pro.yml
uv run anklume apply all
```

## Développement

```bash
uv sync --group dev
uv run anklume dev setup
uv run anklume dev lint
uv run anklume dev test
```

## Concepts

- **Domaine** — une zone isolée (sous-réseau + projet Incus + N instances)
- **Instance** — un conteneur LXC ou une VM KVM
- **Niveau de confiance** — posture de sécurité encodée dans l'adressage IP

Chaque domaine est décrit dans son propre fichier YAML (`domains/<nom>.yml`),
style docker-compose. `anklume apply all` déploie vers Incus.

## Documentation

- [SPEC.md](docs/SPEC.md) — spécification complète
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — décisions d'architecture
- [ROADMAP.md](docs/ROADMAP.md) — état courant et prochaines étapes

## Licence

AGPL-3.0
