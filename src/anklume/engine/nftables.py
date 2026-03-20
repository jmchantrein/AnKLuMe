"""Génération de règles nftables depuis l'infrastructure anklume.

Produit un ruleset nftables complet :
- Table dédiée `inet anklume` (isolée des autres règles)
- Forward chain drop-all + allow sélectif
- Intra-domaine autorisé, inter-domaines bloqué sauf politiques
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from anklume.engine.models import Infrastructure, Policy
from anklume.engine.tor import find_tor_gateways

log = logging.getLogger(__name__)


@dataclass
class _ResolvedTarget:
    """Cible de politique résolue en identifiants nftables."""

    bridge: str | None = None
    ip: str | None = None
    is_host: bool = False
    is_disabled: bool = False
    domain_name: str | None = None


def generate_ruleset(infra: Infrastructure) -> str:
    """Génère le ruleset nftables complet depuis l'infrastructure.

    Fonction pure : prend une Infrastructure (avec adresses assignées),
    retourne le ruleset nftables sous forme de string.
    """
    lines: list[str] = []

    lines.append("#!/usr/sbin/nft -f")
    lines.append("# Généré par anklume — sera écrasé au prochain deploy")
    lines.append("")
    lines.append("table inet anklume")
    lines.append("flush table inet anklume")
    lines.append("")
    lines.append("table inet anklume {")
    lines.append("    chain forward {")
    lines.append("        type filter hook forward priority 0; policy drop;")
    lines.append("")
    lines.append("        # Connexions établies/reliées")
    lines.append("        ct state established,related accept")

    # Passthrough pour le trafic non-anklume (Docker, libvirt, bridges manuels)
    if infra.config.network_passthrough:
        lines.append("")
        lines.append("        # Trafic hors anklume : ne pas interférer")
        lines.append('        iifname != "net-*" oifname != "net-*" accept')

    # Index full_name -> resolved target (O(1) au lieu de O(M*K) par policy)
    machine_index = _build_machine_index(infra)

    # Intra-domaine
    enabled = infra.enabled_domains
    if enabled:
        lines.append("")
        lines.append("        # --- Trafic intra-domaine ---")
        for domain in enabled:
            net = domain.network_name
            lines.append(f'        iifname "{net}" oifname "{net}" accept')

    # Politiques inter-domaines
    if infra.policies:
        lines.append("")
        lines.append("        # --- Politiques inter-domaines ---")
        for policy in infra.policies:
            _append_policy_rules(policy, infra, lines, machine_index)

    lines.append("    }")

    # Routage transparent Tor (DNAT prerouting)
    _append_tor_rules(infra, lines, machine_index)

    lines.append("}")
    lines.append("")

    return "\n".join(lines)


def _build_machine_index(infra: Infrastructure) -> dict[str, _ResolvedTarget]:
    """Construit un index full_name → ResolvedTarget pour les machines."""
    index: dict[str, _ResolvedTarget] = {}
    for domain in infra.domains.values():
        for machine in domain.machines.values():
            index[machine.full_name] = _ResolvedTarget(
                bridge=domain.network_name,
                ip=machine.ip,
                is_disabled=not domain.enabled,
                domain_name=domain.name,
            )
    return index


def _resolve_target(
    target: str,
    infra: Infrastructure,
    machine_index: dict[str, _ResolvedTarget],
) -> _ResolvedTarget | None:
    """Résout une cible de politique en identifiants nftables."""
    if target == "host":
        return _ResolvedTarget(is_host=True)

    # Domaine ?
    if target in infra.domains:
        domain = infra.domains[target]
        return _ResolvedTarget(
            bridge=domain.network_name,
            is_disabled=not domain.enabled,
            domain_name=target,
        )

    # Machine (full_name) ? — lookup O(1)
    return machine_index.get(target)


def _append_policy_rules(
    policy: Policy,
    infra: Infrastructure,
    lines: list[str],
    machine_index: dict[str, _ResolvedTarget],
) -> None:
    """Ajoute les règles nftables d'une politique aux lignes."""
    src = _resolve_target(policy.from_target, infra, machine_index)
    dst = _resolve_target(policy.to_target, infra, machine_index)

    lines.append(f"        # {policy.description}")

    # Cible non résolue : commentaire d'avertissement + log warning
    if src is None:
        log.warning("Politique ignorée : cible '%s' (from) non résolue", policy.from_target)
        lines.append(f"        # [erreur] cible '{policy.from_target}' non résolue")
        return
    if dst is None:
        log.warning("Politique ignorée : cible '%s' (to) non résolue", policy.to_target)
        lines.append(f"        # [erreur] cible '{policy.to_target}' non résolue")
        return

    # Politiques hôte : commentaire informatif uniquement
    if src.is_host or dst.is_host:
        direction = f"{policy.from_target} → {policy.to_target}"
        lines.append(f"        # [hôte] {direction} — trafic hôte libre, règle non appliquée")
        return

    # Domaine désactivé : commentaire informatif
    if src.is_disabled:
        lines.append(f"        # [ignoré] domaine '{src.domain_name}' désactivé")
        return
    if dst.is_disabled:
        lines.append(f"        # [ignoré] domaine '{dst.domain_name}' désactivé")
        return

    # Règle forward
    rule = _build_forward_rule(src, dst, policy)
    lines.append(f"        {rule}")

    # Bidirectionnel : règle inverse
    if policy.bidirectional:
        reverse = _build_forward_rule(dst, src, policy)
        lines.append(f"        {reverse}")


