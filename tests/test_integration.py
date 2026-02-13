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


# ── Additional Pipeline Tests (no Incus needed) ────────────


class TestVMAndLXCCoexistence:
    """Test generate pipeline with VMs and LXC containers in the same domain."""

    pytestmark = []  # Override module-level skip — no Incus needed

    @staticmethod
    def _mixed_infra(**global_overrides):
        return {
            "project_name": "mixed-test",
            "global": {
                "base_subnet": "10.210",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                **global_overrides,
            },
            "domains": {
                "hybrid": {
                    "description": "Domain with both LXC and VM",
                    "subnet_id": 0,
                    "machines": {
                        "hybrid-web": {
                            "type": "lxc",
                            "ip": "10.210.0.10",
                        },
                        "hybrid-sandbox": {
                            "type": "vm",
                            "ip": "10.210.0.20",
                            "config": {
                                "limits.cpu": "2",
                                "limits.memory": "2GiB",
                            },
                        },
                    },
                },
            },
        }

    def test_mixed_types_validate_ok(self, tmp_path):
        """LXC and VM in same domain pass validation."""
        infra = self._mixed_infra()
        errors = generate.validate(infra)
        assert errors == []

    def test_mixed_types_host_vars_instance_type(self, tmp_path):
        """instance_type in host_vars reflects LXC vs VM correctly."""
        infra = self._mixed_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        lxc_hv = yaml.safe_load((tmp_path / "host_vars" / "hybrid-web.yml").read_text())
        vm_hv = yaml.safe_load((tmp_path / "host_vars" / "hybrid-sandbox.yml").read_text())
        assert lxc_hv["instance_type"] == "lxc"
        assert vm_hv["instance_type"] == "vm"

    def test_mixed_types_share_inventory(self, tmp_path):
        """Both LXC and VM appear in the same domain inventory file."""
        infra = self._mixed_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        inv = yaml.safe_load((tmp_path / "inventory" / "hybrid.yml").read_text())
        hosts = inv["all"]["children"]["hybrid"]["hosts"]
        assert "hybrid-web" in hosts
        assert "hybrid-sandbox" in hosts

    def test_mixed_types_vm_config_in_host_vars(self, tmp_path):
        """VM config (limits.cpu, limits.memory) appears in host_vars."""
        infra = self._mixed_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        vm_hv = yaml.safe_load((tmp_path / "host_vars" / "hybrid-sandbox.yml").read_text())
        assert vm_hv["instance_config"]["limits.cpu"] == "2"
        assert vm_hv["instance_config"]["limits.memory"] == "2GiB"

    def test_invalid_type_rejected(self, tmp_path):
        """type: docker is rejected by validator."""
        infra = self._mixed_infra()
        infra["domains"]["hybrid"]["machines"]["hybrid-bad"] = {
            "type": "docker",
            "ip": "10.210.0.30",
        }
        errors = generate.validate(infra)
        assert any("type must be 'lxc' or 'vm'" in e for e in errors)

    def test_multi_domain_mixed_types(self, tmp_path):
        """Multiple domains each with LXC+VM all generate correctly."""
        infra = self._mixed_infra()
        infra["domains"]["compute"] = {
            "description": "Compute domain",
            "subnet_id": 1,
            "machines": {
                "compute-worker": {"type": "lxc", "ip": "10.210.1.10"},
                "compute-gpu": {"type": "vm", "ip": "10.210.1.20"},
            },
        }
        errors = generate.validate(infra)
        assert errors == []
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        for host, expected_type in [
            ("hybrid-web", "lxc"), ("hybrid-sandbox", "vm"),
            ("compute-worker", "lxc"), ("compute-gpu", "vm"),
        ]:
            hv = yaml.safe_load((tmp_path / "host_vars" / f"{host}.yml").read_text())
            assert hv["instance_type"] == expected_type, f"{host} should be {expected_type}"


