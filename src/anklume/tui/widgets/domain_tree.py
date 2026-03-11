"""Arbre de navigation domaines → machines."""

from __future__ import annotations

from dataclasses import dataclass

from textual.message import Message
from textual.widgets import Tree

from anklume.engine.models import TRUST_COLORS, Domain, Infrastructure, Machine


@dataclass
class NodeData:
    """Données attachées à un nœud de l'arbre."""

    kind: str  # "domain" | "machine" | "root"
    domain_name: str = ""
    machine_name: str = ""


class DomainTree(Tree[NodeData]):
    """Arbre navigable des domaines et machines."""

    class Selected(Message):
        """Émis quand un nœud est sélectionné."""

        def __init__(self, data: NodeData) -> None:
            self.data = data
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__("Domaines", data=NodeData(kind="root"), **kwargs)
        self._infra: Infrastructure | None = None

    def load_infra(self, infra: Infrastructure) -> None:
        """Charge l'infrastructure dans l'arbre."""
        self._infra = infra
        self.clear()
        root = self.root
        root.data = NodeData(kind="root")

        for domain in sorted(infra.domains.values(), key=lambda d: d.name):
            color = TRUST_COLORS.get(domain.trust_level)
            prefix = "◉" if domain.enabled else "○"
            label = f"{prefix} {domain.name}"
            if color:
                label = f"[{color.hex}]{label}[/]"

            domain_node = root.add(
                label,
                data=NodeData(kind="domain", domain_name=domain.name),
            )
            for machine in domain.sorted_machines:
                icon = "⚙" if machine.type == "vm" else "▪"
                gpu_tag = " 🎮" if machine.gpu else ""
                m_label = f"{icon} {machine.name}{gpu_tag}"
                domain_node.add_leaf(
                    m_label,
                    data=NodeData(
                        kind="machine",
                        domain_name=domain.name,
                        machine_name=machine.name,
                    ),
                )
            domain_node.expand()

        root.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected[NodeData]) -> None:
        """Propage la sélection vers le parent."""
        if event.node.data:
            self.post_message(self.Selected(event.node.data))

    def get_domain(self, name: str) -> Domain | None:
        """Retourne un domaine depuis l'infra chargée."""
        if self._infra:
            return self._infra.domains.get(name)
        return None

    def get_machine(self, domain_name: str, machine_name: str) -> Machine | None:
        """Retourne une machine."""
        domain = self.get_domain(domain_name)
        if domain:
            return domain.machines.get(machine_name)
        return None
