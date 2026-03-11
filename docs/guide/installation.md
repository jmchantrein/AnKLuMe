# Installation

## Prérequis

| Composant | Version | Usage |
|---|---|---|
| **Linux** | Kernel 5.15+ | Hôte (toute distribution) |
| **Python** | 3.11+ | Runtime anklume |
| **uv** | 0.4+ | Gestion des dépendances Python |
| **Incus** | 6.0+ | Conteneurs LXC et VMs KVM |
| **Ansible** | 2.16+ | Provisioning (optionnel) |

## Installer anklume

=== "Via uv (recommandé)"

    ```bash
    uv tool install anklume
    ```

=== "Depuis les sources"

    ```bash
    git clone https://github.com/jmchantrein/AnKLuMe.git
    cd AnKLuMe
    uv sync
    ```

## Installer Incus

Suivre la [documentation officielle Incus](https://linuxcontainers.org/incus/docs/main/installing/).

```bash
# Exemple sur Debian/Ubuntu
sudo apt install incus
sudo incus admin init --minimal
```

!!! tip "Vérification"
    ```bash
    incus list
    ```
    Doit retourner un tableau vide sans erreur.

## Installer Ansible (optionnel)

Ansible est nécessaire uniquement si vous utilisez des rôles de
provisioning (`roles:` dans les fichiers domaine).

```bash
uv tool install ansible-core
```

## GPU (optionnel)

Pour le passthrough GPU (Ollama, STT, LLM) :

- GPU NVIDIA avec drivers installés
- `nvidia-smi` accessible depuis l'hôte

```bash
nvidia-smi  # doit afficher le GPU
```
