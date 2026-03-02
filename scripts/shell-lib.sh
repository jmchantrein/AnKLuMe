#!/usr/bin/env bash
# shell-lib.sh — Minimal shared library for anklume shell scripts.
# Source this file for logging helpers. For live-OS partition utilities,
# source live-os-lib.sh instead (which re-exports these functions too).
#
# Usage: source "$(dirname "$0")/shell-lib.sh"
# Note: callers are responsible for setting their own `set -euo pipefail`.

info()  { echo -e "\033[0;34m[INFO]\033[0m $*"; }
ok()    { echo -e "\033[0;32m[ OK ]\033[0m $*"; }
warn()  { echo -e "\033[1;33m[WARN]\033[0m $*"; }
err()   { echo -e "\033[0;31m[ERR ]\033[0m $*" >&2; }
