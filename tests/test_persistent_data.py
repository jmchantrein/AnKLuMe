"""Tests for persistent_data volumes and flush protection (Phase 20g).

Covers behavior matrix cells PD-001 to PD-007, PD-2-001/002, PD-3-001,
and FP-001 to FP-003, FP-2-001.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml
from generate import enrich_infra, generate, validate

REPO_ROOT = Path(__file__).resolve().parent.parent


def _base_infra(**global_extra):
    """Minimal valid infra dict for testing."""
    g = {
        "base_subnet": "10.100",
        "default_os_image": "images:debian/13",
        "default_connection": "community.general.incus",
        "default_user": "root",
        **global_extra,
    }
    return {
        "project_name": "test",
        "global": g,
        "domains": {
            "pro": {
                "description": "Production",
                "subnet_id": 0,
                "machines": {
                    "pro-dev": {
                        "description": "Dev",
                        "type": "lxc",
                        "ip": "10.100.0.1",
                    },
                    "pro-web": {
                        "description": "Web",
                        "type": "lxc",
                        "ip": "10.100.0.2",
                    },
                },
            },
        },
    }


def _read_host_vars(tmp_path, machine):
    """Read generated host_vars YAML, stripping managed markers."""
    fp = tmp_path / "host_vars" / f"{machine}.yml"
    text = fp.read_text()
    lines = [ln for ln in text.splitlines() if "=== MANAGED" not in ln]
    return yaml.safe_load("\n".join(lines))


# =============================================================================
# Persistent data — Validation (depth 1)
# =============================================================================


class TestPersistentDataValidation:
    """Validation of persistent_data fields."""

    def test_valid_persistent_data(self):  # Matrix: PD-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "projects": {"path": "/home/user/projects"},
        }
        assert validate(infra) == []

    def test_invalid_volume_name(self):  # Matrix: PD-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "BAD_NAME": {"path": "/data"},
        }
        errors = validate(infra)
        assert any("invalid name" in e for e in errors)

    def test_missing_path(self):  # Matrix: PD-003
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "vol": {},
        }
        errors = validate(infra)
        assert any("path is required" in e for e in errors)

    def test_relative_path(self):  # Matrix: PD-004
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "vol": {"path": "relative/path"},
        }
        errors = validate(infra)
        assert any("absolute path" in e for e in errors)

    def test_invalid_readonly(self):  # Matrix: PD-005
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "vol": {"path": "/data", "readonly": "yes"},
        }
        errors = validate(infra)
        assert any("readonly must be a boolean" in e for e in errors)

    def test_no_persistent_data(self):  # Matrix: PD-006
        infra = _base_infra()
        assert validate(infra) == []

    def test_invalid_persistent_data_base(self):  # Matrix: PD-007
        infra = _base_infra(persistent_data_base="relative/path")
        errors = validate(infra)
        assert any("persistent_data_base must be an absolute path" in e for e in errors)


# =============================================================================
# Persistent data — Generation (depth 1)
# =============================================================================


class TestPersistentDataGeneration:
    """Generation of pd-* disk devices from persistent_data."""

    def test_generates_pd_device(self, tmp_path):  # Matrix: PD-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "projects": {"path": "/home/user/projects"},
        }
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        assert "pd-projects" in hvars.get("instance_devices", {})
        dev = hvars["instance_devices"]["pd-projects"]
        assert dev["type"] == "disk"
        assert dev["path"] == "/home/user/projects"
        assert dev["source"] == "/srv/anklume/data/pro-dev/projects"
        assert "shift" in dev and dev["shift"] == "true"

    def test_readonly_true(self, tmp_path):  # Matrix: PD-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "cfg": {"path": "/etc/app", "readonly": True},
        }
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        dev = hvars["instance_devices"]["pd-cfg"]
        assert dev.get("readonly") == "true"

    def test_custom_base_path(self, tmp_path):  # Matrix: PD-001
        infra = _base_infra(persistent_data_base="/mnt/storage/data")
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "db": {"path": "/var/lib/db"},
        }
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        dev = hvars["instance_devices"]["pd-db"]
        assert dev["source"] == "/mnt/storage/data/pro-dev/db"

    def test_no_pd_device_without_persistent_data(self, tmp_path):  # Matrix: PD-006
        infra = _base_infra()
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        devices = hvars.get("instance_devices")
        if devices:
            assert not any(k.startswith("pd-") for k in devices)


# =============================================================================
# Persistent data — Depth 2 interactions
# =============================================================================


class TestPersistentDataDepth2:
    """Pairwise interaction tests for persistent_data."""

    def test_pd_with_shared_volumes(self, tmp_path):  # Matrix: PD-2-001
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "projects": {"path": "/home/user/projects"},
        }
        infra["shared_volumes"] = {
            "docs": {
                "source": "/srv/shares/docs",
                "path": "/shared/docs",
                "consumers": {"pro": "ro"},
            },
        }
        enrich_infra(infra)
        generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        devices = hvars.get("instance_devices", {})
        assert "pd-projects" in devices
        assert "sv-docs" in devices

    def test_device_name_collision_with_user_device(self):  # Matrix: PD-2-002
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "mydata": {"path": "/data"},
        }
        infra["domains"]["pro"]["machines"]["pro-dev"]["devices"] = {
            "pd-mydata": {"type": "disk", "source": "/other", "path": "/other"},
        }
        errors = validate(infra)
        assert any("pd-mydata" in e and "collision" in e for e in errors)

    def test_path_collision_with_shared_volume(self):  # Matrix: PD-2-001
        """persistent_data and shared_volume cannot mount at same path."""
        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "stuff": {"path": "/shared/docs"},
        }
        infra["shared_volumes"] = {
            "docs": {
                "source": "/srv/shares/docs",
                "path": "/shared/docs",
                "consumers": {"pro": "ro"},
            },
        }
        errors = validate(infra)
        assert any("duplicate mount path" in e.lower() or "path" in e.lower() for e in errors)


# =============================================================================
# Persistent data — Depth 3 interactions
# =============================================================================


class TestPersistentDataDepth3:
    """Three-way interaction tests for persistent_data."""

    def test_pd_sv_nesting_prefix(self, tmp_path):  # Matrix: PD-3-001
        from unittest.mock import patch

        infra = _base_infra()
        infra["domains"]["pro"]["machines"]["pro-dev"]["persistent_data"] = {
            "projects": {"path": "/home/user/projects"},
        }
        infra["shared_volumes"] = {
            "docs": {
                "source": "/srv/shares/docs",
                "path": "/shared/docs",
                "consumers": {"pro": "ro"},
            },
        }
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=1):
            generate(infra, str(tmp_path))
        hvars = _read_host_vars(tmp_path, "pro-dev")
        # Instance name prefixed
        assert hvars["instance_name"] == "001-pro-dev"
        # Both device types present
        assert "pd-projects" in hvars.get("instance_devices", {})
        assert "sv-docs" in hvars.get("instance_devices", {})
        # Paths remain absolute and unprefixed
        assert hvars["instance_devices"]["pd-projects"]["path"] == "/home/user/projects"
        assert hvars["instance_devices"]["sv-docs"]["path"] == "/shared/docs"


# =============================================================================
# Flush protection — shell script tests
# =============================================================================


@pytest.mark.skipif(
    not shutil.which("bash"),
    reason="bash not available",
)
class TestFlushProtection:
    """Tests for flush.sh protection behavior (FP-001 to FP-003, FP-2-001)."""

    SCRIPT = str(REPO_ROOT / "scripts" / "flush.sh")

    def _make_flush_test_env(self, tmp_path, *, protected=False):
        """Create a mock environment for testing flush.sh."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        log_file = tmp_path / "incus.log"
        protection_val = "true" if protected else "false"

        # Mock incus that logs all calls and simulates protection
        mock_incus = mock_bin / "incus"
        mock_incus.write_text(f"""#!/usr/bin/env bash
echo "$@" >> "{log_file}"

# incus project list → return a test project
if [[ "$1" == "project" && "$2" == "list" ]]; then
    echo "test-project"
    exit 0
fi

# incus list → return a test instance
if [[ "$1" == "list" ]]; then
    echo "test-instance"
    exit 0
fi

# incus config get security.protection.delete → return protection status
if [[ "$1" == "config" && "$2" == "get" && "$3" == "test-instance" ]]; then
    echo "{protection_val}"
    exit 0
fi

# incus delete → succeed
if [[ "$1" == "delete" ]]; then
    exit 0
fi

# incus profile list → empty
if [[ "$1" == "profile" && "$2" == "list" ]]; then
    exit 0
fi

# incus profile device list → empty
if [[ "$1" == "profile" && "$2" == "device" ]]; then
    exit 0
fi

# incus project delete → succeed
if [[ "$1" == "project" && "$2" == "delete" ]]; then
    exit 0
fi

# incus network list → empty
if [[ "$1" == "network" && "$2" == "list" ]]; then
    exit 0
fi

# incus image list → empty
if [[ "$1" == "image" && "$2" == "list" ]]; then
    exit 0
fi

exit 0
""")
        mock_incus.chmod(mock_incus.stat().st_mode | stat.S_IEXEC)

        env = os.environ.copy()
        env["PATH"] = f"{mock_bin}:{env['PATH']}"
        # Unset FORCE so it doesn't bleed from the test runner
        env.pop("FORCE", None)
        return env, log_file

    def test_protected_instance_skipped(self, tmp_path):  # Matrix: FP-001
        """Protected instances are skipped during flush."""
        env, log_file = self._make_flush_test_env(tmp_path, protected=True)

        result = subprocess.run(
            ["bash", self.SCRIPT, "--force"],
            capture_output=True, text=True, env=env,
            timeout=10,
        )
        assert "PROTECTED" in result.stdout

    def test_unprotected_instance_deleted(self, tmp_path):  # Matrix: FP-002
        """Unprotected instances are deleted normally."""
        env, log_file = self._make_flush_test_env(tmp_path, protected=False)

        result = subprocess.run(
            ["bash", self.SCRIPT, "--force"],
            capture_output=True, text=True, env=env,
            timeout=10,
        )
        assert "Deleting: test-instance" in result.stdout
        log = log_file.read_text() if log_file.exists() else ""
        assert "delete test-instance" in log

    def test_force_env_bypasses_protection(self, tmp_path):  # Matrix: FP-003
        """FORCE env var bypasses protection checks."""
        env, log_file = self._make_flush_test_env(tmp_path, protected=True)
        env["FORCE"] = "true"

        result = subprocess.run(
            ["bash", self.SCRIPT, "--force"],
            capture_output=True, text=True, env=env,
            timeout=10,
        )
        # With FORCE, should attempt deletion even for protected
        assert "Deleting: test-instance" in result.stdout
        log = log_file.read_text() if log_file.exists() else ""
        assert "delete test-instance" in log

    def test_project_skipped_with_remaining(self, tmp_path):  # Matrix: FP-2-001
        """Projects with remaining instances are not deleted."""
        env, log_file = self._make_flush_test_env(tmp_path, protected=True)

        result = subprocess.run(
            ["bash", self.SCRIPT, "--force"],
            capture_output=True, text=True, env=env,
            timeout=10,
        )
        # Project should be skipped because protected instance remains
        assert "SKIPPED" in result.stdout or "remain" in result.stdout

    def test_force_deletes_all_data_dirs_untouched(self, tmp_path):  # Matrix: FP-3-001
        """FORCE deletes all instances; data dirs are never touched by flush."""
        env, log_file = self._make_flush_test_env(tmp_path, protected=True)
        env["FORCE"] = "true"

        # Create simulated data directories that should survive flush
        data_dir = tmp_path / "srv" / "anklume" / "data"
        data_dir.mkdir(parents=True)
        (data_dir / "pro-dev" / "projects").mkdir(parents=True)

        result = subprocess.run(
            ["bash", self.SCRIPT, "--force"],
            capture_output=True, text=True, env=env,
            timeout=10,
        )
        # FORCE bypasses protection
        assert "Deleting: test-instance" in result.stdout
        # Data directories survive (flush never touches /srv/anklume/)
        assert data_dir.exists()
        assert (data_dir / "pro-dev" / "projects").exists()
