"""Parser des fichiers YAML anklume vers modèles typés."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from anklume.engine.models import (
    SCHEMA_VERSION,
    AddressingConfig,
    Defaults,
    Domain,
    GlobalConfig,
    GpuPolicyConfig,
    Infrastructure,
    Machine,
    NestingConfig,
    Policy,
    Profile,
    ResourcePolicyConfig,
)

log = logging.getLogger(__name__)

# Clés connues par section — pour détecter les typos.
# Synchroniser avec models.py si un champ est ajouté.
_GLOBAL_KEYS = {
    "schema_version",
    "defaults",
    "addressing",
    "nesting",
    "resource_policy",
    "gpu_policy",
    "ai_access_policy",
    "network_passthrough",
    "requires_anklume",
}
_DEFAULTS_KEYS = {"os_image", "trust_level"}
_ADDRESSING_KEYS = {"base", "zone_step"}
_NESTING_KEYS = {"prefix"}
_RESOURCE_POLICY_KEYS = {
    "host_reserve",
    "mode",
    "cpu_mode",
    "memory_enforce",
    "overcommit",
}
_HOST_RESERVE_KEYS = {"cpu", "memory"}
_DOMAIN_KEYS = {
    "description",
    "trust_level",
    "enabled",
    "ephemeral",
    "profiles",
    "machines",
}
_MACHINE_KEYS = {
    "description",
    "type",
    "ip",
    "ephemeral",
    "gpu",
    "gui",
    "profiles",
    "roles",
    "config",
    "persistent",
    "vars",
    "weight",
    "workspace",
}
_POLICY_KEYS = {
    "from",
    "to",
    "description",
    "ports",
    "protocol",
    "bidirectional",
}


def _warn_unknown_keys(raw: dict, known: set[str], location: str) -> None:
    """Log un warning pour chaque clé inconnue dans raw."""
    unknown = set(raw.keys()) - known
    for key in sorted(unknown):
        log.warning("Clé inconnue '%s' dans %s (ignorée)", key, location)


class ParseError(Exception):
    """Erreur de parsing d'un fichier anklume."""

    def __init__(self, path: Path, message: str) -> None:
        self.path = path
        super().__init__(f"{path}: {message}")


def parse_project(project_dir: str | Path) -> Infrastructure:
    """Parser un répertoire projet anklume complet."""
    project_dir = Path(project_dir)

    config = _parse_global_config(project_dir / "anklume.yml")
    domains = _parse_domains(project_dir / "domains", config.defaults)
    policies = _parse_policies(project_dir / "policies.yml")

    return Infrastructure(config=config, domains=domains, policies=policies)


def _parse_global_config(path: Path) -> GlobalConfig:
    """Parser anklume.yml."""
    if not path.exists():
        raise ParseError(path, "fichier introuvable. Lancer 'anklume init' d'abord.")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ParseError(path, "le fichier doit contenir un mapping YAML (clé: valeur).")

    _warn_unknown_keys(raw, _GLOBAL_KEYS, str(path))

    defaults_raw = raw.get("defaults", {})
    _warn_unknown_keys(defaults_raw, _DEFAULTS_KEYS, f"{path} > defaults")
    defaults = Defaults(
        os_image=defaults_raw.get("os_image", "images:debian/13"),
        trust_level=defaults_raw.get("trust_level", "semi-trusted"),
    )

    addressing_raw = raw.get("addressing", {})
    _warn_unknown_keys(addressing_raw, _ADDRESSING_KEYS, f"{path} > addressing")
    addressing = AddressingConfig(
        base=str(addressing_raw.get("base", "10.100")),
        zone_step=addressing_raw.get("zone_step", 10),
    )

    nesting_raw = raw.get("nesting", {})
    _warn_unknown_keys(nesting_raw, _NESTING_KEYS, f"{path} > nesting")
    nesting = NestingConfig(
        prefix=nesting_raw.get("prefix", True),
    )

    resource_policy = None
    rp_raw = raw.get("resource_policy")
    if rp_raw:
        _warn_unknown_keys(rp_raw, _RESOURCE_POLICY_KEYS, f"{path} > resource_policy")
        host_reserve = rp_raw.get("host_reserve", {})
        _warn_unknown_keys(host_reserve, _HOST_RESERVE_KEYS, f"{path} > host_reserve")
        resource_policy = ResourcePolicyConfig(
            host_reserve_cpu=str(host_reserve.get("cpu", "20%")),
            host_reserve_memory=str(host_reserve.get("memory", "20%")),
            mode=rp_raw.get("mode", "proportional"),
            cpu_mode=rp_raw.get("cpu_mode", "allowance"),
            memory_enforce=rp_raw.get("memory_enforce", "soft"),
            overcommit=rp_raw.get("overcommit", False),
        )

    gpu_policy = None
    gp_raw = raw.get("gpu_policy")
    if gp_raw is not None:
        policy_str = gp_raw if isinstance(gp_raw, str) else str(gp_raw)
        gpu_policy = GpuPolicyConfig(policy=policy_str)

    ai_access_policy = raw.get("ai_access_policy", "exclusive")
    network_passthrough = raw.get("network_passthrough", False)
    requires_anklume = raw.get("requires_anklume")
    if requires_anklume is not None:
        requires_anklume = str(requires_anklume)

    return GlobalConfig(
        schema_version=raw.get("schema_version", SCHEMA_VERSION),
        defaults=defaults,
        addressing=addressing,
        nesting=nesting,
        resource_policy=resource_policy,
        gpu_policy=gpu_policy,
        ai_access_policy=ai_access_policy,
        network_passthrough=network_passthrough,
        requires_anklume=requires_anklume,
    )


