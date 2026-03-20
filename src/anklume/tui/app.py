"""Application TUI anklume — point d'entrée."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import yaml
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, TabbedContent, TabPane

from anklume.engine.models import Domain, Infrastructure, Machine
from anklume.engine.parser import ParseError, parse_project
from anklume.engine.validator import validate
from anklume.tui.widgets.domain_form import DomainForm
from anklume.tui.widgets.domain_tree import DomainTree, NodeData
from anklume.tui.widgets.machine_form import MachineForm
from anklume.tui.widgets.policy_table import PolicyTable
from anklume.tui.widgets.yaml_preview import YamlPreview, domain_to_dict


class AnklumeTUI(App):
    """TUI interactif pour éditer les domaines et politiques anklume."""

    CSS_PATH = "styles/app.tcss"
    TITLE = "anklume"
    BINDINGS: ClassVar[list[Binding]] = [
        Binding("ctrl+s", "save", "Sauver", show=True),
        Binding("ctrl+q", "quit", "Quitter", show=True),
        Binding("a", "add_node", "Ajouter", show=True),
        Binding("d", "delete_node", "Supprimer", show=True),
    ]

    def __init__(self, project_dir: Path | None = None) -> None:
        super().__init__()
        self._project_dir = project_dir or Path.cwd()
        self._infra: Infrastructure | None = None
        self._current_node: NodeData | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Domaines", id="tab-domains"), Horizontal(id="main-container"):
                yield DomainTree(id="tree-pane")
                with Vertical(id="detail-pane"):
                    with Vertical(id="form-pane"):
                        yield DomainForm()
                        yield MachineForm()
                    yield YamlPreview()
            with TabPane("Politiques", id="tab-policies"):
                yield PolicyTable()
        yield Footer()

    def on_mount(self) -> None:
        """Charge le projet au démarrage."""
        self._load_project()

    def _load_project(self) -> None:
        """Parse le projet et charge les widgets."""
        try:
            self._infra = parse_project(self._project_dir)
        except ParseError as e:
            self.notify(f"Erreur de parsing : {e}", severity="error")
            return

        result = validate(self._infra)
        if not result.valid:
            self.notify("Projet chargé avec des erreurs de validation", severity="warning")

        # Charger l'arbre
        tree = self.query_one(DomainTree)
        tree.load_infra(self._infra)

        # Charger les politiques
        policy_table = self.query_one(PolicyTable)
        policy_table.load_infra(self._infra)

        # Masquer les formulaires par défaut
        self.query_one(DomainForm).display = False
        self.query_one(MachineForm).display = False
        self.query_one(YamlPreview).show_empty()

        self.sub_title = str(self._project_dir)

    def on_domain_tree_selected(self, message: DomainTree.Selected) -> None:
        """Réagit à la sélection dans l'arbre."""
        self._current_node = message.data
        domain_form = self.query_one(DomainForm)
        machine_form = self.query_one(MachineForm)
        preview = self.query_one(YamlPreview)
        tree = self.query_one(DomainTree)

        if message.data.kind == "domain":
            domain = tree.get_domain(message.data.domain_name)
            if domain:
                domain_form.display = True
                machine_form.display = False
                domain_form.load_domain(domain)
                preview.show_domain(domain)

        elif message.data.kind == "machine":
            machine = tree.get_machine(message.data.domain_name, message.data.machine_name)
            domain = tree.get_domain(message.data.domain_name)
            if machine and domain:
                domain_form.display = False
                machine_form.display = True
                machine_form.load_machine(machine, message.data.domain_name)
                preview.show_machine(domain, machine)

        else:
            domain_form.display = False
            machine_form.display = False
            preview.show_empty()

    def _update_preview(self) -> None:
        """Met à jour le preview YAML depuis le nœud courant."""
        if not self._current_node or not self._infra:
            return
        preview = self.query_one(YamlPreview)
        tree = self.query_one(DomainTree)

        if self._current_node.kind == "domain":
            domain = tree.get_domain(self._current_node.domain_name)
            if domain:
                self.query_one(DomainForm).apply_to_domain(domain)
                preview.show_domain(domain)

        elif self._current_node.kind == "machine":
            machine = tree.get_machine(
                self._current_node.domain_name,
                self._current_node.machine_name,
            )
            domain = tree.get_domain(self._current_node.domain_name)
            if machine and domain:
                self.query_one(MachineForm).apply_to_machine(machine)
                preview.show_machine(domain, machine)

    def on_domain_form_changed(self, message: DomainForm.Changed) -> None:
        self._update_preview()

    def on_machine_form_changed(self, message: MachineForm.Changed) -> None:
        self._update_preview()

    def action_save(self) -> None:
        """Sauvegarde tous les fichiers domaine et politiques."""
        if not self._infra:
            return

        # Appliquer les formulaires avant de sauver
        self._update_preview()

        errors: list[str] = []

        try:
            domains_dir = self._project_dir / "domains"
            domains_dir.mkdir(exist_ok=True)
        except OSError as e:
            self.notify(f"Erreur de sauvegarde : {e}", severity="error")
            return

        # Sauver chaque domaine (continue si un fichier échoue)
        for domain in self._infra.domains.values():
            path = domains_dir / f"{domain.name}.yml"
            data = domain_to_dict(domain)
            try:
                with open(path, "w") as f:
                    yaml.dump(
                        data, f, default_flow_style=False, allow_unicode=True, sort_keys=False
                    )
            except OSError as e:
                errors.append(f"{domain.name}: {e}")

        # Sauver les politiques
        policy_table = self.query_one(PolicyTable)
        policies = policy_table.policies
        policies_path = self._project_dir / "policies.yml"
        if policies:
            policies_data = {
                "policies": [
                    {
                        "description": p.description,
                        "from": p.from_target,
                        "to": p.to_target,
                        "ports": p.ports,
                        "protocol": p.protocol,
                        **({"bidirectional": True} if p.bidirectional else {}),
                    }
                    for p in policies
                ]
            }
            try:
                with open(policies_path, "w") as f:
                    yaml.dump(
                        policies_data,
                        f,
                        default_flow_style=False,
                        allow_unicode=True,
                        sort_keys=False,
                    )
            except OSError as e:
                errors.append(f"policies: {e}")

        if errors:
            self.notify(f"Erreurs : {', '.join(errors)}", severity="error")
        else:
            self.notify(
                f"Sauvegardé : {len(self._infra.domains)} domaines, {len(policies)} politiques"
            )

    def action_add_node(self) -> None:
        """Ajouter un domaine ou une machine."""
        if not self._infra:
            return

        if self._current_node and self._current_node.kind == "domain":
            # Ajouter une machine au domaine sélectionné
            domain = self._infra.domains.get(self._current_node.domain_name)
            if domain:
                # Trouver un nom unique
                i = 1
                while f"new-{i}" in domain.machines:
                    i += 1
                name = f"new-{i}"
                machine = Machine(
                    name=name,
                    full_name=f"{domain.name}-{name}",
                    description="Nouvelle machine",
                )
                domain.machines[name] = machine
                self.query_one(DomainTree).load_infra(self._infra)
                self.notify(f"Machine {name} ajoutée à {domain.name}")

        else:
            # Ajouter un domaine
            i = 1
            while f"new-{i}" in self._infra.domains:
                i += 1
            name = f"new-{i}"
            domain = Domain(name=name, description="Nouveau domaine")
            self._infra.domains[name] = domain
            self.query_one(DomainTree).load_infra(self._infra)
            self.notify(f"Domaine {name} ajouté")

    def action_delete_node(self) -> None:
        """Supprimer le domaine ou la machine sélectionné."""
        if not self._infra or not self._current_node:
            return

        if self._current_node.kind == "machine":
            domain = self._infra.domains.get(self._current_node.domain_name)
            if domain and self._current_node.machine_name in domain.machines:
                del domain.machines[self._current_node.machine_name]
                self._current_node = None
                self.query_one(DomainTree).load_infra(self._infra)
                self.query_one(MachineForm).display = False
                self.query_one(YamlPreview).show_empty()
                self.notify("Machine supprimée")

        elif self._current_node.kind == "domain":
            name = self._current_node.domain_name
            if name in self._infra.domains:
                del self._infra.domains[name]
                # Supprimer le fichier
                path = self._project_dir / "domains" / f"{name}.yml"
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:
                    self.notify(f"Fichier non supprimé : {e}", severity="warning")
                self._current_node = None
                self.query_one(DomainTree).load_infra(self._infra)
                self.query_one(DomainForm).display = False
                self.query_one(YamlPreview).show_empty()
                self.notify(f"Domaine {name} supprimé")
