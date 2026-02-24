"""Tests for shared_volumes feature (ADR-039)."""

import yaml
from generate import (
    enrich_infra,
    generate,
    validate,
)


def _base_infra(shared_volumes=None, domains=None, **global_extra):
    """Helper to build infra dict with optional shared_volumes."""
    g = {
        "base_subnet": "10.100",
        "default_os_image": "images:debian/13",
        "default_connection": "community.general.incus",
        "default_user": "root",
        **global_extra,
    }
    if domains is None:
        domains = {
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
            "ai-tools": {
                "description": "AI",
                "subnet_id": 1,
                "machines": {
                    "gpu-server": {
                        "description": "GPU",
                        "type": "lxc",
                        "ip": "10.100.1.1",
                    },
                },
            },
        }
    infra = {"project_name": "test", "global": g, "domains": domains}
    if shared_volumes is not None:
        infra["shared_volumes"] = shared_volumes
    return infra


# -- Validation tests ----------------------------------------------------------


class TestSharedVolumesValidation:
    def test_valid_domain_consumer(self):  # Matrix: SV-001
        infra = _base_infra(shared_volumes={
            "docs": {
                "consumers": {"pro": "ro"},
            },
        })
        assert validate(infra) == []

    def test_valid_machine_consumer(self):  # Matrix: SV-002
        infra = _base_infra(shared_volumes={
            "docs": {
                "consumers": {"pro-dev": "rw"},
            },
        })
        assert validate(infra) == []

    def test_invalid_volume_name(self):  # Matrix: SV-003
        infra = _base_infra(shared_volumes={
            "My_Docs": {
                "consumers": {"pro": "ro"},
            },
        })
        errors = validate(infra)
        assert any("invalid name" in e for e in errors)

    def test_unknown_consumer(self):  # Matrix: SV-004
        infra = _base_infra(shared_volumes={
            "docs": {
                "consumers": {"nonexistent": "ro"},
            },
        })
        errors = validate(infra)
        assert any("not a known domain or machine" in e for e in errors)

    def test_invalid_access_mode(self):  # Matrix: SV-005
        infra = _base_infra(shared_volumes={
            "docs": {
                "consumers": {"pro": "execute"},
            },
        })
        errors = validate(infra)
        assert any("must be 'ro' or 'rw'" in e for e in errors)

    def test_empty_consumers(self):  # Matrix: SV-006
        infra = _base_infra(shared_volumes={
            "docs": {
                "consumers": {},
            },
        })
        errors = validate(infra)
        assert any("consumers must be a non-empty mapping" in e for e in errors)

    def test_missing_consumers(self):
        infra = _base_infra(shared_volumes={
            "docs": {},
        })
        errors = validate(infra)
        assert any("consumers" in e for e in errors)

    def test_relative_source_path(self):
        infra = _base_infra(shared_volumes={
            "docs": {
                "source": "relative/path",
                "consumers": {"pro": "ro"},
            },
        })
        errors = validate(infra)
        assert any("absolute path" in e for e in errors)

    def test_relative_path(self):
        infra = _base_infra(shared_volumes={
            "docs": {
                "path": "relative/path",
                "consumers": {"pro": "ro"},
            },
        })
        errors = validate(infra)
        assert any("absolute path" in e for e in errors)

    def test_shift_not_boolean(self):
        infra = _base_infra(shared_volumes={
            "docs": {
                "shift": "yes",
                "consumers": {"pro": "ro"},
            },
        })
        errors = validate(infra)
        assert any("shift must be a boolean" in e for e in errors)

    def test_propagate_not_boolean(self):
        infra = _base_infra(shared_volumes={
            "docs": {
                "propagate": "yes",
                "consumers": {"pro": "ro"},
            },
        })
        errors = validate(infra)
        assert any("propagate must be a boolean" in e for e in errors)

    def test_device_name_collision(self):  # Matrix: SV-2-003
        domains = {
            "pro": {
                "description": "Production",
                "subnet_id": 0,
                "machines": {
                    "pro-dev": {
                        "description": "Dev",
                        "type": "lxc",
                        "ip": "10.100.0.1",
                        "devices": {
                            "sv-docs": {"type": "disk", "source": "/x", "path": "/y"},
                        },
                    },
                },
            },
        }
        infra = _base_infra(
            shared_volumes={"docs": {"consumers": {"pro-dev": "rw"}}},
            domains=domains,
        )
        errors = validate(infra)
        assert any("device name 'sv-docs' conflicts" in e for e in errors)

    def test_duplicate_mount_path(self):  # Matrix: SV-2-004
        infra = _base_infra(shared_volumes={
            "docs": {
                "path": "/shared/same",
                "consumers": {"pro": "ro"},
            },
            "data": {
                "path": "/shared/same",
                "consumers": {"pro": "ro"},
            },
        })
        errors = validate(infra)
        assert any("duplicate mount path" in e for e in errors)

    def test_shared_volumes_base_relative(self):
        infra = _base_infra(
            shared_volumes={"docs": {"consumers": {"pro": "ro"}}},
            shared_volumes_base="relative/base",
        )
        errors = validate(infra)
        assert any("shared_volumes_base must be an absolute path" in e for e in errors)


