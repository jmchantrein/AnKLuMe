"""Tests for the system CLI (host resource monitoring)."""

import inspect

from scripts.cli.system import app


class TestSystemCLI:
    """Test system CLI commands."""

    def test_resources_command_exists(self):
        callback_names = [
            cmd.callback.__name__ if cmd.callback else cmd.name
            for cmd in app.registered_commands
        ]
        assert "resources" in callback_names

    def test_system_app_name(self):
        assert app.info.name == "system"

    def test_system_app_in_main(self):
        """system should be registered as a command group."""
        from scripts.cli import app as main_app

        group_names = []
        for grp in main_app.registered_groups:
            if grp.typer_instance and grp.typer_instance.info:
                group_names.append(grp.typer_instance.info.name)
        assert "system" in group_names

    def test_resources_has_output_option(self):
        from scripts.cli.system import resources

        sig = inspect.signature(resources)
        assert "output" in sig.parameters

    def test_resources_has_watch_option(self):
        from scripts.cli.system import resources

        sig = inspect.signature(resources)
        assert "watch" in sig.parameters

    def test_resources_has_json_option(self):
        from scripts.cli.system import resources

        sig = inspect.signature(resources)
        assert "json_output" in sig.parameters
