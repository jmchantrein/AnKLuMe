#!/usr/bin/env bash
# install-incus-guard.sh — Wrapper for incus-guard.sh install subcommand
#
# Delegates to: scripts/incus-guard.sh install
set -euo pipefail

exec "$(dirname "$0")/incus-guard.sh" install
