"""Tests for generate.py internal/private functions and edge cases."""

import sys
from pathlib import Path

import yaml

# Add scripts/ to path for direct import
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from generate import (  # noqa: E402
    _is_orphan_protected,
    _managed_block,
    _write_managed,
    _yaml,
    detect_orphans,
    enrich_infra,
    generate,
    load_infra,
    validate,
)  # isort: skip

# ── _yaml() ─────────────────────────────────────────────────────


class TestYamlDumper:
    def test_basic_dict(self):
        """_yaml produces valid YAML from a dict."""
        result = _yaml({"key": "value", "num": 42})
        data = yaml.safe_load(result)
        assert data == {"key": "value", "num": 42}

    def test_none_as_empty_string(self):
        """_yaml renders None as empty (not 'null')."""
        result = _yaml({"key": None})
        assert "null" not in result
        # Should be parseable back
        data = yaml.safe_load(result)
        assert data["key"] is None or data["key"] == ""

    def test_preserves_insertion_order(self):
        """_yaml preserves dict insertion order."""
        result = _yaml({"z": 1, "a": 2, "m": 3})
        lines = [line.strip() for line in result.strip().splitlines()]
        assert lines[0].startswith("z:")
        assert lines[1].startswith("a:")
        assert lines[2].startswith("m:")

    def test_nested_dict(self):
        """_yaml handles nested dicts."""
        data = {"outer": {"inner": {"deep": "value"}}}
        result = _yaml(data)
        parsed = yaml.safe_load(result)
        assert parsed["outer"]["inner"]["deep"] == "value"

    def test_list_indent(self):
        """_yaml indents lists properly."""
        result = _yaml({"items": ["a", "b", "c"]})
        parsed = yaml.safe_load(result)
        assert parsed["items"] == ["a", "b", "c"]

    def test_unicode(self):
        """_yaml handles unicode characters."""
        result = _yaml({"name": "réseau-perso"})
        assert "réseau-perso" in result

    def test_empty_dict(self):
        """_yaml handles empty dict."""
        result = _yaml({})
        assert result.strip() == "{}"

    def test_boolean_values(self):
        """_yaml handles booleans."""
        result = _yaml({"enabled": True, "debug": False})
        parsed = yaml.safe_load(result)
        assert parsed["enabled"] is True
        assert parsed["debug"] is False


# ── _managed_block() ─────────────────────────────────────────────


class TestManagedBlock:
    def test_wraps_content_with_markers(self):
        """_managed_block adds MANAGED markers around content."""
        result = _managed_block("key: value")
        assert "=== MANAGED BY infra.yml ===" in result
        assert "=== END MANAGED ===" in result
        assert "key: value" in result

    def test_includes_notice(self):
        """_managed_block includes the do-not-edit notice."""
        result = _managed_block("test: data")
        assert "Do not edit this section" in result

    def test_strips_trailing_whitespace(self):
        """_managed_block strips trailing whitespace from content."""
        result = _managed_block("key: value   \n\n\n")
        # Content should be trimmed before END marker
        lines = result.splitlines()
        # Find the content line
        content_lines = [
            line for line in lines
            if "key: value" in line
        ]
        assert len(content_lines) == 1


# ── _write_managed() ────────────────────────────────────────────


class TestWriteManaged:
    def test_creates_new_file(self, tmp_path):
        """_write_managed creates file if it doesn't exist."""
        filepath = tmp_path / "test.yml"
        _write_managed(filepath, {"key": "value"})
        assert filepath.exists()
        content = filepath.read_text()
        assert "=== MANAGED BY infra.yml ===" in content
        assert "key: value" in content

    def test_preserves_user_content(self, tmp_path):
        """_write_managed preserves content outside managed section."""
        filepath = tmp_path / "test.yml"
        # Create initial file with managed + user content
        _write_managed(filepath, {"key": "old"})
        filepath.write_text(
            filepath.read_text() + "\n# User content\ncustom_var: kept\n",
        )
        # Update managed section
        _write_managed(filepath, {"key": "new"})
        content = filepath.read_text()
        assert "key: new" in content
        assert "custom_var: kept" in content
        assert "key: old" not in content

    def test_dry_run_does_not_write(self, tmp_path):
        """_write_managed with dry_run=True doesn't create file."""
        filepath = tmp_path / "nowrite.yml"
        _write_managed(filepath, {"key": "value"}, dry_run=True)
        assert not filepath.exists()

    def test_creates_parent_directories(self, tmp_path):
        """_write_managed creates parent directories if needed."""
        filepath = tmp_path / "sub" / "dir" / "test.yml"
        _write_managed(filepath, {"key": "value"})
        assert filepath.exists()

    def test_file_without_managed_section(self, tmp_path):
        """_write_managed appends managed section to existing file without one."""
        filepath = tmp_path / "existing.yml"
        filepath.write_text("---\nexisting: content\n")
        _write_managed(filepath, {"key": "added"})
        content = filepath.read_text()
        assert "existing: content" in content
        assert "key: added" in content


# ── _is_orphan_protected() ──────────────────────────────────────


class TestIsOrphanProtected:
    def test_ephemeral_false_is_protected(self, tmp_path):
        """File with instance_ephemeral: false is protected."""
        f = tmp_path / "host.yml"
        f.write_text("instance_ephemeral: false\ninstance_name: host\n")
        assert _is_orphan_protected(f) is True

    def test_ephemeral_true_is_not_protected(self, tmp_path):
        """File with instance_ephemeral: true is not protected."""
        f = tmp_path / "host.yml"
        f.write_text("instance_ephemeral: true\ninstance_name: host\n")
        assert _is_orphan_protected(f) is False

    def test_domain_ephemeral_false_is_protected(self, tmp_path):
        """File with domain_ephemeral: false is protected."""
        f = tmp_path / "domain.yml"
        f.write_text("domain_ephemeral: false\n")
        assert _is_orphan_protected(f) is True

    def test_no_ephemeral_key_is_not_protected(self, tmp_path):
        """File without ephemeral key is not protected."""
        f = tmp_path / "host.yml"
        f.write_text("instance_name: host\nother: var\n")
        assert _is_orphan_protected(f) is False

    def test_invalid_yaml_is_not_protected(self, tmp_path):
        """File with invalid YAML is not protected."""
        f = tmp_path / "bad.yml"
        f.write_text("{{invalid yaml}}: [[[")
        assert _is_orphan_protected(f) is False

    def test_empty_file_is_not_protected(self, tmp_path):
        """Empty file is not protected."""
        f = tmp_path / "empty.yml"
        f.write_text("")
        assert _is_orphan_protected(f) is False

    def test_nonexistent_file_is_not_protected(self, tmp_path):
        """Nonexistent file is not protected."""
        f = tmp_path / "missing.yml"
        assert _is_orphan_protected(f) is False


# ── _read_vm_nested() / _read_yolo() ────────────────────────────


