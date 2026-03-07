"""Calcul d'adressage automatique des domaines et machines."""

from __future__ import annotations

from anklume.engine.models import TRUST_LEVELS, Infrastructure


def assign_addresses(infra: Infrastructure) -> None:
    """Assigner les IPs automatiques aux machines sans IP explicite.

    Modifie l'infrastructure en place. Assigne aussi subnet et gateway
    sur chaque domaine activé.
    """
    first_octet = infra.config.addressing.first_octet
    base_octet = infra.config.addressing.base_second_octet

    # Grouper les domaines activés par trust_level, trier alphabétiquement
    domains_by_trust: dict[str, list[str]] = {}
    for name, domain in infra.domains.items():
        if not domain.enabled:
            continue
        domains_by_trust.setdefault(domain.trust_level, []).append(name)

    for names in domains_by_trust.values():
        names.sort()

    # Assigner les adresses
    for trust_level, domain_names in domains_by_trust.items():
        offset = TRUST_LEVELS.get(trust_level, 20)
        second_octet = base_octet + offset

        for domain_seq, domain_name in enumerate(domain_names):
            domain = infra.domains[domain_name]
            subnet_prefix = f"{first_octet}.{second_octet}.{domain_seq}"

            domain.subnet = f"{subnet_prefix}.0/24"
            domain.gateway = f"{subnet_prefix}.254"

            # Collecter les IPs déjà assignées (extraire le 4e octet)
            used_hosts: set[int] = set()
            for machine in domain.machines.values():
                if machine.ip:
                    parts = machine.ip.split(".")
                    if len(parts) == 4:
                        used_hosts.add(int(parts[3]))

            # Assigner les IPs manquantes (plage .1-.99 pour le statique)
            next_host = 1
            for machine_name in sorted(domain.machines.keys()):
                machine = domain.machines[machine_name]
                if machine.ip is not None:
                    continue
                while next_host in used_hosts and next_host < 100:
                    next_host += 1
                if next_host >= 100:
                    break
                machine.ip = f"{subnet_prefix}.{next_host}"
                used_hosts.add(next_host)
                next_host += 1