def _build_forward_rule(src: _ResolvedTarget, dst: _ResolvedTarget, policy: Policy) -> str:
    """Construit une règle nftables forward."""
    parts: list[str] = []

    if src.bridge:
        parts.append(f'iifname "{src.bridge}"')
    if src.ip:
        parts.append(f"ip saddr {src.ip}")
    if dst.bridge:
        parts.append(f'oifname "{dst.bridge}"')
    if dst.ip:
        parts.append(f"ip daddr {dst.ip}")

    if isinstance(policy.ports, list) and policy.ports:
        port_list = ", ".join(str(p) for p in sorted(policy.ports))
        parts.append(f"{policy.protocol} dport {{ {port_list} }}")
    elif policy.ports == "all":
        parts.append(f"meta l4proto {policy.protocol}")

    parts.append("accept")
    return " ".join(parts)


def _append_tor_rules(
    infra: Infrastructure,
    lines: list[str],
    machine_index: dict[str, _ResolvedTarget],
) -> None:
    """Ajoute les règles DNAT prerouting pour le routage transparent Tor."""
    gateways = find_tor_gateways(infra)
    if not gateways:
        return

    lines.append("")
    lines.append("    chain prerouting {")
    lines.append("        type nat hook prerouting priority dstnat; policy accept;")

    for gw in gateways:
        resolved = machine_index.get(gw.instance)
        gw_ip = resolved.ip if resolved else None
        if not gw_ip:
            log.warning(
                "Tor gateway '%s' : pas d'IP assignée, règles DNAT ignorées",
                gw.instance,
            )
            lines.append(f"        # [erreur] Tor gateway '{gw.instance}' sans IP")
            continue

        domain = infra.domains.get(gw.domain)
        if not domain:
            continue

        net = domain.network_name
        lines.append(f"        # Tor transparent : {gw.domain} -> {gw.instance}")
        lines.append(
            f'        iifname "{net}" ip saddr != {gw_ip} '
            f"tcp dport 1-65535 dnat to {gw_ip}:{gw.trans_port}"
        )
        lines.append(
            f'        iifname "{net}" ip saddr != {gw_ip} '
            f"udp dport 53 dnat to {gw_ip}:{gw.dns_port}"
        )

    lines.append("    }")
