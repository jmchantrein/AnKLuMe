"""Tests for the console generator (scripts/console.py)."""

import sys
from pathlib import Path

# Add scripts/ to sys.path (same as conftest.py does for generate.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import console  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture()
def sample_infra():
    """Minimal valid infra.yml as a dict for console tests."""
    return {
        "project_name": "test-console",
        "global": {
            "base_subnet": "10.100",
            "default_os_image": "images:debian/13",
        },
        "domains": {
            "anklume": {
                "description": "Administration",
                "subnet_id": 0,
                "trust_level": "admin",
                "machines": {
                    "admin-ctrl": {
                        "description": "Controller",
                        "type": "lxc",
                        "ip": "10.100.0.10",
                    },
                },
            },
            "lab": {
                "description": "Lab environment",
                "subnet_id": 1,
                "ephemeral": True,
                "machines": {
                    "lab-web": {
                        "type": "lxc",
                        "ip": "10.100.1.10",
                    },
                    "lab-db": {
                        "type": "lxc",
                        "ip": "10.100.1.11",
                    },
                },
            },
        },
    }


# -- infer_trust_level --------------------------------------------------------


def test_infer_trust_level_admin():
    """Domain name containing 'admin' or 'anklume' infers admin trust level."""
    assert console.infer_trust_level("admin", {}) == "admin"
    assert console.infer_trust_level("anklume", {}) == "admin"


def test_infer_trust_level_contains_admin():
    """Domain name containing 'admin' or 'anklume' infers admin trust level."""
    assert console.infer_trust_level("my-admin", {}) == "admin"
    assert console.infer_trust_level("admin-tools", {}) == "admin"
    assert console.infer_trust_level("my-anklume", {}) == "admin"


def test_infer_trust_level_ephemeral():
    """Ephemeral domain infers disposable trust level."""
    assert console.infer_trust_level("temp", {"ephemeral": True}) == "disposable"


def test_infer_trust_level_default():
    """Normal domain defaults to trusted."""
    assert console.infer_trust_level("pro", {}) == "trusted"
    assert console.infer_trust_level("work", {"ephemeral": False}) == "trusted"


# -- trust color mapping ------------------------------------------------------


def test_trust_color_mapping():
    """All 5 trust levels have a color in TRUST_COLORS."""
    expected_levels = {"admin", "trusted", "semi-trusted", "untrusted", "disposable"}
    assert set(console.TRUST_COLORS.keys()) == expected_levels
    assert set(console.TRUST_LABELS.keys()) == expected_levels


# -- build_session_config -----------------------------------------------------


def test_build_session_config(sample_infra):
    """Build session config from sample infra."""
    config = console.build_session_config(sample_infra)

    assert len(config) == 2  # anklume + lab

    # Admin window
    admin_window = config[0]
    assert admin_window["name"] == "anklume"
    assert admin_window["trust"] == "admin"
    assert admin_window["color"] == "dark blue"
    assert len(admin_window["panes"]) == 1
    assert admin_window["panes"][0]["machine"] == "admin-ctrl"
    assert "incus exec admin-ctrl --project anklume -- bash" in admin_window["panes"][0]["command"]

    # Lab window
    lab_window = config[1]
    assert lab_window["name"] == "lab"
    assert lab_window["trust"] == "disposable"  # ephemeral: true
    assert lab_window["color"] == "dark magenta"
    assert len(lab_window["panes"]) == 2
    assert lab_window["panes"][0]["machine"] == "lab-db"
    assert lab_window["panes"][1]["machine"] == "lab-web"


def test_build_session_config_explicit_trust_level(sample_infra):
    """Explicit trust_level overrides heuristic."""
    sample_infra["domains"]["lab"]["trust_level"] = "trusted"
    config = console.build_session_config(sample_infra)

    lab_window = [w for w in config if w["name"] == "lab"][0]
    assert lab_window["trust"] == "trusted"  # Explicit, not disposable


def test_build_session_config_empty_domains():
    """Empty domains dict produces empty config."""
    infra = {"domains": {}}
    assert console.build_session_config(infra) == []


def test_build_session_config_domain_without_machines():
    """Domain with no machines is skipped."""
    infra = {
        "domains": {
            "empty": {
                "subnet_id": 5,
                "machines": {},
            },
        },
    }
    assert console.build_session_config(infra) == []


# -- dry-run output -----------------------------------------------------------


def test_dry_run_output(sample_infra, capsys):
    """Dry-run output contains session name, prefix, and window structure."""
    config = console.build_session_config(sample_infra)
    console.print_dry_run(config, session_name="test-session")

    captured = capsys.readouterr()
    output = captured.out

    assert "Session: test-session" in output
    assert "prefix: C-b" in output
    assert "Window [0] anklume" in output
    assert "trust: admin" in output
    assert "color: dark blue" in output
    assert "Pane: admin-ctrl" in output
    assert "incus exec admin-ctrl --project anklume -- bash" in output
    assert "Window [1] lab" in output
    assert "trust: disposable" in output


def test_dry_run_custom_prefix(sample_infra, capsys):
    """Dry-run output shows custom prefix."""
    config = console.build_session_config(sample_infra)
    console.print_dry_run(config, session_name="test", prefix="C-q")

    captured = capsys.readouterr()
    assert "prefix: C-q" in captured.out


# -- explicit trust_level override heuristic ---------------------------------


def test_explicit_trust_level_overrides_heuristic():
    """Domain with explicit trust_level uses that value, not heuristic."""
    infra = {
        "domains": {
            "anklume": {
                "subnet_id": 0,
                "trust_level": "untrusted",  # Override heuristic
                "machines": {
                    "admin-ctrl": {"type": "lxc", "ip": "10.100.0.10"},
                },
            },
            "lab": {
                "subnet_id": 1,
                "ephemeral": True,
                "trust_level": "semi-trusted",  # Override heuristic
                "machines": {
                    "lab-web": {"type": "lxc", "ip": "10.100.1.10"},
                },
            },
        },
    }

    config = console.build_session_config(infra)

    admin_window = [w for w in config if w["name"] == "anklume"][0]
    assert admin_window["trust"] == "untrusted"  # Not "admin"

    lab_window = [w for w in config if w["name"] == "lab"][0]
    assert lab_window["trust"] == "semi-trusted"  # Not "disposable"
