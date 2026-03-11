"""Tests pour engine/workspace.py et cli/_workspace.py — workspace layout déclaratif."""

from __future__ import annotations

import configparser

from anklume.engine.workspace import (
    VALID_TILES,
    DesktopInfo,
    GridInfo,
    WorkspaceEntry,
    compute_grid_needs,
    parse_workspace,
    resolve_desktop_index,
    resolve_tile,
    validate_workspace_entries,
)

# ---------------------------------------------------------------------------
# WorkspaceEntry dataclass
# ---------------------------------------------------------------------------


class TestWorkspaceEntry:
    """Tests pour la dataclass WorkspaceEntry."""

    def test_defaults(self):
        """Valeurs par défaut correctes."""
        entry = WorkspaceEntry(
            machine_name="perso-firefox",
            domain_name="perso",
            trust_level="semi-trusted",
            desktop=(1, 2),
        )
        assert entry.autostart is False
        assert entry.app == ""
        assert entry.position is None
        assert entry.size is None
        assert entry.fullscreen is False
        assert entry.screen == 0

    def test_full_config(self):
        """Toutes les options renseignées."""
        entry = WorkspaceEntry(
            machine_name="pro-ide",
            domain_name="pro",
            trust_level="trusted",
            desktop=(2, 1),
            autostart=True,
            app="code",
            position=(100, 50),
            size=(1920, 1080),
            fullscreen=True,
            screen=1,
        )
        assert entry.desktop == (2, 1)
        assert entry.autostart is True
        assert entry.app == "code"
        assert entry.position == (100, 50)
        assert entry.size == (1920, 1080)
        assert entry.fullscreen is True
        assert entry.screen == 1


# ---------------------------------------------------------------------------
# DesktopInfo / GridInfo dataclasses
# ---------------------------------------------------------------------------


class TestGridInfo:
    """Tests pour les dataclasses GridInfo et DesktopInfo."""

    def test_desktop_info(self):
        d = DesktopInfo(position=0, uuid="abc-123", name="Bureau 1")
        assert d.position == 0
        assert d.uuid == "abc-123"
        assert d.name == "Bureau 1"

    def test_grid_info(self):
        desktops = [
            DesktopInfo(0, "uuid-1", "Bureau 1"),
            DesktopInfo(1, "uuid-2", "Bureau 2"),
        ]
        grid = GridInfo(cols=2, rows=1, count=2, desktops=desktops)
        assert grid.cols == 2
        assert grid.rows == 1
        assert len(grid.desktops) == 2


# ---------------------------------------------------------------------------
# compute_grid_needs
# ---------------------------------------------------------------------------


class TestComputeGridNeeds:
    """Tests pour compute_grid_needs."""

    def test_single_entry(self):
        entries = [
            WorkspaceEntry("m", "d", "t", desktop=(3, 2)),
        ]
        cols, rows = compute_grid_needs(entries)
        assert cols == 3
        assert rows == 2

    def test_multiple_entries(self):
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1)),
            WorkspaceEntry("m2", "d", "t", desktop=(4, 2)),
            WorkspaceEntry("m3", "d", "t", desktop=(2, 3)),
        ]
        cols, rows = compute_grid_needs(entries)
        assert cols == 4
        assert rows == 3

    def test_empty_entries(self):
        cols, rows = compute_grid_needs([])
        assert cols == 0
        assert rows == 0

    def test_all_same_desktop(self):
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1)),
            WorkspaceEntry("m2", "d", "t", desktop=(1, 1)),
        ]
        cols, rows = compute_grid_needs(entries)
        assert cols == 1
        assert rows == 1


# ---------------------------------------------------------------------------
# resolve_desktop_index
# ---------------------------------------------------------------------------


