# FAI.me — ISO live AnKLuMe pour test matériel

Génère une ISO Debian live personnalisée via [FAI.me](https://fai-project.org/FAIme/live/)
pour tester AnKLuMe sur du matériel cible avant installation.

## Principe

```
build-iso.sh → FAI.me (web) → ISO Debian live → boot USB → test matériel
                                                           → si OK : bootstrap.sh
```

L'ISO inclut :
- Debian trixie + **backports** (kernel récent pour matériel récent)
- Firmware **non-free** (WiFi, GPU)
- Incus, ZFS, Ansible, nftables pré-installés
- Script `postinst.sh` qui détecte et installe le driver NVIDIA :
  - GPU pré-Blackwell → `nvidia-driver` depuis les dépôts
  - GPU Blackwell (RTX 50xx) → driver `.run` 570+ téléchargé automatiquement

## Usage

```bash
# Générer une ISO live KDE (voir la commande sans exécuter)
./build-iso.sh --dry-run

# Lancer la génération sur FAI.me
./build-iso.sh --email moi@example.com

# ISO d'installation (écrit sur le disque — ATTENTION)
./build-iso.sh --install --desktop kde

# Sans bureau (headless)
./build-iso.sh --desktop none
```

## Workflow

1. `./build-iso.sh` → soumet à FAI.me → télécharger l'ISO
2. `dd if=anklume-live.iso of=/dev/sdX bs=4M` → clé USB bootable
3. Booter sur la clé → tester GPU, réseau, stockage
4. Si tout fonctionne → installer ou lancer `bootstrap.sh`

## Fichiers

| Fichier | Rôle |
|---|---|
| `build-iso.sh` | Génère la requête FAI.me (curl) |
| `postinst.sh` | Exécuté au premier boot de l'ISO (NVIDIA + Incus + AnKLuMe) |