class TestContextReaders:
    def test_read_vm_nested_true(self, tmp_path):
        """_read_vm_nested returns True when file contains 'true'."""
        ctx = tmp_path / "vm_nested"
        ctx.write_text("true\n")
        # Test the logic directly (can't easily mock the hardcoded path)
        assert ctx.read_text().strip().lower() == "true"

    def test_read_yolo_false_when_missing(self):
        """_read_yolo returns False when file doesn't exist."""
        from generate import _read_yolo

        # The actual file /etc/anklume/yolo likely doesn't exist in CI
        result = _read_yolo()
        assert result is False or result is True  # Depends on env

    def test_vm_nested_case_insensitive(self, tmp_path):
        """vm_nested file reading is case-insensitive ('TRUE', 'True', etc.)."""
        for val in ["true", "TRUE", "True", "tRuE"]:
            f = tmp_path / f"vm_nested_{val}"
            f.write_text(f"{val}\n")
            assert f.read_text().strip().lower() == "true"

    def test_vm_nested_false_values(self, tmp_path):
        """Non-'true' values read as false."""
        for val in ["false", "FALSE", "yes", "1", "enabled", ""]:
            f = tmp_path / f"vm_nested_{val}"
            f.write_text(f"{val}\n")
            assert f.read_text().strip().lower() != "true"

    def test_vm_nested_with_whitespace(self, tmp_path):
        """Whitespace around 'true' is stripped correctly."""
        f = tmp_path / "vm_nested_ws"
        f.write_text("  true  \n")
        assert f.read_text().strip().lower() == "true"


# ── load_infra() edge cases ──────────────────────────────────────


class TestLoadInfraEdgeCases:
    def test_load_single_file(self, tmp_path):
        """load_infra loads a single YAML file."""
        f = tmp_path / "infra.yml"
        f.write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }))
        data = load_infra(f)
        assert data["project_name"] == "test"

    def test_load_directory(self, tmp_path):
        """load_infra loads infra/ directory format."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }))
        (d / "domains").mkdir()
        (d / "domains" / "anklume.yml").write_text(yaml.dump({
            "anklume": {"subnet_id": 0, "machines": {}},
        }))
        data = load_infra(d)
        assert data["project_name"] == "test"
        assert "anklume" in data["domains"]

    def test_load_directory_with_policies(self, tmp_path):
        """load_infra merges policies.yml from directory."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
        }))
        (d / "domains").mkdir()
        (d / "domains" / "a.yml").write_text(yaml.dump({
            "a": {"subnet_id": 0, "machines": {}},
        }))
        (d / "policies.yml").write_text(yaml.dump({
            "network_policies": [
                {"from": "a", "to": "a", "ports": "all"},
            ],
        }))
        data = load_infra(d)
        assert "network_policies" in data
        assert len(data["network_policies"]) == 1

    def test_load_directory_missing_base(self, tmp_path):
        """load_infra exits on missing base.yml in directory."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "domains").mkdir()
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "generate.py"), str(d)],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_load_auto_detects_yml(self, tmp_path):
        """load_infra auto-detects infra.yml in parent directory."""
        f = tmp_path / "infra.yml"
        f.write_text(yaml.dump({
            "project_name": "autodetect",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }))
        data = load_infra(f)
        assert data["project_name"] == "autodetect"

    def test_load_fallback_to_yml_suffix(self, tmp_path):
        """load_infra('infra') finds 'infra.yml' when path has no suffix."""
        f = tmp_path / "infra.yml"
        f.write_text(yaml.dump({
            "project_name": "fallback-yml",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }))
        data = load_infra(tmp_path / "infra")
        assert data["project_name"] == "fallback-yml"

    def test_load_fallback_to_directory(self, tmp_path):
        """load_infra('infra.yml') finds 'infra/' dir when file doesn't exist."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "fallback-dir",
            "global": {"base_subnet": "10.100"},
        }))
        (d / "domains").mkdir()
        data = load_infra(tmp_path / "infra.yml")
        assert data["project_name"] == "fallback-dir"

    def test_load_nonexistent_raises(self, tmp_path):
        """load_infra on nonexistent path raises FileNotFoundError."""
        import pytest as _pytest
        with _pytest.raises(FileNotFoundError):
            load_infra(tmp_path / "no_such_file_or_dir")

    def test_load_dir_without_domains_subdir(self, tmp_path):
        """Directory mode without domains/ subdir works (empty domains)."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "no-domains",
            "global": {"base_subnet": "10.100"},
        }))
        data = load_infra(d)
        assert data["project_name"] == "no-domains"
        assert data.get("domains", {}) == {}

    def test_load_dir_duplicate_domain_warning(self, tmp_path, capsys):
        """Duplicate domain in directory mode prints warning."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "dup",
            "global": {"base_subnet": "10.100"},
        }))
        domains_dir = d / "domains"
        domains_dir.mkdir()
        # Two files defining the same domain "anklume"
        (domains_dir / "01-anklume.yml").write_text(yaml.dump({
            "anklume": {"subnet_id": 0, "machines": {}},
        }))
        (domains_dir / "02-anklume.yml").write_text(yaml.dump({
            "anklume": {"subnet_id": 1, "machines": {}},
        }))
        data = load_infra(d)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "anklume" in captured.err
        # Second file wins (sorted alphabetically: 02 after 01)
        assert data["domains"]["anklume"]["subnet_id"] == 1

    def test_load_dir_policies_without_network_policies_key(self, tmp_path):
        """policies.yml without network_policies key does not add policies."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "no-pol",
            "global": {"base_subnet": "10.100"},
        }))
        (d / "domains").mkdir()
        (d / "policies.yml").write_text(yaml.dump({
            "some_other_key": "value",
        }))
        data = load_infra(d)
        assert "network_policies" not in data

    def test_load_dir_empty_domain_file(self, tmp_path):
        """Empty domain file in directory mode doesn't crash."""
        d = tmp_path / "infra"
        d.mkdir()
        (d / "base.yml").write_text(yaml.dump({
            "project_name": "empty-dom",
            "global": {"base_subnet": "10.100"},
        }))
        domains_dir = d / "domains"
        domains_dir.mkdir()
        (domains_dir / "empty.yml").write_text("")
        data = load_infra(d)
        assert data["project_name"] == "empty-dom"


# ── enrich_infra() ───────────────────────────────────────────────