class TestResolveDesktopIndex:
    """Tests pour resolve_desktop_index."""

    def test_top_left(self):
        """[1,1] → index 0."""
        assert resolve_desktop_index(1, 1, grid_cols=3) == 0

    def test_second_col(self):
        """[2,1] → index 1."""
        assert resolve_desktop_index(2, 1, grid_cols=3) == 1

    def test_second_row(self):
        """[1,2] → index = grid_cols."""
        assert resolve_desktop_index(1, 2, grid_cols=3) == 3

    def test_bottom_right_3x2(self):
        """[3,2] → index 5 dans une grille 3x2."""
        assert resolve_desktop_index(3, 2, grid_cols=3) == 5

    def test_1x1_grid(self):
        """Grille minimale 1x1."""
        assert resolve_desktop_index(1, 1, grid_cols=1) == 0


# ---------------------------------------------------------------------------
# validate_workspace_entries
# ---------------------------------------------------------------------------


class TestValidateWorkspaceEntries:
    """Tests pour validate_workspace_entries."""

    def test_valid_entry(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1))]
        errors = validate_workspace_entries(entries)
        assert errors == []

    def test_desktop_zero_col(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(0, 1))]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1
        assert "colonne" in errors[0].lower() or "desktop" in errors[0].lower()

    def test_desktop_zero_row(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 0))]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1

    def test_desktop_negative(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(-1, 2))]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1

    def test_position_negative(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1), position=(-100, 50))]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1

    def test_size_negative(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1), size=(-1, 800))]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1

    def test_screen_negative(self):
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1), screen=-1)]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1

    def test_multiple_errors(self):
        entries = [
            WorkspaceEntry("m", "d", "t", desktop=(0, 0), position=(-1, -1), screen=-1),
        ]
        errors = validate_workspace_entries(entries)
        assert len(errors) >= 2

    def test_fullscreen_collision_same_desktop(self):
        """Deux machines fullscreen sur le même desktop+screen = erreur."""
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1), fullscreen=True, screen=0),
            WorkspaceEntry("m2", "d", "t", desktop=(1, 1), fullscreen=True, screen=0),
        ]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1
        assert "collision" in errors[0]
        assert "m1" in errors[0]
        assert "m2" in errors[0]

    def test_fullscreen_no_collision_different_desktop(self):
        """Deux machines fullscreen sur des desktops différents = OK."""
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1), fullscreen=True),
            WorkspaceEntry("m2", "d", "t", desktop=(2, 1), fullscreen=True),
        ]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 0

    def test_fullscreen_no_collision_different_screen(self):
        """Deux machines fullscreen sur le même desktop mais écrans différents = OK."""
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1), fullscreen=True, screen=0),
            WorkspaceEntry("m2", "d", "t", desktop=(1, 1), fullscreen=True, screen=1),
        ]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 0

    def test_no_collision_non_fullscreen(self):
        """Deux machines non-fullscreen sur le même desktop = OK (fenêtres côte à côte)."""
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1), fullscreen=False),
            WorkspaceEntry("m2", "d", "t", desktop=(1, 1), fullscreen=False),
        ]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 0

    def test_fullscreen_and_windowed_same_desktop(self):
        """Une fullscreen + une fenêtrée sur le même desktop = pas de collision."""
        entries = [
            WorkspaceEntry("m1", "d", "t", desktop=(1, 1), fullscreen=True),
            WorkspaceEntry("m2", "d", "t", desktop=(1, 1), fullscreen=False),
        ]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 0

    def test_tile_valid(self):
        """Valeurs tile valides = OK."""

        for tile in VALID_TILES:
            entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1), tile=tile)]
            errors = validate_workspace_entries(entries)
            assert errors == [], f"tile={tile} devrait être valide"

    def test_tile_invalid(self):
        """Valeur tile inconnue = erreur."""
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1), tile="center")]
        errors = validate_workspace_entries(entries)
        assert len(errors) == 1
        assert "invalide" in errors[0]

    def test_tile_conflicts_with_fullscreen(self):
        """tile + fullscreen = erreur."""
        entries = [
            WorkspaceEntry("m", "d", "t", desktop=(1, 1), tile="left", fullscreen=True),
        ]
        errors = validate_workspace_entries(entries)
        assert any("mutuellement exclusifs" in e for e in errors)

    def test_tile_conflicts_with_position(self):
        """tile + position = erreur."""
        entries = [
            WorkspaceEntry("m", "d", "t", desktop=(1, 1), tile="right", position=(0, 0)),
        ]
        errors = validate_workspace_entries(entries)
        assert any("mutuellement exclusifs" in e for e in errors)

    def test_tile_conflicts_with_size(self):
        """tile + size = erreur."""
        entries = [
            WorkspaceEntry("m", "d", "t", desktop=(1, 1), tile="left", size=(960, 1080)),
        ]
        errors = validate_workspace_entries(entries)
        assert any("mutuellement exclusifs" in e for e in errors)

    def test_tile_empty_no_error(self):
        """tile vide = pas d'erreur."""
        entries = [WorkspaceEntry("m", "d", "t", desktop=(1, 1), tile="")]
        errors = validate_workspace_entries(entries)
        assert errors == []


