"""Formulaire d'édition de machine."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.validation import Length
from textual.widgets import Input, Label, Select, SelectionList, Static, Switch

from anklume.engine.models import Machine
from anklume.provisioner import BUILTIN_ROLES_DIR

BUILTIN_ROLES = (
    sorted(d.name for d in BUILTIN_ROLES_DIR.iterdir() if d.is_dir() and not d.name.startswith("."))
    if BUILTIN_ROLES_DIR.is_dir()
    else []
)

MAX_WEIGHT = 1000


def _clamp_weight(value: str) -> int:
    """Parse et clamp le poids dans [1, MAX_WEIGHT]."""
    value = value.strip()
    if value.isdigit() and value != "0":
        return min(int(value), MAX_WEIGHT)
    return 1


class MachineForm(Vertical):
    """Formulaire pour éditer les champs d'une machine."""

    class Changed(Message):
        """Émis quand un champ est modifié."""

        def __init__(self, domain_name: str, machine_name: str) -> None:
            self.domain_name = domain_name
            self.machine_name = machine_name
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(id="machine-form", **kwargs)
        self._domain_name = ""
        self._machine: Machine | None = None

    def compose(self) -> ComposeResult:
        yield Static("Machine", classes="section-title")

        with Vertical(classes="form-group"):
            yield Label("Description")
            yield Input(
                placeholder="Description de la machine",
                id="machine-description",
                validators=[Length(minimum=1)],
            )

        with Vertical(classes="form-group"):
            yield Label("Type")
            yield Select(
                [("LXC (conteneur)", "lxc"), ("VM (KVM)", "vm")],
                id="machine-type",
                value="lxc",
            )

        with Vertical(classes="form-group"):
            yield Label("IP (vide = auto)")
            yield Input(placeholder="ex: 10.120.0.5", id="machine-ip")

        with Vertical(classes="form-group"):
            yield Label("GPU")
            yield Switch(value=False, id="machine-gpu")

        with Vertical(classes="form-group"):
            yield Label("GUI")
            yield Switch(value=False, id="machine-gui")

        with Vertical(classes="form-group"):
            yield Label("Weight")
            yield Input(value="1", id="machine-weight")

        with Vertical(classes="form-group"):
            yield Label("Rôles")
            yield SelectionList[str](
                *[(role, role) for role in BUILTIN_ROLES],
                id="roles-list",
            )

    def load_machine(self, machine: Machine, domain_name: str) -> None:
        """Charge une machine dans le formulaire."""
        if not self.is_mounted:
            return
        self._machine = machine
        self._domain_name = domain_name

        self.query_one("#machine-description", Input).value = machine.description

        self.query_one("#machine-type", Select).value = machine.type
        self.query_one("#machine-ip", Input).value = machine.ip or ""
        self.query_one("#machine-gpu", Switch).value = machine.gpu
        self.query_one("#machine-gui", Switch).value = machine.gui
        self.query_one("#machine-weight", Input).value = str(machine.weight)

        # Cocher les rôles actifs
        roles_list = self.query_one("#roles-list", SelectionList)
        roles_list.deselect_all()
        for role in BUILTIN_ROLES:
            if role in machine.roles:
                roles_list.select(role)

    def apply_to_machine(self, machine: Machine) -> None:
        """Applique les valeurs du formulaire sur la machine."""
        if not self.is_mounted:
            return
        machine.description = self.query_one("#machine-description", Input).value
        mtype = self.query_one("#machine-type", Select).value
        if isinstance(mtype, str):
            machine.type = mtype
        ip_val = self.query_one("#machine-ip", Input).value.strip()
        machine.ip = ip_val if ip_val else None
        machine.gpu = self.query_one("#machine-gpu", Switch).value
        machine.gui = self.query_one("#machine-gui", Switch).value

        weight_str = self.query_one("#machine-weight", Input).value
        machine.weight = _clamp_weight(weight_str)

        roles_list = self.query_one("#roles-list", SelectionList)
        machine.roles = list(roles_list.selected)

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._machine:
            self.post_message(self.Changed(self._domain_name, self._machine.name))

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._machine:
            self.post_message(self.Changed(self._domain_name, self._machine.name))

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if self._machine:
            self.post_message(self.Changed(self._domain_name, self._machine.name))

    def on_selection_list_selected_changed(self, event: SelectionList.SelectedChanged) -> None:
        if self._machine:
            self.post_message(self.Changed(self._domain_name, self._machine.name))
