"""Tests for scripts/generate.py CLI — command-line interface only.

Validation logic is tested in test_generate.py. This file tests ONLY:
- Exit codes (0 on success, non-zero on error)
- CLI flags (--dry-run, --clean-orphans, --base-dir, --help)
- Input modes (single file, directory, missing file)
- Output streams (stdout vs stderr)
- Orphan report format
"""

import subprocess
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATE_PY = PROJECT_ROOT / "scripts" / "generate.py"


def _make_infra(tmp_path, infra_data=None):
    """Create an infra.yml with the given data."""
    if infra_data is None:
        infra_data = {
            "project_name": "test-cli",
            "global": {
                "base_subnet": "10.100",
                "default_os_image": "images:debian/13",
            },
            "domains": {
                "admin": {
                    "subnet_id": 0,
                    "machines": {
                        "admin-ansible": {
                            "type": "lxc",
                            "ip": "10.100.0.10",
                        },
                    },
                },
            },
        }
    infra_file = tmp_path / "infra.yml"
    infra_file.write_text(yaml.dump(infra_data, sort_keys=False))
    return infra_file


def _run_generate(args, cwd=None):
    """Run generate.py with given args."""
    result = subprocess.run(
        [sys.executable, str(GENERATE_PY)] + args,
        capture_output=True, text=True, cwd=str(cwd) if cwd else None,
        timeout=30,
    )
    return result


# -------------------------------------------------------------------
# Exit codes
# -------------------------------------------------------------------

class TestExitCodes:
    """Test exit codes for success, errors, and edge cases."""

    def test_success_exit_zero(self, tmp_path):
        """Valid infra.yml returns exit code 0."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_validation_error_exit_one(self, tmp_path):
        """Validation error returns exit code 1 (representative test)."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {}},
                "d2": {"subnet_id": 0, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1

    def test_nonexistent_file_nonzero(self, tmp_path):
        """Non-existent file returns non-zero exit code."""
        result = _run_generate([str(tmp_path / "nofile.yml")])
        assert result.returncode != 0

    def test_missing_argument_nonzero(self):
        """No infra_file argument gives error."""
        result = _run_generate([])
        assert result.returncode != 0

    def test_warnings_still_exit_zero(self, tmp_path):
        """Warnings (e.g. shared GPU) do not cause non-zero exit."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "gpu_policy": "shared"},
            "domains": {
                "d1": {
                    "subnet_id": 0,
                    "profiles": {
                        "gpu": {"devices": {"gpu": {"type": "gpu"}}},
                    },
                    "machines": {
                        "a": {"type": "lxc", "ip": "10.100.0.10", "gpu": True},
                        "b": {"type": "lxc", "ip": "10.100.0.20", "gpu": True},
                    },
                },
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0


# -------------------------------------------------------------------
# --help flag
# -------------------------------------------------------------------

class TestHelpFlag:
    """Test --help output."""

    def test_help_exits_zero_with_flags(self):
        """--help shows usage with expected flags and exits 0."""
        result = _run_generate(["--help"])
        assert result.returncode == 0
        assert "--dry-run" in result.stdout
        assert "--clean-orphans" in result.stdout
        assert "--base-dir" in result.stdout
        assert "infra_file" in result.stdout

    def test_unknown_flag_rejected(self):
        """Unknown --foo flag gives error."""
        result = _run_generate(["--foo", "infra.yml"])
        assert result.returncode != 0


# -------------------------------------------------------------------
# --dry-run flag
# -------------------------------------------------------------------

class TestDryRun:
    """Test --dry-run prevents file writes and shows preview."""

    def test_dry_run_no_files_written(self, tmp_path):
        """--dry-run does not create any output files."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert not (tmp_path / "inventory").exists()
        assert not (tmp_path / "group_vars").exists()

    def test_dry_run_output_format(self, tmp_path):
        """--dry-run output contains [DRY-RUN] prefix and 'Would write'."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout
        assert "Would write" in result.stdout

    def test_dry_run_clean_orphans_no_delete(self, tmp_path):
        """--dry-run with --clean-orphans does NOT delete files."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "ephemeral": True, "machines": {
                    "alpha-box": {
                        "type": "lxc", "ip": "10.100.0.10", "ephemeral": True,
                    },
                }},
                "beta": {"subnet_id": 1, "ephemeral": True, "machines": {
                    "beta-box": {
                        "type": "lxc", "ip": "10.100.1.10", "ephemeral": True,
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        # Remove beta, run with both flags
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "ephemeral": True, "machines": {
                    "alpha-box": {
                        "type": "lxc", "ip": "10.100.0.10", "ephemeral": True,
                    },
                }},
            },
        })
        result = _run_generate([
            str(infra_file), "--base-dir", str(tmp_path),
            "--dry-run", "--clean-orphans",
        ])
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "beta.yml").exists()


