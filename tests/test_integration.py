"""Integration tests for multi-feature interactions in the PSOT generator.

Tests in this file verify that COMBINATIONS of features work correctly
together. Single-feature tests are covered in test_generate.py and
test_generate_edge_cases.py.

Run with: pytest tests/test_integration.py -v
"""

import copy
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import generate  # noqa: E402  # isort: skip


# ── Helpers ─────────────────────────────────────────────────

GLOBAL_DEFAULTS = {
    "default_os_image": "images:debian/13",
    "default_connection": "community.general.incus",
    "default_user": "root",
}


def _base_infra(**global_overrides):
    """Minimal 3-domain infra for building test scenarios."""
    return {
        "project_name": "integration-test",
        "global": {"base_subnet": "10.200", **GLOBAL_DEFAULTS, **global_overrides},
        "domains": {
            "anklume": {
                "subnet_id": 0,
                "machines": {"admin-ctrl": {"type": "lxc", "ip": "10.200.0.10"}},
            },
            "pro": {
                "subnet_id": 1,
                "machines": {"pro-dev": {"type": "lxc", "ip": "10.200.1.10"}},
            },
            "perso": {
                "subnet_id": 2,
                "ephemeral": True,
                "machines": {"perso-box": {"type": "lxc", "ip": "10.200.2.10"}},
            },
        },
    }


def _ai_infra(**extra_global):
    """Infra with admin + pro + perso + ai-tools for AI access tests."""
    return {
        "project_name": "ai-test",
        "global": {
            "base_subnet": "10.201",
            **GLOBAL_DEFAULTS,
            "ai_access_policy": "exclusive",
            "ai_access_default": "pro",
            **extra_global,
        },
        "domains": {
            "anklume": {
                "subnet_id": 0,
                "machines": {"admin-ctrl": {"type": "lxc", "ip": "10.201.0.10"}},
            },
            "pro": {
                "subnet_id": 1,
                "machines": {"pro-dev": {"type": "lxc", "ip": "10.201.1.10"}},
            },
            "perso": {
                "subnet_id": 2,
                "machines": {"perso-box": {"type": "lxc", "ip": "10.201.2.10"}},
            },
            "ai-tools": {
                "subnet_id": 10,
                "machines": {"gpu-server": {"type": "lxc", "ip": "10.201.10.10"}},
            },
        },
    }


def _full_pipeline(infra, output_dir):
    """Run validate -> enrich -> generate. Assert no validation errors."""
    errors = generate.validate(infra)
    assert errors == [], f"Validation errors: {errors}"
    generate.enrich_infra(infra)
    generate.generate(infra, str(output_dir))
    return infra


# ── Kitchen sink: all features combined ────────────────────


