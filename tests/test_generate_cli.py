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


# ===================================================================
# NEW TESTS BELOW — added for comprehensive CLI coverage
# ===================================================================


class TestGenerateCLIHelpContent:
    """Test that --help includes all expected flags and descriptions."""

    def test_help_mentions_clean_orphans(self):
        """--help output includes --clean-orphans flag."""
        result = _run_generate(["--help"])
        assert "--clean-orphans" in result.stdout

    def test_help_mentions_base_dir(self):
        """--help output includes --base-dir flag."""
        result = _run_generate(["--help"])
        assert "--base-dir" in result.stdout

    def test_help_description(self):
        """--help output includes the program description."""
        result = _run_generate(["--help"])
        assert "Generate Ansible files" in result.stdout

    def test_help_exit_code_zero(self):
        """--help returns exit code 0."""
        result = _run_generate(["--help"])
        assert result.returncode == 0
        assert result.stderr == ""


class TestGenerateCLIArgParsingEdgeCases:
    """Test argument parsing edge cases."""

    def test_unknown_flag_rejected(self):
        """Unknown --foo flag gives error."""
        result = _run_generate(["--foo", "infra.yml"])
        assert result.returncode != 0
        assert "unrecognized" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_dry_run_and_clean_orphans_combined(self, tmp_path):
        """--dry-run and --clean-orphans can be combined."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([
            str(infra_file), "--dry-run", "--clean-orphans",
            "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 0

    def test_base_dir_defaults_to_cwd(self, tmp_path):
        """When --base-dir is not given, output goes to cwd."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file)], cwd=tmp_path)
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "admin.yml").exists()

    def test_base_dir_nonexistent_created(self, tmp_path):
        """--base-dir creates subdirectories as needed."""
        infra_file = _make_infra(tmp_path)
        out_dir = tmp_path / "deep" / "nested" / "dir"
        # out_dir does not exist yet
        result = _run_generate([
            str(infra_file), "--base-dir", str(out_dir),
        ])
        assert result.returncode == 0
        assert (out_dir / "inventory" / "admin.yml").exists()


