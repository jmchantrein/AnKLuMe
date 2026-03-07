"""Driver Incus — wrapper typé autour de subprocess + incus CLI.

Ce module encapsule tous les appels à la CLI Incus. Le reste du moteur
utilise ce driver, jamais subprocess directement.

Phase 3 — squelette avec interface typée.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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

    Toutes les méthodes lèvent NotImplementedError jusqu'à
    l'implémentation en Phase 3.
    """

    def project_list(self) -> list[IncusProject]:
        raise NotImplementedError

    def project_create(self, name: str, description: str = "") -> None:
        raise NotImplementedError

    def project_exists(self, name: str) -> bool:
        raise NotImplementedError

    def network_list(self, project: str) -> list[IncusNetwork]:
        raise NotImplementedError

    def network_create(self, name: str, project: str, config: dict | None = None) -> None:
        raise NotImplementedError

    def instance_list(self, project: str) -> list[IncusInstance]:
        raise NotImplementedError

    def instance_create(
        self,
        name: str,
        project: str,
        image: str,
        instance_type: str = "container",
        profiles: list[str] | None = None,
        config: dict | None = None,
    ) -> None:
        raise NotImplementedError

    def instance_start(self, name: str, project: str) -> None:
        raise NotImplementedError

    def instance_stop(self, name: str, project: str) -> None:
        raise NotImplementedError

    def instance_delete(self, name: str, project: str) -> None:
        raise NotImplementedError

    def snapshot_create(self, instance: str, project: str, name: str) -> None:
        raise NotImplementedError

    def snapshot_restore(self, instance: str, project: str, name: str) -> None:
        raise NotImplementedError

    def snapshot_list(self, instance: str, project: str) -> list[str]:
        raise NotImplementedError