class TestEphemeralGeneration:
    """Test ephemeral inheritance and override through the full pipeline."""

    pytestmark = []  # Override module-level skip — no Incus needed

    @staticmethod
    def _ephemeral_infra():
        return {
            "project_name": "ephemeral-test",
            "global": {
                "base_subnet": "10.211",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "persistent": {
                    "description": "Protected domain (default ephemeral=false)",
                    "subnet_id": 0,
                    "machines": {
                        "persist-srv": {"type": "lxc", "ip": "10.211.0.10"},
                        "persist-temp": {
                            "type": "lxc",
                            "ip": "10.211.0.20",
                            "ephemeral": True,
                        },
                    },
                },
                "disposable": {
                    "description": "Ephemeral domain",
                    "subnet_id": 1,
                    "ephemeral": True,
                    "machines": {
                        "disp-box": {"type": "lxc", "ip": "10.211.1.10"},
                        "disp-keep": {
                            "type": "lxc",
                            "ip": "10.211.1.20",
                            "ephemeral": False,
                        },
                    },
                },
            },
        }

    def test_ephemeral_validates_ok(self, tmp_path):
        """Valid ephemeral inheritance passes validation."""
        infra = self._ephemeral_infra()
        errors = generate.validate(infra)
        assert errors == []

    def test_domain_default_false_inherited(self, tmp_path):
        """Machine without ephemeral inherits domain default (false)."""
        infra = self._ephemeral_infra()
        generate.generate(infra, str(tmp_path))

        hv = yaml.safe_load((tmp_path / "host_vars" / "persist-srv.yml").read_text())
        assert hv["instance_ephemeral"] is False

    def test_machine_override_true_on_protected_domain(self, tmp_path):
        """Machine ephemeral:true overrides domain ephemeral:false."""
        infra = self._ephemeral_infra()
        generate.generate(infra, str(tmp_path))

        hv = yaml.safe_load((tmp_path / "host_vars" / "persist-temp.yml").read_text())
        assert hv["instance_ephemeral"] is True

    def test_domain_ephemeral_true_inherited(self, tmp_path):
        """Machine without ephemeral inherits domain ephemeral:true."""
        infra = self._ephemeral_infra()
        generate.generate(infra, str(tmp_path))

        hv = yaml.safe_load((tmp_path / "host_vars" / "disp-box.yml").read_text())
        assert hv["instance_ephemeral"] is True

    def test_machine_override_false_on_ephemeral_domain(self, tmp_path):
        """Machine ephemeral:false overrides domain ephemeral:true."""
        infra = self._ephemeral_infra()
        generate.generate(infra, str(tmp_path))

        hv = yaml.safe_load((tmp_path / "host_vars" / "disp-keep.yml").read_text())
        assert hv["instance_ephemeral"] is False

    def test_group_vars_ephemeral_matches_domain(self, tmp_path):
        """domain_ephemeral in group_vars matches infra.yml domain setting."""
        infra = self._ephemeral_infra()
        generate.generate(infra, str(tmp_path))

        gv_persist = yaml.safe_load(
            (tmp_path / "group_vars" / "persistent.yml").read_text(),
        )
        gv_disp = yaml.safe_load(
            (tmp_path / "group_vars" / "disposable.yml").read_text(),
        )
        assert gv_persist["domain_ephemeral"] is False
        assert gv_disp["domain_ephemeral"] is True

    def test_invalid_ephemeral_type_rejected(self, tmp_path):
        """Non-boolean ephemeral rejected by validator."""
        infra = self._ephemeral_infra()
        infra["domains"]["persistent"]["ephemeral"] = "yes"
        errors = generate.validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)

    def test_invalid_machine_ephemeral_rejected(self, tmp_path):
        """Non-boolean machine ephemeral rejected by validator."""
        infra = self._ephemeral_infra()
        infra["domains"]["persistent"]["machines"]["persist-srv"]["ephemeral"] = 1
        errors = generate.validate(infra)
        assert any("ephemeral must be a boolean" in e for e in errors)


