# FAI.me — ISO personnalisée pour AnKLuMe

Créer une ISO d'installation ou live via le service web
[FAI.me](https://fai-project.org/FAIme/) pour tester ou installer
AnKLuMe sur du matériel cible.

## URLs FAI.me

| Type | URL | Usage |
|---|---|---|
| Debian install | [fai-project.org/FAIme/](https://fai-project.org/FAIme/) | Installation hors-ligne sur disque |
| Debian live | [fai-project.org/FAIme/live](https://fai-project.org/FAIme/live) | Test matériel sans toucher au disque |
| Ubuntu / Mint | [fai-project.org/FAIme-ubuntu](https://fai-project.org/FAIme-ubuntu) | Ubuntu 24.04, Mint 22.2 (Xfce) |

## Réglages recommandés

Sur le formulaire web, remplir :

| Champ | Valeur |
|---|---|
| Distribution | **trixie** (Debian) ou **Ubuntu 24.04** |
| Backports / HWE | coché (kernel récent) |
| Non-free firmware | coché |
| Desktop | KDE, GNOME ou Xfce selon préférence |
| SSH server | coché |
| Paquets supplémentaires | `curl git jq tmux build-essential dkms ansible-core zfsutils-linux incus nftables pciutils lshw` |
| Custom script | uploader `postinst.sh` (ce répertoire) |
| Execute during first boot | coché |

## Le postinst.sh

Script exécuté automatiquement au premier boot. Il :

1. Détecte le GPU NVIDIA et installe le driver adapté :
   - GPU pré-Blackwell → `nvidia-driver` depuis les dépôts
   - GPU Blackwell (RTX 50xx) → driver `.run` 570+
2. Configure Incus (storage dir, réseau)
3. Installe AnKLuMe via `uv` + alias `ank`

## Workflow

1. Aller sur l'URL FAI.me correspondante
2. Remplir le formulaire (voir réglages ci-dessus)
3. Uploader `postinst.sh` dans le champ "Custom script"
4. Cliquer sur "Create image" → attendre la génération (~30 min)
5. Télécharger l'ISO, flasher sur clé USB :
   ```bash
   dd if=fai-live-*.iso of=/dev/sdX bs=4M status=progress
   ```
6. Booter → tester GPU (`nvidia-smi`), réseau, stockage
7. Si OK → installer ou lancer `bootstrap.sh`