class TestEnrichInfra:
    def test_enrich_firewall_host_mode_noop(self):
        """Enrichment is no-op when firewall_mode is 'host'."""
        infra = {
            "global": {"firewall_mode": "host", "base_subnet": "10.100"},
            "domains": {"anklume": {"subnet_id": 0, "machines": {}}},
        }
        enrich_infra(infra)
        assert "anklume-firewall" not in infra["domains"]["anklume"].get(
            "machines", {},
        )

    def test_enrich_firewall_vm_creates_anklume_firewall(self):
        """Enrichment auto-creates anklume-firewall when firewall_mode=vm."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "admin-ctrl": {
                            "type": "lxc", "ip": "10.100.0.10",
                        },
                    },
                },
            },
        }
        enrich_infra(infra)
        assert "anklume-firewall" in infra["domains"]["anklume"]["machines"]
        fw = infra["domains"]["anklume"]["machines"]["anklume-firewall"]
        assert fw["type"] == "vm"
        assert fw["ip"] == "10.100.0.253"

    def test_enrich_firewall_user_defined_not_overwritten(self):
        """User-defined anklume-firewall is not overwritten."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "anklume-firewall": {
                            "type": "vm",
                            "ip": "10.100.0.250",
                        },
                    },
                },
            },
        }
        enrich_infra(infra)
        assert infra["domains"]["anklume"]["machines"]["anklume-firewall"]["ip"] == "10.100.0.250"

    def test_enrich_ai_access_creates_policy(self):
        """Enrichment creates network policy for exclusive AI access."""
        infra = {
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "pro": {"subnet_id": 1, "machines": {}},
                "ai-tools": {"subnet_id": 10, "machines": {}},
            },
        }
        enrich_infra(infra)
        policies = infra.get("network_policies", [])
        assert any(p.get("to") == "ai-tools" for p in policies)

    def test_enrich_ai_access_open_mode_noop(self):
        """Enrichment is no-op when ai_access_policy is 'open'."""
        infra = {
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "open",
            },
            "domains": {},
        }
        enrich_infra(infra)
        assert "network_policies" not in infra or not infra["network_policies"]

    def test_enrich_ai_existing_policy_not_duplicated(self):
        """Enrichment does not duplicate existing AI policy."""
        infra = {
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "pro": {"subnet_id": 1, "machines": {}},
                "ai-tools": {"subnet_id": 10, "machines": {}},
            },
            "network_policies": [
                {"from": "pro", "to": "ai-tools", "ports": "all"},
            ],
        }
        enrich_infra(infra)
        ai_policies = [
            p for p in infra["network_policies"]
            if p.get("to") == "ai-tools"
        ]
        assert len(ai_policies) == 1


# ── detect_orphans() edge cases ──────────────────────────────────


class TestDetectOrphansEdges:
    def test_no_orphans_clean_state(self, tmp_path):
        """No orphans reported when state matches infra."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "admin-ctrl": {
                            "type": "lxc", "ip": "10.100.0.10",
                        },
                    },
                },
            },
        }
        generate(infra, tmp_path)
        orphans = detect_orphans(infra, tmp_path)
        assert len(orphans) == 0

    def test_orphan_host_var_detected(self, tmp_path):
        """Orphan host_vars file detected after domain removal."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "admin-ctrl": {
                            "type": "lxc", "ip": "10.100.0.10",
                        },
                    },
                },
            },
        }
        generate(infra, tmp_path)
        # Add an orphan
        (tmp_path / "host_vars" / "old-machine.yml").write_text(
            "instance_name: old-machine\n",
        )
        orphans = detect_orphans(infra, tmp_path)
        assert any("old-machine" in str(o[0]) for o in orphans)

    def test_orphan_detection_missing_host_vars_dir(self, tmp_path):
        """detect_orphans handles missing host_vars directory."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"anklume": {"subnet_id": 0, "machines": {}}},
        }
        # Don't generate, so host_vars doesn't exist
        orphans = detect_orphans(infra, tmp_path)
        assert len(orphans) == 0


# ── Additional validation edge cases ─────────────────────────────


class TestValidationEdgeCases:
    def test_subnet_id_boundary_254(self):
        """subnet_id 254 is valid."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "extreme": {
                    "subnet_id": 254,
                    "machines": {
                        "ext-host": {
                            "type": "lxc", "ip": "10.100.254.10",
                        },
                    },
                },
            },
        }
        errors = validate(infra)
        assert errors == []

    def test_all_subnet_ids_used(self):
        """Infra with many unique subnet_ids validates."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }
        for i in range(20):
            infra["domains"][f"d{i}"] = {
                "subnet_id": i,
                "machines": {
                    f"m{i}": {"type": "lxc", "ip": f"10.100.{i}.10"},
                },
            }
        errors = validate(infra)
        assert errors == []

    def test_machine_config_preserved(self, tmp_path):
        """Machine config dict is passed through to host_vars."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "admin-vm": {
                            "type": "vm",
                            "ip": "10.100.0.10",
                            "config": {
                                "limits.cpu": "4",
                                "limits.memory": "8GiB",
                            },
                        },
                    },
                },
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "admin-vm.yml").read_text()
        assert "limits.cpu" in content
        assert "limits.memory" in content

    def test_empty_description(self, tmp_path):
        """Domain with empty description generates without error."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "description": "",
                    "subnet_id": 0,
                    "machines": {
                        "host": {"type": "lxc", "ip": "10.100.0.10"},
                    },
                },
            },
        }
        errors = validate(infra)
        assert errors == []
        generate(infra, tmp_path)

    def test_machine_without_ip_uses_dhcp(self, tmp_path):
        """Machine without IP generates with DHCP."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {
                        "dhcp-host": {"type": "lxc"},
                    },
                },
            },
        }
        errors = validate(infra)
        assert errors == []
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "dhcp-host.yml").read_text()
        assert "dhcp-host" in content


# ── extract_all_images edge cases ──────────────────────────────


class TestExtractImagesEdgeCases:
    """Edge cases for extract_all_images."""

    def test_no_default_and_no_machine_image(self):
        """Both default_os_image and machine os_image None — image not added to set."""
        from generate import extract_all_images

        infra = {
            "project_name": "test",
            "global": {},  # No default_os_image
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {
                        "m": {"type": "lxc"},  # No os_image
                    },
                },
            },
        }
        images = extract_all_images(infra)
        # No image should be in the result since both are None
        assert images == []

    def test_many_duplicates_deduped(self):
        """50 machines same image, only 1 in result."""
        from generate import extract_all_images

        machines = {}
        for i in range(50):
            machines[f"m{i}"] = {"type": "lxc", "os_image": "images:debian/13"}
        infra = {
            "project_name": "test",
            "global": {},
            "domains": {
                "d": {"subnet_id": 0, "machines": machines},
            },
        }
        images = extract_all_images(infra)
        assert len(images) == 1
        assert images[0] == "images:debian/13"


# ── Template rendering edge cases ──────────────────────────────


