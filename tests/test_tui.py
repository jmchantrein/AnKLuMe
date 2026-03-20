"""Tests unitaires pour le TUI anklume."""

from __future__ import annotations

import pytest

pytest.importorskip("textual", reason="textual requis pour les tests TUI")

from anklume.engine.models import (
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
    Policy,
    Profile,
)
from anklume.tui.widgets.domain_tree import NodeData
from anklume.tui.widgets.yaml_preview import domain_to_dict, machine_to_dict

# --- Fixtures ---


@pytest.fixture
def sample_infra() -> Infrastructure:
    """Infrastructure de test avec 2 domaines."""
    return Infrastructure(
        config=GlobalConfig(),
        domains={
            "pro": Domain(
                name="pro",
                description="Professionnel",
                trust_level="semi-trusted",
                machines={
                    "dev": Machine(
                        name="dev",
                        full_name="pro-dev",
                        description="Développement",
                        type="lxc",
                        roles=["base", "dev-tools"],
                    ),
                    "desktop": Machine(
                        name="desktop",
                        full_name="pro-desktop",
                        description="Bureau KDE",
                        type="lxc",
                        gpu=True,
                        gui=True,
                        roles=["base", "desktop"],
                    ),
                },
            ),
            "ai-tools": Domain(
                name="ai-tools",
                description="Services IA",
                trust_level="trusted",
                machines={
                    "gpu-server": Machine(
                        name="gpu-server",
                        full_name="ai-tools-gpu-server",
                        description="Serveur GPU",
                        type="vm",
                        gpu=True,
                        roles=["base", "ollama_server"],
                        weight=3,
                    ),
                },
            ),
        },
        policies=[
            Policy(
                description="Pro accède à Ollama",
                from_target="pro",
                to_target="ai-tools",
                ports=[11434],
            ),
        ],
    )


# --- NodeData ---


class TestNodeData:
    def test_root_node(self) -> None:
        node = NodeData(kind="root")
        assert node.kind == "root"
        assert node.domain_name == ""

    def test_domain_node(self) -> None:
        node = NodeData(kind="domain", domain_name="pro")
        assert node.kind == "domain"
        assert node.domain_name == "pro"

    def test_machine_node(self) -> None:
        node = NodeData(kind="machine", domain_name="pro", machine_name="dev")
        assert node.kind == "machine"
        assert node.machine_name == "dev"


# --- YAML Serialization ---