# ---------------------------------------------------------------------------
# resolve_tile
# ---------------------------------------------------------------------------


class TestResolveTile:
    """Tests pour resolve_tile."""

    def test_maximize_returns_none(self):
        """maximize → None (géré séparément)."""

        assert resolve_tile("maximize", 1920, 1080) is None

    def test_left_half(self):

        pos, size = resolve_tile("left", 1920, 1080)
        assert pos == (0, 0)
        assert size == (960, 1080)

    def test_right_half(self):

        pos, size = resolve_tile("right", 1920, 1080)
        assert pos == (960, 0)
        assert size == (960, 1080)

    def test_top_left_quarter(self):

        pos, size = resolve_tile("top-left", 1920, 1080)
        assert pos == (0, 0)
        assert size == (960, 540)

    def test_top_right_quarter(self):

        pos, size = resolve_tile("top-right", 1920, 1080)
        assert pos == (960, 0)
        assert size == (960, 540)

    def test_bottom_left_quarter(self):

        pos, size = resolve_tile("bottom-left", 1920, 1080)
        assert pos == (0, 540)
        assert size == (960, 540)

    def test_bottom_right_quarter(self):

        pos, size = resolve_tile("bottom-right", 1920, 1080)
        assert pos == (960, 540)
        assert size == (960, 540)

    def test_unknown_tile_returns_none(self):

        assert resolve_tile("center", 1920, 1080) is None

    def test_different_screen_size(self):

        pos, size = resolve_tile("left", 2560, 1440)
        assert pos == (0, 0)
        assert size == (1280, 1440)


# ---------------------------------------------------------------------------
# parse_workspace (intégration avec Infrastructure)
# ---------------------------------------------------------------------------