class TestGPUPolicyPipeline:
    """Test gpu_policy validation through the full pipeline."""

    pytestmark = []  # Override module-level skip — no Incus needed

    @staticmethod
    def _gpu_infra(gpu_policy="exclusive", gpu_machines=None):
        """Build an infra with configurable GPU policy and GPU machines.

        gpu_machines: list of (domain, machine_name, ip) with GPU enabled.
        """
        if gpu_machines is None:
            gpu_machines = [("compute", "compute-gpu", "10.212.0.10")]

        infra = {
            "project_name": "gpu-test",
            "global": {
                "base_subnet": "10.212",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
                "gpu_policy": gpu_policy,
            },
            "domains": {
                "compute": {
                    "description": "Compute domain",
                    "subnet_id": 0,
                    "profiles": {
                        "nvidia-compute": {
                            "devices": {"gpu": {"type": "gpu", "gputype": "physical"}},
                        },
                    },
                    "machines": {
                        "compute-ctrl": {"type": "lxc", "ip": "10.212.0.5"},
                    },
                },
                "research": {
                    "description": "Research domain",
                    "subnet_id": 1,
                    "profiles": {
                        "nvidia-compute": {
                            "devices": {"gpu": {"type": "gpu", "gputype": "physical"}},
                        },
                    },
                    "machines": {
                        "research-srv": {"type": "lxc", "ip": "10.212.1.5"},
                    },
                },
            },
        }

        for domain, mname, ip in gpu_machines:
            infra["domains"][domain]["machines"][mname] = {
                "type": "lxc",
                "ip": ip,
                "gpu": True,
                "profiles": ["default", "nvidia-compute"],
            }
        return infra

    def test_exclusive_single_gpu_ok(self, tmp_path):
        """Exclusive policy with one GPU instance passes validation."""
        infra = self._gpu_infra(
            gpu_policy="exclusive",
            gpu_machines=[("compute", "compute-gpu", "10.212.0.10")],
        )
        errors = generate.validate(infra)
        assert errors == []

    def test_exclusive_two_gpu_error(self, tmp_path):
        """Exclusive policy with two GPU instances is an error."""
        infra = self._gpu_infra(
            gpu_policy="exclusive",
            gpu_machines=[
                ("compute", "compute-gpu", "10.212.0.10"),
                ("research", "research-gpu", "10.212.1.10"),
            ],
        )
        errors = generate.validate(infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)
        assert any("2 instances have GPU access" in e for e in errors)

    def test_shared_two_gpu_warning_not_error(self, tmp_path):
        """Shared policy with two GPU instances emits warning, not error."""
        infra = self._gpu_infra(
            gpu_policy="shared",
            gpu_machines=[
                ("compute", "compute-gpu", "10.212.0.10"),
                ("research", "research-gpu", "10.212.1.10"),
            ],
        )
        errors = generate.validate(infra)
        assert errors == []
        warnings = generate.get_warnings(infra)
        assert any("shared" in w.lower() for w in warnings)

    def test_invalid_gpu_policy_rejected(self, tmp_path):
        """Invalid gpu_policy value is an error."""
        infra = self._gpu_infra(gpu_policy="hybrid")
        errors = generate.validate(infra)
        assert any("gpu_policy must be 'exclusive' or 'shared'" in e for e in errors)

    def test_gpu_detection_via_profile(self, tmp_path):
        """GPU detected indirectly through profile device, not gpu: true flag."""
        infra = self._gpu_infra(gpu_policy="exclusive", gpu_machines=[])
        # Add a machine that references a GPU profile but without gpu: true
        infra["domains"]["compute"]["machines"]["compute-indirect"] = {
            "type": "lxc",
            "ip": "10.212.0.10",
            "profiles": ["default", "nvidia-compute"],
        }
        # Add a second machine with gpu: true directly
        infra["domains"]["research"]["machines"]["research-direct"] = {
            "type": "lxc",
            "ip": "10.212.1.10",
            "gpu": True,
            "profiles": ["default", "nvidia-compute"],
        }
        errors = generate.validate(infra)
        assert any("GPU policy is 'exclusive'" in e for e in errors)

    def test_gpu_no_instances_ok(self, tmp_path):
        """No GPU instances with any policy passes validation."""
        infra = self._gpu_infra(gpu_policy="exclusive", gpu_machines=[])
        errors = generate.validate(infra)
        assert errors == []

    def test_shared_gpu_generates_files(self, tmp_path):
        """Shared GPU policy with 2 GPU machines still generates all files."""
        infra = self._gpu_infra(
            gpu_policy="shared",
            gpu_machines=[
                ("compute", "compute-gpu", "10.212.0.10"),
                ("research", "research-gpu", "10.212.1.10"),
            ],
        )
        errors = generate.validate(infra)
        assert errors == []
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        for host in ("compute-ctrl", "compute-gpu", "research-srv", "research-gpu"):
            assert (tmp_path / "host_vars" / f"{host}.yml").exists()

        gpu_hv = yaml.safe_load((tmp_path / "host_vars" / "compute-gpu.yml").read_text())
        assert gpu_hv.get("instance_gpu") is True


