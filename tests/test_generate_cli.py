"""Tests for scripts/generate.py CLI (main function) — command-line interface."""

import subprocess
import sys
from pathlib import Path

import pytest
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


class TestGenerateCLIBasic:
    """Test basic CLI behavior."""

    def test_help_flag(self):
        """--help shows usage and exits 0."""
        result = _run_generate(["--help"])
        assert result.returncode == 0
        assert "infra_file" in result.stdout
        assert "--dry-run" in result.stdout

    def test_missing_argument(self):
        """No infra_file argument gives error."""
        result = _run_generate([])
        assert result.returncode != 0
        assert "required" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_nonexistent_file(self, tmp_path):
        """Non-existent infra file gives error."""
        result = _run_generate([str(tmp_path / "nofile.yml")])
        assert result.returncode != 0

    def test_invalid_yaml(self, tmp_path):
        """Invalid YAML content gives error."""
        bad_file = tmp_path / "bad.yml"
        bad_file.write_text(": : :\n  bad yaml [[\n")
        result = _run_generate([str(bad_file)])
        assert result.returncode != 0


class TestGenerateCLIDryRun:
    """Test --dry-run mode."""

    def test_dry_run_does_not_write_files(self, tmp_path):
        """--dry-run does not create any output files."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        # No inventory/ or group_vars/ should be created
        assert not (tmp_path / "inventory").exists()
        assert not (tmp_path / "group_vars").exists()

    def test_dry_run_output_contains_prefix(self, tmp_path):
        """--dry-run output contains [DRY-RUN] prefix."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout

    def test_dry_run_lists_would_write(self, tmp_path):
        """--dry-run shows files it would write."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "Would write" in result.stdout


class TestGenerateCLIOutput:
    """Test normal (non-dry-run) output."""

    def test_generates_inventory_file(self, tmp_path):
        """Normal run creates inventory file."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "admin.yml").exists()

    def test_generates_group_vars(self, tmp_path):
        """Normal run creates group_vars file."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "group_vars" / "admin.yml").exists()

    def test_generates_host_vars(self, tmp_path):
        """Normal run creates host_vars file."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "host_vars" / "admin-ansible.yml").exists()

    def test_generates_all_vars(self, tmp_path):
        """Normal run creates group_vars/all.yml."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "group_vars" / "all.yml").exists()

    def test_output_reports_domain_count(self, tmp_path):
        """Output mentions how many domains are being generated."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "1 domain" in result.stdout

    def test_output_shows_done_message(self, tmp_path):
        """Output shows 'Done' after completion."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "Done" in result.stdout

    def test_output_shows_written_files(self, tmp_path):
        """Output lists files that were written."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate(
            [str(infra_file), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "Written:" in result.stdout


class TestGenerateCLIValidationErrors:
    """Test that validation errors are reported correctly."""

    def test_duplicate_subnet_error(self, tmp_path):
        """Duplicate subnet_id gives validation error."""
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
        assert "Validation errors" in result.stderr
        assert "subnet" in result.stderr.lower()

    def test_duplicate_machine_name_error(self, tmp_path):
        """Duplicate machine name gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "d2": {"subnet_id": 1, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "box" in result.stderr

    def test_duplicate_ip_error(self, tmp_path):
        """Duplicate IP gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "lxc", "ip": "10.100.0.10"},
                    "b": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "10.100.0.10" in result.stderr

    def test_ip_outside_subnet_error(self, tmp_path):
        """IP outside its domain's subnet gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "lxc", "ip": "10.100.5.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "subnet" in result.stderr.lower()

    def test_invalid_instance_type_error(self, tmp_path):
        """Invalid instance type gives validation error."""
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
        assert "type" in result.stderr.lower()


class TestGenerateCLIWarnings:
    """Test warning output for non-fatal issues."""

    def test_shared_gpu_warning(self, tmp_path):
        """Shared GPU policy with multiple GPU instances gives warning."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "gpu_policy": "shared",
            },
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