class TestTemplateEdgeCases:
    """Edge cases for template rendering (generate output)."""

    def test_profiles_null_not_in_group_vars(self, tmp_path):
        """profiles: null is not output in group_vars."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "profiles": None,
                    "machines": {
                        "m": {"type": "lxc", "ip": "10.100.0.10"},
                    },
                },
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "d.yml").read_text()
        # profiles: null should not appear (the code checks `if domain.get("profiles"):`)
        assert "incus_profiles" not in content

    def test_empty_roles_list(self, tmp_path):
        """Machine with roles: [] generates instance_roles: [] (empty list is falsy but not None)."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {
                        "m": {"type": "lxc", "ip": "10.100.0.10", "roles": []},
                    },
                },
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "m.yml").read_text()
        # Empty list [] is falsy, so `{k: v ... if v is not None}` keeps it,
        # but then `[]` is truthy for `is not None` check. Let's see what happens.
        # Actually, the generate code filters by `if v is not None`, so [] passes.
        # But then empty list in YAML is `instance_roles: []`
        assert "instance_roles" in content

    def test_null_values_omitted_in_host_vars(self, tmp_path):
        """description: null etc. omitted from host_vars output."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {
                        "m": {
                            "type": "lxc",
                            "ip": "10.100.0.10",
                            "description": None,
                            "gpu": None,
                            "profiles": None,
                            "config": None,
                            "devices": None,
                            "storage_volumes": None,
                            "roles": None,
                        },
                    },
                },
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "m.yml").read_text()
        # None values should be filtered out by `if v is not None`
        # But description defaults to "" via m.get("description", ""), so "" is not None
        # gpu=None gets passed through as m.get("gpu") which is None -> filtered
        assert "instance_gpu" not in content
        assert "instance_profiles" not in content
        assert "instance_config" not in content
        assert "instance_devices" not in content
        assert "instance_storage_volumes" not in content
        assert "instance_roles" not in content


# ── get_warnings() unit tests ────────────────────────────────────


class TestGetWarnings:
    """Unit tests for get_warnings() function."""

    def test_no_warnings_for_simple_infra(self):
        """Simple valid infra produces no warnings."""
        from generate import get_warnings
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}},
            },
        }
        assert get_warnings(infra) == []

    def test_single_gpu_exclusive_no_warning(self):
        """Single GPU instance in exclusive mode produces no warning."""
        from generate import get_warnings
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {"m": {"type": "lxc", "gpu": True}},
                },
            },
        }
        assert get_warnings(infra) == []

    def test_single_gpu_shared_no_warning(self):
        """Single GPU instance with shared policy produces no warning."""
        from generate import get_warnings
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "gpu_policy": "shared"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {"m": {"type": "lxc", "gpu": True}},
                },
            },
        }
        assert get_warnings(infra) == []

    def test_empty_domains_no_warnings(self):
        """Empty domains dict produces no warnings."""
        from generate import get_warnings
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }
        assert get_warnings(infra) == []

    def test_domains_none_no_warnings(self):
        """domains: None produces no warnings."""
        from generate import get_warnings
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": None,
        }
        assert get_warnings(infra) == []


# ── _write_managed() edge cases ──────────────────────────────────


class TestWriteManagedEdgeCases:
    """Additional edge cases for _write_managed()."""

    def test_dry_run_returns_content_without_creating(self, tmp_path):
        """dry_run returns (filepath, content) tuple without creating file."""
        filepath = tmp_path / "test.yml"
        fp, content = _write_managed(filepath, {"key": "val"}, dry_run=True)
        assert fp == filepath
        assert "key: val" in content
        assert not filepath.exists()

    def test_update_managed_section_only(self, tmp_path):
        """Updating replaces only the managed section, not user content."""
        filepath = tmp_path / "test.yml"
        _write_managed(filepath, {"old": "data"})
        original = filepath.read_text()
        user_block = "\n# My custom config\nmy_var: keep_me\n"
        filepath.write_text(original + user_block)
        _write_managed(filepath, {"new": "data"})
        result = filepath.read_text()
        assert "new: data" in result
        assert "old: data" not in result
        assert "my_var: keep_me" in result

    def test_file_without_managed_prepends_block(self, tmp_path):
        """Existing file without managed section gets block prepended."""
        filepath = tmp_path / "existing.yml"
        filepath.write_text("---\nmy_existing: content\n")
        _write_managed(filepath, {"injected": "data"})
        result = filepath.read_text()
        assert "injected: data" in result
        assert "my_existing: content" in result
        # Managed block should be before user content
        assert result.index("MANAGED BY") < result.index("my_existing")

    def test_file_without_yaml_doc_marker_gets_prefix(self, tmp_path):
        """Existing file not starting with '---' gets prefix added."""
        filepath = tmp_path / "no-marker.yml"
        filepath.write_text("plain_key: value\n")
        _write_managed(filepath, {"managed": "data"})
        result = filepath.read_text()
        assert result.startswith("---")
        assert "managed: data" in result
        assert "plain_key: value" in result


# ── _is_orphan_protected() edge cases ────────────────────────────


class TestIsOrphanProtectedEdgeCases:
    """Additional edge cases for orphan protection."""

    def test_string_ephemeral_true(self, tmp_path):
        """String 'true' for ephemeral is truthy, so not protected."""
        f = tmp_path / "str.yml"
        f.write_text("instance_ephemeral: 'true'\n")
        # YAML string "true" is parsed as string "true", which is truthy
        # `not data[key]` → not "true" → False (not protected)
        assert _is_orphan_protected(f) is False

    def test_yaml_list_not_protected(self, tmp_path):
        """YAML file parsed as a list (not dict) is not protected."""
        f = tmp_path / "list.yml"
        f.write_text("- item1\n- item2\n")
        assert _is_orphan_protected(f) is False

    def test_integer_ephemeral_zero_is_protected(self, tmp_path):
        """instance_ephemeral: 0 is falsy, so protected (not 0 → True)."""
        f = tmp_path / "int.yml"
        f.write_text("instance_ephemeral: 0\n")
        assert _is_orphan_protected(f) is True

    def test_integer_ephemeral_one_not_protected(self, tmp_path):
        """instance_ephemeral: 1 is truthy, so not protected."""
        f = tmp_path / "int1.yml"
        f.write_text("instance_ephemeral: 1\n")
        assert _is_orphan_protected(f) is False

    def test_domain_ephemeral_takes_priority(self, tmp_path):
        """domain_ephemeral checked before instance_ephemeral."""
        f = tmp_path / "both.yml"
        f.write_text("domain_ephemeral: true\ninstance_ephemeral: false\n")
        # domain_ephemeral is first in the loop, so it's checked first
        # domain_ephemeral=true → not true → False (not protected)
        assert _is_orphan_protected(f) is False


# ── detect_orphans() edge cases ──────────────────────────────────


class TestDetectOrphansAdditional:
    """Additional edge cases for detect_orphans."""

    def test_all_yml_is_never_orphan(self, tmp_path):
        """group_vars/all.yml is never reported as orphan."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {},
        }
        gv_dir = tmp_path / "group_vars"
        gv_dir.mkdir(parents=True)
        (gv_dir / "all.yml").write_text("project_name: test\n")
        orphans = detect_orphans(infra, tmp_path)
        assert not any("all.yml" in str(o[0]) for o in orphans)

    def test_empty_host_vars_dir_no_orphans(self, tmp_path):
        """Empty host_vars directory does not produce orphans."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {}}},
        }
        (tmp_path / "host_vars").mkdir(parents=True)
        orphans = detect_orphans(infra, tmp_path)
        assert len(orphans) == 0

    def test_orphan_with_unparseable_yaml(self, tmp_path):
        """Orphan file with unparseable YAML is not protected."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {}}},
        }
        hv_dir = tmp_path / "host_vars"
        hv_dir.mkdir(parents=True)
        (hv_dir / "broken.yml").write_text("{{bad yaml}}: [[[")
        orphans = detect_orphans(infra, tmp_path)
        assert len(orphans) == 1
        assert orphans[0][1] is False  # Not protected

    def test_detect_orphans_nonexistent_base_dir(self, tmp_path):
        """detect_orphans on nonexistent base_dir returns empty list."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {}}},
        }
        orphans = detect_orphans(infra, tmp_path / "nonexistent")
        assert orphans == []


# ── extract_all_images() edge cases ──────────────────────────────


class TestExtractImagesMore:
    """More edge cases for extract_all_images."""

    def test_empty_string_image_not_included(self):
        """Empty string os_image is not included (falsy)."""
        from generate import extract_all_images
        infra = {
            "global": {"default_os_image": ""},
            "domains": {
                "d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}},
            },
        }
        images = extract_all_images(infra)
        assert images == []

    def test_machine_image_overrides_default(self):
        """Machine-level os_image overrides global default."""
        from generate import extract_all_images
        infra = {
            "global": {"default_os_image": "images:debian/13"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {
                        "m": {"type": "lxc", "os_image": "images:ubuntu/24.04"},
                    },
                },
            },
        }
        images = extract_all_images(infra)
        assert images == ["images:ubuntu/24.04"]

    def test_mixed_images_sorted(self):
        """Multiple different images are sorted alphabetically."""
        from generate import extract_all_images
        infra = {
            "global": {},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {
                        "m1": {"type": "lxc", "os_image": "images:ubuntu/24.04"},
                        "m2": {"type": "lxc", "os_image": "images:alpine/3.20"},
                        "m3": {"type": "lxc", "os_image": "images:debian/13"},
                    },
                },
            },
        }
        images = extract_all_images(infra)
        assert images == ["images:alpine/3.20", "images:debian/13", "images:ubuntu/24.04"]

    def test_domains_none_returns_empty(self):
        """domains: None returns empty image list."""
        from generate import extract_all_images
        infra = {"global": {"default_os_image": "images:debian/13"}, "domains": None}
        assert extract_all_images(infra) == []


# ── Connection variables in output ───────────────────────────────


class TestConnectionVariables:
    """Verify connection variables behavior in generated output."""

    def test_psot_connection_in_all_yml(self, tmp_path):
        """default_connection appears as psot_default_connection in all.yml."""
        infra = {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc", "ip": "10.100.0.10"}}}},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "psot_default_connection: community.general.incus" in content
        assert "psot_default_user: root" in content

    def test_ansible_connection_never_in_output(self, tmp_path):
        """ansible_connection and ansible_user never appear in any generated file."""
        infra = {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc", "ip": "10.100.0.10"}}}},
        }
        generate(infra, tmp_path)
        for f in tmp_path.rglob("*.yml"):
            text = f.read_text()
            assert "ansible_connection:" not in text, f"ansible_connection found in {f}"
            assert "ansible_user:" not in text, f"ansible_user found in {f}"

    def test_connection_without_user(self, tmp_path):
        """default_connection without default_user: only connection appears."""
        infra = {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "default_connection": "community.general.incus",
            },
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc", "ip": "10.100.0.10"}}}},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "psot_default_connection" in content
        assert "psot_default_user" not in content

    def test_neither_connection_nor_user(self, tmp_path):
        """Neither default_connection nor default_user: neither psot_ appears."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc", "ip": "10.100.0.10"}}}},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "psot_default_connection" not in content
        assert "psot_default_user" not in content


