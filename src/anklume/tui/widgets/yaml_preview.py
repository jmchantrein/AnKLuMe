"""Preview YAML live (read-only)."""

from __future__ import annotations

import yaml
from textual.widgets import TextArea

from anklume.engine.models import Domain, Machine


def machine_to_dict(m: Machine) -> dict:
    """Convertit une Machine en dict YAML-ready (champs non-défaut uniquement)."""
    d: dict = {"description": m.description}
    if m.type != "lxc":
        d["type"] = m.type
    if m.ip is not None:
        d["ip"] = m.ip
    if m.gpu:
        d["gpu"] = True
    if m.gui:
        d["gui"] = True
    if m.ephemeral is not None:
        d["ephemeral"] = m.ephemeral
    if m.profiles != ["default"]:
        d["profiles"] = m.profiles
    if m.roles:
        d["roles"] = m.roles
    if m.config:
        d["config"] = m.config
    if m.persistent:
        d["persistent"] = m.persistent
    if m.vars:
        d["vars"] = m.vars
    if m.weight != 1:
        d["weight"] = m.weight
    if m.workspace:
        d["workspace"] = m.workspace
    return d


def domain_to_dict(d: Domain) -> dict:
    """Convertit un Domain en dict YAML-ready."""
    out: dict = {"description": d.description}
    if d.trust_level != "semi-trusted":
        out["trust_level"] = d.trust_level
    if not d.enabled:
        out["enabled"] = False
    if d.ephemeral:
        out["ephemeral"] = True
    if d.machines:
        out["machines"] = {name: machine_to_dict(m) for name, m in d.machines.items()}
    if d.profiles:
        out["profiles"] = {
            name: {"devices": p.devices, "config": p.config}
            for name, p in d.profiles.items()
            if p.devices or p.config
        }
    return out


class YamlPreview(TextArea):
    """Zone de texte read-only affichant le YAML du domaine sélectionné."""

    def __init__(self, **kwargs) -> None:
        super().__init__(
            "",
            language="yaml",
            read_only=True,
            show_line_numbers=True,
            id="yaml-preview",
            **kwargs,
        )

    def show_domain(self, domain: Domain) -> None:
        """Affiche le YAML d'un domaine."""
        data = domain_to_dict(domain)
        text = yaml.dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        self.load_text(text)

    def show_machine(self, domain: Domain, machine: Machine) -> None:
        """Affiche le YAML d'une machine dans son contexte domaine."""
        lines = [f"# {domain.name} → {machine.name}"]
        m_data = {"machines": {machine.name: machine_to_dict(machine)}}
        text = yaml.dump(m_data, default_flow_style=False, allow_unicode=True, sort_keys=False)
        lines.append(text)
        self.load_text("\n".join(lines))

    def show_empty(self) -> None:
        """Vide le preview."""
        self.load_text("# Sélectionner un domaine ou une machine")