class TestGenerateCLIMissingRequiredKeys:
    """Test missing top-level keys in YAML."""

    def test_missing_project_name(self, tmp_path):
        """infra.yml without project_name gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "global": {"base_subnet": "10.100"},
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "project_name" in result.stderr

    def test_missing_global(self, tmp_path):
        """infra.yml without global gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "global" in result.stderr

    def test_missing_domains_key(self, tmp_path):
        """infra.yml without domains key gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "domains" in result.stderr

    def test_missing_all_required_keys(self, tmp_path):
        """infra.yml with empty dict gives multiple validation errors."""
        infra_file = _make_infra(tmp_path, {})
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "Validation errors" in result.stderr

    def test_multiple_validation_errors_listed(self, tmp_path):
        """Multiple validation errors are all listed."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "lxc", "ip": "10.100.0.10"},
                    "b": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "d2": {"subnet_id": 0, "machines": {
                    "c": {"type": "docker", "ip": "10.100.1.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        # Should have at least: duplicate IP, duplicate subnet_id, invalid type
        lines = result.stderr.strip().split("\n")
        error_lines = [l for l in lines if l.strip().startswith("- ")]
        assert len(error_lines) >= 3


class TestGenerateCLIDomainNameValidation:
    """Test domain name validation."""

    def test_uppercase_domain_name(self, tmp_path):
        """Uppercase domain name gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "Admin": {"subnet_id": 0, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "Admin" in result.stderr
        assert "invalid name" in result.stderr.lower()

    def test_domain_name_with_underscore(self, tmp_path):
        """Domain name with underscore gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "my_domain": {"subnet_id": 0, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "my_domain" in result.stderr

    def test_domain_name_starting_with_hyphen(self, tmp_path):
        """Domain name starting with hyphen gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "-bad": {"subnet_id": 0, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "-bad" in result.stderr

    def test_valid_domain_name_with_hyphen(self, tmp_path):
        """Domain name with hyphen in the middle is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_domain_name_with_space(self, tmp_path):
        """Domain name with space gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "my domain": {"subnet_id": 0, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1


class TestGenerateCLISubnetIdValidation:
    """Test subnet_id validation edge cases."""

    def test_missing_subnet_id(self, tmp_path):
        """Missing subnet_id gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "subnet_id" in result.stderr

    def test_negative_subnet_id(self, tmp_path):
        """Negative subnet_id gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": -1, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "subnet_id" in result.stderr

    def test_subnet_id_above_254(self, tmp_path):
        """subnet_id > 254 gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 255, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "subnet_id" in result.stderr

    def test_subnet_id_zero_valid(self, tmp_path):
        """subnet_id 0 is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_subnet_id_254_valid(self, tmp_path):
        """subnet_id 254 is valid (upper bound)."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 254, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.254.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_subnet_id_string_error(self, tmp_path):
        """Non-integer subnet_id gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": "abc", "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "subnet_id" in result.stderr


class TestGenerateCLIEphemeralValidation:
    """Test ephemeral field validation."""

    def test_domain_ephemeral_non_boolean(self, tmp_path):
        """Domain ephemeral non-boolean gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "ephemeral": "yes", "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ephemeral" in result.stderr
        assert "boolean" in result.stderr

    def test_machine_ephemeral_non_boolean(self, tmp_path):
        """Machine ephemeral non-boolean gives validation error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "ephemeral": 1,
                    },
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ephemeral" in result.stderr

    def test_domain_ephemeral_true_valid(self, tmp_path):
        """Domain ephemeral: true is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "ephemeral": True, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_machine_ephemeral_overrides_domain(self, tmp_path):
        """Machine ephemeral overrides domain ephemeral in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "ephemeral": False, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "ephemeral": True,
                    },
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        hv = (tmp_path / "host_vars" / "box.yml").read_text()
        data = yaml.safe_load(hv)
        assert data["instance_ephemeral"] is True


class TestGenerateCLIProfileValidation:
    """Test profile reference validation."""

    def test_unknown_profile_reference(self, tmp_path):
        """Referencing a non-existent profile gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "profiles": ["default", "nonexistent"],
                    },
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "nonexistent" in result.stderr

    def test_default_profile_always_allowed(self, tmp_path):
        """The 'default' profile is always valid (no domain definition needed)."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "profiles": ["default"],
                    },
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_defined_profile_valid(self, tmp_path):
        """Referencing a domain-defined profile is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {
                    "subnet_id": 0,
                    "profiles": {
                        "nvidia": {"devices": {"gpu": {"type": "gpu"}}},
                    },
                    "machines": {
                        "box": {
                            "type": "lxc", "ip": "10.100.0.10",
                            "profiles": ["default", "nvidia"],
                        },
                    },
                },
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0


class TestGenerateCLINetworkPoliciesValidation:
    """Test network_policies validation through CLI."""

    def test_policy_missing_from(self, tmp_path):
        """Network policy missing 'from' gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"to": "d1", "ports": [80]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "from" in result.stderr

    def test_policy_missing_to(self, tmp_path):
        """Network policy missing 'to' gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "ports": [80]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "to" in result.stderr

    def test_policy_unknown_domain_reference(self, tmp_path):
        """Network policy referencing unknown domain gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "nonexistent", "to": "d1", "ports": [80]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "nonexistent" in result.stderr

    def test_policy_invalid_port(self, tmp_path):
        """Network policy with invalid port gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": [99999]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "99999" in result.stderr

    def test_policy_invalid_port_zero(self, tmp_path):
        """Network policy with port 0 gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": [0]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1

    def test_policy_invalid_protocol(self, tmp_path):
        """Network policy with invalid protocol gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": [80], "protocol": "icmp"},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "protocol" in result.stderr

    def test_policy_ports_all_valid(self, tmp_path):
        """Network policy with ports: all is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": "all"},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_policy_host_keyword_valid(self, tmp_path):
        """Network policy using 'host' keyword as source is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "host", "to": "d1", "ports": [80]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_policy_machine_name_valid(self, tmp_path):
        """Network policy referencing a machine name is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "host", "to": "box", "ports": [80]},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_policy_non_dict_entry(self, tmp_path):
        """Non-dict network policy gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": ["not-a-dict"],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "must be a mapping" in result.stderr

    def test_policy_ports_as_string_invalid(self, tmp_path):
        """Network policy with ports as non-'all' string gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": "80"},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ports" in result.stderr

    def test_valid_tcp_protocol(self, tmp_path):
        """Network policy with protocol: tcp is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": [80], "protocol": "tcp"},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_valid_udp_protocol(self, tmp_path):
        """Network policy with protocol: udp is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "d1", "to": "d1", "ports": [53], "protocol": "udp"},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0


class TestGenerateCLIGpuPolicyValidation:
    """Test GPU policy validation through CLI."""

    def test_invalid_gpu_policy(self, tmp_path):
        """Invalid gpu_policy value gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "gpu_policy": "none"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "gpu_policy" in result.stderr

    def test_exclusive_gpu_multiple_instances(self, tmp_path):
        """Exclusive GPU policy with 2 GPU instances gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "lxc", "ip": "10.100.0.10", "gpu": True},
                    "b": {"type": "lxc", "ip": "10.100.0.20", "gpu": True},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "exclusive" in result.stderr.lower() or "GPU" in result.stderr

    def test_shared_gpu_multiple_instances_warning(self, tmp_path):
        """Shared GPU policy with 2 GPU instances gives warning, not error."""
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

    def test_single_gpu_exclusive_ok(self, tmp_path):
        """Exclusive GPU policy with 1 GPU instance is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "lxc", "ip": "10.100.0.10", "gpu": True},
                    "b": {"type": "lxc", "ip": "10.100.0.20"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0


class TestGenerateCLIFirewallModeValidation:
    """Test firewall_mode validation through CLI."""

    def test_invalid_firewall_mode(self, tmp_path):
        """Invalid firewall_mode gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "firewall_mode": "cloud"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "firewall_mode" in result.stderr

    def test_host_firewall_mode_valid(self, tmp_path):
        """firewall_mode: host is valid."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "firewall_mode": "host"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0


class TestGenerateCLIAiAccessPolicyValidation:
    """Test AI access policy validation through CLI."""

    def test_invalid_ai_access_policy(self, tmp_path):
        """Invalid ai_access_policy value gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "ai_access_policy": "shared"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ai_access_policy" in result.stderr

    def test_exclusive_without_ai_access_default(self, tmp_path):
        """Exclusive ai_access_policy without ai_access_default gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "ai_access_policy": "exclusive"},
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "pro": {"subnet_id": 1, "machines": {
                    "pro-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ai_access_default" in result.stderr

    def test_exclusive_ai_access_default_is_ai_tools(self, tmp_path):
        """ai_access_default cannot be 'ai-tools' itself."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "ai-tools",
            },
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ai-tools" in result.stderr

    def test_exclusive_without_ai_tools_domain(self, tmp_path):
        """Exclusive ai_access_policy without ai-tools domain gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "pro": {"subnet_id": 0, "machines": {
                    "pro-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ai-tools" in result.stderr

    def test_exclusive_ai_access_default_unknown_domain(self, tmp_path):
        """ai_access_default referencing unknown domain gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "nonexistent",
            },
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "nonexistent" in result.stderr

    def test_exclusive_valid_configuration(self, tmp_path):
        """Valid exclusive AI access configuration succeeds."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "pro": {"subnet_id": 1, "machines": {
                    "pro-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_open_ai_access_policy_valid(self, tmp_path):
        """ai_access_policy: open is valid (default)."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "ai_access_policy": "open"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_exclusive_multiple_policies_to_ai_tools(self, tmp_path):
        """Multiple network policies targeting ai-tools in exclusive mode gives error."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "pro": {"subnet_id": 1, "machines": {
                    "pro-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
                "perso": {"subnet_id": 2, "machines": {
                    "perso-box": {"type": "lxc", "ip": "10.100.2.10"},
                }},
            },
            "network_policies": [
                {"from": "pro", "to": "ai-tools", "ports": "all"},
                {"from": "perso", "to": "ai-tools", "ports": "all"},
            ],
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 1
        assert "ai-tools" in result.stderr


class TestGenerateCLIOutputContent:
    """Test the content of generated files."""

    def test_inventory_contains_ansible_host(self, tmp_path):
        """Generated inventory file contains ansible_host."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        inv = yaml.safe_load(
            (tmp_path / "inventory" / "admin.yml").read_text(),
        )
        hosts = inv["all"]["children"]["admin"]["hosts"]
        assert "admin-ansible" in hosts
        assert hosts["admin-ansible"]["ansible_host"] == "10.100.0.10"

    def test_group_vars_contains_domain_name(self, tmp_path):
        """Generated group_vars contains domain_name."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "admin.yml").read_text(),
        )
        assert gv["domain_name"] == "admin"

    def test_group_vars_contains_network_info(self, tmp_path):
        """Generated group_vars contains incus_network info."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "admin.yml").read_text(),
        )
        net = gv["incus_network"]
        assert net["name"] == "net-admin"
        assert net["subnet"] == "10.100.0.0/24"
        assert net["gateway"] == "10.100.0.254"

    def test_host_vars_contains_instance_info(self, tmp_path):
        """Generated host_vars contains instance_name and type."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "admin-ansible.yml").read_text(),
        )
        assert hv["instance_name"] == "admin-ansible"
        assert hv["instance_type"] == "lxc"
        assert hv["instance_domain"] == "admin"
        assert hv["instance_ip"] == "10.100.0.10"

    def test_all_yml_contains_project_name(self, tmp_path):
        """group_vars/all.yml contains project_name."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert allvars["project_name"] == "test-cli"

    def test_all_yml_contains_base_subnet(self, tmp_path):
        """group_vars/all.yml contains base_subnet."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert allvars["base_subnet"] == "10.100"

    def test_all_yml_contains_default_os_image(self, tmp_path):
        """group_vars/all.yml contains default_os_image when set."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert allvars["default_os_image"] == "images:debian/13"

    def test_all_yml_contains_images_list(self, tmp_path):
        """group_vars/all.yml contains incus_all_images."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_os_image": "images:debian/13",
            },
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "a": {"type": "lxc", "ip": "10.100.0.10"},
                    "b": {
                        "type": "lxc", "ip": "10.100.0.20",
                        "os_image": "images:ubuntu/24.04",
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        images = allvars["incus_all_images"]
        assert "images:debian/13" in images
        assert "images:ubuntu/24.04" in images

    def test_connection_vars_stored_as_psot(self, tmp_path):
        """Connection vars stored as psot_* not ansible_*."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert allvars["psot_default_connection"] == "community.general.incus"
        assert allvars["psot_default_user"] == "root"
        assert "ansible_connection" not in allvars
        assert "ansible_user" not in allvars

    def test_network_policies_in_all_yml(self, tmp_path):
        """group_vars/all.yml contains network_policies when defined."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
            "network_policies": [
                {"from": "host", "to": "d1", "ports": [80]},
            ],
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert "network_policies" in allvars
        assert allvars["network_policies"][0]["from"] == "host"


class TestGenerateCLIManagedSections:
    """Test managed section behavior."""

    def test_managed_markers_present(self, tmp_path):
        """Generated files contain managed section markers."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        content = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert "# === MANAGED BY infra.yml ===" in content
        assert "# === END MANAGED ===" in content

    def test_managed_notice_present(self, tmp_path):
        """Generated files contain the do-not-edit notice."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        content = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert "Do not edit this section" in content

    def test_user_content_preserved_outside_managed(self, tmp_path):
        """User content outside managed section is preserved on re-run."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])

        # Add custom content outside managed section
        hv_path = tmp_path / "host_vars" / "admin-ansible.yml"
        original = hv_path.read_text()
        custom_line = "\nmy_custom_var: hello_world\n"
        hv_path.write_text(original + custom_line)

        # Re-run generate
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        updated = hv_path.read_text()
        assert "my_custom_var: hello_world" in updated

    def test_new_files_start_with_yaml_header(self, tmp_path):
        """Newly created files start with --- YAML header."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        content = (tmp_path / "group_vars" / "admin.yml").read_text()
        assert content.startswith("---")


class TestGenerateCLIVMInstances:
    """Test VM type instances through CLI."""

    def test_vm_instance_generates_correct_type(self, tmp_path):
        """VM instance has instance_type: vm in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "my-vm": {
                        "type": "vm",
                        "ip": "10.100.0.10",
                        "config": {
                            "limits.cpu": "2",
                            "limits.memory": "2GiB",
                        },
                    },
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "my-vm.yml").read_text(),
        )
        assert hv["instance_type"] == "vm"

    def test_vm_and_lxc_coexist(self, tmp_path):
        """VM and LXC instances coexist in the same domain."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "my-lxc": {"type": "lxc", "ip": "10.100.0.10"},
                    "my-vm": {"type": "vm", "ip": "10.100.0.20"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        lxc_hv = yaml.safe_load(
            (tmp_path / "host_vars" / "my-lxc.yml").read_text(),
        )
        vm_hv = yaml.safe_load(
            (tmp_path / "host_vars" / "my-vm.yml").read_text(),
        )
        assert lxc_hv["instance_type"] == "lxc"
        assert vm_hv["instance_type"] == "vm"


class TestGenerateCLIMachineProperties:
    """Test various machine properties are reflected in host_vars."""

    def test_machine_os_image_in_host_vars(self, tmp_path):
        """Custom os_image is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "os_image": "images:ubuntu/24.04",
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_os_image"] == "images:ubuntu/24.04"

    def test_machine_roles_in_host_vars(self, tmp_path):
        """Machine roles list is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "roles": ["base_system", "ollama_server"],
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_roles"] == ["base_system", "ollama_server"]

    def test_machine_config_in_host_vars(self, tmp_path):
        """Machine config dict is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "config": {"limits.cpu": "4"},
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_config"]["limits.cpu"] == "4"

    def test_machine_gpu_flag_in_host_vars(self, tmp_path):
        """GPU flag is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "gpu": True,
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_gpu"] is True

    def test_machine_profiles_in_host_vars(self, tmp_path):
        """Machine profiles list is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {
                    "subnet_id": 0,
                    "profiles": {
                        "myprofile": {"config": {"limits.cpu": "2"}},
                    },
                    "machines": {
                        "box": {
                            "type": "lxc", "ip": "10.100.0.10",
                            "profiles": ["default", "myprofile"],
                        },
                    },
                },
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_profiles"] == ["default", "myprofile"]

    def test_machine_description_in_host_vars(self, tmp_path):
        """Machine description is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "description": "A test box",
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_description"] == "A test box"

    def test_machine_storage_volumes_in_host_vars(self, tmp_path):
        """Machine storage_volumes is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "storage_volumes": {"models": {"path": "/data/models"}},
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert "instance_storage_volumes" in hv
        assert hv["instance_storage_volumes"]["models"]["path"] == "/data/models"

    def test_machine_devices_in_host_vars(self, tmp_path):
        """Machine devices is present in host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "devices": {"mydisk": {"type": "disk", "path": "/mnt"}},
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert "instance_devices" in hv
        assert hv["instance_devices"]["mydisk"]["type"] == "disk"


class TestGenerateCLIGroupVarsContent:
    """Test group_vars content details."""

    def test_group_vars_contains_subnet_id(self, tmp_path):
        """group_vars contains subnet_id."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 5, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.5.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "d1.yml").read_text(),
        )
        assert gv["subnet_id"] == 5

    def test_group_vars_contains_incus_project(self, tmp_path):
        """group_vars contains incus_project matching domain name."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "mydom": {"subnet_id": 3, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.3.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "mydom.yml").read_text(),
        )
        assert gv["incus_project"] == "mydom"

    def test_group_vars_contains_domain_ephemeral(self, tmp_path):
        """group_vars contains domain_ephemeral."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "ephemeral": True, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "d1.yml").read_text(),
        )
        assert gv["domain_ephemeral"] is True

    def test_group_vars_profiles_included(self, tmp_path):
        """group_vars contains incus_profiles when domain has profiles."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {
                    "subnet_id": 0,
                    "profiles": {
                        "nvidia": {"devices": {"gpu": {"type": "gpu"}}},
                    },
                    "machines": {
                        "box": {"type": "lxc", "ip": "10.100.0.10"},
                    },
                },
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "d1.yml").read_text(),
        )
        assert "incus_profiles" in gv
        assert "nvidia" in gv["incus_profiles"]