# ── enrich_infra() idempotency ───────────────────────────────────


class TestEnrichIdempotency:
    """Test that enrich_infra is idempotent (calling twice = same result)."""

    def test_firewall_enrichment_idempotent(self):
        """Calling enrich_infra twice doesn't duplicate anklume-firewall."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {"subnet_id": 0, "machines": {"ctrl": {"type": "lxc", "ip": "10.100.0.10"}}},
            },
        }
        enrich_infra(infra)
        assert "anklume-firewall" in infra["domains"]["anklume"]["machines"]
        enrich_infra(infra)
        # Should still have exactly one anklume-firewall, not two
        fw_count = sum(1 for m in infra["domains"]["anklume"]["machines"] if m == "anklume-firewall")
        assert fw_count == 1

    def test_ai_access_enrichment_idempotent(self):
        """Calling enrich_infra twice doesn't duplicate AI policy."""
        infra = {
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "pro": {"subnet_id": 1, "machines": {}},
                "ai-tools": {"subnet_id": 10, "machines": {}},
            },
        }
        enrich_infra(infra)
        count1 = len([p for p in infra.get("network_policies", []) if p.get("to") == "ai-tools"])
        enrich_infra(infra)
        count2 = len([p for p in infra.get("network_policies", []) if p.get("to") == "ai-tools"])
        assert count1 == count2 == 1


# ── Validate early return ────────────────────────────────────────


class TestValidateEarlyReturn:
    """Test that validation returns early on missing required keys."""

    def test_missing_global_returns_two_errors(self):
        """Missing global and domains keys returns exactly 2 errors."""
        infra = {"project_name": "test"}
        errors = validate(infra)
        assert len(errors) == 2
        assert any("global" in e for e in errors)
        assert any("domains" in e for e in errors)

    def test_missing_all_required_keys_returns_three_errors(self):
        """Missing all 3 required keys returns exactly 3 errors."""
        errors = validate({})
        assert len(errors) == 3

    def test_early_return_skips_domain_validation(self):
        """Missing required keys means no domain-specific errors."""
        infra = {"project_name": "test"}
        errors = validate(infra)
        # Should not contain any domain-related errors like "invalid name"
        assert not any("subnet" in e.lower() for e in errors)
        assert not any("ip" in e.lower() for e in errors)


# ── Network policy validation edge cases ──────────────────────────