class TestMachineToDict:
    def test_minimal_machine(self) -> None:
        m = Machine(name="web", full_name="pro-web", description="Serveur web")
        d = machine_to_dict(m)
        assert d == {"description": "Serveur web"}
        assert "type" not in d  # défaut lxc omis

    def test_vm_machine(self) -> None:
        m = Machine(name="vm1", full_name="pro-vm1", description="VM test", type="vm")
        d = machine_to_dict(m)
        assert d["type"] == "vm"

    def test_gpu_machine(self) -> None:
        m = Machine(name="gpu", full_name="ai-gpu", description="GPU", gpu=True)
        d = machine_to_dict(m)
        assert d["gpu"] is True

    def test_gui_machine(self) -> None:
        m = Machine(name="desk", full_name="pro-desk", description="Desktop", gui=True)
        d = machine_to_dict(m)
        assert d["gui"] is True

    def test_roles(self) -> None:
        m = Machine(
            name="dev",
            full_name="pro-dev",
            description="Dev",
            roles=["base", "dev-tools"],
        )
        d = machine_to_dict(m)
        assert d["roles"] == ["base", "dev-tools"]

    def test_weight_non_default(self) -> None:
        m = Machine(name="big", full_name="pro-big", description="Gros", weight=5)
        d = machine_to_dict(m)
        assert d["weight"] == 5

    def test_weight_default_omitted(self) -> None:
        m = Machine(name="std", full_name="pro-std", description="Standard")
        d = machine_to_dict(m)
        assert "weight" not in d

    def test_ip_explicit(self) -> None:
        m = Machine(
            name="fixed",
            full_name="pro-fixed",
            description="IP fixe",
            ip="10.120.0.5",
        )
        d = machine_to_dict(m)
        assert d["ip"] == "10.120.0.5"

    def test_ip_auto_omitted(self) -> None:
        m = Machine(name="auto", full_name="pro-auto", description="Auto")
        d = machine_to_dict(m)
        assert "ip" not in d

    def test_persistent_volumes(self) -> None:
        m = Machine(
            name="vol",
            full_name="pro-vol",
            description="Volumes",
            persistent={"data": "/mnt/data"},
        )
        d = machine_to_dict(m)
        assert d["persistent"] == {"data": "/mnt/data"}

    def test_vars(self) -> None:
        m = Machine(
            name="var",
            full_name="pro-var",
            description="Vars",
            vars={"llm_backend": "local"},
        )
        d = machine_to_dict(m)
        assert d["vars"] == {"llm_backend": "local"}

    def test_profiles_non_default(self) -> None:
        m = Machine(
            name="prof",
            full_name="pro-prof",
            description="Profils",
            profiles=["default", "gpu"],
        )
        d = machine_to_dict(m)
        assert d["profiles"] == ["default", "gpu"]

    def test_profiles_default_omitted(self) -> None:
        m = Machine(name="std", full_name="pro-std", description="Standard")
        d = machine_to_dict(m)
        assert "profiles" not in d

    def test_ephemeral_explicit(self) -> None:
        m = Machine(
            name="tmp",
            full_name="pro-tmp",
            description="Temp",
            ephemeral=True,
        )
        d = machine_to_dict(m)
        assert d["ephemeral"] is True

    def test_ephemeral_none_omitted(self) -> None:
        m = Machine(name="std", full_name="pro-std", description="Standard")
        d = machine_to_dict(m)
        assert "ephemeral" not in d

    def test_workspace(self) -> None:
        m = Machine(
            name="gui",
            full_name="pro-gui",
            description="GUI",
            workspace={"desktop": [1, 1], "tile": "left"},
        )
        d = machine_to_dict(m)
        assert d["workspace"] == {"desktop": [1, 1], "tile": "left"}

    def test_config_overrides(self) -> None:
        m = Machine(
            name="cfg",
            full_name="pro-cfg",
            description="Config",
            config={"limits.cpu": "4"},
        )
        d = machine_to_dict(m)
        assert d["config"] == {"limits.cpu": "4"}


class TestDomainToDict:
    def test_minimal_domain(self) -> None:
        d = Domain(name="test", description="Test domain")
        result = domain_to_dict(d)
        assert result["description"] == "Test domain"
        assert "trust_level" not in result  # défaut omis

    def test_trust_level_non_default(self) -> None:
        d = Domain(name="admin", description="Admin", trust_level="admin")
        result = domain_to_dict(d)
        assert result["trust_level"] == "admin"

    def test_disabled_domain(self) -> None:
        d = Domain(name="off", description="Désactivé", enabled=False)
        result = domain_to_dict(d)
        assert result["enabled"] is False

    def test_ephemeral_domain(self) -> None:
        d = Domain(name="tmp", description="Temp", ephemeral=True)
        result = domain_to_dict(d)
        assert result["ephemeral"] is True

    def test_with_machines(self) -> None:
        d = Domain(
            name="pro",
            description="Pro",
            machines={
                "dev": Machine(name="dev", full_name="pro-dev", description="Dev"),
            },
        )
        result = domain_to_dict(d)
        assert "machines" in result
        assert "dev" in result["machines"]
        assert result["machines"]["dev"]["description"] == "Dev"

    def test_with_profiles(self) -> None:
        d = Domain(
            name="pro",
            description="Pro",
            profiles={
                "gpu": Profile(
                    name="gpu",
                    devices={"gpu": {"type": "gpu"}},
                ),
            },
        )
        result = domain_to_dict(d)
        assert "profiles" in result
        assert "gpu" in result["profiles"]

    def test_empty_profiles_omitted(self) -> None:
        d = Domain(name="pro", description="Pro")
        result = domain_to_dict(d)
        assert "profiles" not in result

    def test_empty_machines_omitted(self) -> None:
        d = Domain(name="pro", description="Pro")
        result = domain_to_dict(d)
        assert "machines" not in result


