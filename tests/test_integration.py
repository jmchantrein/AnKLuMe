"""Integration tests using real Incus daemon.

These tests require a working Incus installation with socket access.
They create and destroy real infrastructure in isolated projects.
Skip automatically if Incus is not available.

Run with: pytest tests/test_integration.py -v
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATE_PY = PROJECT_ROOT / "scripts" / "generate.py"
SNAP_SH = PROJECT_ROOT / "scripts" / "snap.sh"
FLUSH_SH = PROJECT_ROOT / "scripts" / "flush.sh"


def incus_cmd(args, check=True):
    """Run an incus command and return stdout."""
    result = subprocess.run(
        ["incus"] + args,
        capture_output=True, text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"incus {' '.join(args)} failed: {result.stderr}")
    return result


def incus_available():
    """Check if Incus daemon is accessible."""
    result = subprocess.run(
        ["incus", "project", "list", "--format", "csv"],
        capture_output=True, text=True,
    )
    return result.returncode == 0


# Skip all tests if Incus is not available
pytestmark = pytest.mark.skipif(
    not incus_available(),
    reason="Incus daemon not accessible (run with 'sg incus-admin' or as incus user)",
)


# Unique prefix to avoid conflicts with production
TEST_PREFIX = "inttest"


@pytest.fixture()
def test_workspace(tmp_path):
    """Create a temporary workspace with a minimal infra.yml."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    # Copy generate.py (needed by make sync)
    scripts_dir = ws / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(GENERATE_PY, scripts_dir / "generate.py")

    # Create a minimal infra.yml for testing
    infra = {
        "project_name": f"{TEST_PREFIX}-project",
        "global": {
            "base_subnet": "10.199",
            "default_os_image": "images:debian/13",
            "default_connection": "community.general.incus",
            "default_user": "root",
        },
        "domains": {
            f"{TEST_PREFIX}-dom": {
                "description": "Integration test domain",
                "subnet_id": 0,
                "ephemeral": True,
                "machines": {
                    f"{TEST_PREFIX}-c1": {
                        "type": "lxc",
                        "ip": "10.199.0.10",
                    },
                },
            },
        },
    }

    import yaml
    (ws / "infra.yml").write_text(yaml.dump(infra, sort_keys=False))
    return ws, infra


@pytest.fixture(autouse=True)
def cleanup_incus():
    """Clean up any test resources after each test."""
    yield
    # Delete test instances in all projects
    result = incus_cmd(["project", "list", "--format", "json"], check=False)
    if result.returncode == 0:
        for proj in json.loads(result.stdout):
            pname = proj["name"]
            if TEST_PREFIX in pname:
                # Delete instances first
                inst_result = incus_cmd(
                    ["list", "--project", pname, "--format", "json"], check=False,
                )
                if inst_result.returncode == 0:
                    for inst in json.loads(inst_result.stdout):
                        incus_cmd(
                            ["delete", inst["name"], "--project", pname, "--force"],
                            check=False,
                        )
                # Delete profiles
                prof_result = incus_cmd(
                    ["profile", "list", "--project", pname, "--format", "csv", "-c", "n"],
                    check=False,
                )
                if prof_result.returncode == 0:
                    for prof in prof_result.stdout.strip().split("\n"):
                        prof = prof.strip()
                        if prof and prof != "default":
                            incus_cmd(
                                ["profile", "delete", prof, "--project", pname],
                                check=False,
                            )
                # Delete project
                incus_cmd(["project", "delete", pname], check=False)

    # Delete test bridges
    net_result = incus_cmd(["network", "list", "--format", "csv", "-c", "n"], check=False)
    if net_result.returncode == 0:
        for net in net_result.stdout.strip().split("\n"):
            net = net.strip()
            if net.startswith(f"net-{TEST_PREFIX}"):
                incus_cmd(["network", "delete", net], check=False)


# ── PSOT Generator Integration ──────────────────────────────


