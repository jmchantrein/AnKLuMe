# shellcheck shell=bash
# host/lib/common.sh — Fonctions utilitaires partagées (couleurs, logging, check_root)
#
# Source guard : évite le double-chargement
[[ -n "${_LIB_COMMON_SH:-}" ]] && return; _LIB_COMMON_SH=1

# Couleurs
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly NC='\033[0m'

# Logging
info()  { printf "${GREEN}[INFO]${NC}  %s\n" "$1"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$1"; }
error() { printf "${RED}[ERREUR]${NC} %s\n" "$1" >&2; }
step()  { printf "\n${BLUE}── %s${NC}\n\n" "$1"; }

# Vérification root
check_root() {
    if [[ ${EUID} -ne 0 ]]; then
        error "Ce script doit être exécuté en root."
        exit 1
    fi
}