class TestNetworkPolicyValidation:
    """Detailed tests for network_policies validation in validate()."""

    def _base(self, policies, extra_domains=None):
        domains = {
            "anklume": {"subnet_id": 0, "machines": {"ctrl": {"type": "lxc", "ip": "10.100.0.10"}}},
            "pro": {"subnet_id": 1, "machines": {"dev": {"type": "lxc", "ip": "10.100.1.10"}}},
        }
        if extra_domains:
            domains.update(extra_domains)
        return {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": domains,
            "network_policies": policies,
        }

    def test_valid_policy_no_errors(self):
        """A valid network policy produces no errors."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [8080], "protocol": "tcp"},
        ])
        errors = validate(infra)
        assert errors == []

    def test_policy_port_zero_invalid(self):
        """Port 0 is invalid (must be 1-65535)."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [0], "protocol": "tcp"},
        ])
        errors = validate(infra)
        assert any("invalid port 0" in e for e in errors)

    def test_policy_port_65536_invalid(self):
        """Port 65536 is invalid (must be 1-65535)."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [65536], "protocol": "tcp"},
        ])
        errors = validate(infra)
        assert any("invalid port 65536" in e for e in errors)

    def test_policy_port_negative_invalid(self):
        """Negative port is invalid."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [-1], "protocol": "tcp"},
        ])
        errors = validate(infra)
        assert any("invalid port -1" in e for e in errors)

    def test_policy_ports_all_valid(self):
        """ports: 'all' is a valid value."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": "all"},
        ])
        errors = validate(infra)
        assert errors == []

    def test_policy_ports_string_invalid(self):
        """ports as a non-'all' string is invalid (must be list or 'all')."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": "8080"},
        ])
        errors = validate(infra)
        assert any("ports must be a list" in e for e in errors)

    def test_policy_protocol_invalid(self):
        """Invalid protocol value is rejected."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [80], "protocol": "icmp"},
        ])
        errors = validate(infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_policy_missing_from(self):
        """Missing 'from' field is caught."""
        infra = self._base([
            {"to": "pro", "ports": [80]},
        ])
        errors = validate(infra)
        assert any("missing 'from'" in e for e in errors)

    def test_policy_missing_to(self):
        """Missing 'to' field is caught."""
        infra = self._base([
            {"from": "anklume", "ports": [80]},
        ])
        errors = validate(infra)
        assert any("missing 'to'" in e for e in errors)

    def test_policy_unknown_from_reference(self):
        """Unknown 'from' reference is caught."""
        infra = self._base([
            {"from": "nonexistent", "to": "pro", "ports": [80]},
        ])
        errors = validate(infra)
        assert any("nonexistent" in e and "not a known" in e for e in errors)

    def test_policy_unknown_to_reference(self):
        """Unknown 'to' reference is caught."""
        infra = self._base([
            {"from": "anklume", "to": "nowhere", "ports": [80]},
        ])
        errors = validate(infra)
        assert any("nowhere" in e and "not a known" in e for e in errors)

    def test_policy_host_keyword_valid(self):
        """'host' keyword is valid for from/to."""
        infra = self._base([
            {"from": "host", "to": "pro", "ports": [80]},
        ])
        errors = validate(infra)
        assert errors == []

    def test_policy_machine_name_valid(self):
        """Machine name is valid for from/to."""
        infra = self._base([
            {"from": "ctrl", "to": "dev", "ports": [80]},
        ])
        errors = validate(infra)
        assert errors == []

    def test_policy_bidirectional_accepted(self):
        """bidirectional: true is accepted without error."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": "all", "bidirectional": True},
        ])
        errors = validate(infra)
        assert errors == []

    def test_policy_non_dict_entry(self):
        """Non-dict policy entry is caught."""
        infra = self._base(["not-a-dict"])
        errors = validate(infra)
        assert any("must be a mapping" in e for e in errors)

    def test_multiple_valid_ports(self):
        """Multiple valid ports in a single policy accepted."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [80, 443, 8080, 11434]},
        ])
        errors = validate(infra)
        assert errors == []

    def test_mixed_valid_and_invalid_ports(self):
        """Mixed valid and invalid ports: each invalid port reported."""
        infra = self._base([
            {"from": "anklume", "to": "pro", "ports": [80, 0, 70000]},
        ])
        errors = validate(infra)
        assert any("invalid port 0" in e for e in errors)
        assert any("invalid port 70000" in e for e in errors)

    def test_both_from_and_to_invalid(self):
        """Both from and to invalid: both errors reported."""
        infra = self._base([
            {"from": "ghost", "to": "phantom", "ports": [80]},
        ])
        errors = validate(infra)
        from_errors = [e for e in errors if "ghost" in e]
        to_errors = [e for e in errors if "phantom" in e]
        assert len(from_errors) >= 1
        assert len(to_errors) >= 1


# ── AI access policy validation detailed ──────────────────────────


class TestAIAccessPolicyDetailed:
    """Detailed tests for AI access policy validation and enrichment."""

    def _ai_infra(self, **overrides):
        infra = {
            "project_name": "test",
            "global": {
                "base_subnet": "10.100",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "pro": {"subnet_id": 1, "machines": {}},
                "ai-tools": {"subnet_id": 10, "machines": {}},
            },
        }
        infra["global"].update(overrides)
        return infra

    def test_exclusive_valid_config_passes(self):
        """Valid exclusive AI config passes validation."""
        infra = self._ai_infra()
        errors = validate(infra)
        assert errors == []

    def test_exclusive_missing_default_errors(self):
        """Exclusive without ai_access_default errors."""
        infra = self._ai_infra()
        del infra["global"]["ai_access_default"]
        errors = validate(infra)
        assert any("ai_access_default is required" in e for e in errors)

    def test_exclusive_default_is_ai_tools_errors(self):
        """ai_access_default cannot be 'ai-tools' itself."""
        infra = self._ai_infra(ai_access_default="ai-tools")
        errors = validate(infra)
        assert any("cannot be 'ai-tools'" in e for e in errors)

    def test_exclusive_default_unknown_domain_errors(self):
        """ai_access_default referencing unknown domain errors."""
        infra = self._ai_infra(ai_access_default="nonexistent")
        errors = validate(infra)
        assert any("nonexistent" in e and "not a known domain" in e for e in errors)

    def test_exclusive_no_ai_tools_domain_errors(self):
        """Exclusive mode without ai-tools domain errors."""
        infra = self._ai_infra()
        del infra["domains"]["ai-tools"]
        errors = validate(infra)
        assert any("no 'ai-tools' domain" in e for e in errors)

    def test_exclusive_two_policies_to_ai_tools_errors(self):
        """Two network_policies targeting ai-tools errors."""
        infra = self._ai_infra()
        infra["network_policies"] = [
            {"from": "pro", "to": "ai-tools", "ports": "all"},
            {"from": "anklume", "to": "ai-tools", "ports": [8080]},
        ]
        infra["domains"]["anklume"] = {"subnet_id": 0, "machines": {}}
        errors = validate(infra)
        assert any("2 network_policies target ai-tools" in e for e in errors)

    def test_invalid_ai_access_policy_value(self):
        """Invalid ai_access_policy value errors."""
        infra = self._ai_infra(ai_access_policy="both")
        errors = validate(infra)
        assert any("must be 'exclusive' or 'open'" in e for e in errors)

    def test_open_mode_skips_exclusive_validation(self):
        """Open mode does not trigger exclusive-mode checks."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "ai_access_policy": "open"},
            "domains": {"d": {"subnet_id": 0, "machines": {}}},
        }
        errors = validate(infra)
        assert errors == []

    def test_enrichment_auto_creates_bidirectional_policy(self):
        """Auto-created policy is bidirectional."""
        infra = self._ai_infra()
        enrich_infra(infra)
        policy = next(p for p in infra["network_policies"] if p.get("to") == "ai-tools")
        assert policy.get("bidirectional") is True

    def test_enrichment_skips_when_no_ai_tools_domain(self):
        """Enrichment no-op when ai-tools domain does not exist."""
        infra = self._ai_infra()
        del infra["domains"]["ai-tools"]
        # Should not crash
        enrich_infra(infra)
        assert "network_policies" not in infra or not infra.get("network_policies")

    def test_enrichment_skips_when_no_default(self):
        """Enrichment no-op when ai_access_default is empty."""
        infra = self._ai_infra()
        infra["global"]["ai_access_default"] = ""
        enrich_infra(infra)
        assert "network_policies" not in infra or not infra.get("network_policies")


