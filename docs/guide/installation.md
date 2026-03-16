# Installation

## Prérequis

| Composant | Version | Usage |
|---|---|---|
| **Linux** | Kernel 5.15+ | Hôte (toute distribution) |
| **Incus** | 6.0+ | Conteneurs LXC et VMs KVM |
| **Ansible** | 2.16+ | Provisioning (optionnel) |

## Installer avec le script quickstart

Le moyen le plus simple d'installer AnKLuMe et ses dépendances :

```bash
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe/host

# Lire le script avant de l'exécuter
less quickstart.sh

# Exécuter
sudo ./quickstart.sh
```

Le script installe automatiquement : Incus, uv, Python, Ansible,
AnKLuMe et l'alias `ank`. Voir [Préparation de l'hôte](host-setup.md)
pour les détails et les options.

## Installer depuis les sources (développement)

```bash
git clone https://github.com/jmchantrein/AnKLuMe.git
cd AnKLuMe
uv sync
```

!!! note "uv"
    [uv](https://docs.astral.sh/uv/) est installé automatiquement par
    les scripts de bootstrap. Pour l'installer manuellement :
    `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Vérification

```bash
anklume --version
incus list        # tableau vide sans erreur
```

## GPU (optionnel)

Pour le passthrough GPU (Ollama, STT, LLM) :

- GPU NVIDIA avec drivers installés
- `nvidia-smi` accessible depuis l'hôte

Le script quickstart peut installer les drivers automatiquement
avec l'option `--gpu` :

```bash
sudo ./quickstart.sh --gpu
```

## Étape suivante

→ [Démarrage rapide](quickstart.md) — créer et déployer un premier projet
