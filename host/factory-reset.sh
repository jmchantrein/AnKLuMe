#!/usr/bin/env bash
# factory-reset.sh — Retour à l'état fresh install (dev/bootstrap)
#
# Ce script remet la machine dans l'état d'avant bootstrap.sh :
#   1. Détruit le pool ZFS tank (données /home, /srv/*, /var/lib/anklume)
#   2. Recrée des tables GPT vierges sur les disques ZFS mirror
#   3. Rollback btrfs vers le snapshot le plus ancien (≈ fresh install)
#
# ⚠ DESTRUCTIF — toutes les données ZFS sont perdues.
# ⚠ Conçu pour le développement du bootstrap, PAS pour la production.
#
# Usage :
#   sudo ./factory-reset.sh [options]
#
# Options :
#   --zfs-only            Ne toucher qu'au ZFS (pas de rollback btrfs)
#   --btrfs-only          Ne toucher qu'au btrfs (pas de destruction ZFS)
#   --yes                 Pas de confirmation interactive
#   --skip-reboot         Ne pas redémarrer automatiquement à la fin
#   -h, --help            Afficher l'aide
#
# Après exécution : la machine redémarre en état fresh install,
# prête pour un nouveau ./bootstrap.sh.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

readonly POOL="tank"
readonly ZFS_KEY_DIR="/etc/zfs"

# Couleurs
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly BOLD='\033[1m'
readonly NC='\033[0m'

# Flags
ZFS_ONLY=false
BTRFS_ONLY=false
AUTO_YES=false
SKIP_REBOOT=false
DETACHED=false       # true quand re-exec via systemd-run

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --zfs-only)     ZFS_ONLY=true; shift ;;
        --btrfs-only)   BTRFS_ONLY=true; shift ;;
        --yes)          AUTO_YES=true; shift ;;
        --skip-reboot)  SKIP_REBOOT=true; shift ;;
        --detached)     DETACHED=true; shift ;;
        -h|--help)
            sed -n '2,/^$/s/^# \?//p' "$0"
            exit 0
            ;;
        *)
            printf "Option inconnue : %s\n" "$1" >&2
            exit 1
            ;;
    esac
done

if [[ "${ZFS_ONLY}" == true && "${BTRFS_ONLY}" == true ]]; then
    printf "Erreur : --zfs-only et --btrfs-only sont mutuellement exclusifs.\n" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Fonctions utilitaires
# ---------------------------------------------------------------------------

info()  { printf "${GREEN}[INFO]${NC}  %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
error() { printf "${RED}[ERREUR]${NC} %s\n" "$1" >&2; }
step()  { printf "\n${BLUE}── %s${NC}\n\n" "$1"; }

check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "Ce script doit être exécuté en root."
        exit 1
    fi
}

# Nettoyage automatique des montages temporaires à la sortie
cleanup() {
    umount /mnt/btrfs-toplevel 2>/dev/null || true
    rmdir /mnt/btrfs-toplevel 2>/dev/null || true
}
trap cleanup EXIT

# Demande confirmation sauf si --yes
confirm() {
    local msg="$1"
    if [[ "${AUTO_YES}" == true ]]; then
        return 0
    fi
    printf "\n%b%b%s%b\n" "${BOLD}" "${RED}" "${msg}" "${NC}"
    printf "Tapez %bOUI%b en majuscules pour confirmer : " "${BOLD}" "${NC}"
    local answer
    read -r answer
    if [[ "${answer}" != "OUI" ]]; then
        info "Annulé."
        exit 0
    fi
}

# ---------------------------------------------------------------------------
# Phase 1 : Destruction ZFS
# ---------------------------------------------------------------------------

# Identifie les disques physiques du pool (vdevs)
get_pool_disks() {
    if ! zpool list "${POOL}" &>/dev/null; then
        return
    fi
    # zpool status affiche les vdevs, on extrait les lignes de disques
    # Format : "    /dev/disk/by-id/xxx  ONLINE  0  0  0"
    #       ou "    nvme0n1             ONLINE  0  0  0"
    zpool status "${POOL}" 2>/dev/null \
        | awk '/mirror/{found=1; next} found && /ONLINE|DEGRADED/{print $1} /^$/{found=0}' \
        | while read -r vdev; do
            # Résoudre vers /dev/sdX ou /dev/nvmeXnY
            if [[ -e "/dev/${vdev}" ]]; then
                echo "/dev/${vdev}"
            elif [[ -e "/dev/disk/by-id/${vdev}" ]]; then
                readlink -f "/dev/disk/by-id/${vdev}"
            elif [[ -e "${vdev}" ]]; then
                readlink -f "${vdev}"
            fi
        done | sort -u
}

