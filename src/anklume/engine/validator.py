"""Validation de l'infrastructure anklume."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from anklume.engine.models import (
    MACHINE_TYPES,
    PROTOCOLS,
    SCHEMA_VERSION,
    TRUST_LEVELS,
    Infrastructure,
)

_DNS_SAFE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
_IP_V4 = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")


@dataclass
class ValidationError:
    """Une erreur de validation avec contexte et suggestion."""

    location: str
    message: str
    suggestion: str = ""

    def __str__(self) -> str:
        text = f"{self.location}: {self.message}"
        if self.suggestion:
            text += f"\n  → {self.suggestion}"
        return text


@dataclass
class ValidationResult:
    """Résultat de validation : liste d'erreurs."""

    errors: list[ValidationError] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def add(self, location: str, message: str, suggestion: str = "") -> None:
        self.errors.append(ValidationError(location, message, suggestion))

    def __str__(self) -> str:
        if self.valid:
            return "Validation OK"
        lines = [f"{len(self.errors)} erreur(s) de validation :"]
        for e in self.errors:
            lines.append(f"  - {e}")
        return "\n".join(lines)


def validate(infra: Infrastructure) -> ValidationResult:
    """Valider une infrastructure complète."""
    result = ValidationResult()

    _check_schema_version(infra, result)
    _check_domain_names(infra, result)
    _check_trust_levels(infra, result)
    _check_machine_names(infra, result)
    _check_machine_types(infra, result)
    _check_machine_ips(infra, result)
    _check_profile_references(infra, result)
    _check_machine_weights(infra, result)
    _check_policies(infra, result)

    return result


def _check_schema_version(infra: Infrastructure, result: ValidationResult) -> None:
    v = infra.config.schema_version
    if v > SCHEMA_VERSION:
        result.add(
            "anklume.yml",
            f"schema_version {v} est plus récent que la version supportée ({SCHEMA_VERSION}).",
            "Mettre à jour anklume ou vérifier le fichier.",
        )
    elif v < SCHEMA_VERSION:
        result.add(
            "anklume.yml",
            f"schema_version {v} est obsolète (version actuelle : {SCHEMA_VERSION}).",
            "Lancer 'anklume migrate' pour mettre à jour le format.",
        )


def _check_domain_names(infra: Infrastructure, result: ValidationResult) -> None:
    for name in infra.domains:
        if not _DNS_SAFE.match(name):
            result.add(
                f"domains/{name}.yml",
                f"nom de domaine '{name}' invalide.",
                "Utiliser uniquement [a-z0-9-], commençant et finissant par un alphanumérique.",
            )


def _check_trust_levels(infra: Infrastructure, result: ValidationResult) -> None:
    valid_levels = set(TRUST_LEVELS.keys())
    for name, domain in infra.domains.items():
        if domain.trust_level not in valid_levels:
            result.add(
                f"domains/{name}.yml",
                f"trust_level '{domain.trust_level}' invalide.",
                f"Valeurs possibles : {', '.join(sorted(valid_levels))}",
            )


def _check_machine_names(infra: Infrastructure, result: ValidationResult) -> None:
    seen: dict[str, str] = {}
    for domain_name, domain in infra.domains.items():
        for machine in domain.machines.values():
            if not _DNS_SAFE.match(machine.name):
                result.add(
                    f"domains/{domain_name}.yml",
                    f"nom de machine '{machine.name}' invalide.",
                    "Utiliser uniquement [a-z0-9-], commençant et finissant par un alphanumérique.",
                )
            if machine.full_name in seen:
                result.add(
                    f"domains/{domain_name}.yml",
                    f"nom complet '{machine.full_name}' en conflit avec "
                    f"le domaine '{seen[machine.full_name]}'.",
                    "Les noms de machines doivent être globalement uniques après préfixage.",
                )
            seen[machine.full_name] = domain_name


def _check_machine_types(infra: Infrastructure, result: ValidationResult) -> None:
    valid_types = MACHINE_TYPES
    for domain_name, domain in infra.domains.items():
        for machine_name, machine in domain.machines.items():
            if machine.type not in valid_types:
                result.add(
                    f"domains/{domain_name}.yml",
                    f"machine '{machine_name}': type '{machine.type}' invalide.",
                    "Utiliser 'lxc' ou 'vm'.",
                )


def _check_machine_ips(infra: Infrastructure, result: ValidationResult) -> None:
    seen_ips: dict[str, str] = {}
    for domain_name, domain in infra.domains.items():
        for machine_name, machine in domain.machines.items():
            if machine.ip is None:
                continue
            if not _IP_V4.match(machine.ip):
                result.add(
                    f"domains/{domain_name}.yml",
                    f"machine '{machine_name}': IP '{machine.ip}' invalide.",
                    "Utiliser le format IPv4 (ex: 10.120.1.5).",
                )
                continue
            if machine.ip in seen_ips:
                result.add(
                    f"domains/{domain_name}.yml",
                    f"machine '{machine_name}': IP '{machine.ip}' "
                    f"déjà utilisée par '{seen_ips[machine.ip]}'.",
                    "Chaque machine doit avoir une IP unique.",
                )
            seen_ips[machine.ip] = machine.full_name


def _check_profile_references(infra: Infrastructure, result: ValidationResult) -> None:
    for domain_name, domain in infra.domains.items():
        domain_profiles = set(domain.profiles.keys()) | {"default"}
        for machine_name, machine in domain.machines.items():
            for profile in machine.profiles:
                if profile not in domain_profiles:
                    result.add(
                        f"domains/{domain_name}.yml",
                        f"machine '{machine_name}': profil '{profile}' introuvable.",
                        f"Profils disponibles dans ce domaine : "
                        f"{', '.join(sorted(domain_profiles))}",
                    )


def _check_machine_weights(infra: Infrastructure, result: ValidationResult) -> None:
    for domain_name, domain in infra.domains.items():
        for machine_name, machine in domain.machines.items():
            if machine.weight < 1:
                result.add(
                    f"domains/{domain_name}.yml",
                    f"machine '{machine_name}': weight {machine.weight} invalide.",
                    "Le poids doit être >= 1.",
                )


def _check_policies(infra: Infrastructure, result: ValidationResult) -> None:
    all_domains = set(infra.domains.keys())
    all_machines = set()
    for domain in infra.domains.values():
        for machine in domain.machines.values():
            all_machines.add(machine.full_name)

    valid_targets = all_domains | all_machines | {"host"}

    for i, policy in enumerate(infra.policies):
        loc = f"policies.yml (politique #{i + 1})"
        if policy.from_target not in valid_targets:
            result.add(
                loc,
                f"'from: {policy.from_target}' ne correspond à aucun domaine ou machine.",
                f"Cibles disponibles : {', '.join(sorted(valid_targets))}",
            )
        if policy.to_target not in valid_targets:
            result.add(
                loc,
                f"'to: {policy.to_target}' ne correspond à aucun domaine ou machine.",
                f"Cibles disponibles : {', '.join(sorted(valid_targets))}",
            )
        if policy.protocol not in PROTOCOLS:
            result.add(
                loc,
                f"protocole '{policy.protocol}' invalide.",
                "Utiliser 'tcp' ou 'udp'.",
            )
