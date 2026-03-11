"""Formulaire d'édition de domaine."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.validation import Length
from textual.widgets import Input, Label, Select, Static, Switch

from anklume.engine.models import TRUST_LEVELS, Domain


class DomainForm(Vertical):
    """Formulaire pour éditer les champs d'un domaine."""

    class Changed(Message):
        """Émis quand un champ est modifié."""

        def __init__(self, domain_name: str) -> None:
            self.domain_name = domain_name
            super().__init__()

    def __init__(self, **kwargs) -> None:
        super().__init__(id="domain-form", **kwargs)
        self._domain: Domain | None = None

    def compose(self) -> ComposeResult:
        yield Static("Domaine", classes="section-title")

        with Vertical(classes="form-group"):
            yield Label("Description")
            yield Input(
                placeholder="Description du domaine",
                id="domain-description",
                validators=[Length(minimum=1)],
            )

        with Vertical(classes="form-group"):
            yield Label("Trust level")
            yield Select(
                [(level, level) for level in TRUST_LEVELS],
                id="domain-trust-level",
                value="semi-trusted",
            )

        with Vertical(classes="form-group"):
            yield Label("Activé")
            yield Switch(value=True, id="domain-enabled")

        with Vertical(classes="form-group"):
            yield Label("Éphémère")
            yield Switch(value=False, id="domain-ephemeral")

    def load_domain(self, domain: Domain) -> None:
        """Charge un domaine dans le formulaire."""
        self._domain = domain
        self.query_one("#domain-description", Input).value = domain.description
        self.query_one("#domain-trust-level", Select).value = domain.trust_level
        self.query_one("#domain-enabled", Switch).value = domain.enabled
        self.query_one("#domain-ephemeral", Switch).value = domain.ephemeral

    def apply_to_domain(self, domain: Domain) -> None:
        """Applique les valeurs du formulaire sur le domaine."""
        domain.description = self.query_one("#domain-description", Input).value
        trust = self.query_one("#domain-trust-level", Select).value
        if isinstance(trust, str):
            domain.trust_level = trust
        domain.enabled = self.query_one("#domain-enabled", Switch).value
        domain.ephemeral = self.query_one("#domain-ephemeral", Switch).value

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._domain:
            self.post_message(self.Changed(self._domain.name))

    def on_select_changed(self, event: Select.Changed) -> None:
        if self._domain:
            self.post_message(self.Changed(self._domain.name))

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if self._domain:
            self.post_message(self.Changed(self._domain.name))
