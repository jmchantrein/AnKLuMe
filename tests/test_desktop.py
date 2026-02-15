"""Tests for Phase 21 desktop integration scripts."""

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
                "admin": {
                    "subnet_id": 0,
                    "trust_level": "admin",
                    "machines": {"admin-ansible": {"type": "lxc", "ip": "10.100.0.10"}},
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
        assert "admin" in names
        assert "pro" in names

    def test_trust_level_inference(self, infra_file):
        from desktop_config import gather_domains
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        by_name = {d["name"]: d for d in domains}
        assert by_name["admin"]["trust_level"] == "admin"
        assert by_name["pro"]["trust_level"] == "trusted"
        assert by_name["sandbox"]["trust_level"] == "disposable"

    def test_sway_config_generation(self, infra_file):
        from desktop_config import gather_domains, generate_sway_config
        from generate import load_infra

        infra = load_infra(infra_file)
        domains = gather_domains(infra)
        config = generate_sway_config(domains)
        assert "for_window" in config
        assert "admin" in config
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


class TestDashboard:
    """Tests for the web dashboard (pure logic, no server)."""

    def test_render_status_html_empty(self):
        from dashboard import render_status_html

        status = {"instances": [], "networks": [], "policies": [], "project_name": "test"}
        html = render_status_html(status)
        assert "No instances found" in html
        assert "No AnKLuMe networks" in html

    def test_render_status_html_with_data(self):
        from dashboard import render_status_html

        status = {
            "instances": [{
                "name": "test-vm",
                "status": "Running",
                "type": "container",
                "project": "admin",
                "ip": "10.100.0.10",
                "domain": "admin",
                "trust_level": "admin",
                "colors": {"border": "#3333ff", "bg": "#0a0a2a"},
            }],
            "networks": [{"name": "net-admin", "type": "bridge", "config": {"ipv4.address": "10.100.0.1/24"}}],
            "policies": [{"description": "test policy", "from": "admin", "to": "pro", "ports": [80]}],
            "project_name": "test",
        }
        html = render_status_html(status)
        assert "test-vm" in html
        assert "Running" in html
        assert "net-admin" in html
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
