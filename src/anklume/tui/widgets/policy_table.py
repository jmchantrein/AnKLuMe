"""Table et formulaire d'édition des politiques réseau."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.validation import Length
from textual.widgets import Button, DataTable, Input, Label, Select, Static, Switch

from anklume.engine.models import Infrastructure, Policy


class PolicyTable(Vertical):
    """Table des politiques avec formulaire d'édition inline."""

    class Changed(Message):
        """Émis quand une politique est modifiée."""

    def __init__(self, **kwargs) -> None:
        super().__init__(id="policy-view", **kwargs)
        self._policies: list[Policy] = []
        self._domains: list[str] = []
        self._selected_idx: int | None = None

    def compose(self) -> ComposeResult:
        yield Static("Politiques réseau", classes="section-title")
        yield DataTable(id="policy-table")

        yield Static("Édition", classes="section-title")

        with Vertical(classes="form-group"):
            yield Label("Description")
            yield Input(
                placeholder="Justification de la politique",
                id="policy-description",
                validators=[Length(minimum=1)],
            )

        with Vertical(classes="form-group"):
            yield Label("De (from)")
            yield Select([], id="policy-from", allow_blank=True)

        with Vertical(classes="form-group"):
            yield Label("Vers (to)")
            yield Select([], id="policy-to", allow_blank=True)

        with Vertical(classes="form-group"):
            yield Label("Ports")
            yield Input(placeholder="ex: 80, 443 ou all", id="policy-ports")

        with Vertical(classes="form-group"):
            yield Label("Protocole")
            yield Select(
                [("TCP", "tcp"), ("UDP", "udp")],
                id="policy-protocol",
                value="tcp",
            )

        with Vertical(classes="form-group"):
            yield Label("Bidirectionnel")
            yield Switch(value=False, id="policy-bidirectional")

        with Horizontal(classes="action-bar"):
            yield Button("Appliquer", id="policy-apply", variant="primary")
            yield Button("+ Ajouter", id="policy-add", variant="success")
            yield Button("Supprimer", id="policy-delete", variant="error")

    def on_mount(self) -> None:
        table = self.query_one("#policy-table", DataTable)
        table.add_columns("De", "Vers", "Ports", "Proto", "Bidi", "Description")

    def load_infra(self, infra: Infrastructure) -> None:
        """Charge les politiques et domaines dans la vue."""
        self._policies = list(infra.policies)
        self._domains = sorted(infra.domains.keys())

        # Mettre à jour les Select from/to avec domaines + machines + host
        targets: list[tuple[str, str]] = [("host", "host")]
        for dname in self._domains:
            targets.append((dname, dname))
            domain = infra.domains[dname]
            for m in domain.sorted_machines:
                targets.append((f"  {m.full_name}", m.full_name))

        self.query_one("#policy-from", Select).set_options(targets)
        self.query_one("#policy-to", Select).set_options(targets)

        self._refresh_table()

    def _refresh_table(self) -> None:
        """Rafraîchit le DataTable depuis la liste des politiques."""
        table = self.query_one("#policy-table", DataTable)
        table.clear()
        for p in self._policies:
            ports_str = (
                str(p.ports) if isinstance(p.ports, str) else ", ".join(str(x) for x in p.ports)
            )
            table.add_row(
                p.from_target,
                p.to_target,
                ports_str,
                p.protocol,
                "✓" if p.bidirectional else "",
                p.description[:40],
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Charge la politique sélectionnée dans le formulaire."""
        idx = event.cursor_row
        if 0 <= idx < len(self._policies):
            self._selected_idx = idx
            p = self._policies[idx]
            self.query_one("#policy-description", Input).value = p.description
            self.query_one("#policy-from", Select).value = p.from_target
            self.query_one("#policy-to", Select).value = p.to_target
            if isinstance(p.ports, str):
                self.query_one("#policy-ports", Input).value = p.ports
            else:
                self.query_one("#policy-ports", Input).value = ", ".join(str(x) for x in p.ports)
            self.query_one("#policy-protocol", Select).value = p.protocol
            self.query_one("#policy-bidirectional", Switch).value = p.bidirectional

    def _parse_ports(self, text: str) -> list[int] | str:
        """Parse le champ ports."""
        text = text.strip()
        if text.lower() == "all":
            return "all"
        parts = [p.strip() for p in text.split(",") if p.strip()]
        return [int(p) for p in parts if p.isdigit()]

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "policy-apply" and self._selected_idx is not None:
            p = self._policies[self._selected_idx]
            p.description = self.query_one("#policy-description", Input).value
            from_val = self.query_one("#policy-from", Select).value
            if isinstance(from_val, str):
                p.from_target = from_val
            to_val = self.query_one("#policy-to", Select).value
            if isinstance(to_val, str):
                p.to_target = to_val
            p.ports = self._parse_ports(self.query_one("#policy-ports", Input).value)
            proto = self.query_one("#policy-protocol", Select).value
            if isinstance(proto, str):
                p.protocol = proto
            p.bidirectional = self.query_one("#policy-bidirectional", Switch).value
            self._refresh_table()
            self.post_message(self.Changed())

        elif event.button.id == "policy-add":
            new_policy = Policy(
                description="Nouvelle politique",
                from_target="host",
                to_target=self._domains[0] if self._domains else "host",
                ports=[],
                protocol="tcp",
                bidirectional=False,
            )
            self._policies.append(new_policy)
            self._refresh_table()
            self._selected_idx = len(self._policies) - 1
            self.post_message(self.Changed())

        elif event.button.id == "policy-delete" and self._selected_idx is not None:
            if 0 <= self._selected_idx < len(self._policies):
                self._policies.pop(self._selected_idx)
                self._selected_idx = None
                self._refresh_table()
                self.post_message(self.Changed())

    @property
    def policies(self) -> list[Policy]:
        return list(self._policies)
