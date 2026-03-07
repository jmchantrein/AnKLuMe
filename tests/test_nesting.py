"""Tests de nesting — vérifient le nesting Incus jusqu'à 5 niveaux.

Ce test crée des conteneurs imbriqués avec Incus installé à chaque niveau.
Chaque niveau installe Incus, l'initialise, et crée le conteneur suivant.

LENT — chaque niveau télécharge des paquets + une image (~2-3 min/niveau).
Prérequis : Incus installé sur l'hôte, accès internet.
"""

from __future__ import annotations

import json
import subprocess
import textwrap
import time

import pytest

NEST_PROJECT = "e2e-nest"
MAX_DEPTH = 5

_NEST_SCRIPT = textwrap.dedent("""\
#!/bin/bash
set -euo pipefail

LEVEL=$1
MAX_LEVEL=$2

echo "=== Nesting level $LEVEL: installing Incus ==="
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq > /dev/null 2>&1

# Installer Incus (disponible dans Debian trixie)
if ! apt-get install -y -qq incus > /dev/null 2>&1; then
    echo "Incus absent des repos par défaut, ajout du repo Zabbly..."
    apt-get install -y -qq curl gpg > /dev/null 2>&1
    curl -fsSL https://pkgs.zabbly.com/key.asc | gpg --dearmor \
        -o /etc/apt/keyrings/zabbly.gpg
    cat > /etc/apt/sources.list.d/zabbly-incus-stable.sources <<REPO
Enabled: yes
Types: deb
URIs: https://pkgs.zabbly.com/incus/stable
Suites: $(. /etc/os-release && echo ${VERSION_CODENAME})
Components: main
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/zabbly.gpg
REPO
    apt-get update -qq > /dev/null 2>&1
    apt-get install -y -qq incus > /dev/null 2>&1
fi

echo "=== Nesting level $LEVEL: initializing Incus ==="
incus admin init --minimal

if [ "$LEVEL" -lt "$MAX_LEVEL" ]; then
    NEXT=$((LEVEL + 1))
    echo "=== Nesting level $LEVEL: creating level $NEXT container ==="

    incus launch images:debian/13 "nest-l${NEXT}" \
        -c security.nesting=true \
        -c security.privileged=true

    # Attendre que le conteneur soit accessible
    echo "Attente de nest-l${NEXT}..."
    for i in $(seq 1 60); do
        if incus exec "nest-l${NEXT}" -- true 2>/dev/null; then
            break
        fi
        sleep 2
    done

    # Attendre que le réseau soit prêt (DNS, apt)
    sleep 5

    # Copier le script et exécuter récursivement
    incus file push /tmp/nest-setup.sh "nest-l${NEXT}/tmp/nest-setup.sh"
    incus exec "nest-l${NEXT}" -- chmod +x /tmp/nest-setup.sh
    incus exec "nest-l${NEXT}" -- /tmp/nest-setup.sh "$NEXT" "$MAX_LEVEL"
fi

echo "=== Nesting level $LEVEL: OK ==="
""")


def _incus_json(args: list[str]) -> list | dict:
    result = subprocess.run(
        ["incus", *args, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return json.loads(result.stdout)


def _incus_run(args: list[str], timeout: int = 120) -> None:
    result = subprocess.run(
        ["incus", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        pytest.fail(f"incus {' '.join(args)} a échoué : {result.stderr}")


def _project_exists(name: str) -> bool:
    projects = _incus_json(["project", "list"])
    return any(p["name"] == name for p in projects)


def _cleanup_nest():
    """Nettoyer le projet de nesting."""
    if not _project_exists(NEST_PROJECT):
        return

    instances = _incus_json(["list", "--project", NEST_PROJECT])
    for inst in instances:
        name = inst["name"]
        subprocess.run(
            [
                "incus",
                "config",
                "set",
                name,
                "security.protection.delete=false",
                "--project",
                NEST_PROJECT,
            ],
            capture_output=True,
        )
        if inst["status"] == "Running":
            subprocess.run(
                ["incus", "stop", name, "--project", NEST_PROJECT, "--force"],
                capture_output=True,
            )
        subprocess.run(
            ["incus", "delete", name, "--project", NEST_PROJECT, "--force"],
            capture_output=True,
        )

    networks = _incus_json(["network", "list", "--project", NEST_PROJECT])
    for net in networks:
        if net.get("managed"):
            subprocess.run(
                ["incus", "network", "delete", net["name"], "--project", NEST_PROJECT],
                capture_output=True,
            )

    subprocess.run(
        ["incus", "project", "delete", NEST_PROJECT],
        capture_output=True,
    )


@pytest.fixture()
def nest_env(tmp_path):
    """Fixture pour le test de nesting — cleanup avant et après."""
    _cleanup_nest()
    yield tmp_path
    _cleanup_nest()


class TestNesting:
    """Nesting Incus à 5 niveaux de profondeur."""

    @pytest.mark.slow
    def test_five_levels(self, nest_env):
        """Crée 5 niveaux de conteneurs imbriqués avec Incus à chaque niveau."""
        path = nest_env

        # 1. Créer le projet Incus
        _incus_run(
            [
                "project",
                "create",
                NEST_PROJECT,
                "-c",
                "features.images=false",
                "-c",
                "features.profiles=false",
            ]
        )

        # 2. Créer le conteneur level 1 avec nesting
        _incus_run(
            [
                "launch",
                "images:debian/13",
                "nest-l1",
                "--project",
                NEST_PROJECT,
                "-c",
                "security.nesting=true",
                "-c",
                "security.privileged=true",
            ]
        )

        # 3. Attendre que le conteneur soit prêt
        time.sleep(10)

        # 4. Pousser le script récursif
        script_path = path / "nest-setup.sh"
        script_path.write_text(_NEST_SCRIPT)

        _incus_run(
            [
                "file",
                "push",
                str(script_path),
                "nest-l1/tmp/nest-setup.sh",
                "--project",
                NEST_PROJECT,
            ]
        )
        _incus_run(
            [
                "exec",
                "nest-l1",
                "--project",
                NEST_PROJECT,
                "--",
                "chmod",
                "+x",
                "/tmp/nest-setup.sh",  # noqa: S108
            ]
        )

        # 5. Exécuter — crée récursivement les niveaux 2 à 5
        result = subprocess.run(
            [
                "incus",
                "exec",
                "nest-l1",
                "--project",
                NEST_PROJECT,
                "--",
                "/tmp/nest-setup.sh",  # noqa: S108
                "1",
                str(MAX_DEPTH),
            ],
            capture_output=True,
            text=True,
            timeout=900,  # 15 minutes
        )

        assert result.returncode == 0, (
            f"Script de nesting échoué :\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )

        # 6. Vérifier que tous les niveaux rapportent OK
        for level in range(1, MAX_DEPTH + 1):
            assert f"Nesting level {level}: OK" in result.stdout, (
                f"Level {level} n'a pas rapporté OK.\nSTDOUT:\n{result.stdout}"
            )