class TestKitchenSinkInfra:
    """Full complex infra.yml with ALL features generates valid, consistent output."""

    GPU_PROFILE = {"devices": {"gpu": {"type": "gpu", "gputype": "physical"}}}

    @classmethod
    def _kitchen_sink(cls):
        return {
            "project_name": "kitchen-sink",
            "global": {
                "base_subnet": "10.200",
                **GLOBAL_DEFAULTS,
                "firewall_mode": "vm",
                "gpu_policy": "shared",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "anklume": {
                    "subnet_id": 0,
                    "machines": {"admin-ctrl": {"type": "lxc", "ip": "10.200.0.10"}},
                },
                "pro": {
                    "subnet_id": 1,
                    "machines": {
                        "pro-dev": {"type": "lxc", "ip": "10.200.1.10"},
                        "pro-sandbox": {
                            "type": "vm",
                            "ip": "10.200.1.20",
                            "config": {"limits.cpu": "2", "limits.memory": "2GiB"},
                        },
                    },
                },
                "perso": {
                    "subnet_id": 2,
                    "ephemeral": True,
                    "machines": {
                        "perso-box": {"type": "lxc", "ip": "10.200.2.10"},
                        "perso-keep": {"type": "lxc", "ip": "10.200.2.20", "ephemeral": False},
                    },
                },
                "ai-tools": {
                    "subnet_id": 10,
                    "profiles": {"nvidia-compute": cls.GPU_PROFILE},
                    "machines": {
                        "gpu-server": {
                            "type": "lxc",
                            "ip": "10.200.10.10",
                            "gpu": True,
                            "profiles": ["default", "nvidia-compute"],
                        },
                        "ai-webui": {"type": "lxc", "ip": "10.200.10.20"},
                    },
                },
                "homelab": {
                    "subnet_id": 3,
                    "profiles": {"nvidia-compute": cls.GPU_PROFILE},
                    "machines": {
                        "homelab-llm": {
                            "type": "lxc",
                            "ip": "10.200.3.10",
                            "gpu": True,
                            "profiles": ["default", "nvidia-compute"],
                        },
                    },
                },
            },
            "network_policies": [
                {
                    "from": "pro",
                    "to": "ai-tools",
                    "ports": [11434, 3000],
                    "protocol": "tcp",
                    "bidirectional": True,
                },
                {"from": "host", "to": "gpu-server", "ports": [11434], "protocol": "tcp"},
            ],
        }

    def test_all_files_generated_with_auto_created_resources(self, tmp_path):
        """All domains + auto-created sys-firewall generate files.

        Combines: firewall_mode=vm + gpu_policy + ai_access + VM + LXC
        + ephemeral + profiles + network_policies.
        """
        infra = self._kitchen_sink()
        _full_pipeline(infra, tmp_path)

        for domain in ("anklume", "pro", "perso", "ai-tools", "homelab"):
            assert (tmp_path / "inventory" / f"{domain}.yml").exists()
            assert (tmp_path / "group_vars" / f"{domain}.yml").exists()

        expected_hosts = [
            "admin-ctrl",
            "sys-firewall",
            "pro-dev",
            "pro-sandbox",
            "perso-box",
            "perso-keep",
            "gpu-server",
            "ai-webui",
            "homelab-llm",
        ]
        for host in expected_hosts:
            assert (tmp_path / "host_vars" / f"{host}.yml").exists(), f"Missing {host}"

    def test_mixed_types_and_ephemeral_in_host_vars(self, tmp_path):
        """instance_type and ephemeral correct across all host_vars.

        Combines: VM/LXC type + ephemeral inheritance + machine override.
        """
        infra = self._kitchen_sink()
        _full_pipeline(infra, tmp_path)

        expected = {
            ("admin-ctrl", "lxc", False),
            ("sys-firewall", "vm", False),
            ("pro-dev", "lxc", False),
            ("pro-sandbox", "vm", False),
            ("perso-box", "lxc", True),
            ("perso-keep", "lxc", False),
            ("gpu-server", "lxc", False),
            ("homelab-llm", "lxc", False),
        }
        for host, exp_type, exp_eph in expected:
            hv = yaml.safe_load((tmp_path / "host_vars" / f"{host}.yml").read_text())
            assert hv["instance_type"] == exp_type, f"{host} type"
            assert hv["instance_ephemeral"] is exp_eph, f"{host} ephemeral"

    def test_gpu_shared_with_multiple_domains(self, tmp_path):
        """gpu_policy=shared + 2 GPU instances across domains -> warning, not error.

        Combines: gpu_policy + profiles + multi-domain GPU.
        """
        infra = self._kitchen_sink()
        errors = generate.validate(infra)
        assert errors == []
        warnings = generate.get_warnings(infra)
        assert any("shared" in w.lower() for w in warnings)


# ── Firewall VM + GPU + network policies ──────────────────


class TestFirewallGPUPolicies:
    """firewall_mode=vm + GPU + network policies interact correctly."""

    def test_firewall_vm_with_exclusive_gpu_and_policies(self, tmp_path):
        """sys-firewall auto-created, GPU host_vars correct, policies in all.yml.

        Combines: firewall_mode=vm + gpu_policy=exclusive + network_policies.
        """
        infra = _base_infra(firewall_mode="vm", gpu_policy="exclusive")
        infra["domains"]["pro"]["profiles"] = {
            "nvidia-compute": {"devices": {"gpu": {"type": "gpu", "gputype": "physical"}}},
        }
        infra["domains"]["pro"]["machines"]["pro-gpu"] = {
            "type": "lxc",
            "ip": "10.200.1.20",
            "gpu": True,
            "profiles": ["default", "nvidia-compute"],
        }
        infra["network_policies"] = [
            {"from": "pro", "to": "perso", "ports": [80], "protocol": "tcp"},
            {"from": "host", "to": "pro-gpu", "ports": [11434], "protocol": "tcp"},
        ]

        _full_pipeline(infra, tmp_path)

        fw_hv = yaml.safe_load((tmp_path / "host_vars" / "sys-firewall.yml").read_text())
        assert fw_hv["instance_type"] == "vm"

        gpu_hv = yaml.safe_load((tmp_path / "host_vars" / "pro-gpu.yml").read_text())
        assert gpu_hv.get("instance_gpu") is True

        all_vars = yaml.safe_load((tmp_path / "group_vars" / "all.yml").read_text())
        assert len(all_vars["network_policies"]) == 2