class TestParseWorkspace:
    """Tests pour parse_workspace à partir d'une Infrastructure."""

    def _make_infra(self, machines_data):
        """Helper : crée une Infrastructure minimale avec workspace."""
        from anklume.engine.models import (
            AddressingConfig,
            Defaults,
            Domain,
            GlobalConfig,
            Infrastructure,
            Machine,
        )

        machines = {}
        for name, data in machines_data.items():
            machines[name] = Machine(
                name=name,
                full_name=f"test-{name}",
                description=f"Machine {name}",
                gui=data.get("gui", False),
                workspace=data.get("workspace"),
            )

        domain = Domain(
            name="test",
            description="Domaine test",
            trust_level="semi-trusted",
            machines=machines,
        )

        config = GlobalConfig(
            defaults=Defaults(),
            addressing=AddressingConfig(),
        )

        return Infrastructure(config=config, domains={"test": domain}, policies=[])

    def test_single_machine_with_workspace(self):
        infra = self._make_infra(
            {
                "firefox": {
                    "gui": True,
                    "workspace": {
                        "desktop": [1, 2],
                        "autostart": True,
                        "app": "firefox",
                    },
                },
            }
        )
        layout = parse_workspace(infra)
        assert len(layout.entries) == 1
        assert layout.entries[0].desktop == (1, 2)
        assert layout.entries[0].autostart is True
        assert layout.entries[0].app == "firefox"
        assert layout.grid_cols == 1
        assert layout.grid_rows == 2

    def test_machine_without_workspace(self):
        infra = self._make_infra(
            {
                "server": {"gui": False},
            }
        )
        layout = parse_workspace(infra)
        assert len(layout.entries) == 0
        assert layout.grid_cols == 0
        assert layout.grid_rows == 0

    def test_workspace_none(self):
        infra = self._make_infra(
            {
                "browser": {"gui": True, "workspace": None},
            }
        )
        layout = parse_workspace(infra)
        assert len(layout.entries) == 0

    def test_multi_domain(self):
        """Entrées de plusieurs domaines."""
        from anklume.engine.models import (
            AddressingConfig,
            Defaults,
            Domain,
            GlobalConfig,
            Infrastructure,
            Machine,
        )

        m1 = Machine(
            name="firefox",
            full_name="perso-firefox",
            description="Browser",
            gui=True,
            workspace={"desktop": [1, 1], "autostart": True, "app": "firefox"},
        )
        m2 = Machine(
            name="ide",
            full_name="pro-ide",
            description="IDE",
            gui=True,
            workspace={"desktop": [2, 1], "app": "code"},
        )
        d1 = Domain(
            name="perso",
            description="Perso",
            trust_level="semi-trusted",
            machines={"firefox": m1},
        )
        d2 = Domain(name="pro", description="Pro", trust_level="trusted", machines={"ide": m2})

        config = GlobalConfig(defaults=Defaults(), addressing=AddressingConfig())
        infra = Infrastructure(config=config, domains={"perso": d1, "pro": d2}, policies=[])

        layout = parse_workspace(infra)
        assert len(layout.entries) == 2
        assert layout.grid_cols == 2
        assert layout.grid_rows == 1

    def test_disabled_domain_ignored(self):
        """Domaines désactivés ignorés."""
        from anklume.engine.models import (
            AddressingConfig,
            Defaults,
            Domain,
            GlobalConfig,
            Infrastructure,
            Machine,
        )

        m = Machine(
            name="app",
            full_name="off-app",
            description="App",
            gui=True,
            workspace={"desktop": [1, 1]},
        )
        d = Domain(name="off", description="Off", enabled=False, machines={"app": m})
        config = GlobalConfig(defaults=Defaults(), addressing=AddressingConfig())
        infra = Infrastructure(config=config, domains={"off": d}, policies=[])

        layout = parse_workspace(infra)
        assert len(layout.entries) == 0

    def test_optional_fields(self):
        """Champs optionnels (position, size, fullscreen, screen)."""
        infra = self._make_infra(
            {
                "app": {
                    "gui": True,
                    "workspace": {
                        "desktop": [3, 2],
                        "position": [100, 200],
                        "size": [1920, 1080],
                        "fullscreen": True,
                        "screen": 1,
                    },
                },
            }
        )
        layout = parse_workspace(infra)
        entry = layout.entries[0]
        assert entry.position == (100, 200)
        assert entry.size == (1920, 1080)
        assert entry.fullscreen is True
        assert entry.screen == 1

    def test_tile_field(self):
        """Champ tile: lu depuis le workspace."""
        infra = self._make_infra(
            {
                "comms": {
                    "gui": True,
                    "workspace": {
                        "desktop": [2, 1],
                        "app": "thunderbird",
                        "tile": "left",
                    },
                },
            }
        )
        layout = parse_workspace(infra)
        assert layout.entries[0].tile == "left"

    def test_tile_default_empty(self):
        """Sans tile: → chaîne vide."""
        infra = self._make_infra(
            {
                "app": {
                    "gui": True,
                    "workspace": {"desktop": [1, 1]},
                },
            }
        )
        layout = parse_workspace(infra)
        assert layout.entries[0].tile == ""


# ---------------------------------------------------------------------------
# Validation workspace dans le validator
# ---------------------------------------------------------------------------


