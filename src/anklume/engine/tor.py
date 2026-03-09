"""Tor gateway — détection et validation des passerelles Tor.

Détecte les machines avec le rôle tor_gateway dans l'infrastructure
et valide la cohérence de la configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from anklume.engine.models import Infrastructure

log = logging.getLogger(__name__)

TOR_ROLE = "tor_gateway"


@dataclass
class TorGateway:
    """Passerelle Tor détectée dans l'infra."""

    instance: str
    domain: str
    trans_port: int = 9040
    dns_port: int = 5353
    socks_port: int = 9050


def find_tor_gateways(infra: Infrastructure) -> list[TorGateway]:
    """Détecte les machines avec le rôle tor_gateway."""
    gateways: list[TorGateway] = []

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if TOR_ROLE in machine.roles:
                gateways.append(
                    TorGateway(
                        instance=machine.full_name,
                        domain=domain.name,
                        trans_port=machine.vars.get("tor_trans_port", 9040),
                        dns_port=machine.vars.get("tor_dns_port", 5353),
                        socks_port=machine.vars.get("tor_socks_port", 9050),
                    )
                )

    return gateways


def validate_tor_config(infra: Infrastructure) -> list[str]:
    """Valide la cohérence Tor.

    Vérifications :
    - Max 1 passerelle par domaine
    - La passerelle devrait être une VM (warning si LXC)

    Returns:
        Liste de messages d'erreur/warning.
    """
    errors: list[str] = []

    for domain in infra.enabled_domains:
        tor_machines = [m for m in domain.machines.values() if TOR_ROLE in m.roles]

        if len(tor_machines) > 1:
            names = ", ".join(m.full_name for m in tor_machines)
            errors.append(
                f"Domaine {domain.name} : plusieurs passerelles Tor ({names}), max 1 autorisée"
            )

        for machine in tor_machines:
            if machine.type != "vm":
                errors.append(
                    f"{machine.full_name} : passerelle Tor recommandée en VM, "
                    f"actuellement {machine.type}"
                )

    return errors
