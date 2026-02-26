# Transfert de fichiers et sauvegarde

> **Note** : La version anglaise (`file-transfer.md`) fait foi en cas de
> divergence.

anklume fournit un transfert de fichiers controle entre instances et
une sauvegarde/restauration chiffree via `scripts/transfer.sh`.

## Demarrage rapide

### Copier un fichier entre instances

```bash
anklume portal copy pro-dev:/etc/hosts perso-desktop:/tmp/hosts
```

### Sauvegarder une instance

```bash
anklume backup create anklume-instance
anklume backup create anklume-instance --gpg user@example.com
anklume backup create anklume-instance --output /mnt/external
```

### Restaurer depuis une sauvegarde

```bash
anklume backup restore --file backups/anklume-instance-20260214-120000.tar.gz
anklume backup restore --file backups/anklume-instance.tar.gz.gpg --name admin-v2 --project anklume
```

## Commandes

### copy

Copie un fichier d'une instance vers une autre en utilisant les
operations de fichiers Incus. Le script resout automatiquement chaque
instance vers son projet Incus.

```bash
scripts/transfer.sh copy <src_instance:/chemin> <dst_instance:/chemin>
```

La copie est effectuee via un pipe :

```
incus file pull <src> - | incus file push - <dst>
```

Le contenu du fichier transite par le conteneur anklume (ou l'endroit
ou le script est execute) mais n'est jamais ecrit sur le disque de
l'hote.

**Exemples** :

```bash
# Copier un fichier de config de pro vers anklume
scripts/transfer.sh copy pro-dev:/etc/nginx/nginx.conf anklume-instance:/tmp/nginx.conf

# Copier un log vers perso pour analyse
scripts/transfer.sh copy homelab-ai:/var/log/ollama.log perso-desktop:/tmp/ollama.log
```

### backup

Exporte une instance vers une archive compressee avec chiffrement GPG
optionnel.

```bash
scripts/transfer.sh backup [options] <instance>
```

**Options** :

| Option | Description |
|--------|-------------|
| `--gpg-recipient ID` | Chiffrer avec une cle publique GPG |
| `--output DIR` | Repertoire de sortie (defaut : `backups/`) |
| `--force` | Ecraser un fichier de sauvegarde existant |

La sauvegarde utilise `incus export` qui cree une archive complete de
l'instance (rootfs, configuration, snapshots). Le nom de fichier suit
le format `<instance>-AAAAMMJJ-HHMMSS.tar.gz`.

**Exemples** :

```bash
# Sauvegarde simple
scripts/transfer.sh backup anklume-instance

# Sauvegarde chiffree
scripts/transfer.sh backup --gpg-recipient admin@example.com anklume-instance

# Repertoire de sortie personnalise
scripts/transfer.sh backup --output /mnt/backup homelab-ai
```

### restore

Importe une instance depuis une archive de sauvegarde. Supporte les
fichiers chiffres GPG (extension `.gpg` detectee automatiquement).

```bash
scripts/transfer.sh restore [options] <fichier-de-sauvegarde>
```

**Options** :

| Option | Description |
|--------|-------------|
| `--name NOM` | Importer avec un nom d'instance different |
| `--project PROJET` | Projet Incus cible |
| `--force` | Forcer l'import |

Les sauvegardes chiffrees GPG (extension `.gpg`) sont automatiquement
dechiffrees avant l'import. Le fichier dechiffre est supprime apres
un import reussi.

**Exemples** :

```bash
# Restaurer depuis une sauvegarde
scripts/transfer.sh restore backups/anklume-instance-20260214-120000.tar.gz

# Restaurer avec un nouveau nom
scripts/transfer.sh restore --name admin-v2 --project anklume backups/anklume-instance.tar.gz

# Restaurer depuis une sauvegarde chiffree
scripts/transfer.sh restore backups/anklume-instance.tar.gz.gpg
```

## Cibles Makefile

| Cible | Utilisation |
|-------|-------------|
| `file-copy` | `anklume portal copy instance:/chemin instance:/chemin` |
| `backup` | `anklume backup create <instance> [GPG=<destinataire>] [O=<repertoire>]` |
| `restore-backup` | `anklume backup restore --file <fichier> [NAME=<nom>] [PROJECT=<projet>]` |

## Chiffrement GPG

Le chiffrement des sauvegardes utilise la cryptographie a cle publique
GPG. Le destinataire doit avoir une paire de cles GPG configuree sur
la machine ou la sauvegarde est creee (pour le chiffrement) et
restauree (pour le dechiffrement).

### Configuration

```bash
# Generer une paire de cles (si necessaire)
gpg --full-generate-key

# Lister les cles disponibles
gpg --list-keys

# Sauvegarde avec chiffrement
anklume backup create anklume-instance --gpg admin@example.com
```

## Resolution instance-vers-projet

Le script resout automatiquement les noms d'instances vers leur projet
Incus en interrogeant `incus list --all-projects --format json`. Les
noms d'instances doivent etre globalement uniques (ADR-008), donc la
resolution est non ambigue.

## Migration inter-machines

Pour migrer des instances entre differents hotes, combinez `backup`
et `restore` :

```bash
# Sur l'hote source
anklume backup create pro-dev --output /tmp

# Transferer vers l'hote de destination
scp /tmp/backups/pro-dev-*.tar.gz dest-host:/tmp/

# Sur l'hote de destination
anklume backup restore --file /tmp/pro-dev-*.tar.gz --name pro-dev --project pro
```

Pour une migration en direct entre hotes Incus avec connectivite
directe :

```bash
incus copy local:pro-dev remote:pro-dev --project pro
```

## Depannage

### "Instance not found"

Verifiez que l'instance existe et est visible :

```bash
incus list --all-projects | grep <nom-instance>
```

### "Permission denied" sur file pull/push

Assurez-vous que le script s'execute depuis un contexte avec acces au
socket Incus (typiquement le conteneur anklume).

### Echec du dechiffrement GPG

Verifiez que la cle privee est disponible :

```bash
gpg --list-secret-keys
```

### Fichier de sauvegarde trop volumineux

`incus export` inclut tous les snapshots par defaut. Supprimez les
anciens snapshots avant la sauvegarde pour reduire la taille :

```bash
anklume snapshot delete <instance> --name <nom-snapshot>
```