# -------------------------------------------------------------------
# --clean-orphans flag
# -------------------------------------------------------------------

class TestCleanOrphans:
    """Test --clean-orphans deletes ephemeral orphans, skips protected."""

    def test_clean_orphans_deletes_ephemeral(self, tmp_path):
        """--clean-orphans deletes orphan files from ephemeral domains."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "ephemeral": True, "machines": {
                    "alpha-box": {
                        "type": "lxc", "ip": "10.100.0.10", "ephemeral": True,
                    },
                }},
                "beta": {"subnet_id": 1, "ephemeral": True, "machines": {
                    "beta-box": {
                        "type": "lxc", "ip": "10.100.1.10", "ephemeral": True,
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert (tmp_path / "inventory" / "beta.yml").exists()

        # Remove beta domain, run with --clean-orphans
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "ephemeral": True, "machines": {
                    "alpha-box": {
                        "type": "lxc", "ip": "10.100.0.10", "ephemeral": True,
                    },
                }},
            },
        })
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path), "--clean-orphans"],
        )
        assert result.returncode == 0
        assert "Deleted" in result.stdout
        assert not (tmp_path / "inventory" / "beta.yml").exists()

    def test_clean_orphans_skips_protected(self, tmp_path):
        """--clean-orphans skips protected (ephemeral=false) orphans."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "machines": {
                    "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "beta": {"subnet_id": 1, "machines": {
                    "beta-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        # Remove beta domain
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "machines": {
                    "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path), "--clean-orphans"],
        )
        assert result.returncode == 0
        assert "PROTECTED" in result.stdout or "Skipped" in result.stdout
        # Protected orphans should still exist
        assert (tmp_path / "group_vars" / "beta.yml").exists()
        assert (tmp_path / "host_vars" / "beta-box.yml").exists()


# -------------------------------------------------------------------
# --base-dir flag
# -------------------------------------------------------------------