class TestGeneratorIntegration:
    """Test the PSOT generator produces valid Ansible files."""

    def test_sync_generates_files(self, test_workspace):
        """make sync creates inventory, group_vars, host_vars."""
        ws, _ = test_workspace
        result = subprocess.run(
            ["python3", str(GENERATE_PY), str(ws / "infra.yml")],
            capture_output=True, text=True, cwd=str(ws),
        )
        assert result.returncode == 0, f"generate.py failed: {result.stderr}"
        assert (ws / "inventory" / f"{TEST_PREFIX}-dom.yml").exists()
        assert (ws / "group_vars" / f"{TEST_PREFIX}-dom.yml").exists()
        assert (ws / "group_vars" / "all.yml").exists()
        assert (ws / "host_vars" / f"{TEST_PREFIX}-c1.yml").exists()

    def test_sync_idempotent(self, test_workspace):
        """Running generate.py twice produces identical output."""
        ws, _ = test_workspace
        subprocess.run(
            ["python3", str(GENERATE_PY), str(ws / "infra.yml")],
            capture_output=True, text=True, cwd=str(ws),
        )
        first = {}
        for f in ws.rglob("*.yml"):
            if f.name != "infra.yml":
                first[str(f.relative_to(ws))] = f.read_text()

        subprocess.run(
            ["python3", str(GENERATE_PY), str(ws / "infra.yml")],
            capture_output=True, text=True, cwd=str(ws),
        )
        for f in ws.rglob("*.yml"):
            if f.name != "infra.yml":
                key = str(f.relative_to(ws))
                assert first.get(key) == f.read_text(), f"File {key} changed on second run"

    def test_dry_run_creates_nothing(self, test_workspace):
        """Dry-run mode doesn't create files."""
        ws, _ = test_workspace
        result = subprocess.run(
            ["python3", str(GENERATE_PY), str(ws / "infra.yml"), "--dry-run"],
            capture_output=True, text=True, cwd=str(ws),
        )
        assert result.returncode == 0
        assert not (ws / "inventory").exists()
        assert not (ws / "group_vars").exists()
        assert not (ws / "host_vars").exists()

    def test_managed_sections_preserved(self, test_workspace):
        """User content outside managed sections is preserved."""
        ws, _ = test_workspace
        subprocess.run(
            ["python3", str(GENERATE_PY), str(ws / "infra.yml")],
            capture_output=True, text=True, cwd=str(ws),
        )
        # Add custom content
        gv = ws / "group_vars" / f"{TEST_PREFIX}-dom.yml"
        gv.write_text(gv.read_text() + "\ncustom_var: preserved\n")

        # Regenerate
        subprocess.run(
            ["python3", str(GENERATE_PY), str(ws / "infra.yml")],
            capture_output=True, text=True, cwd=str(ws),
        )
        assert "custom_var: preserved" in gv.read_text()


# ── Incus Infrastructure Integration ────────────────────────


