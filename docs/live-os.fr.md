# Phase 31 : Live OS avec Stockage Persistant Chiffre

> Traduction francaise de [`live-os.md`](live-os.md). En cas de divergence, la version anglaise fait foi.

## Introduction

anklume Live OS permet de faire fonctionner une infrastructure compartimentee depuis un support USB bootable, avec des donnees persistantes chiffrees sur un disque separe. Demarrez sur un live OS, lancez des conteneurs immediatement et conservez l'etat entre les redemarrages.

**Fonctionnalites cles :**
- Demarrage depuis USB (aucune installation requise)
- Disque de donnees chiffre (LUKS + ZFS/BTRFS)
- Mises a jour A/B (atomiques, securisees avec rollback automatique)
- Modele de chiffrement a trois couches pour une securite maximale
- Stockage Incus persistant entre les redemarrages

## Vue d'ensemble de l'architecture

### Organisation du support de demarrage (partitionnement GPT)

```
┌─────────────────────────────────────┐
│ EFI System Partition (512 MB)       │ ANKLUME-EFI
├─────────────────────────────────────┤
│ OS Slot A (1536 MB, squashfs)       │ ANKLUME-OS-A
├─────────────────────────────────────┤
│ OS Slot B (1536 MB, squashfs)       │ ANKLUME-OS-B
├─────────────────────────────────────┤
│ Persistent Boot Config (100 MB)     │ ANKLUME-PERSIST
└─────────────────────────────────────┘
```

- **ANKLUME-EFI** : bootloader systemd-boot, kernel et initramfs
- **ANKLUME-OSA/OSB** : Deux images OS squashfs en lecture seule avec dm-verity
- **ANKLUME-PERSIST** : Partition persistante non chiffree (etat de demarrage, metadonnees du pool ZFS)

### Organisation du disque de donnees (NVMe/SSD separe)

```
┌─────────────────────────────────────┐
│ LUKS Encrypted Container            │ (protege par phrase de passe)
├─────────────────────────────────────┤
│ ZFS/BTRFS Filesystem                │
├─────────────────────────────────────┤
│ • Data volumes                      │
│ • Incus storage pool                │
│ • Container rootfs and layers       │
└─────────────────────────────────────┘
```

## Modele de chiffrement a trois couches

### Couche 1 : Integrite de l'OS (dm-verity)

- Partition OS squashfs en lecture seule avec verification d'integrite cryptographique
- Toute alteration detectee empeche le demarrage
- Arbre de hachage stocke dans ANKLUME-PERSIST
- Veritysetup valide a chaque demarrage

**Ce que cela protege :** kernel de l'OS, systemd, binaires essentiels contre l'alteration

**Overhead :** ~2% de performance (verification de hachage), ~5 Mo de metadonnees par slot OS

### Couche 2 : Donnees au repos (LUKS)

- Chiffrement complet du disque de donnees avec LUKS2
- Protection par phrase de passe ou fichier de cle (configurable au premier demarrage)
- Ouvre vers `/dev/mapper/anklume-data-<pool-name>`
- ZFS/BTRFS monte par-dessus

**Ce que cela protege :** Toutes les donnees utilisateur, systemes de fichiers des conteneurs Incus, stockage persistant

**Overhead :** ~3-5% de performance (chiffrement/dechiffrement), phrase de passe requise au montage

### Couche 3 : Chiffrement de la memoire (optionnel)

- Parametre kernel : `anklume.ram_crypt=1` (necessite AMD SME ou Intel TME)
- Chiffre l'integralite du contenu de la RAM en fonctionnement
- Destruction automatique de la cle a l'arret
- Empeche les attaques par demarrage a froid sur un systeme en cours d'execution

**Ce que cela protege :** Processus des conteneurs, donnees dechiffrees en RAM

**Pre-requis :** CPU avec SME (AMD) ou TME (Intel), support firmware active

## Construction d'une image

### Creer une image Live OS

```bash
cd /path/to/anklume-repo

# Build default image (Debian 13, amd64, 3GB)
anklume live build OUT=anklume-live.img

# Build with custom base OS
anklume live build OUT=custom.img BASE=ubuntu ARCH=arm64

# Output: /path/to/custom.img (ready to write to USB)

# Selectionner l'environnement de bureau
anklume live build OUT=anklume-sway.iso DESKTOP=sway
anklume live build OUT=anklume-kde.iso DESKTOP=kde
```

### Environnements de bureau

Le live OS propose trois environnements de bureau, selectionnables au menu GRUB :