class TestBaseDir:
    """Test --base-dir changes output directory."""

    def test_custom_base_dir(self, tmp_path):
        """--base-dir directs output to specified directory."""
        infra_file = _make_infra(tmp_path)
        out_dir = tmp_path / "custom_output"
        out_dir.mkdir()
        result = _run_generate(
            [str(infra_file), "--base-dir", str(out_dir)],
        )
        assert result.returncode == 0
        assert (out_dir / "inventory" / "admin.yml").exists()

    def test_base_dir_defaults_to_cwd(self, tmp_path):
        """Without --base-dir, output goes to cwd."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file)], cwd=tmp_path)
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "admin.yml").exists()


# -------------------------------------------------------------------
# Orphan report format
# -------------------------------------------------------------------

class TestOrphanReport:
    """Test orphan detection output format."""

    def test_orphan_reported_in_stdout(self, tmp_path):
        """Orphan files from removed domain appear in stdout."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "machines": {
                    "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "beta": {"subnet_id": 1, "machines": {
                    "beta-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        # Remove beta domain
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "machines": {
                    "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Orphan" in result.stdout or "ORPHAN" in result.stdout
        # Files NOT deleted without --clean-orphans
        assert (tmp_path / "inventory" / "beta.yml").exists()

    def test_no_orphan_section_when_clean(self, tmp_path):
        """No orphan section when there are no orphans."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Orphan" not in result.stdout


# -------------------------------------------------------------------
# Stderr/stdout separation
# -------------------------------------------------------------------

class TestOutputStreams:
    """Test that errors go to stderr, normal output to stdout."""

    def test_validation_errors_on_stderr(self, tmp_path):
        """Validation errors are on stderr, not stdout."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "docker", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "Validation errors" in result.stderr
        assert "Validation errors" not in result.stdout
        # Error items prefixed with dash
        assert "  - " in result.stderr

    def test_clean_run_no_stderr(self, tmp_path):
        """Clean successful run produces empty stderr."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert result.stderr == ""

    def test_warnings_on_stderr(self, tmp_path):
        """Warnings go to stderr, not stdout."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "gpu_policy": "shared"},
            "domains": {
                "d1": {
                    "subnet_id": 0,
                    "profiles": {
                        "gpu": {"devices": {"gpu": {"type": "gpu"}}},
                    },
                    "machines": {
                        "a": {"type": "lxc", "ip": "10.100.0.10", "gpu": True},
                        "b": {"type": "lxc", "ip": "10.100.0.20", "gpu": True},
                    },
                },
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "WARNING" in result.stderr
        assert "WARNING" not in result.stdout


# -------------------------------------------------------------------
# Directory mode (infra/ directory input)
# -------------------------------------------------------------------

class TestDirectoryMode:
    """Test infra/ directory as input."""

    def _make_infra_dir(self, tmp_path, domains=None, policies=None):
        """Helper to create infra/ directory structure."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "dir-test",
            "global": {"base_subnet": "10.100"},
        }, sort_keys=False))
        if domains:
            domains_dir = infra_dir / "domains"
            domains_dir.mkdir()
            for name, data in domains.items():
                (domains_dir / f"{name}.yml").write_text(
                    yaml.dump({name: data}, sort_keys=False),
                )
        if policies:
            (infra_dir / "policies.yml").write_text(
                yaml.dump({"network_policies": policies}, sort_keys=False),
            )
        return infra_dir

    def test_directory_accepted(self, tmp_path):
        """Generator accepts infra/ directory as input."""
        infra_dir = self._make_infra_dir(tmp_path, domains={
            "alpha": {"subnet_id": 0, "machines": {
                "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
        })
        result = _run_generate(
            [str(infra_dir), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "alpha.yml").exists()

    def test_multiple_domain_files_merged(self, tmp_path):
        """Multiple domain files in infra/domains/ are merged."""
        infra_dir = self._make_infra_dir(tmp_path, domains={
            "alpha": {"subnet_id": 0, "machines": {
                "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
            "beta": {"subnet_id": 1, "machines": {
                "beta-box": {"type": "lxc", "ip": "10.100.1.10"},
            }},
        })
        result = _run_generate(
            [str(infra_dir), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "2 domain" in result.stdout
        assert (tmp_path / "inventory" / "alpha.yml").exists()
        assert (tmp_path / "inventory" / "beta.yml").exists()

    def test_policies_file_merged(self, tmp_path):
        """policies.yml in infra/ directory is merged."""
        infra_dir = self._make_infra_dir(
            tmp_path,
            domains={
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            policies=[
                {"from": "host", "to": "d1", "ports": [80]},
            ],
        )
        result = _run_generate(
            [str(infra_dir), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert "network_policies" in allvars

    def test_directory_dry_run(self, tmp_path):
        """--dry-run works with directory input."""
        infra_dir = self._make_infra_dir(tmp_path, domains={
            "test": {"subnet_id": 0, "machines": {
                "test-box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
        })
        result = _run_generate(
            [str(infra_dir), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout
        assert not (tmp_path / "inventory").exists()

    def test_missing_base_yml_error(self, tmp_path):
        """infra/ directory without base.yml gives error."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        result = _run_generate([str(infra_dir), "--base-dir", str(tmp_path)])
        assert result.returncode != 0


# -------------------------------------------------------------------
# Normal output
# -------------------------------------------------------------------

class TestNormalOutput:
    """Test stdout content for successful runs."""

    def test_creates_expected_files(self, tmp_path):
        """Normal run creates inventory, group_vars, host_vars, all.yml."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "admin.yml").exists()
        assert (tmp_path / "group_vars" / "admin.yml").exists()
        assert (tmp_path / "host_vars" / "admin-ansible.yml").exists()
        assert (tmp_path / "group_vars" / "all.yml").exists()

    def test_reports_domain_count(self, tmp_path):
        """Output mentions domain count."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "1 domain" in result.stdout

    def test_shows_written_files(self, tmp_path):
        """Output lists written files."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "Written:" in result.stdout

    def test_empty_domains_nothing_to_generate(self, tmp_path):
        """Empty domains dict prints 'Nothing to generate'."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Nothing to generate" in result.stdout

    def test_idempotent_second_run(self, tmp_path):
        """Running twice with same input produces identical files."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        files_before = {}
        for d in ("inventory", "group_vars", "host_vars"):
            dd = tmp_path / d
            if dd.exists():
                for f in dd.glob("*.yml"):
                    files_before[str(f.relative_to(tmp_path))] = f.read_text()

        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        for rel_path, content_before in files_before.items():
            assert content_before == (tmp_path / rel_path).read_text(), \
                f"File {rel_path} changed on second run"