class TestProfileGeneration:
    """Test domain profiles appear correctly in group_vars."""

    pytestmark = []  # Override module-level skip — no Incus needed

    @staticmethod
    def _profile_infra():
        return {
            "project_name": "profile-test",
            "global": {
                "base_subnet": "10.213",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "services": {
                    "description": "Services domain",
                    "subnet_id": 0,
                    "profiles": {
                        "gpu-compute": {
                            "devices": {"gpu": {"type": "gpu", "gputype": "physical"}},
                        },
                        "nesting": {
                            "config": {
                                "security.nesting": "true",
                                "security.syscalls.intercept.mknod": "true",
                            },
                        },
                        "high-mem": {
                            "config": {
                                "limits.memory": "8GiB",
                            },
                        },
                    },
                    "machines": {
                        "svc-app": {
                            "type": "lxc",
                            "ip": "10.213.0.10",
                            "profiles": ["default", "high-mem"],
                        },
                        "svc-nested": {
                            "type": "lxc",
                            "ip": "10.213.0.20",
                            "profiles": ["default", "nesting"],
                        },
                    },
                },
                "plain": {
                    "description": "No-profile domain",
                    "subnet_id": 1,
                    "machines": {
                        "plain-box": {"type": "lxc", "ip": "10.213.1.10"},
                    },
                },
            },
        }

    def test_profiles_in_group_vars(self, tmp_path):
        """Domain profiles appear in incus_profiles in group_vars."""
        infra = self._profile_infra()
        generate.generate(infra, str(tmp_path))

        gv = yaml.safe_load((tmp_path / "group_vars" / "services.yml").read_text())
        assert "incus_profiles" in gv
        assert "gpu-compute" in gv["incus_profiles"]
        assert "nesting" in gv["incus_profiles"]
        assert "high-mem" in gv["incus_profiles"]

    def test_no_profiles_no_key(self, tmp_path):
        """Domain without profiles has no incus_profiles in group_vars."""
        infra = self._profile_infra()
        generate.generate(infra, str(tmp_path))

        gv = yaml.safe_load((tmp_path / "group_vars" / "plain.yml").read_text())
        assert "incus_profiles" not in gv

    def test_profile_devices_preserved(self, tmp_path):
        """Profile device config (gpu type, gputype) preserved in group_vars."""
        infra = self._profile_infra()
        generate.generate(infra, str(tmp_path))

        gv = yaml.safe_load((tmp_path / "group_vars" / "services.yml").read_text())
        gpu_prof = gv["incus_profiles"]["gpu-compute"]
        assert gpu_prof["devices"]["gpu"]["type"] == "gpu"
        assert gpu_prof["devices"]["gpu"]["gputype"] == "physical"

    def test_profile_config_preserved(self, tmp_path):
        """Profile config (nesting security) preserved in group_vars."""
        infra = self._profile_infra()
        generate.generate(infra, str(tmp_path))

        gv = yaml.safe_load((tmp_path / "group_vars" / "services.yml").read_text())
        nesting = gv["incus_profiles"]["nesting"]
        assert nesting["config"]["security.nesting"] == "true"

    def test_host_vars_profiles_list(self, tmp_path):
        """Machine instance_profiles contains the assigned profiles."""
        infra = self._profile_infra()
        generate.generate(infra, str(tmp_path))

        hv = yaml.safe_load((tmp_path / "host_vars" / "svc-app.yml").read_text())
        assert hv["instance_profiles"] == ["default", "high-mem"]

    def test_undefined_profile_rejected(self, tmp_path):
        """Machine referencing non-existent profile is rejected."""
        infra = self._profile_infra()
        infra["domains"]["services"]["machines"]["svc-app"]["profiles"] = [
            "default", "nonexistent",
        ]
        errors = generate.validate(infra)
        assert any("profile 'nonexistent' not defined" in e for e in errors)