| Bureau | Description | Impact sur la taille |
|--------|-------------|----------------------|
| **sway** (defaut) | Compositeur Wayland tiling, leger | +20 Mo |
| **labwc** | Compositeur Wayland stacking (style Openbox) | +150 Mo |
| **KDE Plasma** | Environnement de bureau complet | +500-700 Mo |
| **minimal** | Console uniquement (terminal foot, pas de compositeur) | 0 |

L'option `--desktop` controle les bureaux inclus dans l'image :

```bash
# Tous les bureaux (defaut)
sudo scripts/build-image.sh --desktop all

# Un seul bureau pour une image plus legere
sudo scripts/build-image.sh --desktop sway

# Console uniquement (image la plus legere)
sudo scripts/build-image.sh --desktop minimal
```

**Raccourcis clavier** communs a sway et labwc :
- `Super+Entree` ouvre un terminal (foot)
- `Super+d` ouvre le lanceur d'applications (fuzzel)
- `Alt+Maj` bascule la disposition clavier (AZERTY/QWERTY)
- Reference complete : `cat /opt/anklume/host/boot/desktop/KEYBINDINGS.txt`

### Guide de bienvenue

Au premier demarrage du bureau, un guide de bienvenue se lance automatiquement :

```bash
# Accessible a tout moment via :
anklume guide                  # Mode TUI (terminal)
anklume welcome WEB=1          # Mode web (navigateur)
```

Le guide propose :
1. **Configurer la persistance** — disque de donnees chiffre (LUKS + ZFS/BTRFS)
2. **Monter un disque existant** — detecter et monter un disque deja configure
3. **Visite guidee** — introduction pas a pas aux commandes anklume
4. **Raccourcis clavier** — reference des raccourcis du bureau

### Flasher sur USB

```bash
# Identify USB device (e.g., /dev/sdX)
lsblk

# Write image (WARNING: destructive)
sudo dd if=anklume-live.img of=/dev/sdX bs=1M status=progress
sudo sync
```

### Processus de construction

1. **debootstrap** de l'OS dans un rootfs temporaire (paquets Debian, systemd, Incus)
2. **Configuration** du kernel, hooks initramfs, services systemd, systemd-boot
3. **Mksquashfs** du rootfs en image OS comprimee en lecture seule (~600 Mo -> ~200 Mo)
4. **Veritysetup** pour generer les hachages d'integrite dm-verity
5. **Sgdisk** pour creer les partitions GPT sur le peripherique USB
6. **Ecriture** de l'EFI, kernel, initramfs, slots OS, partition persistante

**Taille de l'image :** ~1,2 Go sur USB (inclut le bootloader, 2x slots OS, partition persistante)

**Temps de construction :** ~10-15 minutes (depend de la vitesse internet et du CPU)

## Assistant de premier demarrage

Le premier demarrage detecte si le systeme n'a jamais ete initialise :

### Etapes automatiques du premier demarrage

1. **Detection du disque**
   - Liste les peripheriques blocs disponibles
   - Demande a l'utilisateur de selectionner le disque de donnees (ex. `/dev/nvme0n1`)
   - Confirme que ce n'est PAS le peripherique USB de demarrage

2. **Configuration LUKS**
   - Demande la phrase de passe (ou le chemin vers un fichier de cle)
   - Cree le conteneur LUKS2 sur le disque selectionne
   - Prend ~30 secondes

3. **Creation du pool**
   - Demande le nom du pool ZFS ou le point de montage BTRFS
   - Cree le pool sur le peripherique dechiffre
   - Configure la compression (zstd pour ZFS)

4. **Pool de stockage Incus**
   - Configure automatiquement Incus pour utiliser le pool ZFS/BTRFS
   - Met en place le stockage des conteneurs, la mise en cache des images
   - Active les snapshots et le clonage

5. **Drapeau de persistance**
   - Ecrit `/mnt/anklume-persist/pool.conf` (metadonnees du pool)
   - Les demarrages suivants sautent le premier demarrage et montent automatiquement les donnees

### Premier demarrage manuel (si necessaire)

```bash
# If first-boot service fails, run manually:
sudo /opt/anklume/scripts/first-boot.sh --interactive

# Or with defaults:
sudo /opt/anklume/scripts/first-boot.sh \
  --disk /dev/nvme0n1 \
  --pool-name datapool \
  --passphrase-file ~/.anklume-passphrase
```

## Mecanisme de mise a jour A/B