# Stopper les services qui dépendent de ZFS
stop_zfs_consumers() {
    step "Arrêt des services ZFS"

    # Incus (utilise tank/_incus comme storage)
    if systemctl is-active --quiet incus.service 2>/dev/null; then
        systemctl stop incus.service incus.socket 2>/dev/null || true
        info "Incus arrêté."
    fi

    # Le service de déverrouillage
    systemctl stop zfs-load-key-tank.service 2>/dev/null || true

    # Tuer les processus qui utilisent les points de montage ZFS
    local zfs_mounts
    zfs_mounts=$(zfs list -H -o mountpoint "${POOL}" -r 2>/dev/null \
        | grep -v '^-$' | grep -v '^none$' | grep -v '^legacy$') || true

    if [[ -n "${zfs_mounts}" ]]; then
        for mp in ${zfs_mounts}; do
            if mountpoint -q "${mp}" 2>/dev/null; then
                fuser -km "${mp}" 2>/dev/null || true
                info "Processus tués sur ${mp}."
            fi
        done
    fi
}

# Démonter proprement tout le pool
unmount_zfs() {
    step "Démontage ZFS"

    # Démonter /home en premier (peut être le cwd d'un shell)
    if mountpoint -q /home 2>/dev/null; then
        local home_fstype
        home_fstype=$(findmnt -no FSTYPE /home 2>/dev/null) || home_fstype=""
        if [[ "${home_fstype}" == "zfs" ]]; then
            # Se déplacer hors de /home
            cd /root
            umount -l /home 2>/dev/null || zfs unmount -f "${POOL}/_home" 2>/dev/null || true
            info "/home ZFS démonté."
        fi
    fi

    # Démonter tous les datasets ZFS
    zfs unmount -a -f 2>/dev/null || true
    info "Tous les datasets ZFS démontés."
}

# Détruire le pool et nettoyer les traces
destroy_zfs_pool() {
    step "Destruction du pool ZFS '${POOL}'"

    if ! zpool list "${POOL}" &>/dev/null; then
        info "Pool '${POOL}' inexistant, rien à détruire."
        return
    fi

    # Récupérer les disques AVANT destruction
    local disks
    disks=$(get_pool_disks)

    stop_zfs_consumers
    unmount_zfs

    # Détruire le pool
    zpool destroy -f "${POOL}"
    info "Pool '${POOL}' détruit."

    # Nettoyer les keyfiles
    rm -f "${ZFS_KEY_DIR}/tank.key" "${ZFS_KEY_DIR}/tank.key.enc"
    info "Keyfiles ZFS supprimés."

    # Nettoyer les services systemd
    rm -f /etc/systemd/system/zfs-load-key-tank.service
    rm -f /etc/systemd/system/incus.service.d/after-zfs.conf
    rm -f /usr/local/bin/zfs-unlock-tank
    systemctl daemon-reload 2>/dev/null || true
    info "Services systemd ZFS nettoyés."

    # Recréer les tables GPT vierges
    if [[ -n "${disks}" ]]; then
        wipe_disks "${disks}"
    else
        warn "Disques du pool non identifiés — tables GPT non recréées."
        warn "Utilisez 'sgdisk -Z /dev/nvmeXnY' manuellement si nécessaire."
    fi
}

# Recréer une table GPT vierge sur chaque disque
wipe_disks() {
    local disks="$1"
    step "Recréation des tables GPT"

    for disk in ${disks}; do
        if [[ ! -b "${disk}" ]]; then
            warn "Disque ${disk} introuvable, ignoré."
            continue
        fi
        # Effacer toute signature (ZFS, GPT, MBR) et créer une GPT vierge
        sgdisk -Z "${disk}" 2>/dev/null || wipefs -a "${disk}" 2>/dev/null || true
        sgdisk -o "${disk}"
        partprobe "${disk}" 2>/dev/null || true
        info "GPT vierge : ${disk}"
    done
}

# ---------------------------------------------------------------------------
# Phase 2 : Rollback btrfs vers le premier snapshot
# ---------------------------------------------------------------------------