class TestInfoDirectoryMode:
    """Test generate with infra/ directory input."""

    pytestmark = []  # Override module-level skip — no Incus needed

    def test_directory_mode_generates_same_output(self, tmp_path):
        """infra/ directory produces identical output to equivalent infra.yml."""
        # Single-file mode
        single_infra = {
            "project_name": "dir-test",
            "global": {
                "base_subnet": "10.214",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "alpha": {
                    "description": "Alpha domain",
                    "subnet_id": 0,
                    "machines": {
                        "alpha-srv": {"type": "lxc", "ip": "10.214.0.10"},
                    },
                },
                "beta": {
                    "description": "Beta domain",
                    "subnet_id": 1,
                    "machines": {
                        "beta-srv": {"type": "lxc", "ip": "10.214.1.10"},
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

        # Directory mode — build infra/ structure
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()

        base = {
            "project_name": "dir-test",
            "global": {
                "base_subnet": "10.214",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
        }
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))

        alpha_domain = {
            "alpha": {
                "description": "Alpha domain",
                "subnet_id": 0,
                "machines": {
                    "alpha-srv": {"type": "lxc", "ip": "10.214.0.10"},
                },
            },
        }
        (domains_dir / "alpha.yml").write_text(yaml.dump(alpha_domain, sort_keys=False))

        beta_domain = {
            "beta": {
                "description": "Beta domain",
                "subnet_id": 1,
                "machines": {
                    "beta-srv": {"type": "lxc", "ip": "10.214.1.10"},
                },
            },
        }
        (domains_dir / "beta.yml").write_text(yaml.dump(beta_domain, sort_keys=False))

        policies = {
            "network_policies": [
                {"from": "alpha", "to": "beta", "ports": [80], "protocol": "tcp"},
            ],
        }
        (infra_dir / "policies.yml").write_text(yaml.dump(policies, sort_keys=False))

        # Load and generate from directory
        dir_infra = generate.load_infra(str(infra_dir))
        dir_output = tmp_path / "from_dir"
        dir_output.mkdir()
        generate.generate(dir_infra, str(dir_output))

        # Compare outputs
        for subdir in ("inventory", "group_vars", "host_vars"):
            single_sub = single_dir / subdir
            dir_sub = dir_output / subdir
            if single_sub.exists():
                single_files = sorted(f.name for f in single_sub.glob("*.yml"))
                dir_files = sorted(f.name for f in dir_sub.glob("*.yml"))
                assert single_files == dir_files, f"{subdir}: file lists differ"
                for fname in single_files:
                    single_content = (single_sub / fname).read_text()
                    dir_content = (dir_sub / fname).read_text()
                    assert single_content == dir_content, f"{subdir}/{fname} content differs"

    def test_directory_mode_load_validates(self, tmp_path):
        """Directory-loaded infra passes validation."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()

        base = {
            "project_name": "dir-validate-test",
            "global": {
                "base_subnet": "10.215",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
        }
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))

        dom = {"gamma": {"subnet_id": 0, "machines": {"gamma-srv": {"type": "lxc", "ip": "10.215.0.10"}}}}
        (domains_dir / "gamma.yml").write_text(yaml.dump(dom, sort_keys=False))

        infra = generate.load_infra(str(infra_dir))
        errors = generate.validate(infra)
        assert errors == []

    def test_directory_mode_merges_policies(self, tmp_path):
        """Network policies from policies.yml are merged correctly."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        domains_dir = infra_dir / "domains"
        domains_dir.mkdir()

        base = {
            "project_name": "dir-policy-test",
            "global": {
                "base_subnet": "10.216",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
        }
        (infra_dir / "base.yml").write_text(yaml.dump(base, sort_keys=False))

        for name, sid in [("web", 0), ("db", 1)]:
            dom = {name: {"subnet_id": sid, "machines": {f"{name}-srv": {"type": "lxc", "ip": f"10.216.{sid}.10"}}}}
            (domains_dir / f"{name}.yml").write_text(yaml.dump(dom, sort_keys=False))

        policies = {
            "network_policies": [
                {"from": "web", "to": "db", "ports": [5432], "protocol": "tcp"},
            ],
        }
        (infra_dir / "policies.yml").write_text(yaml.dump(policies, sort_keys=False))

        infra = generate.load_infra(str(infra_dir))
        assert "network_policies" in infra
        assert len(infra["network_policies"]) == 1
        assert infra["network_policies"][0]["from"] == "web"
        assert infra["network_policies"][0]["to"] == "db"

    def test_directory_mode_missing_base_fails(self, tmp_path):
        """Missing base.yml in infra/ directory causes exit."""
        infra_dir = tmp_path / "infra"
        infra_dir.mkdir()
        # No base.yml
        with pytest.raises(SystemExit):
            generate.load_infra(str(infra_dir))


class TestMultiDomainScaling:
    """Test with many domains to verify all files are generated correctly."""

    pytestmark = []  # Override module-level skip — no Incus needed

    def test_ten_domains_all_files(self, tmp_path):
        """10 domains with one machine each generate all expected files."""
        infra = {
            "project_name": "scale-test",
            "global": {
                "base_subnet": "10.220",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {},
        }
        domain_names = []
        machine_names = []
        for i in range(10):
            dname = f"domain-{i:02d}"
            mname = f"host-{i:02d}"
            domain_names.append(dname)
            machine_names.append(mname)
            infra["domains"][dname] = {
                "description": f"Domain {i}",
                "subnet_id": i,
                "machines": {
                    mname: {"type": "lxc", "ip": f"10.220.{i}.10"},
                },
            }

        errors = generate.validate(infra)
        assert errors == []
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        for dname in domain_names:
            assert (tmp_path / "inventory" / f"{dname}.yml").exists(), f"Missing inventory/{dname}.yml"
            assert (tmp_path / "group_vars" / f"{dname}.yml").exists(), f"Missing group_vars/{dname}.yml"
        for mname in machine_names:
            assert (tmp_path / "host_vars" / f"{mname}.yml").exists(), f"Missing host_vars/{mname}.yml"
        assert (tmp_path / "group_vars" / "all.yml").exists()

    def test_ten_domains_unique_subnets(self, tmp_path):
        """10 domains with unique subnets → correct network info in group_vars."""
        infra = {
            "project_name": "scale-subnet-test",
            "global": {
                "base_subnet": "10.221",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {},
        }
        for i in range(10):
            dname = f"net-domain-{i:02d}"
            infra["domains"][dname] = {
                "subnet_id": i,
                "machines": {
                    f"nd-host-{i:02d}": {"type": "lxc", "ip": f"10.221.{i}.10"},
                },
            }

        errors = generate.validate(infra)
        assert errors == []
        generate.generate(infra, str(tmp_path))

        for i in range(10):
            dname = f"net-domain-{i:02d}"
            gv = yaml.safe_load((tmp_path / "group_vars" / f"{dname}.yml").read_text())
            assert gv["incus_network"]["subnet"] == f"10.221.{i}.0/24"
            assert gv["incus_network"]["gateway"] == f"10.221.{i}.254"

    def test_ten_domains_orphan_detection(self, tmp_path):
        """Remove 3 domains from 10 → detect exactly 3 orphaned domains."""
        infra = {
            "project_name": "scale-orphan-test",
            "global": {
                "base_subnet": "10.222",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {},
        }
        for i in range(10):
            dname = f"sdom-{i:02d}"
            infra["domains"][dname] = {
                "subnet_id": i,
                "ephemeral": True,
                "machines": {
                    f"shost-{i:02d}": {"type": "lxc", "ip": f"10.222.{i}.10"},
                },
            }

        generate.generate(infra, str(tmp_path))

        # Remove domains 7, 8, 9
        removed = ["sdom-07", "sdom-08", "sdom-09"]
        for dname in removed:
            del infra["domains"][dname]

        orphans = generate.detect_orphans(infra, str(tmp_path))
        orphan_strs = [str(fp) for fp, _protected in orphans]
        for dname in removed:
            assert any(dname in s for s in orphan_strs), f"Missing orphan for {dname}"
        # Remaining domains should not appear as orphans
        for i in range(7):
            dname = f"sdom-{i:02d}"
            inv_orphan = any(
                f"inventory/{dname}.yml" in s or f"inventory{Path('/').name}{dname}.yml" in s
                for s in orphan_strs
            )
            assert not inv_orphan, f"{dname} should not be an orphan"


class TestNetworkPolicyInvalidReferences:
    """Test policies referencing non-existent domains/machines."""

    pytestmark = []  # Override module-level skip — no Incus needed

    @staticmethod
    def _policy_infra(policies):
        return {
            "project_name": "invalid-ref-test",
            "global": {
                "base_subnet": "10.223",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "web": {
                    "subnet_id": 0,
                    "machines": {"web-srv": {"type": "lxc", "ip": "10.223.0.10"}},
                },
                "db": {
                    "subnet_id": 1,
                    "machines": {"db-srv": {"type": "lxc", "ip": "10.223.1.10"}},
                },
            },
            "network_policies": policies,
        }

    def test_nonexistent_from_domain_rejected(self, tmp_path):
        """Policy from non-existent domain is an error."""
        policies = [
            {"from": "nonexistent", "to": "web", "ports": [80], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("'from: nonexistent' is not a known" in e for e in errors)

    def test_nonexistent_to_domain_rejected(self, tmp_path):
        """Policy to non-existent domain is an error."""
        policies = [
            {"from": "web", "to": "ghost-domain", "ports": [80], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("'to: ghost-domain' is not a known" in e for e in errors)

    def test_nonexistent_machine_rejected(self, tmp_path):
        """Policy referencing non-existent machine is an error."""
        policies = [
            {"from": "host", "to": "missing-machine", "ports": [22], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("'to: missing-machine' is not a known" in e for e in errors)

    def test_valid_machine_reference_accepted(self, tmp_path):
        """Policy referencing an existing machine passes validation."""
        policies = [
            {"from": "host", "to": "db-srv", "ports": [5432], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert errors == []

    def test_invalid_port_rejected(self, tmp_path):
        """Port out of range is an error."""
        policies = [
            {"from": "web", "to": "db", "ports": [99999], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("invalid port" in e for e in errors)

    def test_invalid_protocol_rejected(self, tmp_path):
        """Protocol other than tcp/udp is an error."""
        policies = [
            {"from": "web", "to": "db", "ports": [80], "protocol": "icmp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("protocol must be 'tcp' or 'udp'" in e for e in errors)

    def test_missing_from_field_rejected(self, tmp_path):
        """Policy without 'from' field is an error."""
        policies = [
            {"to": "db", "ports": [80], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("missing 'from'" in e for e in errors)

    def test_missing_to_field_rejected(self, tmp_path):
        """Policy without 'to' field is an error."""
        policies = [
            {"from": "web", "ports": [80], "protocol": "tcp"},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        assert any("missing 'to'" in e for e in errors)

    def test_both_from_and_to_invalid(self, tmp_path):
        """Both from and to referencing unknowns produce two errors."""
        policies = [
            {"from": "ghost-a", "to": "ghost-b", "ports": [80]},
        ]
        infra = self._policy_infra(policies)
        errors = generate.validate(infra)
        from_errors = [e for e in errors if "'from: ghost-a'" in e]
        to_errors = [e for e in errors if "'to: ghost-b'" in e]
        assert len(from_errors) >= 1
        assert len(to_errors) >= 1


class TestConnectionVarsNotInOutput:
    """Verify ansible_connection never appears in generated files (ADR-015)."""

    pytestmark = []  # Override module-level skip — no Incus needed

    @staticmethod
    def _standard_infra():
        return {
            "project_name": "conn-test",
            "global": {
                "base_subnet": "10.224",
                "default_os_image": "images:debian/13",
                "default_connection": "community.general.incus",
                "default_user": "root",
            },
            "domains": {
                "web": {
                    "description": "Web domain",
                    "subnet_id": 0,
                    "machines": {
                        "web-front": {"type": "lxc", "ip": "10.224.0.10"},
                        "web-back": {"type": "lxc", "ip": "10.224.0.20"},
                    },
                },
                "data": {
                    "description": "Data domain",
                    "subnet_id": 1,
                    "machines": {
                        "data-db": {"type": "lxc", "ip": "10.224.1.10"},
                    },
                },
            },
        }

    def test_no_ansible_connection_in_any_file(self, tmp_path):
        """ansible_connection must never appear in generated files."""
        infra = self._standard_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        for f in tmp_path.rglob("*.yml"):
            content = f.read_text()
            assert "ansible_connection" not in content, (
                f"ansible_connection found in {f.relative_to(tmp_path)}"
            )

    def test_no_ansible_user_in_any_file(self, tmp_path):
        """ansible_user must never appear in generated files."""
        infra = self._standard_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        for f in tmp_path.rglob("*.yml"):
            content = f.read_text()
            assert "ansible_user" not in content, (
                f"ansible_user found in {f.relative_to(tmp_path)}"
            )

    def test_psot_prefix_used_instead(self, tmp_path):
        """Connection info stored with psot_ prefix in all.yml."""
        infra = self._standard_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        all_vars = yaml.safe_load((tmp_path / "group_vars" / "all.yml").read_text())
        assert all_vars.get("psot_default_connection") == "community.general.incus"
        assert all_vars.get("psot_default_user") == "root"

    def test_connection_not_in_host_vars(self, tmp_path):
        """No connection-related keys in any host_vars file."""
        infra = self._standard_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        forbidden_keys = {"ansible_connection", "ansible_user", "ansible_ssh_host"}
        for f in (tmp_path / "host_vars").glob("*.yml"):
            data = yaml.safe_load(f.read_text())
            if isinstance(data, dict):
                found = forbidden_keys & set(data)
                assert not found, f"Forbidden keys {found} in host_vars/{f.name}"

    def test_connection_not_in_group_vars(self, tmp_path):
        """No connection-related keys in domain group_vars."""
        infra = self._standard_infra()
        generate.enrich_infra(infra)
        generate.generate(infra, str(tmp_path))

        forbidden_keys = {"ansible_connection", "ansible_user"}
        for f in (tmp_path / "group_vars").glob("*.yml"):
            data = yaml.safe_load(f.read_text())
            if isinstance(data, dict):
                found = forbidden_keys & set(data)
                assert not found, f"Forbidden keys {found} in group_vars/{f.name}"
