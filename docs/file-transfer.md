# File Transfer and Backup

AnKLuMe provides controlled file transfer between instances and
encrypted backup/restore via `scripts/transfer.sh`.

For persistent, declarative cross-domain directory sharing, see
[shared_volumes](SPEC.md) (ADR-039) which provides host bind mounts
with RO/RW access control. `transfer.sh` is for one-off transfers.

## Quick start

### Copy a file between instances

```bash
make file-copy SRC=pro-dev:/etc/hosts DST=perso-desktop:/tmp/hosts
```

### Backup an instance

```bash
make backup I=anklume-instance
make backup I=anklume-instance GPG=user@example.com
make backup I=anklume-instance O=/mnt/external
```

### Restore from backup

```bash
make restore-backup FILE=backups/anklume-instance-20260214-120000.tar.gz
make restore-backup FILE=backups/anklume-instance.tar.gz.gpg NAME=admin-v2 PROJECT=anklume
```

## Commands

### copy

Copy a file from one instance to another using Incus file operations.
The script resolves each instance to its Incus project automatically.

```bash
scripts/transfer.sh copy <src_instance:/path> <dst_instance:/path>
```

The copy is performed via a pipe:

```
incus file pull <src> - | incus file push - <dst>
```

This means the file content passes through the anklume container (or
wherever the script runs) but is never written to disk on the host.

**Examples**:

```bash
# Copy a config file from pro to anklume
scripts/transfer.sh copy pro-dev:/etc/nginx/nginx.conf anklume-instance:/tmp/nginx.conf

# Copy a log file to perso for analysis
scripts/transfer.sh copy gpu-server:/var/log/ollama.log perso-desktop:/tmp/ollama.log
```

### backup

Export an instance to a compressed archive with optional GPG encryption.

```bash
scripts/transfer.sh backup [options] <instance>
```

**Options**:

| Option | Description |
|--------|-------------|
| `--gpg-recipient ID` | Encrypt with GPG public key |
| `--output DIR` | Output directory (default: `backups/`) |
| `--force` | Overwrite existing backup file |

The backup uses `incus export` which creates a complete archive of the
instance (rootfs, configuration, snapshots). The filename follows the
pattern `<instance>-YYYYMMDD-HHMMSS.tar.gz`.

**Examples**:

```bash
# Basic backup
scripts/transfer.sh backup anklume-instance

# Encrypted backup
scripts/transfer.sh backup --gpg-recipient admin@example.com anklume-instance

# Custom output directory
scripts/transfer.sh backup --output /mnt/backup gpu-server
```

### restore

Import an instance from a backup archive. Supports GPG-encrypted files
(`.gpg` extension auto-detected).

```bash
scripts/transfer.sh restore [options] <backup-file>
```

**Options**:

| Option | Description |
|--------|-------------|
| `--name NEW_NAME` | Import with a different instance name |
| `--project PROJECT` | Target Incus project |
| `--force` | Force import |

GPG-encrypted backups (`.gpg` extension) are automatically decrypted
before import. The decrypted file is removed after successful import.

**Examples**:

```bash
# Restore from backup
scripts/transfer.sh restore backups/anklume-instance-20260214-120000.tar.gz

# Restore with new name
scripts/transfer.sh restore --name admin-v2 --project anklume backups/anklume-instance.tar.gz

# Restore from encrypted backup
scripts/transfer.sh restore backups/anklume-instance.tar.gz.gpg
```

## Makefile targets

| Target | Usage |
|--------|-------|
| `file-copy` | `make file-copy SRC=instance:/path DST=instance:/path` |
| `backup` | `make backup I=<instance> [GPG=<recipient>] [O=<dir>]` |
| `restore-backup` | `make restore-backup FILE=<file> [NAME=<name>] [PROJECT=<project>]` |

## GPG encryption

Backup encryption uses GPG public-key cryptography. The recipient must
have a GPG key pair configured on the machine where the backup is
created (for encryption) and restored (for decryption).

### Setup

```bash
# Generate a key pair (if needed)
gpg --full-generate-key

# List available keys
gpg --list-keys

# Backup with encryption
make backup I=anklume-instance GPG=admin@example.com
```

### Key management

For automated backup workflows, ensure the GPG key is available in
the keyring of the user running the backup. For decryption, the
private key must be available on the restore machine.

## Instance-to-project resolution

The script automatically resolves instance names to their Incus
project by querying `incus list --all-projects --format json`.
Instance names must be globally unique (ADR-008), so resolution
is unambiguous.

## Cross-machine migration

For migrating instances between different hosts, combine `backup`
and `restore`:

```bash
# On source host
make backup I=pro-dev O=/tmp

# Transfer to destination host
scp /tmp/backups/pro-dev-*.tar.gz dest-host:/tmp/

# On destination host
make restore-backup FILE=/tmp/pro-dev-*.tar.gz NAME=pro-dev PROJECT=pro
```

For live migration between Incus hosts with direct connectivity:

```bash
incus copy local:pro-dev remote:pro-dev --project pro
```

## Troubleshooting

### "Instance not found"

Verify the instance exists and is visible:

```bash
incus list --all-projects | grep <instance-name>
```

### "Permission denied" on file pull/push

Ensure the script runs from a context with access to the Incus socket
(typically the anklume container).

### GPG decryption fails

Verify the private key is available:

```bash
gpg --list-secret-keys
```

### Backup file too large

`incus export` includes all snapshots by default. Delete old snapshots
before backing up to reduce file size:

```bash
make snap-delete I=<instance> S=<snapshot-name>
```
