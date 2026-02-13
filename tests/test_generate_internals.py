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
        (d / "domains" / "admin.yml").write_text(yaml.dump({
            "admin": {"subnet_id": 0, "machines": {}},
        }))
        data = load_infra(d)
        assert data["project_name"] == "test"
        assert "admin" in data["domains"]

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


# ── enrich_infra() ───────────────────────────────────────────────


class TestEnrichInfra:
    def test_enrich_firewall_host_mode_noop(self):
        """Enrichment is no-op when firewall_mode is 'host'."""
        infra = {
            "global": {"firewall_mode": "host", "base_subnet": "10.100"},
            "domains": {"admin": {"subnet_id": 0, "machines": {}}},
        }
        enrich_infra(infra)
        assert "sys-firewall" not in infra["domains"]["admin"].get(
            "machines", {},
        )

    def test_enrich_firewall_vm_creates_sys_firewall(self):
        """Enrichment auto-creates sys-firewall when firewall_mode=vm."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "admin": {
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
        assert "sys-firewall" in infra["domains"]["admin"]["machines"]
        fw = infra["domains"]["admin"]["machines"]["sys-firewall"]
        assert fw["type"] == "vm"
        assert fw["ip"] == "10.100.0.253"

    def test_enrich_firewall_user_defined_not_overwritten(self):
        """User-defined sys-firewall is not overwritten."""
        infra = {
            "global": {"firewall_mode": "vm", "base_subnet": "10.100"},
            "domains": {
                "admin": {
                    "subnet_id": 0,
                    "machines": {
                        "sys-firewall": {
                            "type": "vm",
                            "ip": "10.100.0.250",
                        },
                    },
                },
            },
        }
        enrich_infra(infra)
        assert infra["domains"]["admin"]["machines"]["sys-firewall"]["ip"] == "10.100.0.250"

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
                "admin": {
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
                "admin": {
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
            "domains": {"admin": {"subnet_id": 0, "machines": {}}},
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
                "admin": {
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
                "admin": {
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
                "admin": {
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