def _parse_domains(domains_dir: Path, defaults: Defaults) -> dict[str, Domain]:
    """Parser tous les fichiers domaine."""
    if not domains_dir.is_dir():
        return {}

    domains = {}
    for yml_path in sorted(domains_dir.glob("*.yml")):
        domain = _parse_domain(yml_path, defaults)
        domains[domain.name] = domain

    return domains


def _parse_domain(path: Path, defaults: Defaults) -> Domain:
    """Parser un fichier domaine individuel."""
    raw = yaml.safe_load(path.read_text())
    if not raw:
        raise ParseError(path, "fichier domaine vide.")
    if not isinstance(raw, dict):
        raise ParseError(path, "le fichier domaine doit contenir un mapping YAML.")

    _warn_unknown_keys(raw, _DOMAIN_KEYS, str(path))

    domain_name = path.stem

    if "description" not in raw:
        raise ParseError(path, "champ 'description' requis.")

    trust_level = raw.get("trust_level", defaults.trust_level)

    # Profils
    profiles = {}
    for prof_name, prof_data in (raw.get("profiles") or {}).items():
        prof_data = prof_data or {}
        profiles[prof_name] = Profile(
            name=prof_name,
            devices=prof_data.get("devices", {}),
            config=prof_data.get("config", {}),
        )

    # Machines
    machines = {}
    domain_ephemeral = raw.get("ephemeral", False)
    for machine_name, machine_data in (raw.get("machines") or {}).items():
        machine_data = machine_data or {}
        _warn_unknown_keys(machine_data, _MACHINE_KEYS, f"{path} > machines > {machine_name}")

        if "description" not in machine_data:
            raise ParseError(path, f"machine '{machine_name}': champ 'description' requis.")

        full_name = f"{domain_name}-{machine_name}"

        ephemeral = machine_data.get("ephemeral")
        if ephemeral is None:
            ephemeral = domain_ephemeral

        machines[machine_name] = Machine(
            name=machine_name,
            full_name=full_name,
            description=machine_data["description"],
            type=machine_data.get("type", "lxc"),
            ip=machine_data.get("ip"),
            ephemeral=ephemeral,
            gpu=machine_data.get("gpu", False),
            gui=machine_data.get("gui", False),
            profiles=machine_data.get("profiles", ["default"]),
            roles=machine_data.get("roles", []),
            config=machine_data.get("config", {}),
            persistent=machine_data.get("persistent", {}),
            vars=machine_data.get("vars", {}),
            weight=machine_data.get("weight", 1),
            workspace=machine_data.get("workspace"),
        )

    return Domain(
        name=domain_name,
        description=raw["description"],
        trust_level=trust_level,
        enabled=raw.get("enabled", True),
        ephemeral=domain_ephemeral,
        machines=machines,
        profiles=profiles,
    )


def _parse_policies(path: Path) -> list[Policy]:
    """Parser policies.yml."""
    if not path.exists():
        return []

    raw = yaml.safe_load(path.read_text())
    if not raw:
        return []

    policies_raw = raw.get("policies", [])
    if not policies_raw:
        return []

    policies = []
    for i, p in enumerate(policies_raw):
        _warn_unknown_keys(p, _POLICY_KEYS, f"{path} > policies[{i}]")
        if "from" not in p or "to" not in p:
            raise ParseError(path, f"politique #{i + 1}: 'from' et 'to' requis.")
        if "description" not in p:
            raise ParseError(path, f"politique #{i + 1}: 'description' requis.")

        ports = p.get("ports", [])
        if isinstance(ports, str) and ports != "all":
            raise ParseError(
                path, f"politique #{i + 1}: 'ports' doit être une liste d'entiers ou \"all\"."
            )

        policies.append(
            Policy(
                description=p["description"],
                from_target=p["from"],
                to_target=p["to"],
                ports=ports,
                protocol=p.get("protocol", "tcp"),
                bidirectional=p.get("bidirectional", False),
            )
        )

    return policies