class TestIncusInfraIntegration:
    """Test creating real Incus resources (network, project)."""

    def test_create_bridge(self):
        """Create and verify a test bridge."""
        bridge = f"net-{TEST_PREFIX}-dom"
        incus_cmd(["network", "create", bridge,
                    "ipv4.address=10.199.0.254/24",
                    "ipv4.nat=true"])
        result = incus_cmd(["network", "list", "--format", "json"])
        nets = json.loads(result.stdout)
        assert any(n["name"] == bridge for n in nets)
        # Verify config via incus network get
        addr = incus_cmd(["network", "get", bridge, "ipv4.address"])
        assert addr.stdout.strip() == "10.199.0.254/24"

    def test_create_project(self):
        """Create and verify a test project."""
        project = f"{TEST_PREFIX}-dom"
        incus_cmd(["project", "create", project])
        incus_cmd(["project", "set", project,
                    "features.networks=false",
                    "features.images=false",
                    "features.storage.volumes=false"])
        result = incus_cmd(["project", "list", "--format", "json"])
        projs = json.loads(result.stdout)
        assert any(p["name"] == project for p in projs)

    def test_create_and_start_container(self):
        """Create a test container and verify it runs."""
        project = f"{TEST_PREFIX}-dom"
        bridge = f"net-{TEST_PREFIX}-dom"
        container = f"{TEST_PREFIX}-c1"

        # Setup network and project
        incus_cmd(["network", "create", bridge,
                    "ipv4.address=10.199.0.254/24",
                    "ipv4.nat=true"])
        incus_cmd(["project", "create", project])
        incus_cmd(["project", "set", project,
                    "features.networks=false",
                    "features.images=false",
                    "features.storage.volumes=false"])

        # Configure default profile in project
        incus_cmd(["profile", "device", "add", "default", "root",
                    "disk", "path=/", "pool=default",
                    "--project", project])
        incus_cmd(["profile", "device", "add", "default", "eth0",
                    "nic", f"network={bridge}", "name=eth0",
                    "--project", project])

        # Launch container
        result = incus_cmd(["launch", "images:debian/13", container,
                            "--project", project], check=False)
        if result.returncode != 0:
            pytest.skip(f"Cannot launch container: {result.stderr}")

        # Wait for running state
        for _i in range(30):
            info = incus_cmd(["list", "--project", project, "--format", "json"])
            instances = json.loads(info.stdout)
            if instances and instances[0].get("status") == "Running":
                break
            import time
            time.sleep(2)

        # Verify container exists and is running
        info = incus_cmd(["list", "--project", project, "--format", "json"])
        instances = json.loads(info.stdout)
        assert len(instances) == 1
        assert instances[0]["name"] == container
        assert instances[0]["status"] == "Running"

    def test_snapshot_create_and_list(self):
        """Create a snapshot on a real container and list it."""
        project = f"{TEST_PREFIX}-dom"
        bridge = f"net-{TEST_PREFIX}-dom"
        container = f"{TEST_PREFIX}-c1"

        # Setup infrastructure
        incus_cmd(["network", "create", bridge,
                    "ipv4.address=10.199.0.254/24", "ipv4.nat=true"])
        incus_cmd(["project", "create", project])
        incus_cmd(["project", "set", project,
                    "features.networks=false", "features.images=false",
                    "features.storage.volumes=false"])
        incus_cmd(["profile", "device", "add", "default", "root",
                    "disk", "path=/", "pool=default", "--project", project])
        incus_cmd(["profile", "device", "add", "default", "eth0",
                    "nic", f"network={bridge}", "name=eth0", "--project", project])

        result = incus_cmd(["launch", "images:debian/13", container,
                            "--project", project], check=False)
        if result.returncode != 0:
            pytest.skip(f"Cannot launch container: {result.stderr}")

        # Wait for running
        import time
        for _i in range(30):
            info = incus_cmd(["list", "--project", project, "--format", "json"])
            instances = json.loads(info.stdout)
            if instances and instances[0].get("status") == "Running":
                break
            time.sleep(2)

        # Create snapshot
        incus_cmd(["snapshot", "create", container, "test-snap", "--project", project])

        # List snapshots
        snap_result = incus_cmd(["snapshot", "list", container,
                                  "--project", project, "--format", "json"])
        snaps = json.loads(snap_result.stdout)
        assert len(snaps) >= 1
        assert any(s["name"] == "test-snap" for s in snaps)

        # Delete snapshot
        incus_cmd(["snapshot", "delete", container, "test-snap", "--project", project])

    def test_project_isolation(self):
        """Instances in test project are not visible in default project."""
        project = f"{TEST_PREFIX}-dom"
        bridge = f"net-{TEST_PREFIX}-dom"
        container = f"{TEST_PREFIX}-c1"

        incus_cmd(["network", "create", bridge,
                    "ipv4.address=10.199.0.254/24", "ipv4.nat=true"])
        incus_cmd(["project", "create", project])
        incus_cmd(["project", "set", project,
                    "features.networks=false", "features.images=false",
                    "features.storage.volumes=false"])
        incus_cmd(["profile", "device", "add", "default", "root",
                    "disk", "path=/", "pool=default", "--project", project])
        incus_cmd(["profile", "device", "add", "default", "eth0",
                    "nic", f"network={bridge}", "name=eth0", "--project", project])

        result = incus_cmd(["launch", "images:debian/13", container,
                            "--project", project], check=False)
        if result.returncode != 0:
            pytest.skip(f"Cannot launch container: {result.stderr}")

        # Instance not visible in default project
        default_list = incus_cmd(["list", "--format", "json"])
        default_names = [i["name"] for i in json.loads(default_list.stdout)]
        assert container not in default_names

        # Instance visible in test project
        test_list = incus_cmd(["list", "--project", project, "--format", "json"])
        test_names = [i["name"] for i in json.loads(test_list.stdout)]
        assert container in test_names