rollback_btrfs() {
    step "Rollback btrfs vers le premier snapshot"

    # Identifier les subvolumes btrfs montés (partitions système)
    local btrfs_mounts
    btrfs_mounts=$(findmnt -t btrfs -n -o TARGET,SOURCE | sort) || true

    if [[ -z "${btrfs_mounts}" ]]; then
        warn "Aucun montage btrfs détecté."
        return
    fi

    info "Montages btrfs détectés :"
    echo "${btrfs_mounts}" | while read -r target source; do
        printf "  %-20s  %s\n" "${target}" "${source}"
    done

    # Trouver le device btrfs principal (racine /)
    local root_dev
    root_dev=$(findmnt -no SOURCE / 2>/dev/null) || true

    if [[ -z "${root_dev}" ]]; then
        error "Impossible de trouver le device racine."
        return 1
    fi

    # Extraire le device sous-jacent (sans le subvolume)
    # /dev/mapper/luks-xxx[/@] → /dev/mapper/luks-xxx
    local btrfs_dev
    btrfs_dev="${root_dev%%\[*}"

    info "Device btrfs : ${btrfs_dev}"

    # Monter le toplevel btrfs (subvolid=5) pour accéder à tous les subvolumes
    local toplevel="/mnt/btrfs-toplevel"
    mkdir -p "${toplevel}"

    # Si c'est LUKS, le device est déjà déchiffré via /dev/mapper
    mount -o subvolid=5 "${btrfs_dev}" "${toplevel}" 2>/dev/null || {
        error "Impossible de monter le toplevel btrfs."
        error "Device : ${btrfs_dev}"
        return 1
    }

    info "Toplevel btrfs monté sur ${toplevel}"

    # Lister les snapshots disponibles
    # CachyOS/Snapper : .snapshots/N/snapshot ou @snapshots/N/snapshot
    # Timeshift : timeshift-btrfs/snapshots/YYYY-MM-DD_HH-MM-SS/@
    local snapshots_found=false

    # --- Snapper (CachyOS par défaut) ---
    if [[ -d "${toplevel}/@/.snapshots" || -d "${toplevel}/.snapshots" ]]; then
        local snap_dir
        if [[ -d "${toplevel}/@/.snapshots" ]]; then
            snap_dir="${toplevel}/@/.snapshots"
        else
            snap_dir="${toplevel}/.snapshots"
        fi

        info "Snapshots Snapper détectés dans ${snap_dir}"

        # Le snapshot le plus ancien (numéro le plus bas, tri numérique)
        local oldest_num
        oldest_num=$(find "${snap_dir}" -maxdepth 2 -name snapshot -type d 2>/dev/null \
            | sed 's|.*/\([0-9]*\)/snapshot|\1|' \
            | sort -n | head -1) || true

        if [[ -n "${oldest_num}" ]]; then
            snapshots_found=true
            rollback_snapper "${toplevel}" "${snap_dir}" "${oldest_num}"
        fi
    fi

    # --- Timeshift ---
    if [[ "${snapshots_found}" == false ]]; then
        local ts_dir="${toplevel}/timeshift-btrfs/snapshots"
        if [[ -d "${ts_dir}" ]]; then
            info "Snapshots Timeshift détectés dans ${ts_dir}"

            local oldest_snap
            oldest_snap=$(find "${ts_dir}" -maxdepth 1 -mindepth 1 -type d 2>/dev/null \
                | sort | head -1) || true

            if [[ -n "${oldest_snap}" ]]; then
                snapshots_found=true
                rollback_timeshift "${toplevel}" "${oldest_snap}"
            fi
        fi
    fi

    # --- Subvolumes @_snapshot_* (convention manuelle) ---
    if [[ "${snapshots_found}" == false ]]; then
        local manual_snaps
        manual_snaps=$(find "${toplevel}" -maxdepth 1 -name '@_snapshot_*' -type d 2>/dev/null \
            | sort | head -1) || true

        if [[ -n "${manual_snaps}" ]]; then
            snapshots_found=true
            info "Snapshots manuels détectés."
            warn "Rollback manuel non implémenté — utiliser les commandes suivantes :"
            warn "  btrfs subvolume delete ${toplevel}/@"
            warn "  btrfs subvolume snapshot ${manual_snaps} ${toplevel}/@"
        fi
    fi

    if [[ "${snapshots_found}" == false ]]; then
        warn "Aucun snapshot btrfs trouvé."
        warn "Le système ne peut pas être rollback au premier snapshot."
        warn "Subvolumes présents sur le toplevel :"
        find "${toplevel}" -maxdepth 1 -mindepth 1 -printf '%f\n' 2>/dev/null | head -20
    fi

    # Le trap EXIT se charge du umount/rmdir
}