# ── AI exclusive + network policies ────────────────────────


class TestAIAccessWithPolicies:
    """ai_access_policy=exclusive + network policies combined."""

    def test_auto_creates_policy_and_generates_files(self, tmp_path):
        """No user policy -> auto-creates from ai_access_default, appears in all.yml.

        Combines: AI access enrichment + full generation pipeline.
        """
        infra = _ai_infra()
        _full_pipeline(infra, tmp_path)

        ai_policies = [p for p in infra.get("network_policies", []) if p.get("to") == "ai-tools"]
        assert len(ai_policies) == 1
        assert ai_policies[0]["from"] == "pro"

        all_vars = yaml.safe_load((tmp_path / "group_vars" / "all.yml").read_text())
        assert "network_policies" in all_vars

    def test_user_non_ai_policy_plus_auto_creation(self, tmp_path):
        """User non-ai policy preserved alongside auto-created ai policy.

        Combines: user network_policies + AI enrichment auto-creation.
        """
        infra = _ai_infra()
        infra["network_policies"] = [
            {"from": "pro", "to": "perso", "ports": [80], "protocol": "tcp"},
        ]
        generate.enrich_infra(infra)

        ai_policies = [p for p in infra["network_policies"] if p.get("to") == "ai-tools"]
        other_policies = [p for p in infra["network_policies"] if p.get("to") != "ai-tools"]
        assert len(ai_policies) == 1
        assert len(other_policies) == 1

    def test_user_ai_policy_suppresses_auto_creation(self, tmp_path):
        """User-provided ai-tools policy -> enrichment skips auto-creation.

        Combines: user network_policy targeting ai-tools + AI enrichment.
        """
        infra = _ai_infra()
        infra["network_policies"] = [
            {"from": "pro", "to": "ai-tools", "ports": [11434], "protocol": "tcp"},
        ]
        generate.enrich_infra(infra)
        assert len([p for p in infra["network_policies"] if p.get("to") == "ai-tools"]) == 1

    def test_ai_exclusive_with_firewall_vm(self, tmp_path):
        """Both enrichments applied: sys-firewall + AI network policy.

        Combines: ai_access_policy=exclusive + firewall_mode=vm.
        """
        infra = _ai_infra(firewall_mode="vm")
        generate.enrich_infra(infra)

        assert "sys-firewall" in infra["domains"]["anklume"]["machines"]
        assert any(p.get("to") == "ai-tools" for p in infra.get("network_policies", []))


# ── Enrichment idempotency with combined features ──────────


class TestEnrichmentIdempotency:
    """Combined enrichment (firewall + AI) is idempotent."""

    def test_double_enrich_identical(self, tmp_path):
        """enrich_infra twice with firewall_mode=vm + ai_access=exclusive -> same result.

        Combines: firewall enrichment + AI enrichment + idempotency check.
        """
        infra = _ai_infra(firewall_mode="vm")
        generate.enrich_infra(infra)
        first = copy.deepcopy(infra)
        generate.enrich_infra(infra)
        assert infra == first


# ── Ephemeral + orphan detection ───────────────────────────