class TestWorkspaceValidation:
    """Tests pour la validation workspace dans le validator."""

    def _make_infra_with_workspace(self, gui=True, workspace=None):
        from anklume.engine.models import (
            AddressingConfig,
            Defaults,
            Domain,
            GlobalConfig,
            Infrastructure,
            Machine,
        )

        m = Machine(
            name="app",
            full_name="test-app",
            description="App",
            gui=gui,
            workspace=workspace,
        )
        d = Domain(name="test", description="Test", machines={"app": m})
        config = GlobalConfig(defaults=Defaults(), addressing=AddressingConfig())
        return Infrastructure(config=config, domains={"test": d}, policies=[])

    def test_workspace_without_gui_rejected(self):
        """workspace: sans gui: true est une erreur."""
        from anklume.engine.validator import validate

        infra = self._make_infra_with_workspace(gui=False, workspace={"desktop": [1, 1]})
        result = validate(infra)
        assert not result.valid
        assert any("gui" in str(e).lower() for e in result.errors)

    def test_workspace_with_gui_ok(self):
        """workspace: avec gui: true est valide."""
        from anklume.engine.validator import validate

        infra = self._make_infra_with_workspace(gui=True, workspace={"desktop": [1, 1]})
        result = validate(infra)
        # Pas d'erreur workspace (il peut y avoir d'autres erreurs de domaine)
        ws_errors = [e for e in result.errors if "workspace" in str(e).lower()]
        assert len(ws_errors) == 0

    def test_workspace_bad_desktop_format(self):
        """desktop: avec un seul entier rejeté."""
        from anklume.engine.validator import validate

        infra = self._make_infra_with_workspace(gui=True, workspace={"desktop": [1]})
        result = validate(infra)
        ws_errors = [e for e in result.errors if "desktop" in str(e).lower()]
        assert len(ws_errors) >= 1

    def test_workspace_desktop_zero(self):
        """desktop: [0, 1] rejeté (1-indexed)."""
        from anklume.engine.validator import validate

        infra = self._make_infra_with_workspace(gui=True, workspace={"desktop": [0, 1]})
        result = validate(infra)
        ws_errors = [e for e in result.errors if "desktop" in str(e).lower()]
        assert len(ws_errors) >= 1

    def test_workspace_no_desktop_rejected(self):
        """workspace: sans desktop: est une erreur."""
        from anklume.engine.validator import validate

        infra = self._make_infra_with_workspace(gui=True, workspace={"autostart": True})
        result = validate(infra)
        ws_errors = [e for e in result.errors if "desktop" in str(e).lower()]
        assert len(ws_errors) >= 1


# ---------------------------------------------------------------------------
# Parser workspace dans domains/*.yml
# ---------------------------------------------------------------------------


class TestParserWorkspace:
    """Tests pour le parsing de workspace: dans le fichier domaine."""

    def test_parse_workspace_from_yaml(self, tmp_path):
        """Le parser lit workspace: depuis le YAML."""
        from anklume.engine.parser import parse_project

        # Créer un projet minimal
        project = tmp_path / "test-project"
        project.mkdir()
        (project / "anklume.yml").write_text(
            "schema_version: 1\ndefaults:\n  os_image: images:debian/13\n"
        )
        domains_dir = project / "domains"
        domains_dir.mkdir()
        (domains_dir / "perso.yml").write_text(
            """description: "Perso"
trust_level: semi-trusted
machines:
  firefox:
    description: "Navigateur"
    gui: true
    workspace:
      desktop: [2, 1]
      autostart: true
      app: firefox
      position: [0, 0]
      size: [1920, 1080]
"""
        )

        infra = parse_project(project)
        machine = infra.domains["perso"].machines["firefox"]
        assert machine.workspace is not None
        assert machine.workspace["desktop"] == [2, 1]
        assert machine.workspace["autostart"] is True
        assert machine.workspace["app"] == "firefox"
        assert machine.workspace["position"] == [0, 0]
        assert machine.workspace["size"] == [1920, 1080]

    def test_parse_no_workspace(self, tmp_path):
        """Machine sans workspace: → workspace is None."""
        from anklume.engine.parser import parse_project

        project = tmp_path / "test-project"
        project.mkdir()
        (project / "anklume.yml").write_text(
            "schema_version: 1\ndefaults:\n  os_image: images:debian/13\n"
        )
        domains_dir = project / "domains"
        domains_dir.mkdir()
        (domains_dir / "pro.yml").write_text(
            """description: "Pro"
machines:
  server:
    description: "Serveur"
"""
        )

        infra = parse_project(project)
        machine = infra.domains["pro"].machines["server"]
        assert machine.workspace is None