# Rollback Snapper : remplacer @ par le plus ancien snapshot
rollback_snapper() {
    local toplevel="$1"
    local snap_dir="$2"
    local snap_num="$3"
    local snap_path="${snap_dir}/${snap_num}/snapshot"

    if [[ ! -d "${snap_path}" ]]; then
        error "Snapshot ${snap_path} introuvable."
        return 1
    fi

    # Afficher les infos du snapshot
    if [[ -f "${snap_dir}/${snap_num}/info.xml" ]]; then
        info "Snapshot #${snap_num} :"
        grep -E '<(date|description|type)>' "${snap_dir}/${snap_num}/info.xml" \
            | sed 's/<[^>]*>//g; s/^[[:space:]]*/  /' || true
    fi

    # Lister TOUS les subvolumes à rollback (@ @home @log @cache etc.)
    # On cherche les paires : subvol actif + snapshot correspondant
    info "Subvolumes sur le toplevel :"
    btrfs subvolume list -o "${toplevel}" 2>/dev/null \
        | awk '{print $NF}' | head -20 || ls -1 "${toplevel}"/

    confirm "ROLLBACK BTRFS : remplacer les subvolumes actifs par le snapshot #${snap_num} ?"

    # Rollback du subvolume principal @
    # Méthode Snapper : le snapshot est sous @/.snapshots/N/snapshot
    # On renomme @ → @.old, puis on snapshot le snapshot vers @
    local subvols_to_rollback=("@")

    # Chercher les subvolumes additionnels avec leurs snapshots
    # CachyOS crée souvent : @, @home, @log, @cache, @tmp
    for sv in "@home" "@log" "@cache" "@tmp" "@srv"; do
        if [[ -d "${toplevel}/${sv}" ]]; then
            # Vérifier si un snapshot existe pour ce subvolume
            local sv_snap_dir="${toplevel}/${sv}/.snapshots"
            if [[ -d "${sv_snap_dir}/${snap_num}/snapshot" ]]; then
                subvols_to_rollback+=("${sv}")
            fi
        fi
    done

    for sv in "${subvols_to_rollback[@]}"; do
        local sv_path="${toplevel}/${sv}"
        local sv_old="${toplevel}/${sv}.factory-reset-backup"
        local sv_snap

        if [[ "${sv}" == "@" ]]; then
            sv_snap="${snap_path}"
        else
            sv_snap="${toplevel}/${sv}/.snapshots/${snap_num}/snapshot"
        fi

        if [[ ! -d "${sv_snap}" ]]; then
            warn "Pas de snapshot #${snap_num} pour ${sv}, ignoré."
            continue
        fi

        info "Rollback ${sv} → snapshot #${snap_num}..."

        # Supprimer un éventuel backup précédent
        if [[ -d "${sv_old}" ]]; then
            btrfs subvolume delete "${sv_old}" 2>/dev/null || rm -rf "${sv_old}"
            warn "  Ancien backup ${sv}.factory-reset-backup supprimé."
        fi

        # Renommer le subvolume actif
        mv "${sv_path}" "${sv_old}"
        info "  ${sv} → ${sv}.factory-reset-backup"

        # Créer un nouveau subvolume à partir du snapshot
        btrfs subvolume snapshot "${sv_snap}" "${sv_path}"
        info "  Snapshot #${snap_num} → ${sv} (nouveau)"
    done

    info "Rollback Snapper terminé."
    warn "Les anciens subvolumes sont dans *.factory-reset-backup"
    warn "Après validation, supprimez-les avec :"
    for sv in "${subvols_to_rollback[@]}"; do
        warn "  btrfs subvolume delete ${toplevel}/${sv}.factory-reset-backup"
    done
}

# Rollback Timeshift : remplacer @ par le plus ancien snapshot
rollback_timeshift() {
    local toplevel="$1"
    local snap_path="$2"

    info "Plus ancien snapshot Timeshift : ${snap_path}"

    confirm "ROLLBACK BTRFS : remplacer @ par le snapshot Timeshift le plus ancien ?"

    # Timeshift stocke @ dans le snapshot
    local snap_root="${snap_path}/@"
    if [[ ! -d "${snap_root}" ]]; then
        error "Subvolume @ introuvable dans le snapshot Timeshift."
        return 1
    fi

    # Renommer et remplacer (supprimer un éventuel backup précédent)
    if [[ -d "${toplevel}/@.factory-reset-backup" ]]; then
        btrfs subvolume delete "${toplevel}/@.factory-reset-backup" 2>/dev/null || true
    fi
    mv "${toplevel}/@" "${toplevel}/@.factory-reset-backup"
    btrfs subvolume snapshot "${snap_root}" "${toplevel}/@"
    info "Rollback Timeshift terminé."

    # Idem pour @home si présent
    if [[ -d "${snap_path}/@home" && -d "${toplevel}/@home" ]]; then
        if [[ -d "${toplevel}/@home.factory-reset-backup" ]]; then
            btrfs subvolume delete "${toplevel}/@home.factory-reset-backup" 2>/dev/null || true
        fi
        mv "${toplevel}/@home" "${toplevel}/@home.factory-reset-backup"
        btrfs subvolume snapshot "${snap_path}/@home" "${toplevel}/@home"
        info "Rollback @home Timeshift terminé."
    fi

    warn "Anciens subvolumes dans *.factory-reset-backup"
}