class TestGenerateCLIOutputMessages:
    """Test stdout/stderr message formatting."""

    def test_no_domains_message_on_stdout(self, tmp_path):
        """Empty domains prints 'Nothing to generate' on stdout."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Nothing to generate" in result.stdout
        # Should NOT print "Done" when nothing generated
        assert "Done" not in result.stdout

    def test_dry_run_no_done_message(self, tmp_path):
        """Dry-run does NOT print the 'Done' message."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([
            str(infra_file), "--dry-run", "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 0
        assert "Done" not in result.stdout

    def test_validation_errors_on_stderr(self, tmp_path):
        """Validation errors are printed to stderr, not stdout."""
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

    def test_warnings_on_stderr(self, tmp_path):
        """Warnings are printed to stderr, not stdout."""
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
        assert "WARNING" not in result.stdout

    def test_error_items_prefixed_with_dash(self, tmp_path):
        """Validation error items are prefixed with '  - '."""
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
        assert "  - " in result.stderr

    def test_orphan_count_in_output(self, tmp_path):
        """Orphan report shows the count of orphan files."""
        # Generate with two domains
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

        # Remove beta
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
        assert "Orphan files (" in result.stdout

    def test_no_orphan_section_when_none(self, tmp_path):
        """No orphan section printed when there are no orphans."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Orphan" not in result.stdout

    def test_written_count_matches_files(self, tmp_path):
        """Number of 'Written:' lines matches expected file count."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        written_lines = [l for l in result.stdout.split("\n") if "Written:" in l]
        # all.yml + admin inventory + admin group_vars + admin-ansible host_vars = 4
        assert len(written_lines) == 4

    def test_dry_run_would_write_count_matches(self, tmp_path):
        """Number of 'Would write' lines matches expected file count."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([
            str(infra_file), "--dry-run", "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 0
        would_lines = [l for l in result.stdout.split("\n") if "Would write" in l]
        assert len(would_lines) == 4


class TestGenerateCLIInfraDirectoryEdgeCases:
    """Test infra/ directory mode edge cases."""

    def test_infra_dir_missing_base_yml(self, tmp_path):
        """infra/ directory without base.yml gives error."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        # No base.yml
        result = _run_generate([str(infra_dir), "--base-dir", str(tmp_path)])
        assert result.returncode != 0

    def test_infra_dir_no_domains_dir(self, tmp_path):
        """infra/ directory without domains/ subdir still works (no domains)."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }, sort_keys=False))
        result = _run_generate([str(infra_dir), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "Nothing to generate" in result.stdout

    def test_infra_dir_multiple_domain_files(self, tmp_path):
        """infra/ directory with multiple domain files merges all."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }, sort_keys=False))
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        (domains_dir / "alpha.yml").write_text(yaml.dump({
            "alpha": {"subnet_id": 0, "machines": {
                "alpha-box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
        }, sort_keys=False))
        (domains_dir / "beta.yml").write_text(yaml.dump({
            "beta": {"subnet_id": 1, "machines": {
                "beta-box": {"type": "lxc", "ip": "10.100.1.10"},
            }},
        }, sort_keys=False))

        result = _run_generate([str(infra_dir), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "2 domain" in result.stdout
        assert (tmp_path / "inventory" / "alpha.yml").exists()
        assert (tmp_path / "inventory" / "beta.yml").exists()

    def test_infra_dir_with_policies(self, tmp_path):
        """infra/ directory with policies.yml merges network policies."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }, sort_keys=False))
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()
        (domains_dir / "d1.yml").write_text(yaml.dump({
            "d1": {"subnet_id": 0, "machines": {
                "box": {"type": "lxc", "ip": "10.100.0.10"},
            }},
        }, sort_keys=False))
        (infra_dir / "policies.yml").write_text(yaml.dump({
            "network_policies": [
                {"from": "host", "to": "d1", "ports": [80]},
            ],
        }, sort_keys=False))

        result = _run_generate([str(infra_dir), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert "network_policies" in allvars

    def test_infra_dir_autodetect_from_yml_suffix(self, tmp_path):
        """Generator auto-detects directory when .yml path doesn't exist but dir does."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }, sort_keys=False))
        # Pass infra.yml but the file doesn't exist; infra/ directory does
        result = _run_generate([
            str(tmp_path / "infra.yml"), "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 0


class TestGenerateCLIEnrichment:
    """Test enrichment behavior visible through CLI."""

    def test_firewall_vm_auto_created(self, tmp_path):
        """firewall_mode: vm auto-creates sys-firewall in admin domain."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "firewall_mode": "vm"},
            "domains": {
                "admin": {"subnet_id": 0, "machines": {
                    "admin-ansible": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        # sys-firewall should be auto-created
        assert (tmp_path / "host_vars" / "sys-firewall.yml").exists()
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "sys-firewall.yml").read_text(),
        )
        assert hv["instance_type"] == "vm"
        assert hv["instance_ip"] == "10.100.0.253"

    def test_firewall_vm_info_on_stderr(self, tmp_path):
        """firewall_mode: vm prints INFO about auto-creation on stderr."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "firewall_mode": "vm"},
            "domains": {
                "admin": {"subnet_id": 0, "machines": {
                    "admin-ansible": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "INFO" in result.stderr
        assert "sys-firewall" in result.stderr

    def test_firewall_vm_user_override(self, tmp_path):
        """User-declared sys-firewall prevents auto-creation."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "firewall_mode": "vm"},
            "domains": {
                "admin": {"subnet_id": 0, "machines": {
                    "admin-ansible": {"type": "lxc", "ip": "10.100.0.10"},
                    "sys-firewall": {
                        "type": "vm", "ip": "10.100.0.200",
                        "config": {"limits.cpu": "4"},
                    },
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "sys-firewall.yml").read_text(),
        )
        # User's IP, not the auto-generated .253
        assert hv["instance_ip"] == "10.100.0.200"

    def test_exclusive_ai_auto_creates_policy(self, tmp_path):
        """Exclusive AI access auto-creates network policy."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "ai-tools": {"subnet_id": 0, "machines": {
                    "ai-box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
                "pro": {"subnet_id": 1, "machines": {
                    "pro-box": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        # Should print INFO about auto-created policy
        assert "INFO" in result.stderr
        assert "ai_access_policy" in result.stderr or "ai-tools" in result.stderr
        # all.yml should contain the auto-created policy
        allvars = yaml.safe_load(
            (tmp_path / "group_vars" / "all.yml").read_text(),
        )
        assert "network_policies" in allvars
        ai_policies = [p for p in allvars["network_policies"] if p.get("to") == "ai-tools"]
        assert len(ai_policies) == 1


class TestGenerateCLIMultipleMachinesPerDomain:
    """Test domains with multiple machines."""

    def test_multiple_machines_all_get_host_vars(self, tmp_path):
        """All machines in a domain get their own host_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "m1": {"type": "lxc", "ip": "10.100.0.10"},
                    "m2": {"type": "lxc", "ip": "10.100.0.20"},
                    "m3": {"type": "lxc", "ip": "10.100.0.30"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        for m in ("m1", "m2", "m3"):
            assert (tmp_path / "host_vars" / f"{m}.yml").exists()

    def test_multiple_machines_in_inventory(self, tmp_path):
        """All machines appear in the domain inventory file."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "m1": {"type": "lxc", "ip": "10.100.0.10"},
                    "m2": {"type": "lxc", "ip": "10.100.0.20"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        inv = yaml.safe_load(
            (tmp_path / "inventory" / "d1.yml").read_text(),
        )
        hosts = inv["all"]["children"]["d1"]["hosts"]
        assert "m1" in hosts
        assert "m2" in hosts

    def test_written_count_multiple_machines(self, tmp_path):
        """Written count includes all host_vars files."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "m1": {"type": "lxc", "ip": "10.100.0.10"},
                    "m2": {"type": "lxc", "ip": "10.100.0.20"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        written_lines = [l for l in result.stdout.split("\n") if "Written:" in l]
        # all.yml + d1 inventory + d1 group_vars + m1 host_vars + m2 host_vars = 5
        assert len(written_lines) == 5


class TestGenerateCLIOrphanEdgeCases:
    """Test orphan detection edge cases."""

    def test_orphan_without_clean_flag(self, tmp_path):
        """Orphans are reported but NOT deleted without --clean-orphans."""
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

        # Remove beta
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
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "ORPHAN" in result.stdout
        # Files should still exist (no --clean-orphans)
        assert (tmp_path / "inventory" / "beta.yml").exists()

    def test_orphan_host_vars_detected(self, tmp_path):
        """Orphan host_vars files are detected when a machine is removed."""
        # Generate with a machine
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "keep": {"type": "lxc", "ip": "10.100.0.10"},
                    "remove": {"type": "lxc", "ip": "10.100.0.20"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert (tmp_path / "host_vars" / "remove.yml").exists()

        # Remove the machine
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "keep": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "remove.yml" in result.stdout

    def test_all_yml_never_orphan(self, tmp_path):
        """group_vars/all.yml is never reported as an orphan."""
        infra_file = _make_infra(tmp_path)
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        # Rerun with different domain name
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "newdom": {"subnet_id": 1, "machines": {
                    "newbox": {"type": "lxc", "ip": "10.100.1.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        # all.yml should not be listed as orphan
        orphan_lines = [l for l in result.stdout.split("\n")
                        if "all.yml" in l and ("ORPHAN" in l or "PROTECTED" in l)]
        assert len(orphan_lines) == 0

    def test_protected_orphan_label_in_output(self, tmp_path):
        """Protected orphans show 'PROTECTED' label in output."""
        # Generate with non-ephemeral domain
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

        # Remove beta (default ephemeral=false => protected)
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
        assert "PROTECTED" in result.stdout


class TestGenerateCLIDomainEmptyMachines:
    """Test domains with empty or no machines."""

    def test_domain_with_empty_machines(self, tmp_path):
        """Domain with empty machines dict still creates inventory and group_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "empty": {"subnet_id": 0, "machines": {}},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "empty.yml").exists()
        assert (tmp_path / "group_vars" / "empty.yml").exists()

    def test_domain_with_null_machines(self, tmp_path):
        """Domain with machines: null still creates files."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "nullm": {"subnet_id": 0, "machines": None},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert (tmp_path / "inventory" / "nullm.yml").exists()


class TestGenerateCLIExitCodes:
    """Test exit codes for various scenarios."""

    def test_success_exit_code_zero(self, tmp_path):
        """Successful generation returns exit code 0."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_validation_error_exit_code_one(self, tmp_path):
        """Validation errors return exit code 1."""
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

    def test_nonexistent_file_nonzero_exit(self, tmp_path):
        """Non-existent file returns non-zero exit code."""
        result = _run_generate([str(tmp_path / "does_not_exist.yml")])
        assert result.returncode != 0

    def test_empty_domains_exit_code_zero(self, tmp_path):
        """Empty domains returns exit code 0 (not an error)."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0

    def test_dry_run_exit_code_zero(self, tmp_path):
        """Dry-run returns exit code 0."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([
            str(infra_file), "--dry-run", "--base-dir", str(tmp_path),
        ])
        assert result.returncode == 0

    def test_warnings_still_exit_code_zero(self, tmp_path):
        """Warnings do not cause non-zero exit code."""
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


class TestGenerateCLISpecialInputs:
    """Test special/edge-case inputs."""

    def test_yaml_with_null_content(self, tmp_path):
        """YAML file resolving to None gives error."""
        f = tmp_path / "null.yml"
        f.write_text("---\n")
        result = _run_generate([str(f), "--base-dir", str(tmp_path)])
        assert result.returncode != 0

    def test_yaml_with_list_instead_of_dict(self, tmp_path):
        """YAML file with a list instead of dict gives error."""
        f = tmp_path / "list.yml"
        f.write_text("- item1\n- item2\n")
        result = _run_generate([str(f), "--base-dir", str(tmp_path)])
        assert result.returncode != 0

    def test_empty_project_name(self, tmp_path):
        """Empty project_name still works (no validation on value)."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        # Should either succeed or fail with clear error (depends on impl)
        # Empty string is truthy check passes, so it succeeds
        assert result.returncode == 0

    def test_machine_without_ip(self, tmp_path):
        """Machine without IP (DHCP) generates correctly."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert (tmp_path / "host_vars" / "box.yml").exists()

    def test_machine_without_type_defaults_to_lxc(self, tmp_path):
        """Machine without explicit type defaults to lxc."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"ip": "10.100.0.10"},
                }},
            },
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_type"] == "lxc"

    def test_domain_description_in_group_vars(self, tmp_path):
        """Domain description appears in group_vars."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {
                    "description": "My test domain",
                    "subnet_id": 0,
                    "machines": {
                        "box": {"type": "lxc", "ip": "10.100.0.10"},
                    },
                },
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        gv = yaml.safe_load(
            (tmp_path / "group_vars" / "d1.yml").read_text(),
        )
        assert gv["domain_description"] == "My test domain"

    def test_large_number_of_domains(self, tmp_path):
        """Generator handles many domains without issues."""
        domains = {}
        for i in range(20):
            domains[f"d{i}"] = {
                "subnet_id": i,
                "machines": {
                    f"box-{i}": {"type": "lxc", "ip": f"10.100.{i}.10"},
                },
            }
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": domains,
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert "20 domain" in result.stdout
        for i in range(20):
            assert (tmp_path / "inventory" / f"d{i}.yml").exists()


class TestGenerateCLIDefaultOsImage:
    """Test default_os_image inheritance."""

    def test_default_os_image_inherited_by_machine(self, tmp_path):
        """Machine without os_image inherits global default."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_os_image": "images:debian/13",
            },
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {"type": "lxc", "ip": "10.100.0.10"},
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_os_image"] == "images:debian/13"

    def test_machine_os_image_overrides_default(self, tmp_path):
        """Machine os_image overrides global default."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_os_image": "images:debian/13",
            },
            "domains": {
                "d1": {"subnet_id": 0, "machines": {
                    "box": {
                        "type": "lxc", "ip": "10.100.0.10",
                        "os_image": "images:ubuntu/24.04",
                    },
                }},
            },
        })
        _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        hv = yaml.safe_load(
            (tmp_path / "host_vars" / "box.yml").read_text(),
        )
        assert hv["instance_os_image"] == "images:ubuntu/24.04"


class TestGenerateCLIStderrStdoutSeparation:
    """Test that outputs go to the correct stream."""

    def test_generating_message_on_stdout(self, tmp_path):
        """'Generating files for...' message is on stdout."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert "Generating files for" in result.stdout
        assert "Generating files for" not in result.stderr

    def test_done_message_on_stdout(self, tmp_path):
        """'Done' message is on stdout."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert "Done" in result.stdout
        assert "Done" not in result.stderr

    def test_nothing_to_generate_on_stdout(self, tmp_path):
        """'Nothing to generate' message is on stdout."""
        infra_file = _make_infra(tmp_path, {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        })
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert "Nothing to generate" in result.stdout
        assert "Nothing to generate" not in result.stderr

    def test_clean_run_no_stderr(self, tmp_path):
        """Clean run with no warnings produces empty stderr."""
        infra_file = _make_infra(tmp_path)
        result = _run_generate([str(infra_file), "--base-dir", str(tmp_path)])
        assert result.returncode == 0
        assert result.stderr == ""