# ---------------------------------------------------------------------------
# CLI workspace registration
# ---------------------------------------------------------------------------


class TestWorkspaceCLI:
    """Tests d'enregistrement des commandes CLI workspace."""

    def test_workspace_app_registered(self):
        """Le typer workspace_app est enregistré dans l'app principale."""
        from anklume.cli import app

        # Chercher la commande workspace dans les typer_instances
        names = [info.name for info in app.registered_groups]
        assert "workspace" in names

    def test_workspace_load_command(self):
        """La commande load est enregistrée."""
        from anklume.cli import workspace_app

        cmd_names = [cmd.name for cmd in workspace_app.registered_commands]
        assert "load" in cmd_names

    def test_workspace_status_command(self):
        """La commande status est enregistrée."""
        from anklume.cli import workspace_app

        cmd_names = [cmd.name for cmd in workspace_app.registered_commands]
        assert "status" in cmd_names

    def test_workspace_grid_command(self):
        """La sous-commande grid est enregistrée."""
        from anklume.cli import workspace_app

        # grid est un callback avec invoke_without_command
        group_names = [info.name for info in workspace_app.registered_groups]
        assert "grid" in group_names


# ---------------------------------------------------------------------------
# kwinrulesrc workspace rules
# ---------------------------------------------------------------------------


class TestWorkspaceKwinRules:
    """Tests pour l'écriture des règles kwinrulesrc workspace."""

    def test_install_workspace_rule_desktop(self, tmp_path):
        """La règle contient desktops=<uuid>."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="perso-firefox",
            domain_name="perso",
            trust_level="semi-trusted",
            desktop=(1, 1),
            app="firefox",
        )
        uuid_map = {(1, 1): "abc-def-123"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        section = "anklume-perso-firefox"
        assert section in config
        assert config[section]["desktops"] == "abc-def-123"
        assert config[section]["desktopsrule"] == "2"

    def test_install_workspace_rule_position(self, tmp_path):
        """La règle contient position=x,y si spécifié."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="pro-ide",
            domain_name="pro",
            trust_level="trusted",
            desktop=(2, 1),
            position=(100, 50),
            size=(1200, 800),
            app="code",
        )
        uuid_map = {(2, 1): "uuid-2"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        section = "anklume-pro-ide"
        assert config[section]["position"] == "100,50"
        assert config[section]["positionrule"] == "3"
        assert config[section]["size"] == "1200,800"
        assert config[section]["sizerule"] == "3"

    def test_install_workspace_rule_fullscreen(self, tmp_path):
        """La règle contient fullscreen=true si activé."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="perso-media",
            domain_name="perso",
            trust_level="semi-trusted",
            desktop=(1, 1),
            fullscreen=True,
            app="vlc",
        )
        uuid_map = {(1, 1): "uuid-1"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        assert config["anklume-perso-media"]["fullscreen"] == "true"
        assert config["anklume-perso-media"]["fullscreenrule"] == "2"

    def test_install_workspace_rule_trust_color(self, tmp_path):
        """La règle fusionne couleur trust et desktop."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="perso-firefox",
            domain_name="perso",
            trust_level="semi-trusted",
            desktop=(1, 1),
            app="firefox",
        )
        uuid_map = {(1, 1): "uuid-1"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        section = "anklume-perso-firefox"
        # Couleur trust ET desktop dans la même section
        assert "decocolor" in config[section]
        assert "desktops" in config[section]
        assert config[section]["decocolor"] == "anklume-semi-trusted"

    def test_install_workspace_rule_tile_maximize(self, tmp_path):
        """tile: maximize → maximizehoriz + maximizevert."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="sandbox-browse",
            domain_name="sandbox",
            trust_level="disposable",
            desktop=(1, 1),
            app="firefox",
            tile="maximize",
        )
        uuid_map = {(1, 1): "uuid-1"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        section = "anklume-sandbox-browse"
        assert config[section]["maximizehoriz"] == "true"
        assert config[section]["maximizehorizrule"] == "2"
        assert config[section]["maximizevert"] == "true"
        assert config[section]["maximizevertrule"] == "2"

    def test_install_workspace_rule_tile_left(self, tmp_path):
        """tile: left → position moitié gauche, taille moitié écran."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="pro-comms",
            domain_name="pro",
            trust_level="trusted",
            desktop=(2, 1),
            app="thunderbird",
            tile="left",
        )
        uuid_map = {(2, 1): "uuid-2"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
            screen_size=(1920, 1080),
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        section = "anklume-pro-comms"
        assert config[section]["position"] == "0,0"
        assert config[section]["size"] == "960,1080"

    def test_install_workspace_rule_tile_bottom_right(self, tmp_path):
        """tile: bottom-right → position et taille quart inférieur droit."""
        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="pro-terminal",
            domain_name="pro",
            trust_level="trusted",
            desktop=(1, 1),
            app="konsole",
            tile="bottom-right",
        )
        uuid_map = {(1, 1): "uuid-1"}
        kwin_path = tmp_path / ".config" / "kwinrulesrc"

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
            screen_size=(2560, 1440),
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        section = "anklume-pro-terminal"
        assert config[section]["position"] == "1280,720"
        assert config[section]["size"] == "1280,720"

    def test_install_preserves_existing_rules(self, tmp_path):
        """Les règles existantes (non-anklume) sont préservées."""
        kwin_path = tmp_path / ".config" / "kwinrulesrc"
        kwin_path.parent.mkdir(parents=True, exist_ok=True)
        kwin_path.write_text(
            "[General]\ncount=1\nrules=my-custom-rule\n\n"
            "[my-custom-rule]\nDescription=Custom\nwmclass=kate\n"
        )

        from anklume.cli._workspace import install_workspace_rules

        entry = WorkspaceEntry(
            machine_name="perso-firefox",
            domain_name="perso",
            trust_level="semi-trusted",
            desktop=(1, 1),
            app="firefox",
        )
        uuid_map = {(1, 1): "uuid-1"}

        install_workspace_rules(
            [entry],
            uuid_map,
            kwin_path=kwin_path,
        )

        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(kwin_path))

        assert "my-custom-rule" in config
        assert "anklume-perso-firefox" in config


