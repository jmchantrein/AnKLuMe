"""Tests for git push production protection (pre-push hook + CLI)."""

import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestPrePushHook:
    """Test the pre-push hook script."""

    hook_path = PROJECT_ROOT / "scripts" / "hooks" / "pre-push"

    def _make_hook(self, tmp_path: Path, marker: Path) -> Path:
        """Create a patched hook script with a custom marker path."""
        wrapper = tmp_path / "test-hook.sh"
        hook_text = self.hook_path.read_text().replace(
            'DEPLOYED_MARKER="/etc/anklume/deployed"',
            f'DEPLOYED_MARKER="{marker}"',
        )
        wrapper.write_text(hook_text)
        wrapper.chmod(0o755)
        return wrapper

    def _run_hook(self, tmp_path: Path, wrapper: Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["sh", str(wrapper)],
            cwd=str(tmp_path),
            capture_output=True, text=True, timeout=10,
        )

    def test_hook_exists_and_executable(self):
        assert self.hook_path.is_file()
        assert self.hook_path.stat().st_mode & 0o111

    def test_hook_is_posix_shell(self):
        """Hook should use /bin/sh for portability."""
        first_line = self.hook_path.read_text().splitlines()[0]
        assert first_line == "#!/bin/sh"

    def test_exits_0_without_marker(self, tmp_path):
        """Without deployed marker, hook should pass."""
        marker = tmp_path / "nonexistent"
        wrapper = self._make_hook(tmp_path, marker)
        result = self._run_hook(tmp_path, wrapper)
        assert result.returncode == 0

    def test_exits_1_with_marker(self, tmp_path):
        """With /etc/anklume/deployed, hook should block."""
        marker = tmp_path / "deployed"
        marker.write_text("deployed=test\n")
        wrapper = self._make_hook(tmp_path, marker)
        result = self._run_hook(tmp_path, wrapper)
        assert result.returncode == 1
        assert "BLOCKED" in result.stdout

    def test_block_message_contains_guidance(self, tmp_path):
        """Block message should explain how to fix."""
        marker = tmp_path / "deployed"
        marker.write_text("deployed=test\n")
        wrapper = self._make_hook(tmp_path, marker)
        result = self._run_hook(tmp_path, wrapper)
        assert "anklume setup production --off" in result.stdout
        assert "--no-verify" in result.stdout

    def test_bypass_with_dev_marker(self, tmp_path):
        """With .anklume-no-verify, hook should pass even with deployed marker."""
        (tmp_path / ".anklume-no-verify").touch()
        result = subprocess.run(
            ["sh", str(self.hook_path)],
            cwd=str(tmp_path),
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0

    def test_hook_set_dash_e(self):
        """Hook uses set -e for fail-fast."""
        text = self.hook_path.read_text()
        assert "set -e" in text


class TestSetupProductionCLI:
    """Test the CLI production command."""

    def test_production_command_exists(self):
        from scripts.cli.setup import app

        callback_names = [
            cmd.callback.__name__ if cmd.callback else cmd.name
            for cmd in app.registered_commands
        ]
        assert "production" in callback_names

    def test_production_callable(self):
        from scripts.cli.setup import production
        assert callable(production)

    def test_production_on(self, tmp_path, monkeypatch):
        """Production on should create the marker file."""
        marker = tmp_path / "etc" / "anklume" / "deployed"
        marker.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr("scripts.cli.setup.Path", lambda x: marker if x == "/etc/anklume/deployed" else Path(x))
        from scripts.cli.setup import production
        production(off=False)
        assert marker.exists()
        assert "deployed=" in marker.read_text()

    def test_production_off(self, tmp_path, monkeypatch):
        """Production off should remove the marker file."""
        marker = tmp_path / "etc" / "anklume" / "deployed"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("deployed=test\n")
        monkeypatch.setattr("scripts.cli.setup.Path", lambda x: marker if x == "/etc/anklume/deployed" else Path(x))
        from scripts.cli.setup import production
        production(off=True)
        assert not marker.exists()


class TestMakefileHookInstall:
    """Test Makefile install-hooks target."""

    makefile_path = PROJECT_ROOT / "Makefile"

    def test_makefile_references_pre_push(self):
        text = self.makefile_path.read_text()
        assert "pre-push" in text

    def test_makefile_installs_both_hooks(self):
        text = self.makefile_path.read_text()
        assert "pre-commit" in text
        assert "pre-push" in text


class TestBootstrapProductionMarker:
    """Test that bootstrap --prod creates the deployed marker."""

    bootstrap_path = PROJECT_ROOT / "scripts" / "bootstrap.sh"

    def test_bootstrap_writes_deployed_marker(self):
        text = self.bootstrap_path.read_text()
        assert "/etc/anklume/deployed" in text
        assert "Production marker set" in text