# ---------------------------------------------------------------------------
# Détachement de la session utilisateur
# ---------------------------------------------------------------------------
# fuser -km /home tue TOUS les processus sur /home, y compris le shell
# de l'utilisateur. Si le script tourne dans cette session, il meurt aussi.
# Solution : après la confirmation interactive, se re-exécuter via
# systemd-run --scope pour être indépendant de la session.

readonly RESET_LOG="/root/factory-reset.log"

# Re-exec le script détaché de la session utilisateur.
# La confirmation interactive est déjà passée → on passe --yes --detached.
detach_and_rerun() {
    local args=("--yes" "--detached")
    [[ "${ZFS_ONLY}" == true ]]    && args+=("--zfs-only")
    [[ "${BTRFS_ONLY}" == true ]]  && args+=("--btrfs-only")
    [[ "${SKIP_REBOOT}" == true ]] && args+=("--skip-reboot")

    local self
    self="$(readlink -f "$0")"

    info "Détachement du script de la session utilisateur..."
    info "La suite est loggée dans ${RESET_LOG}"
    info "Votre session va être coupée — c'est normal."
    echo ""

    # systemd-run --scope crée un scope systemd indépendant du login session
    systemd-run --scope --unit=factory-reset \
        bash "${self}" "${args[@]}" \
        &> "${RESET_LOG}" &

    # Laisser systemd-run démarrer avant de quitter
    sleep 2
    info "Script détaché (PID $!). Consultez ${RESET_LOG} après reboot."
    exit 0
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    echo ""
    echo "=== factory-reset.sh — Retour à l'état fresh install ==="
    echo ""

    check_root

    # Toujours travailler depuis /root (pas /home qui va être démonté)
    cd /root

    # Si on tourne détaché, la sortie va dans le log — on redirige stdout/stderr
    if [[ "${DETACHED}" == true ]]; then
        exec > >(tee -a "${RESET_LOG}") 2>&1
        info "=== Exécution détachée — $(date) ==="
    fi

    # Résumé de ce qui va se passer
    printf "%bCe script va :%b\n" "${BOLD}" "${NC}"
    if [[ "${BTRFS_ONLY}" != true ]]; then
        printf "  %b✗%b Détruire le pool ZFS '%s' (TOUTES les données)\n" "${RED}" "${NC}" "${POOL}"
        printf "  %b✗%b Recréer des tables GPT vierges sur les disques mirror\n" "${RED}" "${NC}"
        printf "  %b✗%b Supprimer les keyfiles et services systemd ZFS\n" "${RED}" "${NC}"
    fi
    if [[ "${ZFS_ONLY}" != true ]]; then
        printf "  %b✗%b Rollback btrfs vers le premier snapshot (fresh install)\n" "${RED}" "${NC}"
    fi
    echo ""

    # Phase interactive : confirmation puis détachement
    if [[ "${DETACHED}" != true ]]; then
        confirm "FACTORY RESET — Cette opération est IRRÉVERSIBLE. Continuer ?"
        detach_and_rerun
        # On ne revient jamais ici (exit dans detach_and_rerun)
    fi

    # --- À partir d'ici, on tourne détaché de la session ---

    if [[ "${BTRFS_ONLY}" != true ]]; then
        destroy_zfs_pool
    fi

    if [[ "${ZFS_ONLY}" != true ]]; then
        rollback_btrfs
    fi

    step "Factory reset terminé"

    info "État actuel :"
    if [[ "${BTRFS_ONLY}" != true ]]; then
        if zpool list "${POOL}" &>/dev/null; then
            warn "Pool '${POOL}' encore présent (erreur ?)."
        else
            info "Pool ZFS '${POOL}' : détruit."
        fi
    fi

    echo ""
    info "Prochaines étapes :"
    info "  1. Redémarrer"
    info "  2. Relancer ./bootstrap.sh avec les options habituelles"
    echo ""

    if [[ "${SKIP_REBOOT}" == true ]]; then
        warn "Redémarrage ignoré (--skip-reboot)."
        warn "Redémarrez manuellement : sudo reboot"
    else
        warn "Redémarrage dans 10 secondes..."
        sleep 10
        reboot
    fi
}

main
