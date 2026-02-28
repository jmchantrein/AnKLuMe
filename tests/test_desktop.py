"""Tests for Phase 21 desktop integration scripts."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))


# ── desktop-config.py tests ──────────────────────────────────────


class TestDesktopConfig:
    """Tests for the desktop configuration generator."""

    @pytest.fixture()
    def infra_file(self, tmp_path):
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "trust_level": "admin",
                    "machines": {"anklume-instance": {"type": "lxc", "ip": "10.100.0.10"}},
                },
                "pro": {
                    "subnet_id": 2,
                    "trust_level": "trusted",
                    "machines": {"pro-dev": {"type": "lxc", "ip": "10.100.2.10"}},
                },
                "sandbox": {
                    "subnet_id": 5,
                    "ephemeral": True,
                    "machines": {"sandbox-test": {"type": "lxc", "ip": "10.100.5.10"}},
                },
            },
        }
        path = tmp_path / "infra.yml"
        path.write_text(yaml.dump(infra, sort_keys=False))
        return str(path)

    def test_gather_domains(self, infra_file):
        from desktop_config import gather_domains
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        assert len(domains) == 3
        names = [d["name"] for d in domains]
        assert "anklume" in names
        assert "pro" in names

    def test_trust_level_inference(self, infra_file):
        from desktop_config import gather_domains
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        by_name = {d["name"]: d for d in domains}
        assert by_name["anklume"]["trust_level"] == "admin"
        assert by_name["pro"]["trust_level"] == "trusted"
        assert by_name["sandbox"]["trust_level"] == "disposable"

    def test_sway_config_generation(self, infra_file):
        from desktop_config import gather_domains, generate_sway_config
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        config = generate_sway_config(domains)
        assert "for_window" in config
        assert "anklume" in config
        assert "pro" in config
        assert "border pixel 3" in config

    def test_foot_config_generation(self, infra_file):
        from desktop_config import gather_domains, generate_foot_config
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        config = generate_foot_config(domains)
        assert "foot" in config.lower()
        assert "background=" in config

    def test_desktop_entries(self, infra_file, tmp_path):
        from desktop_config import gather_domains, generate_desktop_entries
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        output_dir = str(tmp_path / "desktop")
        entries = generate_desktop_entries(domains, output_dir)
        assert len(entries) == 3  # one per machine
        for entry_path in entries:
            content = Path(entry_path).read_text()
            assert "[Desktop Entry]" in content
            assert "domain-exec.sh" in content

    def test_color_mappings_complete(self):
        from desktop_config import TRUST_BG_COLORS, TRUST_BORDER_COLORS

        expected = {"admin", "trusted", "semi-trusted", "untrusted", "disposable"}
        assert set(TRUST_BORDER_COLORS.keys()) == expected
        assert set(TRUST_BG_COLORS.keys()) == expected


# ── dashboard.py tests ───────────────────────────────────────────


@pytest.mark.skipif(
    not shutil.which("uvicorn") and not importlib.util.find_spec("uvicorn"),
    reason="uvicorn not installed (dashboard requires fastapi/uvicorn)",
)
class TestDashboard:
    """Tests for the web dashboard (pure logic, no server)."""

    def test_render_status_html_empty(self):
        from dashboard import render_status_html

        status = {"instances": [], "networks": [], "policies": [], "project_name": "test"}
        html = render_status_html(status)
        assert "No instances found" in html
        assert "No anklume networks" in html

    def test_render_status_html_with_data(self):
        from dashboard import render_status_html

        status = {
            "instances": [{
                "name": "test-vm",
                "status": "Running",
                "type": "container",
                "project": "anklume",
                "ip": "10.100.0.10",
                "domain": "anklume",
                "trust_level": "admin",
                "colors": {"border": "#3333ff", "bg": "#0a0a2a"},
            }],
            "networks": [{"name": "net-anklume", "type": "bridge", "config": {"ipv4.address": "10.100.0.1/24"}}],
            "policies": [{"description": "test policy", "from": "anklume", "to": "pro", "ports": [80]}],
            "project_name": "test",
        }
        html = render_status_html(status)
        assert "test-vm" in html
        assert "Running" in html
        assert "net-anklume" in html
        assert "test policy" in html

    def test_trust_colors_complete(self):
        from dashboard import TRUST_COLORS

        expected = {"admin", "trusted", "semi-trusted", "untrusted", "disposable"}
        assert set(TRUST_COLORS.keys()) == expected
        for colors in TRUST_COLORS.values():
            assert "border" in colors
            assert "bg" in colors

    def test_infer_trust_level(self):
        from dashboard import infer_trust_level

        assert infer_trust_level("admin", {}) == "admin"
        assert infer_trust_level("anklume", {}) == "admin"
        assert infer_trust_level("my-admin-domain", {}) == "admin"
        assert infer_trust_level("sandbox", {"ephemeral": True}) == "disposable"
        assert infer_trust_level("pro", {}) == "trusted"
        assert infer_trust_level("pro", {"trust_level": "untrusted"}) == "untrusted"


# ── clipboard.sh tests ──────────────────────────────────────────


class TestClipboard:
    """Tests for the clipboard bridge script (argument parsing only)."""

    def test_help_exit_zero(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "clipboard.sh"), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "copy-to" in result.stdout
        assert "copy-from" in result.stdout

    def test_missing_args_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "clipboard.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


# ── domain-exec.sh tests ────────────────────────────────────────


class TestDomainExec:
    """Tests for the domain-exec wrapper (argument parsing only)."""

    def test_help_exit_zero(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "domain-exec.sh"), "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "INSTANCE" in result.stdout

    def test_missing_instance_fails(self):
        result = subprocess.run(
            ["bash", str(SCRIPTS_DIR / "domain-exec.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode != 0


# ── PipeWire audio forwarding tests ───────────────────────────────


class TestDomainExecAudio:
    """Verify domain-exec.sh sets up PipeWire audio forwarding."""

    @classmethod
    def setup_class(cls):
        # Audio setup lives in domain-lib.sh (sourced by domain-exec.sh)
        cls.content = (SCRIPTS_DIR / "domain-lib.sh").read_text()

    def test_pipewire_socket_detection(self):
        """Script checks for host PipeWire socket."""
        assert "pipewire-0" in self.content

    def test_proxy_device_setup(self):
        """Script adds Incus proxy devices for PipeWire."""
        assert "proxy" in self.content
        assert "anklume-pw" in self.content

    def test_pulseaudio_compat(self):
        """Script forwards PulseAudio compat socket for PA-only apps."""
        assert "pulse" in self.content
        assert "anklume-pa" in self.content

    def test_pipewire_env_vars(self):
        """Script sets PIPEWIRE_REMOTE and PULSE_SERVER env vars."""
        assert "PIPEWIRE_REMOTE" in self.content
        assert "PULSE_SERVER" in self.content

    def test_audio_idempotent(self):
        """Proxy device add is idempotent (ignores errors if exists)."""
        assert "2>/dev/null || true" in self.content


# ── GUI display forwarding tests ─────────────────────────────


class TestDomainExecDisplay:
    """Verify domain-exec.sh sets up Wayland/X11/GPU display forwarding."""

    @classmethod
    def setup_class(cls):
        # Display setup lives in domain-lib.sh (sourced by domain-exec.sh)
        cls.content = (SCRIPTS_DIR / "domain-lib.sh").read_text()

    def test_wayland_socket_detection(self):
        # Matrix: GF-001
        assert "wayland-0" in self.content

    def test_proxy_device_setup_wayland(self):
        # Matrix: GF-002
        assert "anklume-wl" in self.content

    def test_x11_socket_forwarding(self):
        # Matrix: GF-003
        assert "anklume-x11" in self.content
        assert ".X11-unix" in self.content

    def test_gpu_device_setup(self):
        # Matrix: GF-004
        assert "anklume-gpu" in self.content

    def test_display_env_vars(self):
        # Matrix: GF-005
        assert "WAYLAND_DISPLAY" in self.content
        assert "XDG_RUNTIME_DIR" in self.content
        assert "DISPLAY" in self.content

    def test_gui_flag_in_usage(self):
        """--gui flag is documented in domain-exec.sh usage()."""
        exec_content = (SCRIPTS_DIR / "domain-exec.sh").read_text()
        assert "--gui" in exec_content

    def test_security_warning_untrusted(self):
        # Matrix: GF-006
        assert "untrusted" in self.content
        assert "disposable" in self.content


# ── domain-lib.sh shared library tests ───────────────────────


class TestDomainLib:
    """Verify domain-lib.sh exists and is sourced by both scripts."""

    def test_library_exists(self):
        lib_path = SCRIPTS_DIR / "domain-lib.sh"
        assert lib_path.exists(), "scripts/domain-lib.sh must exist"

    def test_library_sourced_by_domain_exec(self):
        content = (SCRIPTS_DIR / "domain-exec.sh").read_text()
        assert "domain-lib.sh" in content

    def test_library_sourced_by_export_app(self):
        content = (SCRIPTS_DIR / "export-app.sh").read_text()
        assert "domain-lib.sh" in content

    def test_library_not_directly_executable(self):
        """Library has a source guard preventing direct execution."""
        content = (SCRIPTS_DIR / "domain-lib.sh").read_text()
        assert "BASH_SOURCE" in content