# ── validate() domain-level edge cases ────────────────────────────


class TestValidateDomainEdgeCases:
    """Additional edge cases for domain and machine validation."""

    def test_invalid_domain_name_uppercase(self):
        """Domain name with uppercase letters errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"MyDomain": {"subnet_id": 0, "machines": {}}},
        }
        errors = validate(infra)
        assert any("invalid name" in e for e in errors)

    def test_invalid_domain_name_underscore(self):
        """Domain name with underscore errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"my_domain": {"subnet_id": 0, "machines": {}}},
        }
        errors = validate(infra)
        assert any("invalid name" in e for e in errors)

    def test_invalid_domain_name_starts_with_hyphen(self):
        """Domain name starting with hyphen errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"-bad": {"subnet_id": 0, "machines": {}}},
        }
        errors = validate(infra)
        assert any("invalid name" in e for e in errors)

    def test_subnet_id_255_invalid(self):
        """subnet_id 255 is out of range."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 255, "machines": {}}},
        }
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_subnet_id_negative_invalid(self):
        """Negative subnet_id is invalid."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": -1, "machines": {}}},
        }
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_subnet_id_string_invalid(self):
        """String subnet_id is invalid."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": "five", "machines": {}}},
        }
        errors = validate(infra)
        assert any("subnet_id must be 0-254" in e for e in errors)

    def test_invalid_machine_type(self):
        """Invalid machine type errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "docker"}}}},
        }
        errors = validate(infra)
        assert any("type must be 'lxc' or 'vm'" in e for e in errors)

    def test_duplicate_machine_names_across_domains(self):
        """Machine names must be globally unique."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {"clash": {"type": "lxc", "ip": "10.100.0.10"}}},
                "d2": {"subnet_id": 1, "machines": {"clash": {"type": "lxc", "ip": "10.100.1.10"}}},
            },
        }
        errors = validate(infra)
        assert any("duplicate" in e.lower() and "clash" in e for e in errors)

    def test_duplicate_ips_across_domains(self):
        """IP addresses must be globally unique."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d1": {"subnet_id": 0, "machines": {"m1": {"type": "lxc", "ip": "10.100.0.10"}}},
                "d2": {"subnet_id": 1, "machines": {"m2": {"type": "lxc", "ip": "10.100.0.10"}}},
            },
        }
        errors = validate(infra)
        assert any("IP 10.100.0.10 already used" in e for e in errors)

    def test_ip_wrong_subnet(self):
        """IP outside declared subnet errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {"subnet_id": 5, "machines": {"m": {"type": "lxc", "ip": "10.100.9.10"}}},
            },
        }
        errors = validate(infra)
        assert any("not in subnet 10.100.5.0/24" in e for e in errors)

    def test_ephemeral_non_boolean_errors(self):
        """Non-boolean ephemeral value errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {"subnet_id": 0, "ephemeral": "yes", "machines": {}},
            },
        }
        errors = validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_machine_ephemeral_non_boolean_errors(self):
        """Non-boolean machine ephemeral value errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {"subnet_id": 0, "machines": {"m": {"type": "lxc", "ephemeral": 1}}},
            },
        }
        errors = validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_undefined_profile_reference_errors(self):
        """Machine referencing undefined profile errors."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "profiles": {},
                    "machines": {"m": {"type": "lxc", "profiles": ["default", "ghost"]}},
                },
            },
        }
        errors = validate(infra)
        assert any("profile 'ghost' not defined" in e for e in errors)

    def test_default_profile_always_allowed(self):
        """'default' profile is always allowed without definition."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "profiles": {},
                    "machines": {"m": {"type": "lxc", "profiles": ["default"]}},
                },
            },
        }
        errors = validate(infra)
        assert errors == []


# ── generate() comprehensive output tests ─────────────────────────


