#!/usr/bin/env bash
# build-iso.sh — Génère une URL FAI.me pour une ISO live AnKLuMe
#
# Génère la commande curl pour créer une ISO Debian live via FAI.me
# avec : backports (kernel récent), firmware non-free, Incus, et le
# script postinst.sh qui installe AnKLuMe + détecte/installe NVIDIA.
#
# Usage :
#   ./build-iso.sh [options]
#
# Options :
#   --install     Générer une ISO d'installation (au lieu de live)
#   --desktop kde Choisir le bureau (kde, gnome, xfce, none)
#   --email ADDR  Recevoir un email quand l'ISO est prête
#   --dry-run     Afficher la commande curl sans l'exécuter
#   -h, --help    Afficher l'aide
#
# Prérequis : curl, le fichier postinst.sh dans le même répertoire.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Paramètres par défaut
ISO_TYPE="live"
DESKTOP="kde"
EMAIL=""
DRY_RUN=false

# FAI.me endpoint
FAIME_URL="https://fai-project.org/cgi/faime.cgi"

# ---------------------------------------------------------------------------
# Parsing des arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --install)   ISO_TYPE="install"; shift ;;
        --desktop)
            [[ -z "${2:-}" ]] && { echo "Erreur : --desktop nécessite une valeur." >&2; exit 1; }
            DESKTOP="$2"; shift 2 ;;
        --email)
            [[ -z "${2:-}" ]] && { echo "Erreur : --email nécessite une adresse." >&2; exit 1; }
            EMAIL="$2"; shift 2 ;;
        --dry-run)   DRY_RUN=true; shift ;;
        -h|--help)
            sed -n '2,/^$/s/^# \?//p' "$0"
            exit 0
            ;;
        *)
            echo "Option inconnue : $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Vérifications
# ---------------------------------------------------------------------------

POSTINST="${SCRIPT_DIR}/postinst.sh"
if [[ ! -f "${POSTINST}" ]]; then
    echo "Erreur : postinst.sh introuvable dans ${SCRIPT_DIR}" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Paquets à inclure dans l'ISO
# ---------------------------------------------------------------------------

# Paquets de base pour AnKLuMe (disponibles dans les dépôts Debian)
PACKAGES=(
    # Système
    curl git jq tmux
    # Build (pour NVIDIA DKMS si nécessaire)
    build-essential dkms pkg-config
    # Ansible
    ansible-core
    # ZFS (pour le bootstrap complet après test live)
    zfsutils-linux
    # Incus
    incus
    # Réseau
    nftables
    # Détection matérielle
    pciutils lshw
)

PACKAGES_STR="${PACKAGES[*]}"

# ---------------------------------------------------------------------------
# Résolution du desktop
# ---------------------------------------------------------------------------

case "${DESKTOP}" in
    kde)   DESKTOP_PARAM="KDE" ;;
    gnome) DESKTOP_PARAM="GNOME" ;;
    xfce)  DESKTOP_PARAM="XFCE" ;;
    none)  DESKTOP_PARAM="" ;;
    *)
        echo "Bureau inconnu : ${DESKTOP}. Choix : kde, gnome, xfce, none" >&2
        exit 1
        ;;
esac

# ---------------------------------------------------------------------------
# Construction de la commande curl
# ---------------------------------------------------------------------------

echo ""
echo "=== FAI.me ISO Builder — AnKLuMe ==="
echo ""
echo "  Type        : ${ISO_TYPE}"
echo "  Bureau      : ${DESKTOP}"
echo "  Backports   : oui (kernel récent)"
echo "  Non-free    : oui (firmware GPU)"
echo "  Postinst    : ${POSTINST}"
echo ""

# Construire les arguments curl
CURL_ARGS=(
    -s
    -F "type=${ISO_TYPE}"
    -F "distro=trixie"
    -F "BACKPORTS=on"
    -F "NONFREE=on"
    -F "SSH_SERVER=on"
    -F "STANDARD=on"
    -F "lang=fr"
    -F "keyboard=fr"
    -F "packages=${PACKAGES_STR}"
    -F "postinst=@${POSTINST}"
)

