"""Driver Incus — wrapper typé autour de subprocess + incus CLI.

Ce module encapsule tous les appels à la CLI Incus. Le reste du moteur
utilise ce driver, jamais subprocess directement.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field


class IncusError(Exception):
    """Erreur lors d'un appel à la CLI Incus."""

    def __init__(self, command: list[str], returncode: int, stderr: str) -> None:
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        cmd_str = " ".join(command)
        super().__init__(f"Commande échouée ({returncode}): {cmd_str}\n{stderr}")


@dataclass
class IncusProject:
    """État d'un projet Incus."""

    name: str
    description: str = ""


@dataclass
class IncusNetwork:
    """État d'un réseau Incus."""

    name: str
    type: str = "bridge"
    config: dict = field(default_factory=dict)


@dataclass
class IncusSnapshot:
    """Snapshot d'une instance Incus."""

    name: str
    created_at: str = ""


@dataclass
class IncusImage:
    """Image Incus."""

    fingerprint: str
    aliases: list[str] = field(default_factory=list)
    size: int = 0  # octets
    created_at: str = ""


@dataclass
class IncusInstance:
    """État d'une instance Incus."""

    name: str
    status: str
    type: str
    project: str
    profiles: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)


class IncusDriver:
    """Interface typée vers la CLI Incus.

    Toutes les méthodes encapsulent un appel subprocess vers `incus`.
    """

    def _run(
        self,
        args: list[str],
        *,
        check: bool = True,
        input: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Exécute une commande incus et retourne le résultat."""
        cmd = ["incus", *args]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            input=input,
        )
        if check and result.returncode != 0:
            raise IncusError(cmd, result.returncode, result.stderr)
        return result

    def _run_json(self, args: list[str]) -> list | dict:
        """Exécute une commande incus et parse la sortie JSON."""
        cmd = [*args, "--format", "json"]
        result = self._run(cmd)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as e:
            raise IncusError(
                ["incus", *cmd], 0, f"JSON invalide: {e}\nSortie: {result.stdout[:500]}"
            ) from None

    # --- Projets ---

    def project_list(self) -> list[IncusProject]:
        data = self._run_json(["project", "list"])
        return [IncusProject(name=p["name"], description=p.get("description", "")) for p in data]

    def project_create(self, name: str, description: str = "") -> None:
        args = [
            "project",
            "create",
            name,
            "-c",
            "features.images=false",
            "-c",
            "features.profiles=false",
        ]
        if description:
            args.extend(["--description", description])
        self._run(args)

    def project_exists(self, name: str) -> bool:
        return any(p.name == name for p in self.project_list())

    # --- Réseaux ---

    def network_list(self, project: str) -> list[IncusNetwork]:
        data = self._run_json(["network", "list", "--project", project])
        return [
            IncusNetwork(
                name=n["name"],
                type=n.get("type", "bridge"),
                config=n.get("config", {}),
            )
            for n in data
        ]

    def network_create(self, name: str, project: str, config: dict | None = None) -> None:
        args = ["network", "create", name, "--project", project, "--type", "bridge"]
        for key, value in (config or {}).items():
            args.extend([f"{key}={value}"])
        self._run(args)

    def network_exists(self, name: str, project: str) -> bool:
        return any(n.name == name for n in self.network_list(project))

    # --- Instances ---

    def instance_list(self, project: str) -> list[IncusInstance]:
        data = self._run_json(["list", "--project", project])
        return [
            IncusInstance(
                name=i["name"],
                status=i.get("status", "Unknown"),
                type=i.get("type", "container"),
                project=project,
                profiles=i.get("profiles", []),
                config=i.get("config", {}),
            )
            for i in data
        ]

    def instance_create(
        self,
        name: str,
        project: str,
        image: str,
        instance_type: str = "container",
        profiles: list[str] | None = None,
        config: dict | None = None,
        network: str | None = None,
    ) -> None:
        args = ["init", image, name, "--project", project]
        if instance_type == "virtual-machine":
            args.append("--vm")
        if network:
            args.extend(["--network", network])
        for profile in profiles or []:
            args.extend(["-p", profile])
        for key, value in (config or {}).items():
            args.extend(["-c", f"{key}={value}"])
        self._run(args)

    def instance_start(self, name: str, project: str) -> None:
        self._run(["start", name, "--project", project])

    def instance_stop(self, name: str, project: str) -> None:
        self._run(["stop", name, "--project", project])

    def instance_delete(self, name: str, project: str) -> None:
        self._run(["delete", name, "--project", project])

    # --- Snapshots ---

    def snapshot_create(self, instance: str, project: str, name: str) -> None:
        self._run(["snapshot", "create", instance, name, "--project", project])

    def snapshot_restore(self, instance: str, project: str, name: str) -> None:
        self._run(["snapshot", "restore", instance, name, "--project", project])

    def snapshot_list(self, instance: str, project: str) -> list[IncusSnapshot]:
        data = self._run_json(["snapshot", "list", instance, "--project", project])
        return [IncusSnapshot(name=s["name"], created_at=s.get("created_at", "")) for s in data]

    def snapshot_delete(self, instance: str, project: str, name: str) -> None:
        self._run(["snapshot", "delete", instance, name, "--project", project])

    def instance_config_set(self, instance: str, project: str, key: str, value: str) -> None:
        self._run(["config", "set", instance, f"{key}={value}", "--project", project])

    def network_delete(self, name: str, project: str) -> None:
        self._run(["network", "delete", name, "--project", project])

    def project_delete(self, name: str) -> None:
        self._run(["project", "delete", name])

    # --- Profils ---

    def profile_list(self, project: str) -> list[str]:
        """Liste les noms de profils dans un projet."""
        data = self._run_json(["profile", "list", "--project", project])
        return [p["name"] for p in data]

    def profile_exists(self, name: str, project: str) -> bool:
        return name in self.profile_list(project)

    def profile_create(self, name: str, project: str) -> None:
        self._run(["profile", "create", name, "--project", project])

    def profile_device_add(
        self,
        profile: str,
        device: str,
        dtype: str,
        config: dict[str, str] | None = None,
        *,
        project: str,
    ) -> None:
        args = ["profile", "device", "add", profile, device, dtype, "--project", project]
        for key, value in (config or {}).items():
            args.append(f"{key}={value}")
        self._run(args)

    # --- Info ---

    def host_resources(self) -> dict:
        """Retourne les ressources hardware de l'hôte via `incus info --resources`."""
        return self._run_json(["info", "--resources"])

    # --- Fichiers ---

    def file_push(
        self,
        instance: str,
        project: str,
        local_path: str,
        remote_path: str,
    ) -> None:
        """Push un fichier vers une instance via incus file push."""
        self._run(
            [
                "file",
                "push",
                local_path,
                f"{instance}{remote_path}",
                "--project",
                project,
            ]
        )

    def file_pull(
        self,
        instance: str,
        project: str,
        remote_path: str,
        local_path: str,
    ) -> None:
        """Pull un fichier depuis une instance via incus file pull."""
        self._run(
            [
                "file",
                "pull",
                f"{instance}{remote_path}",
                local_path,
                "--project",
                project,
            ]
        )

    # --- Images ---

    def image_publish(
        self,
        instance: str,
        project: str,
        *,
        alias: str,
    ) -> dict:
        """Publie une instance comme image.

        Returns:
            Dict avec fingerprint et size.
        """
        result = self._run(
            [
                "publish",
                instance,
                "--project",
                project,
                "--alias",
                alias,
            ]
        )
        # Parse la sortie pour récupérer le fingerprint
        # Format typique: "Instance published with fingerprint: <fp>"
        fingerprint = ""
        for line in result.stdout.splitlines():
            if "fingerprint" in line.lower():
                parts = line.split(":")
                if len(parts) >= 2:
                    fingerprint = parts[-1].strip()

        return {"fingerprint": fingerprint, "size": 0}

    def image_list(self, project: str = "default") -> list[IncusImage]:
        """Liste les images Incus du projet."""
        data = self._run_json(["image", "list", "--project", project])
        results: list[IncusImage] = []
        for img in data:
            aliases = [a.get("name", "") for a in img.get("aliases", [])]
            results.append(
                IncusImage(
                    fingerprint=img.get("fingerprint", ""),
                    aliases=aliases,
                    size=img.get("size", 0),
                    created_at=img.get("created_at", ""),
                )
            )
        return results

    def image_delete(self, fingerprint: str, project: str = "default") -> None:
        """Supprime une image par fingerprint."""
        self._run(["image", "delete", fingerprint, "--project", project])

    def image_alias_exists(self, alias: str, project: str = "default") -> bool:
        """Vérifie si un alias d'image existe."""
        images = self.image_list(project)
        return any(alias in img.aliases for img in images)

    # --- Exec ---

    def instance_exec(
        self,
        instance: str,
        project: str,
        command: list[str],
        *,
        input: str | None = None,
    ) -> subprocess.CompletedProcess:
        """Exécute une commande dans une instance.

        Args:
            input: données à envoyer sur stdin de la commande.
        """
        args = ["exec", instance, "--project", project, "--", *command]
        return self._run(args, input=input)