class TestEphemeralOrphanInteraction:
    """Ephemeral inheritance interacts correctly with orphan detection."""

    def test_mixed_ephemeral_orphans_with_protection_status(self, tmp_path):
        """Protected (ephemeral=false) vs unprotected orphans detected correctly.

        Combines: ephemeral domain setting + orphan detection + protection status.
        """
        infra = {
            "project_name": "eph-orphan",
            "global": {"base_subnet": "10.202", **GLOBAL_DEFAULTS},
            "domains": {
                "keep": {
                    "subnet_id": 0,
                    "machines": {"keep-srv": {"type": "lxc", "ip": "10.202.0.10"}},
                },
                "remove-protected": {
                    "subnet_id": 1,
                    "ephemeral": False,
                    "machines": {"prot-srv": {"type": "lxc", "ip": "10.202.1.10"}},
                },
                "remove-ephemeral": {
                    "subnet_id": 2,
                    "ephemeral": True,
                    "machines": {"eph-srv": {"type": "lxc", "ip": "10.202.2.10"}},
                },
            },
        }
        generate.generate(infra, str(tmp_path))

        del infra["domains"]["remove-protected"]
        del infra["domains"]["remove-ephemeral"]
        orphan_names = {fp.stem: protected for fp, protected in generate.detect_orphans(infra, str(tmp_path))}

        assert "prot-srv" in orphan_names
        assert "eph-srv" in orphan_names
        assert orphan_names["prot-srv"] is True, "ephemeral=false -> protected"
        assert orphan_names["eph-srv"] is False, "ephemeral=true -> unprotected"
        assert "keep-srv" not in orphan_names

    def test_machine_override_ephemeral_in_orphan_protection(self, tmp_path):
        """Machine ephemeral=false override -> protected in orphan detection.

        Combines: ephemeral inheritance (domain=true, machine=false) + generation
        + orphan detection reading protection from generated files.
        """
        infra = {
            "project_name": "eph-override",
            "global": {"base_subnet": "10.203", **GLOBAL_DEFAULTS},
            "domains": {
                "mixed": {
                    "subnet_id": 0,
                    "ephemeral": True,
                    "machines": {
                        "mixed-temp": {"type": "lxc", "ip": "10.203.0.10"},
                        "mixed-keep": {"type": "lxc", "ip": "10.203.0.20", "ephemeral": False},
                    },
                },
            },
        }
        generate.generate(infra, str(tmp_path))

        temp_hv = yaml.safe_load((tmp_path / "host_vars" / "mixed-temp.yml").read_text())
        keep_hv = yaml.safe_load((tmp_path / "host_vars" / "mixed-keep.yml").read_text())
        assert temp_hv["instance_ephemeral"] is True
        assert keep_hv["instance_ephemeral"] is False

        del infra["domains"]["mixed"]
        orphan_names = {fp.stem: protected for fp, protected in generate.detect_orphans(infra, str(tmp_path))}
        assert orphan_names["mixed-keep"] is True
        assert orphan_names["mixed-temp"] is False


# ── Directory mode round-trip ──────────────────────────────


class TestDirectoryModeRoundTrip:
    """infra/ directory produces identical output to equivalent infra.yml."""

    def test_single_file_vs_directory_identical(self, tmp_path):
        """Domains + policies + ephemeral + VM: both input modes produce same output.

        Combines: directory mode + single-file mode + network_policies + ephemeral + VM.
        """
        single_infra = {
            "project_name": "roundtrip",
            "global": {"base_subnet": "10.204", **GLOBAL_DEFAULTS},
            "domains": {
                "alpha": {
                    "subnet_id": 0,
                    "machines": {"alpha-srv": {"type": "lxc", "ip": "10.204.0.10"}},
                },
                "beta": {
                    "subnet_id": 1,
                    "ephemeral": True,
                    "machines": {
                        "beta-web": {"type": "lxc", "ip": "10.204.1.10"},
                        "beta-vm": {"type": "vm", "ip": "10.204.1.20"},
                    },
                },
            },
            "network_policies": [
                {"from": "alpha", "to": "beta", "ports": [80], "protocol": "tcp"},
            ],
        }

        single_dir = tmp_path / "single"
        single_dir.mkdir()
        generate.generate(single_infra, str(single_dir))

        # Build equivalent infra/ directory
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        (infra_dir / "domains").mkdir()

        _write_yaml(
            infra_dir / "base.yml",
            {
                "project_name": "roundtrip",
                "global": {"base_subnet": "10.204", **GLOBAL_DEFAULTS},
            },
        )
        _write_yaml(
            infra_dir / "domains" / "alpha.yml",
            {
                "alpha": {
                    "subnet_id": 0,
                    "machines": {"alpha-srv": {"type": "lxc", "ip": "10.204.0.10"}},
                }
            },
        )
        _write_yaml(
            infra_dir / "domains" / "beta.yml",
            {
                "beta": {
                    "subnet_id": 1,
                    "ephemeral": True,
                    "machines": {
                        "beta-web": {"type": "lxc", "ip": "10.204.1.10"},
                        "beta-vm": {"type": "vm", "ip": "10.204.1.20"},
                    },
                }
            },
        )
        _write_yaml(
            infra_dir / "policies.yml",
            {
                "network_policies": [
                    {"from": "alpha", "to": "beta", "ports": [80], "protocol": "tcp"},
                ]
            },
        )

        dir_output = tmp_path / "from_dir"
        dir_output.mkdir()
        generate.generate(generate.load_infra(str(infra_dir)), str(dir_output))

        for subdir in ("inventory", "group_vars", "host_vars"):
            single_sub = single_dir / subdir
            dir_sub = dir_output / subdir
            if single_sub.exists():
                single_files = sorted(f.name for f in single_sub.glob("*.yml"))
                dir_files = sorted(f.name for f in dir_sub.glob("*.yml"))
                assert single_files == dir_files, f"{subdir}: file lists differ"
                for fname in single_files:
                    assert (single_sub / fname).read_text() == (dir_sub / fname).read_text(), (
                        f"{subdir}/{fname} differs"
                    )