if [[ -n "${DESKTOP_PARAM}" ]]; then
    CURL_ARGS+=(-F "desktop=${DESKTOP_PARAM}")
fi

if [[ -n "${EMAIL}" ]]; then
    CURL_ARGS+=(-F "email=${EMAIL}")
fi

# sbm=0 = créer l'image, sbm=1 = afficher l'URL API
CURL_ARGS+=(-F "sbm=0")
CURL_ARGS+=("${FAIME_URL}")

# ---------------------------------------------------------------------------
# Extraction du path de téléchargement depuis la réponse HTML
# ---------------------------------------------------------------------------

# FAI.me retourne du HTML contenant un lien vers l'ISO générée.
# On cherche un path de type /fai-cd/*.iso ou une URL complète.
extract_download_path() {
    local html="$1"
    local path

    # Chercher un href contenant .iso (lien de téléchargement)
    path=$(echo "${html}" | grep -oP 'href="[^"]*\.iso[^"]*"' | head -1 | tr -d '"' | sed 's/^href=//')

    if [[ -z "${path}" ]]; then
        # Chercher un path fai-cd/ dans le texte brut
        path=$(echo "${html}" | grep -oP '/fai-cd/[^\s<"]+' | head -1)
    fi

    if [[ -z "${path}" ]]; then
        # Chercher toute URL contenant fai-project.org et .iso
        path=$(echo "${html}" | grep -oP 'https?://fai-project\.org[^\s<"]*\.iso[^\s<"]*' | head -1)
    fi

    echo "${path}"
}

if [[ "${DRY_RUN}" == true ]]; then
    echo "Commande curl (dry-run) :"
    echo ""
    echo "curl -L \\"
    i=0
    total=${#CURL_ARGS[@]}
    while [[ $i -lt $total ]]; do
        if [[ "${CURL_ARGS[$i]}" == "-F" ]] && [[ $((i + 1)) -lt $total ]]; then
            echo "  -F '${CURL_ARGS[$((i + 1))]}' \\"
            i=$((i + 2))
        elif [[ "${CURL_ARGS[$i]}" == -* ]]; then
            echo "  ${CURL_ARGS[$i]} \\"
            i=$((i + 1))
        else
            echo "  '${CURL_ARGS[$i]}'"
            i=$((i + 1))
        fi
    done
    echo ""
    echo "Le postinst.sh sera uploadé et exécuté au premier boot."
else
    echo "Envoi de la requête à FAI.me..."
    echo "(La génération peut prendre jusqu'à 30 minutes pour une ISO live)"
    echo ""
    response=$(curl -L "${CURL_ARGS[@]}" 2>&1) || {
        echo "Erreur lors de la requête FAI.me." >&2
        echo "${response}" >&2
        exit 1
    }

    download_path=$(extract_download_path "${response}")

    if [[ -n "${download_path}" ]]; then
        # Construire l'URL complète si c'est un path relatif
        if [[ "${download_path}" == /* ]]; then
            download_url="https://fai-project.org${download_path}"
        elif [[ "${download_path}" == http* ]]; then
            download_url="${download_path}"
        else
            download_url="https://fai-project.org/${download_path}"
        fi
        echo "ISO prête à télécharger :"
        echo ""
        echo "  ${download_url}"
        echo ""
        echo "Pour télécharger :"
        echo "  curl -LO ${download_url}"
    else
        # Fallback : afficher la réponse brute si on ne trouve pas le path
        echo "Réponse FAI.me (path de téléchargement non détecté automatiquement) :"
        echo ""
        echo "${response}" | sed 's/<[^>]*>//g' | sed '/^$/d' | head -30
        echo ""
        echo "Consultez la page FAI.me ou l'email (si fourni) pour le lien de téléchargement."
    fi
fi

echo ""
echo "Une fois l'ISO bootée :"
echo "  1. Le postinst.sh détecte le GPU et installe le driver NVIDIA si nécessaire"
echo "  2. Incus est installé et initialisé"
echo "  3. AnKLuMe est installé avec l'alias 'ank'"
echo ""
echo "Pour un déploiement complet (ZFS, toram, etc.) :"
echo "  sudo ./bootstrap.sh --zfs-disk1 ... --zfs-disk2 ..."
echo ""