# -- Generation tests ----------------------------------------------------------


class TestSharedVolumesGeneration:
    def test_no_shared_volumes_no_change(self, tmp_path):  # Matrix: SV-007
        """Without shared_volumes, generation works unchanged."""
        infra = _base_infra()
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv_dev = tmp_path / "host_vars" / "pro-dev.yml"
        content = yaml.safe_load(hv_dev.read_text())
        assert "instance_devices" not in content

    def test_domain_consumer_all_machines(self, tmp_path):  # Matrix: SV-001
        """Domain consumer gives all domain machines the sv-* device."""
        infra = _base_infra(shared_volumes={
            "docs": {"consumers": {"pro": "ro"}},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        for mname in ("pro-dev", "pro-web"):
            hv = tmp_path / "host_vars" / f"{mname}.yml"
            content = yaml.safe_load(hv.read_text())
            devs = content.get("instance_devices", {})
            assert "sv-docs" in devs, f"sv-docs missing in {mname}"
            assert devs["sv-docs"]["type"] == "disk"
            assert devs["sv-docs"]["readonly"] == "true"

    def test_machine_consumer_only_that_machine(self, tmp_path):  # Matrix: SV-002
        """Machine consumer gives only that specific machine the device."""
        infra = _base_infra(shared_volumes={
            "docs": {"consumers": {"pro-dev": "rw"}},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv_dev = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        hv_web = yaml.safe_load((tmp_path / "host_vars" / "pro-web.yml").read_text())
        assert "sv-docs" in hv_dev.get("instance_devices", {})
        assert "sv-docs" not in (hv_web.get("instance_devices") or {})

    def test_defaults_applied(self, tmp_path):
        """Default source and path are computed from base and volume name."""
        infra = _base_infra(shared_volumes={
            "docs": {"consumers": {"pro-dev": "ro"}},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        dev = hv["instance_devices"]["sv-docs"]
        assert dev["source"] == "/srv/anklume/shares/docs"
        assert dev["path"] == "/shared/docs"

    def test_custom_base_path(self, tmp_path):
        """Custom shared_volumes_base is used for default source."""
        infra = _base_infra(
            shared_volumes={"docs": {"consumers": {"pro-dev": "ro"}}},
            shared_volumes_base="/mnt/data/shares",
        )
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        dev = hv["instance_devices"]["sv-docs"]
        assert dev["source"] == "/mnt/data/shares/docs"

    def test_machine_overrides_domain_access(self, tmp_path):  # Matrix: SV-2-001
        """Machine-level access overrides domain-level for that machine."""
        infra = _base_infra(shared_volumes={
            "docs": {"consumers": {"pro": "ro", "pro-dev": "rw"}},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv_dev = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        hv_web = yaml.safe_load((tmp_path / "host_vars" / "pro-web.yml").read_text())
        # pro-dev overridden to rw
        assert "readonly" not in hv_dev["instance_devices"]["sv-docs"]
        # pro-web inherits domain ro
        assert hv_web["instance_devices"]["sv-docs"]["readonly"] == "true"

    def test_merge_with_user_devices(self, tmp_path):  # Matrix: SV-2-002
        """sv-* devices are merged alongside user-declared devices."""
        domains = {
            "pro": {
                "description": "Production",
                "subnet_id": 0,
                "machines": {
                    "pro-dev": {
                        "description": "Dev",
                        "type": "lxc",
                        "ip": "10.100.0.1",
                        "devices": {
                            "myhome": {"type": "disk", "source": "/home", "path": "/mnt/home"},
                        },
                    },
                },
            },
        }
        infra = _base_infra(
            shared_volumes={"docs": {"consumers": {"pro-dev": "ro"}}},
            domains=domains,
        )
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        devs = hv["instance_devices"]
        assert "myhome" in devs
        assert "sv-docs" in devs

    def test_disabled_domain_skipped(self, tmp_path):  # Matrix: SV-2-005
        """Disabled domain's machines are skipped in generation."""
        domains = {
            "pro": {
                "description": "Production",
                "subnet_id": 0,
                "enabled": False,
                "machines": {
                    "pro-dev": {
                        "description": "Dev",
                        "type": "lxc",
                        "ip": "10.100.0.1",
                    },
                },
            },
            "work": {
                "description": "Work",
                "subnet_id": 1,
                "machines": {
                    "work-dev": {
                        "description": "Dev",
                        "type": "lxc",
                        "ip": "10.100.1.1",
                    },
                },
            },
        }
        infra = _base_infra(
            shared_volumes={"docs": {"consumers": {"pro": "ro", "work": "ro"}}},
            domains=domains,
        )
        enrich_infra(infra)
        generate(infra, tmp_path)
        # pro-dev host_vars should not exist (domain disabled)
        assert not (tmp_path / "host_vars" / "pro-dev.yml").exists()
        # work-dev should have the device
        hv = yaml.safe_load((tmp_path / "host_vars" / "work-dev.yml").read_text())
        assert "sv-docs" in hv.get("instance_devices", {})

    def test_readonly_absent_for_rw(self, tmp_path):
        """rw access does not set readonly key."""
        infra = _base_infra(shared_volumes={
            "docs": {"consumers": {"pro-dev": "rw"}},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        dev = hv["instance_devices"]["sv-docs"]
        assert "readonly" not in dev

    def test_shift_disabled(self, tmp_path):
        """shift: false omits shift key from device."""
        infra = _base_infra(shared_volumes={
            "docs": {"shift": False, "consumers": {"pro-dev": "ro"}},
        })
        enrich_infra(infra)
        generate(infra, tmp_path)
        hv = yaml.safe_load((tmp_path / "host_vars" / "pro-dev.yml").read_text())
        dev = hv["instance_devices"]["sv-docs"]
        assert "shift" not in dev

    def test_shared_volumes_nesting_prefix_addressing(self, tmp_path):  # Matrix: SV-3-001
        """Shared volumes + nesting prefix + addressing: devices have correct
        unprefixed paths, instance names are prefixed, IPs are zone-aware."""
        from unittest.mock import patch

        infra = {
            "project_name": "test",
            "global": {
                "addressing": {"base_octet": 10, "zone_base": 100},
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                "nesting_prefix": True,
            },
            "domains": {
                "pro": {
                    "description": "Production",
                    "trust_level": "semi-trusted",
                    "machines": {
                        "pro-dev": {
                            "description": "Dev",
                            "type": "lxc",
                        },
                    },
                },
                "ai-tools": {
                    "description": "AI",
                    "trust_level": "trusted",
                    "machines": {
                        "gpu-server": {
                            "description": "GPU",
                            "type": "lxc",
                        },
                    },
                },
            },
            "shared_volumes": {
                "datasets": {
                    "source": "/mnt/data/datasets",
                    "path": "/shared/datasets",
                    "consumers": {"pro": "ro", "gpu-server": "rw"},
                },
            },
        }
        enrich_infra(infra)
        with patch("generate._read_absolute_level", return_value=1):
            generate(infra, str(tmp_path))
        # Instance names are prefixed
        hv_dev = yaml.safe_load(
            (tmp_path / "host_vars" / "pro-dev.yml").read_text()
        )
        assert hv_dev["instance_name"] == "001-pro-dev"
        # Device paths are NOT prefixed (ADR-039: host paths stay absolute)
        dev = hv_dev["instance_devices"]["sv-datasets"]
        assert dev["source"] == "/mnt/data/datasets"
        assert dev["path"] == "/shared/datasets"
        assert dev["readonly"] == "true"
        # gpu-server has rw access
        hv_gpu = yaml.safe_load(
            (tmp_path / "host_vars" / "gpu-server.yml").read_text()
        )
        assert hv_gpu["instance_name"] == "001-gpu-server"
        gpu_dev = hv_gpu["instance_devices"]["sv-datasets"]
        assert "readonly" not in gpu_dev
        assert gpu_dev["source"] == "/mnt/data/datasets"
        # IPs are zone-aware (semi-trusted=120, trusted=110)
        gv_pro = yaml.safe_load(
            (tmp_path / "group_vars" / "pro.yml").read_text()
        )
        assert "120" in gv_pro["incus_network"]["subnet"]
        gv_ai = yaml.safe_load(
            (tmp_path / "group_vars" / "ai-tools.yml").read_text()
        )
        assert "110" in gv_ai["incus_network"]["subnet"]