class TestGenerateCLIOrphans:
    """Test orphan detection and clean-orphans flag."""

    def test_orphan_detected(self, tmp_path):
        """Files from a removed domain are detected as orphans."""
        # First, generate with two domains
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

        # Now remove beta domain
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

    def test_clean_orphans_deletes(self, tmp_path):
        """--clean-orphans deletes orphan files."""
        # Generate with two domains
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
        # Generate with two domains (beta is protected by default)
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
        # group_vars and host_vars contain domain_ephemeral/instance_ephemeral
        assert (tmp_path / "group_vars" / "beta.yml").exists()
        assert (tmp_path / "host_vars" / "beta-box.yml").exists()

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
        # Protected orphans (group_vars, host_vars) should still exist
        # inventory/beta.yml is NOT protected (no ephemeral key in it)
        assert (tmp_path / "group_vars" / "beta.yml").exists()
        assert (tmp_path / "host_vars" / "beta-box.yml").exists()

    def test_dry_run_clean_orphans_does_not_delete(self, tmp_path):
        """--dry-run with --clean-orphans does NOT delete files."""
        # Generate with two domains
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
        result = _run_generate(
            [
                str(infra_file), "--base-dir", str(tmp_path),
                "--dry-run", "--clean-orphans",
            ],
        )
        assert result.returncode == 0
        # File should NOT be deleted (dry-run)
        assert (tmp_path / "inventory" / "beta.yml").exists()


class TestGenerateCLIMultiDomain:
    """Test CLI with multiple domains."""

    def test_multi_domain_reports_count(self, tmp_path):
        """Multiple domains are reported correctly in output."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "a": {"subnet_id": 0, "machines": {
                    "a-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "b": {"subnet_id": 1, "machines": {
                    "b-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
                "c": {"subnet_id": 2, "machines": {
                    "c-box": {"type": "lxc", "ip": "10.100.2.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "3 domain" in result.stdout

    def test_multi_domain_creates_all_files(self, tmp_path):
        """All domains get their inventory, group_vars, and host_vars files."""
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
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        for domain in ("alpha", "beta"):
            assert (tmp_path / "inventory" / f"{domain}.yml").exists()
            assert (tmp_path / "group_vars" / f"{domain}.yml").exists()
        assert (tmp_path / "host_vars" / "alpha-box.yml").exists()
        assert (tmp_path / "host_vars" / "beta-box.yml").exists()


class TestGenerateCLIIdempotent:
    """Test that running twice produces the same result."""

    def test_second_run_same_output(self, tmp_path):
        """Running generate twice with same input is idempotent."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        # Read all generated files
        files_before = {}
        for d in ("inventory", "group_vars", "host_vars"):
            dd = tmp_path / d
            if dd.exists():
                for f in dd.glob("*.yml"):
                    files_before[str(f.relative_to(tmp_path))] = f.read_text()

        # Run again
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        # Read again and compare
        for rel_path, content_before in files_before.items():
            content_after = (tmp_path / rel_path).read_text()
            assert content_before == content_after, \
                f"File {rel_path} changed on second run"


class TestGenerateCLIInfraDirectory:
    """Test CLI with infra/ directory input."""

    def test_infra_directory_accepted(self, tmp_path):
        """Generator accepts infra/ directory as input."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "dir-test",
            "global": {"base_subnet": "10.100"},
        }, sort_keys=False))
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        (domains_dir / "alpha.yml").write_text(yaml.dump({
            "alpha": {"subnet_id": 0, "machines": {
                "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
        }, sort_keys=False))

        result = _run_generate(
            [str(infra_dir), "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "alpha.yml").exists()

    def test_infra_directory_dry_run(self, tmp_path):
        """Dry-run works with infra/ directory input."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "dir-test",
            "global": {"base_subnet": "10.100"},
        }, sort_keys=False))
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        (domains_dir / "test.yml").write_text(yaml.dump({
            "test": {"subnet_id": 0, "machines": {
                "test-box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
        }, sort_keys=False))

        result = _run_generate(
            [str(infra_dir), "--dry-run", "--base-dir", str(tmp_path)],
        )
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout
        assert not (tmp_path / "inventory").exists()


class TestGenerateCLIEmptyDomains:
    """Test CLI with empty or no domains."""

    def test_no_domains(self, tmp_path):
        """infra.yml with empty domains gives info message."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Nothing to generate" in result.stdout


class TestGenerateCLIBaseDir:
    """Test --base-dir flag."""

    def test_custom_base_dir(self, tmp_path):
        """--base-dir changes the output directory."""
        infra_file = _make_infra(tmp_path)
        out_dir = tmp_path / "custom_output"
        out_dir.mkdir()
        result = _run_generate(
            [str(infra_file), "--base-dir", str(out_dir)],
        )
        assert result.returncode == 0
        assert (out_dir / "inventory" / "admin.yml").exists()
        # Original location should NOT have files
        assert not (tmp_path / "inventory").exists() or \
            not (tmp_path / "inventory" / "admin.yml").exists()