def _write_yaml(path, data):
    """Write data as YAML to path."""
    path.write_text(yaml.dump(data, sort_keys=False))


# ── Multi-domain consistency ───────────────────────────────


class TestMultiDomainConsistency:
    """Multiple domains + mixed features -> all generated files consistent."""

    def test_five_domains_vm_lxc_profiles_policies(self, tmp_path):
        """5 domains with VM/LXC + profiles + policies -> all correct.

        Combines: multiple domains + VM type + profiles + network_policies
        + ephemeral + config in host_vars.
        """
        infra = _base_infra()
        infra["domains"]["sandbox"] = {
            "subnet_id": 3,
            "ephemeral": True,
            "profiles": {"nesting": {"config": {"security.nesting": "true"}}},
            "machines": {
                "sandbox-vm": {
                    "type": "vm",
                    "ip": "10.200.3.10",
                    "config": {"limits.cpu": "2", "limits.memory": "2GiB"},
                },
                "sandbox-nested": {
                    "type": "lxc",
                    "ip": "10.200.3.20",
                    "profiles": ["default", "nesting"],
                },
            },
        }
        infra["domains"]["lab"] = {
            "subnet_id": 4,
            "machines": {"lab-srv": {"type": "lxc", "ip": "10.200.4.10"}},
        }
        infra["network_policies"] = [
            {"from": "pro", "to": "lab", "ports": [80, 443], "protocol": "tcp"},
            {"from": "sandbox", "to": "lab", "ports": "all"},
        ]

        _full_pipeline(infra, tmp_path)

        for domain in ("anklume", "pro", "perso", "sandbox", "lab"):
            assert (tmp_path / "inventory" / f"{domain}.yml").exists()
            gv = yaml.safe_load((tmp_path / "group_vars" / f"{domain}.yml").read_text())
            assert "incus_network" in gv

        vm_hv = yaml.safe_load((tmp_path / "host_vars" / "sandbox-vm.yml").read_text())
        assert vm_hv["instance_type"] == "vm"
        assert vm_hv["instance_config"]["limits.cpu"] == "2"

        sandbox_gv = yaml.safe_load((tmp_path / "group_vars" / "sandbox.yml").read_text())
        assert "nesting" in sandbox_gv.get("incus_profiles", {})

        all_vars = yaml.safe_load((tmp_path / "group_vars" / "all.yml").read_text())
        assert len(all_vars["network_policies"]) == 2

    def test_scaling_ten_domains_orphan_detection(self, tmp_path):
        """10 domains -> remove 3 -> exactly those 3 detected as orphans.

        Combines: many domains + ephemeral + orphan detection at scale.
        """
        infra = {
            "project_name": "scale-test",
            "global": {"base_subnet": "10.208", **GLOBAL_DEFAULTS},
            "domains": {},
        }
        for i in range(10):
            infra["domains"][f"dom-{i:02d}"] = {
                "subnet_id": i,
                "ephemeral": True,
                "machines": {f"host-{i:02d}": {"type": "lxc", "ip": f"10.208.{i}.10"}},
            }
        generate.generate(infra, str(tmp_path))

        for i in (7, 8, 9):
            del infra["domains"][f"dom-{i:02d}"]

        orphan_strs = [str(fp) for fp, _ in generate.detect_orphans(infra, str(tmp_path))]
        for i in (7, 8, 9):
            assert any(f"dom-{i:02d}" in s or f"host-{i:02d}" in s for s in orphan_strs)
        for i in range(7):
            assert not any(f"dom-{i:02d}.yml" in s for s in orphan_strs if "inventory" in s)