# ---------------------------------------------------------------------------
# Grid operations
# ---------------------------------------------------------------------------


class TestGridOperations:
    """Tests pour les opérations sur la grille de bureaux virtuels."""

    def test_compute_add_cols(self):
        """add-cols augmente le nombre de colonnes."""
        from anklume.engine.workspace import compute_grid_change

        new_count, new_rows = compute_grid_change(
            current_cols=3,
            current_rows=2,
            current_count=6,
            add_cols=1,
            add_rows=0,
        )
        assert new_count == 8  # 4 x 2
        assert new_rows == 2

    def test_compute_add_rows(self):
        """add-rows augmente le nombre de lignes."""
        from anklume.engine.workspace import compute_grid_change

        new_count, new_rows = compute_grid_change(
            current_cols=3,
            current_rows=2,
            current_count=6,
            add_cols=0,
            add_rows=1,
        )
        assert new_count == 9  # 3 x 3
        assert new_rows == 3

    def test_compute_add_both(self):
        """add-cols et add-rows simultanément."""
        from anklume.engine.workspace import compute_grid_change

        new_count, new_rows = compute_grid_change(
            current_cols=2,
            current_rows=2,
            current_count=4,
            add_cols=1,
            add_rows=1,
        )
        assert new_count == 9  # 3 x 3
        assert new_rows == 3

    def test_compute_set_grid(self):
        """set force une grille spécifique."""
        from anklume.engine.workspace import compute_grid_set

        new_count, new_rows = compute_grid_set(target_cols=4, target_rows=3)
        assert new_count == 12
        assert new_rows == 3

    def test_compute_set_grid_smaller(self):
        """set peut réduire la grille."""
        from anklume.engine.workspace import compute_grid_set

        new_count, new_rows = compute_grid_set(target_cols=2, target_rows=2)
        assert new_count == 4
        assert new_rows == 2