Le Live OS utilise des mises a jour atomiques A/B pour garantir des mises a niveau securisees avec rollback automatique.

### Processus de mise a jour

```bash
# Download and apply update
anklume live update URL=https://example.com/anklume-live-v1.2.img

# Behind the scenes:
# 1. Detects active slot (A or B)
# 2. Downloads new image to inactive slot
# 3. Verifies dm-verity hash
# 4. Resets boot counter to 0
# 5. Reboots into new slot
# 6. If successful, keep new slot
```

### Mise a jour manuelle

```bash
# Check current status
anklume live status
# Output: Active slot: A, Boot count: 0, Data pool: datapool

# Trigger manual update (requires USB write access)
sudo scripts/live-update.sh \
  --url https://cdn.example.com/anklume-v1.2.img \
  --verify-hash 6a3b2c...

# Reboot to apply
sudo reboot
```

## Rollback

Le Live OS effectue automatiquement un rollback si le demarrage echoue 3 fois consecutives.

### Mecanisme du compteur de demarrage

- **Compteur = 0** : Demarrage frais
- **Le compteur s'incremente** a chaque demarrage echoue (watchdog systemd ou manuel)
- **Le compteur atteint 3** : Le kernel bascule sur le slot A/B precedent
- **Le compteur se reinitialise** a 0 apres un demarrage reussi

### Rollback manuel

```bash
# Check current state
sudo scripts/live-os-lib.sh status

# Force rollback to previous slot (requires persist mount)
sudo scripts/live-os-lib.sh set_active_slot B
sudo reboot
```

### Recuperation apres rollback

Si le systeme ne demarre plus apres une mise a jour :

1. Demarrer depuis une cle USB live (ou la meme cle, en selectionnant une version kernel precedente si disponible)
2. Monter la partition persistante : `mount /dev/disk/by-label/ANKLUME-PERSIST /mnt/persist`
3. Verifier l'etat A/B : `cat /mnt/persist/ab-state`
4. Forcer le slot precedent : `echo A > /mnt/persist/ab-state` (si le slot courant est B)
5. Redemarrer

## Mode toram

Le mode toram copie l'integralite de l'OS en RAM, permettant de retirer la cle USB apres le demarrage.

### Activer toram

Ajouter le parametre kernel : `anklume.toram=1`

- Via le bootloader (systemd-boot) : Editer `/boot/loader/entries/default.conf`, ajouter aux options
- Via GRUB : Editer `/etc/default/grub`, ajouter a `GRUB_CMDLINE_LINUX`
- Via la ligne de commande kernel (USB live) : Ajouter a l'invite de demarrage

### Pre-requis

- RAM >= OS_SIZE_MB (typiquement 2-3 Go)
- 30-60 secondes de temps de demarrage supplementaire (copie initiale)

### Avantages

- La cle USB peut etre retiree en toute securite apres le demarrage
- Lectures plus rapides (RAM vs USB 3.0)
- USB reutilisable pour d'autres systemes

### Overhead

- Utilisation RAM : ~1,5-2 Go (l'OS comprime se decompresse en RAM)
- Temps de demarrage : +30-60 secondes (copie unique)

## Considerations de securite

### Securite de la phrase de passe LUKS

- La phrase de passe n'est jamais stockee sur le disque (sauf l'en-tete LUKS, qui est sale et itere)
- L'utilisateur saisit la phrase de passe une fois par demarrage (ou automatise via un fichier de cle)
- Les phrases de passe faibles (< 12 caracteres) sont vulnerables aux attaques par dictionnaire

**Recommandation :** Utiliser une phrase de passe de 16+ caracteres ou un fichier de cle dedie

### Detection d'alteration dm-verity

- Tout changement de bit dans la partition OS est detecte
- Le demarrage echoue avec un message d'erreur
- Empeche l'escalade de privileges par modification du kernel de l'OS

### Chaine de confiance du bootloader

- Le firmware UEFI verifie la signature de systemd-boot (si Secure Boot active)
- systemd-boot verifie le kernel et l'initramfs
- L'initramfs verifie le squashfs OS via dm-verity

**Recommandation :** Activer Secure Boot et ajouter `/boot/EFI/Boot/bootx64.efi` a la liste blanche

### Isolation Incus

- Isolation des conteneurs basee sur les espaces de noms (pas au niveau hyperviseur)
- Necessite des regles nftables pour l'isolation reseau (voir `anklume network rules`)
- La separation par domaines de confiance garantit que les conteneurs non fiables ne peuvent pas acceder au systeme de fichiers d'administration