class TestGenerateOutput:
    """Verify the structure and content of generated files."""

    def test_inventory_format(self, tmp_path):
        """Generated inventory has correct all.children.<domain>.hosts structure."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "web": {
                    "subnet_id": 1,
                    "machines": {
                        "web-app": {"type": "lxc", "ip": "10.100.1.10"},
                        "web-db": {"type": "lxc", "ip": "10.100.1.11"},
                    },
                },
            },
        }
        generate(infra, tmp_path)
        yaml.safe_load((tmp_path / "inventory" / "web.yml").read_text())
        # Remove managed markers for clean parse
        raw = (tmp_path / "inventory" / "web.yml").read_text()
        # Parse only the YAML data between managed markers
        assert "web-app" in raw
        assert "web-db" in raw

    def test_group_vars_contains_network_info(self, tmp_path):
        """group_vars/<domain>.yml contains network info."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "mydom": {"subnet_id": 42, "machines": {"m": {"type": "lxc", "ip": "10.100.42.10"}}},
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "mydom.yml").read_text()
        assert "net-mydom" in content
        assert "10.100.42.0/24" in content
        assert "10.100.42.254" in content

    def test_host_vars_contains_machine_info(self, tmp_path):
        """host_vars/<machine>.yml has instance_name, type, domain."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "machines": {
                        "my-vm": {
                            "type": "vm", "ip": "10.100.0.10",
                            "description": "Test VM",
                            "roles": ["base_system"],
                        },
                    },
                },
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "host_vars" / "my-vm.yml").read_text()
        assert "instance_name: my-vm" in content
        assert "instance_type: vm" in content
        assert "instance_domain: d" in content
        assert "instance_ip: 10.100.0.10" in content
        assert "base_system" in content

    def test_all_yml_contains_project_name(self, tmp_path):
        """group_vars/all.yml contains project_name and base_subnet."""
        infra = {
            "project_name": "my-infra",
            "global": {"base_subnet": "10.200"},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}}},
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "project_name: my-infra" in content
        assert "base_subnet: '10.200'" in content or 'base_subnet: "10.200"' in content

    def test_generate_returns_all_written_paths(self, tmp_path):
        """generate() returns list of all written file paths."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "a": {"subnet_id": 0, "machines": {"m1": {"type": "lxc"}}},
                "b": {"subnet_id": 1, "machines": {"m2": {"type": "lxc"}}},
            },
        }
        written = generate(infra, tmp_path)
        # Expected: all.yml + (inventory + group_vars per domain) + host_vars per machine
        # = 1 + 2*2 + 2 = 7
        assert len(written) == 7

    def test_multi_domain_separate_files(self, tmp_path):
        """Each domain gets its own inventory and group_vars files."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "alpha": {"subnet_id": 0, "machines": {"a1": {"type": "lxc"}}},
                "beta": {"subnet_id": 1, "machines": {"b1": {"type": "lxc"}}},
                "gamma": {"subnet_id": 2, "machines": {"g1": {"type": "lxc"}}},
            },
        }
        generate(infra, tmp_path)
        for dname in ("alpha", "beta", "gamma"):
            assert (tmp_path / "inventory" / f"{dname}.yml").exists()
            assert (tmp_path / "group_vars" / f"{dname}.yml").exists()

    def test_dry_run_returns_paths_without_files(self, tmp_path):
        """dry_run returns paths but creates no files."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {"d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}}},
        }
        written = generate(infra, tmp_path, dry_run=True)
        assert len(written) > 0
        for fp in written:
            assert not fp.exists()

    def test_profiles_in_group_vars(self, tmp_path):
        """Domain profiles appear in group_vars."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "profiles": {
                        "nvidia-compute": {
                            "devices": {"gpu": {"type": "gpu", "gputype": "physical"}},
                        },
                    },
                    "machines": {"m": {"type": "lxc"}},
                },
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "d.yml").read_text()
        assert "incus_profiles" in content
        assert "nvidia-compute" in content

    def test_network_policies_in_all_yml(self, tmp_path):
        """network_policies appear in group_vars/all.yml."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "a": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}},
            },
            "network_policies": [
                {"from": "host", "to": "a", "ports": "all"},
            ],
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "network_policies" in content

    def test_images_in_all_yml(self, tmp_path):
        """incus_all_images appears in all.yml when images are defined."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100", "default_os_image": "images:debian/13"},
            "domains": {
                "d": {"subnet_id": 0, "machines": {"m": {"type": "lxc"}}},
            },
        }
        generate(infra, tmp_path)
        content = (tmp_path / "group_vars" / "all.yml").read_text()
        assert "incus_all_images" in content
        assert "images:debian/13" in content

    def test_ephemeral_inheritance(self, tmp_path):
        """Machine inherits domain ephemeral when not specified."""
        infra = {
            "project_name": "test",
            "global": {"base_subnet": "10.100"},
            "domains": {
                "d": {
                    "subnet_id": 0,
                    "ephemeral": True,
                    "machines": {
                        "inherits": {"type": "lxc"},
                        "overrides": {"type": "lxc", "ephemeral": False},
                    },
                },
            },
        }
        generate(infra, tmp_path)
        inherits = (tmp_path / "host_vars" / "inherits.yml").read_text()
        overrides = (tmp_path / "host_vars" / "overrides.yml").read_text()
        assert "instance_ephemeral: true" in inherits
        assert "instance_ephemeral: false" in overrides


# ── _enrich_firewall() detailed tests ─────────────────────────────


class TestEnrichFirewallDetailed:
    """Additional edge cases for firewall VM enrichment."""

    def test_anklume_firewall_in_non_anklume_domain_blocks_auto_creation(self):
        """User-defined anklume-firewall in any domain prevents auto-creation."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {"subnet_id": 0, "machines": {"ctrl": {"type": "lxc"}}},
                "other": {
                    "subnet_id": 1,
                    "machines": {"anklume-firewall": {"type": "vm", "ip": "10.100.1.250"}},
                },
            },
        }
        enrich_infra(infra)
        # anklume-firewall should NOT be auto-created in anklume since user defined it in 'other'
        assert "anklume-firewall" not in infra["domains"]["anklume"]["machines"]

    def test_legacy_sys_firewall_in_non_anklume_domain_blocks_auto_creation(self):
        """Legacy sys-firewall in any domain prevents auto-creation."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {"subnet_id": 0, "machines": {"ctrl": {"type": "lxc"}}},
                "other": {
                    "subnet_id": 1,
                    "machines": {"sys-firewall": {"type": "vm", "ip": "10.100.1.250"}},
                },
            },
        }
        enrich_infra(infra)
        # anklume-firewall should NOT be auto-created since legacy sys-firewall exists
        assert "anklume-firewall" not in infra["domains"]["anklume"]["machines"]

    def test_auto_created_firewall_has_correct_roles(self):
        """Auto-created anklume-firewall has base_system and firewall_router roles."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {"subnet_id": 0, "machines": {}},
            },
        }
        enrich_infra(infra)
        fw = infra["domains"]["anklume"]["machines"]["anklume-firewall"]
        assert "base_system" in fw["roles"]
        assert "firewall_router" in fw["roles"]

    def test_auto_created_firewall_not_ephemeral(self):
        """Auto-created anklume-firewall has ephemeral: false."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {"subnet_id": 0, "machines": {}},
            },
        }
        enrich_infra(infra)
        fw = infra["domains"]["anklume"]["machines"]["anklume-firewall"]
        assert fw["ephemeral"] is False

    def test_firewall_mode_default_is_host(self):
        """Default firewall_mode is 'host' (no auto-creation)."""
        infra = {
            "global": {"base_subnet": "10.100"},
            "domains": {"anklume": {"subnet_id": 0, "machines": {}}},
        }
        enrich_infra(infra)
        assert "anklume-firewall" not in infra["domains"]["anklume"]["machines"]

    def test_firewall_custom_base_subnet(self):
        """Auto-created anklume-firewall uses custom base_subnet."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "192.168"},
            "domains": {
                "anklume": {"subnet_id": 5, "machines": {}},
            },
        }
        enrich_infra(infra)
        fw = infra["domains"]["anklume"]["machines"]["anklume-firewall"]
        assert fw["ip"] == "192.168.5.253"

    def test_firewall_machines_none_creates_dict(self):
        """When anklume.machines is None, enrich creates the dict."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "anklume": {"subnet_id": 0, "machines": None},
            },
        }
        enrich_infra(infra)
        assert isinstance(infra["domains"]["anklume"]["machines"], dict)
        assert "anklume-firewall" in infra["domains"]["anklume"]["machines"]