# --- Rôles embarqués ---


class TestBuiltinRoles:
    def test_roles_discovered(self) -> None:
        from anklume.tui.widgets.machine_form import BUILTIN_ROLES

        assert isinstance(BUILTIN_ROLES, list)
        assert len(BUILTIN_ROLES) > 0
        assert "base" in BUILTIN_ROLES
        assert "desktop" in BUILTIN_ROLES
        assert "ollama_server" in BUILTIN_ROLES

    def test_roles_sorted(self) -> None:
        from anklume.tui.widgets.machine_form import BUILTIN_ROLES

        assert sorted(BUILTIN_ROLES) == BUILTIN_ROLES


# --- CLI registration ---


class TestTuiCliRegistration:
    def test_tui_command_registered(self) -> None:
        from typer.testing import CliRunner

        from anklume.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["tui", "--help"])
        assert result.exit_code == 0
        assert "TUI" in result.output or "interactif" in result.output

    def test_tui_with_project_option(self) -> None:
        from typer.testing import CliRunner

        from anklume.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["tui", "--help"])
        assert "--project" in result.output


# --- Policy parsing ---


class TestPolicyParsing:
    def test_parse_ports_numeric(self) -> None:
        from anklume.tui.widgets.policy_table import PolicyTable

        table = PolicyTable()
        assert table._parse_ports("80, 443") == [80, 443]

    def test_parse_ports_all(self) -> None:
        from anklume.tui.widgets.policy_table import PolicyTable

        table = PolicyTable()
        assert table._parse_ports("all") == "all"

    def test_parse_ports_single(self) -> None:
        from anklume.tui.widgets.policy_table import PolicyTable

        table = PolicyTable()
        assert table._parse_ports("8080") == [8080]

    def test_parse_ports_empty(self) -> None:
        from anklume.tui.widgets.policy_table import PolicyTable

        table = PolicyTable()
        assert table._parse_ports("") == []


# --- Weight validation ---


class TestWeightClamping:
    def test_valid_weight(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("5") == 5

    def test_weight_one(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("1") == 1

    def test_zero_weight_clamped(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("0") == 1

    def test_negative_weight_clamped(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("-1") == 1

    def test_overflow_weight_clamped(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("99999") == 1000

    def test_max_weight(self) -> None:
        from anklume.tui.widgets.machine_form import MAX_WEIGHT, _clamp_weight

        assert _clamp_weight("1000") == MAX_WEIGHT

    def test_empty_string_defaults(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("") == 1

    def test_non_numeric_defaults(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("abc") == 1

    def test_whitespace_stripped(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("  42  ") == 42

    def test_float_string_defaults(self) -> None:
        from anklume.tui.widgets.machine_form import _clamp_weight

        assert _clamp_weight("3.5") == 1


# --- Form mounted guard ---


class TestFormMountedGuard:
    """Vérifie que les forms ne crashent pas si appelés avant mount."""

    def test_domain_form_load_before_mount(self) -> None:
        from anklume.tui.widgets.domain_form import DomainForm

        form = DomainForm()
        domain = Domain(name="test", description="Test")
        # Ne doit pas lever d'exception (guard is_mounted)
        form.load_domain(domain)

    def test_domain_form_apply_before_mount(self) -> None:
        from anklume.tui.widgets.domain_form import DomainForm

        form = DomainForm()
        domain = Domain(name="test", description="Test")
        form.apply_to_domain(domain)
        # Le domaine ne doit pas être modifié
        assert domain.description == "Test"

    def test_machine_form_load_before_mount(self) -> None:
        from anklume.tui.widgets.machine_form import MachineForm

        form = MachineForm()
        machine = Machine(name="m1", full_name="test-m1", description="Machine")
        form.load_machine(machine, "test")

    def test_machine_form_apply_before_mount(self) -> None:
        from anklume.tui.widgets.machine_form import MachineForm

        form = MachineForm()
        machine = Machine(name="m1", full_name="test-m1", description="Machine", weight=5)
        form.apply_to_machine(machine)
        # Le poids ne doit pas être modifié
        assert machine.weight == 5