## Support Arch Linux

anklume Live OS peut etre construit avec Arch Linux comme OS de base, offrant une alternative legere a Debian.

### Construire avec Arch

```bash
# Build Arch-based Live OS image
anklume live build OUT=anklume-arch.img BASE=arch

# Specify architecture
anklume live build OUT=anklume-arch-arm64.img BASE=arch ARCH=arm64
```

### Quand choisir Arch vs Debian

**Arch est recommande pour les machines avec des GPU recents** (NVIDIA 40xx/50xx, AMD RDNA 3/4, Intel Arc).
Arch fournit les derniers Mesa, `linux-firmware` et pilotes kernel nativement, ce qui assure
un support immediat du materiel recent. Debian Stable gele les versions des pilotes au moment de la
publication, ce qui signifie que les GPU sortis apres ce gel manquent souvent de support adequat
(pas d'acceleration Wayland, blobs firmware manquants, repli sur le rendu logiciel).

Cela concerne aussi **l'inference IA locale** : les GPU recents avec support CUDA ou ROCm
peuvent executer de grands modeles de langage (parametres 7B-70B) via Ollama ou llama.cpp. Sans
pilotes a jour, l'acceleration GPU est indisponible et l'inference se replie sur le CPU.
A noter que les petits modeles (parametres 1B-3B) peuvent fonctionner en **CPU uniquement** avec
des performances acceptables sur les processeurs recents (Intel 12e gen+, AMD Zen 4+) grace
aux jeux d'instructions AVX-512 et AMX -- mais les bibliotheques d'inference (llama.cpp, GGML)
doivent etre compilees avec des toolchains recentes pour tirer parti de ces instructions,
ce qu'Arch fournit naturellement tandis que Debian Stable peut livrer des versions anterieures.

Pour les serveurs ou machines sans interface graphique ou le support GPU et l'IA locale ne sont
pas pertinents, Debian Stable reste le choix le plus sur grace a son cycle de mise a jour
previsible et son support de securite plus long.

### Differences cles vs Debian

| Aspect | Arch | Debian |
|--------|------|--------|
| **Bootstrap** | `pacstrap` | `debootstrap` |
| **Initramfs** | `mkinitcpio` | `initramfs-tools` |
| **Cycle de publication** | Rolling release | Instantanes stables |
| **Synchronisation paquets** | Toujours les derniers | Versions figees |
| **Pilotes GPU** | Derniers (Mesa, firmware, kernel) | Geles a la publication |

### Implications du rolling release

- Arch se met a jour frequemment (nouvelles versions kernel, mises a jour glibc)
- Le Live OS herite de l'etat de l'OS de base au moment de la construction
- Recommandation : Reconstruire mensuellement pour integrer les derniers correctifs

### Systeme de fichiers recommande

BTRFS est le choix par defaut recommande pour les images basees sur Arch :

- BTRFS est stable dans le kernel mainline, aucun module externe necessaire
- ZFS necessite le depot `archzfs` et le paquet `zfs-dkms`
- ZFS peut casser lors des mises a jour kernel (rolling release vs compatibilite DKMS)

### Pre-requis sur l'hote

Pour construire des images basees sur Arch depuis un hote CachyOS/Arch :

```bash
sudo pacman -S arch-install-scripts  # provides pacstrap
sudo pacman -S btrfs-progs           # for BTRFS pool creation
```

## Compatibilite Ventoy

Les images anklume Live OS (Arch et Debian) sont entierement compatibles avec [Ventoy](https://www.ventoy.net/), un gestionnaire de demarrage USB qui simplifie les configurations multiboot.

### USB multiboot

Ventoy permet de placer plusieurs fichiers ISO/IMG sur un seul peripherique USB :

```
USB Device (Ventoy):
├── anklume-live-debian.img
├── anklume-live-arch.img
└── other-distro.iso
```

- Un menu de demarrage apparait au lancement ; selectionnez l'OS souhaite
- Pas besoin de reecrire la cle USB pour chaque image

### Independance du disque de donnees

Le disque de donnees chiffre est **completement independant** du support de demarrage :

- Possibilite de demarrer sur l'image Arch un jour, Debian le lendemain, en utilisant le meme disque de donnees
- `mount-data.sh` et `umount-data.sh` sont agnostiques de la distribution
- La phrase de passe LUKS reste valide quel que soit le changement de methode de demarrage
- Les pools ZFS/BTRFS sont automatiquement reconnus au demarrage suivant

### Copie en RAM par defaut

Par defaut, `anklume.toram=1` est actif dans la configuration du bootloader :

- L'OS est copie en RAM au demarrage (~30-60 secondes)
- La cle USB peut etre retiree en toute securite une fois le demarrage termine
- Necessite 2-3 Go de RAM libre

## Sommes de controle

Les constructions anklume Live OS generent automatiquement des sommes de controle SHA256.

### Generation automatique

Pendant la construction, un fichier de somme de controle `.sha256` est cree a cote de l'image :

```
Build output:
├── anklume-live.img          (image file)
└── anklume-live.img.sha256   (checksum file)
```

### Verifier l'integrite de l'image

```bash
# Verify against checksum file
sha256sum -c anklume-live.img.sha256
# Output: anklume-live.img: OK

# Or manually compute and compare
sha256sum anklume-live.img
```

## FAQ / Depannage

### Q : Le demarrage echoue apres une mise a jour

**R :** Le compteur de demarrage a atteint 3, le systeme a effectue un rollback. Verifiez les journaux :
```bash
# Mount old USB boot media
mount /dev/sdX1 /tmp/boot-old

# Check boot counter
cat /mnt/persist/boot-count

# Check dmesg for errors
dmesg | tail -50
```

**Solution :** Reinitialiser le compteur de demarrage et reessayer :
```bash
echo 0 | sudo tee /mnt/persist/boot-count
sudo reboot
```

### Q : Le deverrouillage LUKS echoue avec "No key available"

**R :** Phrase de passe incorrecte ou fichier de cle manquant. Options :

1. Redemarrer et reessayer la phrase de passe
2. Utiliser un fichier de cle different : `sudo cryptsetup luksOpen /dev/nvme0n1 anklume-data --key-file ~/.backup-key`
3. Ajouter une cle de recuperation depuis une sauvegarde (si disponible)

### Q : Le montage des donnees echoue : "zpool import failed"

**R :** Pool ZFS introuvable sur le peripherique dechiffre. Verifier :

```bash
# Verify LUKS device is open
ls -la /dev/mapper/anklume-*

# List pools on device
sudo zpool import -d /dev/mapper/anklume-data

# If found, import manually
sudo zpool import -d /dev/mapper/anklume-data pool-name

# Verify mount
mount | grep anklume
```

### Q : Le mode toram ejecte la cle USB trop tot

**R :** Le kernel est encore en train de lire depuis la cle USB. Attendre le message :
```
[INFO] Copying squashfs to RAM...
[OK] OS copied to RAM, USB can be safely removed
```

**Ne pas ejecter la cle USB pendant la phase de copie.**

### Q : Le systeme demarre en mode degrade (mono-utilisateur)

**R :** Un ou plusieurs services ont echoue. Verifier :

```bash
sudo systemctl status anklume-data-mount.service
sudo systemctl status anklume-first-boot.service
sudo journalctl -u anklume-data-mount -n 50
```

Causes frequentes :
- Disque de donnees non connecte
- Phrase de passe LUKS incorrecte
- Configuration du pool manquante (`/mnt/anklume-persist/pool.conf`)

### Q : Comment sauvegarder la configuration persistante ?

**R :** Sauvegarder `/mnt/anklume-persist/` :

```bash
sudo tar czf anklume-backup.tar.gz /mnt/anklume-persist/
sudo cp anklume-backup.tar.gz ~/backups/
```

Restaurer sur une nouvelle cle USB :
```bash
# After booting new USB, mount old persist
mount /dev/disk/by-label/ANKLUME-PERSIST /tmp/old-persist

# Restore config
sudo tar xzf anklume-backup.tar.gz -C /
```

### Q : Peut-on fonctionner sans chiffrement LUKS ?

**R :** Non recommande, mais techniquement possible :

```bash
# During first-boot, select "none" for encryption
# Data disk will use unencrypted ZFS/BTRFS

# Security implications:
# - Cold-boot attacks possible
# - Data disk readable by anyone with physical access
# - Only use in trusted environments
```

## Obtenir de l'aide

- Consulter les journaux : `sudo journalctl -b` (demarrage courant)
- Verifier les services : `systemctl status | grep anklume`
- Tester le pool : `zpool status` ou `btrfs filesystem show`
- Operations manuelles : Lancer les scripts avec le drapeau `--help`

```bash
/opt/anklume/scripts/first-boot.sh --help
/opt/anklume/scripts/live-update.sh --help
/opt/anklume/scripts/mount-data.sh --help
```
