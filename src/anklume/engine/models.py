"""Modèles de données pour l'infrastructure anklume."""

from __future__ import annotations

from dataclasses import dataclass, field

TRUST_LEVELS = {
    "admin": 0,
    "trusted": 10,
    "semi-trusted": 20,
    "untrusted": 40,
    "disposable": 50,
}

MACHINE_TYPES = {"lxc", "vm"}
PROTOCOLS = {"tcp", "udp"}

SCHEMA_VERSION = 1


@dataclass
class Machine:
    """Instance LXC ou VM dans un domaine."""

    name: str
    full_name: str
    description: str
    type: str = "lxc"
    ip: str | None = None
    ephemeral: bool | None = None
    gpu: bool = False
    profiles: list[str] = field(default_factory=lambda: ["default"])
    roles: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    persistent: dict[str, str] = field(default_factory=dict)
    vars: dict = field(default_factory=dict)
    weight: int = 1

    @property
    def incus_type(self) -> str:
        """Type Incus : 'virtual-machine' ou 'container'."""
        return "virtual-machine" if self.type == "vm" else "container"


@dataclass
class Profile:
    """Profil Incus réutilisable."""

    name: str
    devices: dict = field(default_factory=dict)
    config: dict = field(default_factory=dict)


@dataclass
class Domain:
    """Domaine = zone isolée avec sous-réseau + projet Incus + N instances."""

    name: str
    description: str
    trust_level: str = "semi-trusted"
    enabled: bool = True
    ephemeral: bool = False
    machines: dict[str, Machine] = field(default_factory=dict)
    profiles: dict[str, Profile] = field(default_factory=dict)
    subnet: str | None = None
    gateway: str | None = None

    @property
    def network_name(self) -> str:
        """Nom du bridge réseau Incus pour ce domaine."""
        return f"net-{self.name}"

    @property
    def sorted_machines(self) -> list[Machine]:
        """Machines triées par full_name."""
        return sorted(self.machines.values(), key=lambda m: m.full_name)


@dataclass
class Policy:
    """Règle de trafic inter-domaines."""

    description: str
    from_target: str
    to_target: str
    ports: list[int] | str = field(default_factory=list)
    protocol: str = "tcp"
    bidirectional: bool = False


@dataclass
class AddressingConfig:
    """Configuration de l'adressage IP."""

    base: str = "10.100"
    zone_step: int = 10

    def __post_init__(self) -> None:
        parts = self.base.split(".")
        self._first_octet = int(parts[0])
        self._base_second_octet = int(parts[1])

    @property
    def first_octet(self) -> int:
        return self._first_octet

    @property
    def base_second_octet(self) -> int:
        return self._base_second_octet


@dataclass
class NestingConfig:
    """Configuration du nesting Incus."""

    prefix: bool = True


@dataclass
class Defaults:
    """Valeurs par défaut globales."""

    os_image: str = "images:debian/13"
    trust_level: str = "semi-trusted"


@dataclass
class ResourcePolicyConfig:
    """Configuration de l'allocation des ressources."""

    host_reserve_cpu: str = "20%"
    host_reserve_memory: str = "20%"
    mode: str = "proportional"
    cpu_mode: str = "allowance"
    memory_enforce: str = "soft"
    overcommit: bool = False


@dataclass
class GpuPolicyConfig:
    """Configuration de la politique GPU."""

    policy: str = "exclusive"  # "exclusive" ou "shared"


@dataclass
class GlobalConfig:
    """Configuration globale du projet anklume."""

    schema_version: int = SCHEMA_VERSION
    defaults: Defaults = field(default_factory=Defaults)
    addressing: AddressingConfig = field(default_factory=AddressingConfig)
    nesting: NestingConfig = field(default_factory=NestingConfig)
    resource_policy: ResourcePolicyConfig | None = None
    gpu_policy: GpuPolicyConfig | None = None
    ai_access_policy: str = "exclusive"  # "exclusive" | "open"


@dataclass
class Infrastructure:
    """Représentation complète de l'infrastructure."""

    config: GlobalConfig
    domains: dict[str, Domain]
    policies: list[Policy]

    @property
    def enabled_domains(self) -> list[Domain]:
        """Domaines actifs, triés par nom."""
        return sorted(
            (d for d in self.domains.values() if d.enabled),
            key=lambda d: d.name,
        )
