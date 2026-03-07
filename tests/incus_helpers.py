"""Utilitaires partagés pour les tests Incus (pytest + behave)."""

from __future__ import annotations

import json
import subprocess


def incus_json(args: list[str]) -> list | dict:
    """Appel incus avec sortie JSON. Retourne [] si échec."""
    result = subprocess.run(
        ["incus", *args, "--format", "json"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return json.loads(result.stdout)


def incus_run(args: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    """Appel incus direct. Lève RuntimeError si échec."""
    result = subprocess.run(
        ["incus", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"incus {' '.join(args)} a échoué : {result.stderr}")
    return result


def project_exists(name: str) -> bool:
    projects = incus_json(["project", "list"])
    return any(p["name"] == name for p in projects)


def network_exists(name: str, project: str) -> bool:
    networks = incus_json(["network", "list", "--project", project])
    return any(n["name"] == name for n in networks)


def instance_exists(name: str, project: str) -> bool:
    instances = incus_json(["list", "--project", project])
    return any(i["name"] == name for i in instances)


def instance_status(name: str, project: str) -> str:
    instances = incus_json(["list", "--project", project])
    for i in instances:
        if i["name"] == name:
            return i["status"]
    return "NotFound"


def instance_config_get(name: str, project: str, key: str) -> str:
    result = subprocess.run(
        ["incus", "config", "get", name, key, "--project", project],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def cleanup_project(name: str) -> None:
    """Nettoyer un projet : arrêter/supprimer instances, réseaux, projet."""
    if not project_exists(name):
        return
    instances = incus_json(["list", "--project", name])
    if isinstance(instances, list):
        for inst in instances:
            inst_name = inst["name"]
            subprocess.run(
                [
                    "incus",
                    "config",
                    "set",
                    inst_name,
                    "security.protection.delete=false",
                    "--project",
                    name,
                ],
                capture_output=True,
            )
            if inst["status"] == "Running":
                subprocess.run(
                    ["incus", "stop", inst_name, "--project", name, "--force"],
                    capture_output=True,
                )
            subprocess.run(
                ["incus", "delete", inst_name, "--project", name, "--force"],
                capture_output=True,
            )

    networks = incus_json(["network", "list", "--project", name])
    if isinstance(networks, list):
        for net in networks:
            if net.get("managed"):
                subprocess.run(
                    ["incus", "network", "delete", net["name"], "--project", name],
                    capture_output=True,
                )

    subprocess.run(["incus", "project", "delete", name], capture_output=True)