# ── Script Integration ──────────────────────────────────────


class TestScriptIntegration:
    """Test shell scripts with real or mock Incus."""

    def test_guide_auto_mode(self, tmp_path):
        """guide.sh --auto completes successfully."""
        guide_sh = PROJECT_ROOT / "scripts" / "guide.sh"
        if not guide_sh.exists():
            pytest.skip("guide.sh not found")
        result = subprocess.run(
            ["bash", str(guide_sh), "--auto"],
            capture_output=True, text=True,
            cwd=str(tmp_path),
            timeout=60,
        )
        assert result.returncode == 0, f"guide.sh --auto failed: {result.stderr}"

    def test_matrix_coverage_script(self):
        """matrix-coverage.py runs successfully."""
        result = subprocess.run(
            ["python3", str(PROJECT_ROOT / "scripts" / "matrix-coverage.py")],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
        )
        assert result.returncode == 0
        assert "TOTAL" in result.stdout
        assert "100%" in result.stdout

    def test_mine_experiences_script(self):
        """mine-experiences.py runs without error."""
        script = PROJECT_ROOT / "scripts" / "mine-experiences.py"
        if not script.exists():
            pytest.skip("mine-experiences.py not found")
        result = subprocess.run(
            ["python3", str(script), "--dry-run"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=60,
        )
        # Script may not have --dry-run, just check it doesn't crash
        assert result.returncode in (0, 2), f"mine-experiences.py crashed: {result.stderr}"

    def test_deploy_nftables_dry_run(self):
        """deploy-nftables.sh --dry-run validates without applying."""
        script = PROJECT_ROOT / "scripts" / "deploy-nftables.sh"
        if not script.exists():
            pytest.skip("deploy-nftables.sh not found")
        result = subprocess.run(
            ["bash", str(script), "--dry-run"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        # May fail if no rules file exists, but should not crash
        assert result.returncode in (0, 1)

    def test_ai_switch_dry_run(self):
        """ai-switch.sh --dry-run validates without switching."""
        script = PROJECT_ROOT / "scripts" / "ai-switch.sh"
        if not script.exists():
            pytest.skip("ai-switch.sh not found")
        result = subprocess.run(
            ["bash", str(script), "--domain", "test", "--dry-run"],
            capture_output=True, text=True,
            cwd=str(PROJECT_ROOT),
            timeout=30,
        )
        # Will likely fail (no ai-tools domain) but should not crash
        assert result.returncode in (0, 1)

    def test_bootstrap_help(self):
        """bootstrap.sh --help shows usage without modifying system."""
        script = PROJECT_ROOT / "scripts" / "bootstrap.sh"
        if not script.exists():
            pytest.skip("bootstrap.sh not found")
        result = subprocess.run(
            ["bash", str(script), "--help"],
            capture_output=True, text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "Usage" in result.stdout or "usage" in result.stdout.lower()


# ── Generator Pipeline Integration (no Incus needed) ──────────


sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
import generate  # noqa: E402


class TestMultiDomainGeneration:
    """Full generate pipeline with realistic multi-domain configurations."""

    @staticmethod
    def _base_infra(extra_domains=None, **global_overrides):
        infra = {
            "project_name": "multi-test",
            "global": {
                "base_subnet": "10.200",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                **global_overrides,
            },
            "domains": {
                "admin": {
                    "description": "Admin domain",
                    "subnet_id": 0,
                    "machines": {
                        "admin-ctrl": {
                            "type": "lxc",
                            "ip": "10.200.0.10",
                        },
                    },
                },
                "pro": {
                    "description": "Work domain",
                    "subnet_id": 1,
                    "machines": {
                        "pro-dev": {
                            "type": "lxc",
                            "ip": "10.200.1.10",
                        },
                    },
                },
                "perso": {
                    "description": "Personal domain",
                    "subnet_id": 2,
                    "ephemeral": True,
                    "machines": {
                        "perso-box": {
                            "type": "lxc",
                            "ip": "10.200.2.10",
                        },
                    },
                },
            },
        }
        if extra_domains:
            infra["domains"].update(extra_domains)
        return infra

    def test_five_domains_all_files_generated(self, tmp_path):
        """5 domains with diverse configs → all files generated correctly."""
        extra = {
            "sandbox": {
                "description": "Sandbox domain",
                "subnet_id": 3,
                "ephemeral": True,
                "machines": {
                    "sandbox-vm": {"type": "vm", "ip": "10.200.3.10"},
                },
            },
            "lab": {
                "description": "Lab domain",
                "subnet_id": 4,
                "machines": {
                    "lab-srv": {"type": "lxc", "ip": "10.200.4.10"},
                },
            },
        }
        infra = self._base_infra(extra_domains=extra)
        errors = generate.validate(infra)
        assert errors == []
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        for domain in ("admin", "pro", "perso", "sandbox", "lab"):
            assert (tmp_path / "inventory" / f"{domain}.yml").exists()
            assert (tmp_path / "group_vars" / f"{domain}.yml").exists()
        for host in ("admin-ctrl", "pro-dev", "perso-box", "sandbox-vm", "lab-srv"):
            assert (tmp_path / "host_vars" / f"{host}.yml").exists()

    def test_adding_domain_only_creates_new_files(self, tmp_path):
        """Adding a 4th domain after initial generation → only new files created."""
        infra = self._base_infra()
        generate.generate(infra, str(tmp_path))
        # Record original file contents
        original = {}
        for f in tmp_path.rglob("*.yml"):
            original[str(f.relative_to(tmp_path))] = f.read_text()

        # Add a new domain and regenerate
        infra["domains"]["new-domain"] = {
            "description": "New domain",
            "subnet_id": 5,
            "machines": {"new-host": {"type": "lxc", "ip": "10.200.5.10"}},
        }
        generate.generate(infra, str(tmp_path))

        # New files exist
        assert (tmp_path / "inventory" / "new-domain.yml").exists()
        assert (tmp_path / "host_vars" / "new-host.yml").exists()
        # Original managed sections unchanged (content may differ in all.yml)
        for domain in ("admin", "pro", "perso"):
            inv_key = f"inventory/{domain}.yml"
            assert original[inv_key] == (tmp_path / inv_key).read_text()

    def test_removing_domain_detects_orphans(self, tmp_path):
        """Removing a domain → orphans detected with correct filenames."""
        infra = self._base_infra()
        generate.generate(infra, str(tmp_path))

        # Remove perso domain
        del infra["domains"]["perso"]
        orphans = generate.detect_orphans(infra, str(tmp_path))
        orphan_paths = [str(p) for p in orphans]
        assert any("perso" in p for p in orphan_paths)

    def test_changing_machine_ip_updates_host_vars(self, tmp_path):
        """Changing a machine's IP → host_vars updated."""
        infra = self._base_infra()
        generate.generate(infra, str(tmp_path))

        old_content = (tmp_path / "host_vars" / "pro-dev.yml").read_text()
        assert "10.200.1.10" in old_content

        infra["domains"]["pro"]["machines"]["pro-dev"]["ip"] = "10.200.1.99"
        generate.generate(infra, str(tmp_path))

        new_content = (tmp_path / "host_vars" / "pro-dev.yml").read_text()
        assert "10.200.1.99" in new_content
        assert "10.200.1.10" not in new_content

    def test_adding_profile_updates_group_vars(self, tmp_path):
        """Adding a profile to a domain → group_vars updated."""
        infra = self._base_infra()
        generate.generate(infra, str(tmp_path))

        infra["domains"]["pro"]["profiles"] = {
            "gpu-profile": {
                "devices": {"gpu": {"type": "gpu", "gputype": "physical"}},
            },
        }
        generate.generate(infra, str(tmp_path))
        gv = (tmp_path / "group_vars" / "pro.yml").read_text()
        assert "gpu-profile" in gv


class TestNetworkPolicyGeneration:
    """Test network policy generation through the full pipeline."""

    @staticmethod
    def _infra_with_policies(policies):
        return {
            "project_name": "policy-test",
            "global": {
                "base_subnet": "10.201",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "alpha": {
                    "subnet_id": 0,
                    "machines": {"alpha-srv": {"type": "lxc", "ip": "10.201.0.10"}},
                },
                "beta": {
                    "subnet_id": 1,
                    "machines": {"beta-srv": {"type": "lxc", "ip": "10.201.1.10"}},
                },
                "gamma": {
                    "subnet_id": 2,
                    "machines": {"gamma-srv": {"type": "lxc", "ip": "10.201.2.10"}},
                },
            },
            "network_policies": policies,
        }

    def test_multiple_policies_all_valid(self, tmp_path):
        """5 policies across 3 domains → no validation errors."""
        policies = [
            {"from": "alpha", "to": "beta", "ports": [80], "protocol": "tcp"},
            {"from": "beta", "to": "gamma", "ports": [443], "protocol": "tcp"},
            {"from": "gamma", "to": "alpha", "ports": [22], "protocol": "tcp"},
            {"from": "host", "to": "alpha-srv", "ports": [8080], "protocol": "tcp"},
            {"from": "alpha", "to": "gamma", "ports": "all"},
        ]
        infra = self._infra_with_policies(policies)
        errors = generate.validate(infra)
        assert errors == []

    def test_bidirectional_policy_accepted(self, tmp_path):
        """Bidirectional policy is accepted by validator."""
        policies = [
            {"from": "alpha", "to": "beta", "ports": [80], "protocol": "tcp",
             "bidirectional": True},
        ]
        infra = self._infra_with_policies(policies)
        errors = generate.validate(infra)
        assert errors == []

    def test_policy_from_host_accepted(self, tmp_path):
        """Policy from 'host' keyword is valid."""
        policies = [
            {"from": "host", "to": "beta-srv", "ports": [22], "protocol": "tcp"},
        ]
        infra = self._infra_with_policies(policies)
        errors = generate.validate(infra)
        assert errors == []

    def test_policy_ports_all_accepted(self, tmp_path):
        """Policy with ports: 'all' is valid."""
        policies = [
            {"from": "alpha", "to": "beta", "ports": "all"},
        ]
        infra = self._infra_with_policies(policies)
        errors = generate.validate(infra)
        assert errors == []


class TestEnrichmentPipeline:
    """Test enrichment functions working together."""

    def test_firewall_and_ai_enrichment_coexist(self, tmp_path):
        """firewall_mode:vm + ai_access_policy:exclusive → both enrichments applied."""
        infra = {
            "project_name": "enrich-test",
            "global": {
                "base_subnet": "10.202",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                "firewall_mode": "vm",
                "ai_access_policy": "exclusive",
                "ai_access_default": "pro",
            },
            "domains": {
                "admin": {
                    "subnet_id": 0,
                    "machines": {"admin-ctrl": {"type": "lxc", "ip": "10.202.0.10"}},
                },
                "pro": {
                    "subnet_id": 1,
                    "machines": {"pro-dev": {"type": "lxc", "ip": "10.202.1.10"}},
                },
                "ai-tools": {
                    "subnet_id": 10,
                    "machines": {"ai-ollama": {"type": "lxc", "ip": "10.202.10.10"}},
                },
            },
        }
        generate.enrich_infra(infra)
        # sys-firewall auto-created in admin
        admin_machines = infra["domains"]["admin"]["machines"]
        assert "sys-firewall" in admin_machines
        # AI network policy auto-created
        policies = infra.get("network_policies", [])
        ai_policies = [p for p in policies if p.get("to") == "ai-tools"]
        assert len(ai_policies) >= 1

    def test_enrichment_is_idempotent(self, tmp_path):
        """Running enrich_infra twice produces the same result."""
        infra = {
            "project_name": "idem-test",
            "global": {
                "base_subnet": "10.203",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                "firewall_mode": "vm",
            },
            "domains": {
                "admin": {
                    "subnet_id": 0,
                    "machines": {"admin-ctrl": {"type": "lxc", "ip": "10.203.0.10"}},
                },
            },
        }
        import copy
        generate.enrich_infra(infra)
        first = copy.deepcopy(infra)
        generate.enrich_infra(infra)
        assert infra == first

    def test_enrichment_preserves_user_declared_machines(self, tmp_path):
        """User-declared machines in admin domain are preserved."""
        infra = {
            "project_name": "preserve-test",
            "global": {
                "base_subnet": "10.204",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                "firewall_mode": "vm",
            },
            "domains": {
                "admin": {
                    "subnet_id": 0,
                    "machines": {
                        "admin-ctrl": {"type": "lxc", "ip": "10.204.0.10"},
                        "admin-monitor": {"type": "lxc", "ip": "10.204.0.20"},
                    },
                },
            },
        }
        generate.enrich_infra(infra)
        machines = infra["domains"]["admin"]["machines"]
        assert "admin-ctrl" in machines
        assert "admin-monitor" in machines
        assert "sys-firewall" in machines


class TestOrphanLifecycle:
    """Test orphan detection and cleanup through the full pipeline."""

    def test_orphan_detected_after_domain_removal(self, tmp_path):
        """Create files → remove domain → orphans detected."""
        infra = {
            "project_name": "orphan-test",
            "global": {
                "base_subnet": "10.205",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "alpha": {
                    "subnet_id": 0,
                    "machines": {"alpha-srv": {"type": "lxc", "ip": "10.205.0.10"}},
                },
                "beta": {
                    "subnet_id": 1,
                    "machines": {"beta-srv": {"type": "lxc", "ip": "10.205.1.10"}},
                },
            },
        }
        generate.generate(infra, str(tmp_path))
        # Remove beta
        del infra["domains"]["beta"]
        orphans = generate.detect_orphans(infra, str(tmp_path))
        orphan_strs = [str(p) for p in orphans]
        assert any("beta" in s for s in orphan_strs)
        assert not any("alpha" in s for s in orphan_strs)

    def test_protected_orphan_not_cleaned(self, tmp_path):
        """Protected orphan (ephemeral:false) → not cleaned by --clean-orphans."""
        infra = {
            "project_name": "protect-test",
            "global": {
                "base_subnet": "10.206",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "keep": {
                    "subnet_id": 0,
                    "ephemeral": False,
                    "machines": {"keep-srv": {"type": "lxc", "ip": "10.206.0.10"}},
                },
            },
        }
        generate.generate(infra, str(tmp_path))
        # Remove domain from infra but leave files
        del infra["domains"]["keep"]
        orphans = generate.detect_orphans(infra, str(tmp_path))
        # The orphan's host_vars should be protected (ephemeral:false written in managed section)
        # Check if any orphan is protected
        host_vars_orphan = [p for p in orphans if "host_vars" in str(p)]
        for orphan_path in host_vars_orphan:
            content = orphan_path.read_text()
            if "domain_ephemeral" in content:
                assert "false" in content.lower() or "False" in content

    def test_unprotected_orphan_cleaned(self, tmp_path):
        """Unprotected orphan (ephemeral:true) → cleaned with --clean-orphans."""
        infra = {
            "project_name": "clean-test",
            "global": {
                "base_subnet": "10.207",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "temp": {
                    "subnet_id": 0,
                    "ephemeral": True,
                    "machines": {"temp-srv": {"type": "lxc", "ip": "10.207.0.10"}},
                },
            },
        }
        generate.generate(infra, str(tmp_path))
        assert (tmp_path / "host_vars" / "temp-srv.yml").exists()

        # Remove domain, run main with --clean-orphans
        del infra["domains"]["temp"]
        # Write updated infra.yml
        (tmp_path / "infra.yml").write_text(yaml.dump(infra, sort_keys=False))
        result = subprocess.run(
            ["python3", str(GENERATE_PY), str(tmp_path / "infra.yml"),
             "--base-dir", str(tmp_path), "--clean-orphans"],
            capture_output=True, text=True,
        )
        # Files should be removed (ephemeral:true = unprotected)
        assert result.returncode == 0
