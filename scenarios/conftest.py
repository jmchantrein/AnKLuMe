"""Shared fixtures and step definitions for AnKLuMe E2E scenario tests.

Uses pytest-bdd with Gherkin .feature files. Designed to run inside
the Phase 12 sandbox (Incus-in-Incus) or any environment with a live
Incus daemon.

Usage:
    pytest scenarios/ -v --tb=long
    pytest scenarios/best_practices/ -v
    pytest scenarios/bad_practices/ -v
"""

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from pytest_bdd import given, parsers, then, when

logger = logging.getLogger("anklume.scenarios")

PROJECT_DIR = Path(__file__).resolve().parent.parent


# ── Data classes ─────────────────────────────────────────────────


@dataclass
class CommandResult:
    """Result of a command execution."""

    returncode: int
    stdout: str
    stderr: str
    command: str
    duration: float = 0.0


@dataclass
class Sandbox:
    """Manages sandbox state for scenario execution."""

    project_dir: Path
    results: list[CommandResult] = field(default_factory=list)
    instances_created: list[str] = field(default_factory=list)

    @property
    def last_result(self) -> CommandResult:
        if not self.results:
            raise RuntimeError("No command has been executed yet")
        return self.results[-1]

    def run(self, command: str, timeout: int = 300) -> CommandResult:
        """Run a shell command and return the result."""
        start = time.monotonic()
        proc = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=str(self.project_dir),
            timeout=timeout,
        )
        duration = time.monotonic() - start
        result = CommandResult(
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            command=command,
            duration=duration,
        )
        self.results.append(result)
        logger.info(
            "Command: %s (rc=%d, %.1fs)", command, result.returncode, duration
        )
        if result.returncode != 0:
            logger.debug("stdout: %s", result.stdout[:500])
            logger.debug("stderr: %s", result.stderr[:500])
        return result

    def incus(self, *args: str, project: str | None = None) -> CommandResult:
        """Run an incus command."""
        cmd_parts = ["incus"]
        if project:
            cmd_parts += ["--project", project]
        cmd_parts.extend(args)
        return self.run(" ".join(cmd_parts))

    def instance_exists(self, name: str) -> bool:
        """Check if an instance exists in any project."""
        result = self.run(
            "incus list --all-projects --format json 2>/dev/null"
        )
        if result.returncode != 0:
            return False
        try:
            instances = json.loads(result.stdout)
            return any(i.get("name") == name for i in instances)
        except (json.JSONDecodeError, TypeError):
            return False

    def instance_running(self, name: str) -> bool:
        """Check if an instance is running."""
        result = self.run(
            "incus list --all-projects --format json 2>/dev/null"
        )
        if result.returncode != 0:
            return False
        try:
            instances = json.loads(result.stdout)
            return any(
                i.get("name") == name and i.get("status") == "Running"
                for i in instances
            )
        except (json.JSONDecodeError, TypeError):
            return False

    def get_instance_ip(self, name: str, project: str) -> str | None:
        """Get the IPv4 address of an instance."""
        result = self.run(
            f"incus list --project {project} --format json 2>/dev/null"
        )
        if result.returncode != 0:
            return None
        try:
            instances = json.loads(result.stdout)
            for inst in instances:
                if inst.get("name") != name:
                    continue
                for net_name, net in inst.get("state", {}).get("network", {}).items():
                    if net_name == "lo":
                        continue
                    for addr in net.get("addresses", []):
                        if addr.get("family") == "inet":
                            return addr["address"]
        except (json.JSONDecodeError, TypeError, KeyError):
            pass
        return None

    def load_infra(self) -> dict:
        """Load the current infra.yml."""
        infra_path = self.project_dir / "infra.yml"
        with open(infra_path) as f:
            return yaml.safe_load(f)

    def all_declared_instances(self) -> list[tuple[str, str]]:
        """Return (instance_name, domain_name) pairs from infra.yml."""
        infra = self.load_infra()
        pairs = []
        for domain_name, domain in infra.get("domains", {}).items():
            for machine_name in domain.get("machines", {}):
                pairs.append((machine_name, domain_name))
        return pairs

    def cross_domain_pairs(self) -> list[tuple[str, str, str]]:
        """Return (src_instance, dst_instance, dst_ip) for cross-domain tests."""
        infra = self.load_infra()
        instances_by_domain: dict[str, list[tuple[str, str]]] = {}
        for domain_name, domain in infra.get("domains", {}).items():
            for machine_name, machine in domain.get("machines", {}).items():
                ip = machine.get("ip", "")
                instances_by_domain.setdefault(domain_name, []).append(
                    (machine_name, ip)
                )
        pairs = []
        domains = list(instances_by_domain.keys())
        for i, src_domain in enumerate(domains):
            for dst_domain in domains[i + 1 :]:
                src_name = instances_by_domain[src_domain][0][0]
                dst_name, dst_ip = instances_by_domain[dst_domain][0]
                if dst_ip:
                    pairs.append((src_name, dst_name, dst_ip))
        return pairs


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def sandbox():
    """Provide a sandbox instance for scenario steps."""
    return Sandbox(project_dir=PROJECT_DIR)


@pytest.fixture()
def infra_backup(sandbox):
    """Backup infra.yml before test and restore after."""
    infra_path = sandbox.project_dir / "infra.yml"
    backup_path = sandbox.project_dir / "infra.yml.scenario-backup"
    if infra_path.exists():
        backup_path.write_text(infra_path.read_text())
    yield
    if backup_path.exists():
        infra_path.write_text(backup_path.read_text())
        backup_path.unlink()


# ── Given steps ──────────────────────────────────────────────────


@given("a clean sandbox environment")
def clean_sandbox(sandbox):
    """Verify we're in a working AnKLuMe directory."""
    assert (sandbox.project_dir / "scripts" / "generate.py").exists(), (
        "Not in an AnKLuMe project directory"
    )


@given("images are pre-cached via shared repository")
def precache_images(sandbox):
    """Ensure images are available locally (skip if no Incus)."""
    result = sandbox.run("incus info 2>/dev/null")
    if result.returncode != 0:
        pytest.skip("No Incus daemon available")


@given(parsers.parse('infra.yml from "{example}"'))
def load_infra_from_example(sandbox, example):
    """Copy an example infra.yml into place."""
    src = sandbox.project_dir / "examples" / example / "infra.yml"
    if not src.exists():
        src = sandbox.project_dir / "examples" / f"{example}.infra.yml"
    assert src.exists(), f"Example not found: {src}"
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(src.read_text())


@given("infra.yml exists but no inventory files")
def infra_without_inventory(sandbox, infra_backup):
    """Ensure infra.yml exists but inventory/ is empty."""
    infra_path = sandbox.project_dir / "infra.yml"
    if not infra_path.exists():
        example = sandbox.project_dir / "examples" / "student-sysadmin" / "infra.yml"
        if example.exists():
            infra_path.write_text(example.read_text())
    inv_dir = sandbox.project_dir / "inventory"
    if inv_dir.exists():
        for f in inv_dir.glob("*.yml"):
            f.rename(f.with_suffix(".yml.scenario-hidden"))


@given("a running infrastructure")
def running_infra(sandbox):
    """Verify that instances are running."""
    result = sandbox.run("incus list --all-projects --format json 2>/dev/null")
    if result.returncode != 0:
        pytest.skip("No Incus daemon available")
    try:
        instances = json.loads(result.stdout)
        running = [i for i in instances if i.get("status") == "Running"]
        if not running:
            pytest.skip("No running instances found")
    except (json.JSONDecodeError, TypeError):
        pytest.skip("Cannot parse Incus output")


@given(parsers.parse('infra.yml with two machines sharing "{ip}"'))
def infra_with_duplicate_ip(sandbox, ip, tmp_path):
    """Create an infra.yml with duplicate IPs."""
    infra = {
        "project_name": "scenario-test",
        "global": {"base_subnet": "10.100"},
        "domains": {
            "test-a": {
                "subnet_id": 200,
                "machines": {
                    "test-a-one": {"type": "lxc", "ip": ip},
                },
            },
            "test-b": {
                "subnet_id": 201,
                "machines": {
                    "test-b-one": {"type": "lxc", "ip": ip},
                },
            },
        },
    }
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given(parsers.parse('infra.yml with managed section content in "{filename}"'))
def infra_with_managed_content(sandbox, filename):
    """Verify a generated file with managed sections exists."""
    path = sandbox.project_dir / filename
    assert path.exists(), f"File not found: {path}"


# ── When steps ───────────────────────────────────────────────────


@when(parsers.parse('I run "{command}"'))
def run_command(sandbox, command):
    """Execute a command in the project directory."""
    sandbox.run(command, timeout=600)


@when(parsers.parse('I run "{command}" and it may fail'))
def run_command_may_fail(sandbox, command):
    """Execute a command that is expected to potentially fail."""
    sandbox.run(command, timeout=600)


@when(parsers.parse('I add a domain "{domain}" to infra.yml'))
def add_domain_to_infra(sandbox, domain):
    """Add a new domain to the current infra.yml."""
    infra = sandbox.load_infra()
    max_subnet = max(
        d.get("subnet_id", 0) for d in infra.get("domains", {}).values()
    )
    infra.setdefault("domains", {})[domain] = {
        "subnet_id": max_subnet + 1,
        "machines": {
            f"{domain}-test": {
                "type": "lxc",
                "ip": f"10.100.{max_subnet + 1}.10",
            }
        },
    }
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@when(parsers.parse('I edit the managed section in "{filename}"'))
def edit_managed_section(sandbox, filename):
    """Modify content inside a managed section."""
    path = sandbox.project_dir / filename
    content = path.read_text()
    if "=== MANAGED" in content:
        content = content.replace(
            "# === END MANAGED ===",
            "# SCENARIO-INJECTED: this will be overwritten\n# === END MANAGED ===",
        )
        path.write_text(content)


# ── Then steps ───────────────────────────────────────────────────


@then("exit code is 0")
def check_exit_zero(sandbox):
    assert sandbox.last_result.returncode == 0, (
        f"Expected exit 0, got {sandbox.last_result.returncode}\n"
        f"stdout: {sandbox.last_result.stdout[:500]}\n"
        f"stderr: {sandbox.last_result.stderr[:500]}"
    )


@then("exit code is non-zero")
def check_exit_nonzero(sandbox):
    assert sandbox.last_result.returncode != 0, (
        f"Expected non-zero exit, got 0\n"
        f"stdout: {sandbox.last_result.stdout[:500]}"
    )


@then(parsers.parse('output contains "{text}"'))
def check_output_contains(sandbox, text):
    combined = sandbox.last_result.stdout + sandbox.last_result.stderr
    assert text in combined, (
        f"Expected '{text}' in output, not found.\n"
        f"stdout: {sandbox.last_result.stdout[:500]}\n"
        f"stderr: {sandbox.last_result.stderr[:500]}"
    )


@then(parsers.parse('stderr contains "{text}"'))
def check_stderr_contains(sandbox, text):
    assert text in sandbox.last_result.stderr, (
        f"Expected '{text}' in stderr, not found.\n"
        f"stderr: {sandbox.last_result.stderr[:500]}"
    )


@then("inventory files exist for all domains")
def check_inventory_files(sandbox):
    infra = sandbox.load_infra()
    for domain in infra.get("domains", {}):
        inv = sandbox.project_dir / "inventory" / f"{domain}.yml"
        assert inv.exists(), f"Missing inventory file: {inv}"


@then(parsers.parse('file "{path}" exists'))
def check_file_exists(sandbox, path):
    full = sandbox.project_dir / path
    assert full.exists(), f"File not found: {full}"


@then(parsers.parse('file "{path}" does not exist'))
def check_file_not_exists(sandbox, path):
    full = sandbox.project_dir / path
    assert not full.exists(), f"File should not exist: {full}"


@then("all declared instances are running")
def check_all_running(sandbox):
    for name, _domain in sandbox.all_declared_instances():
        assert sandbox.instance_running(name), f"Instance {name} is not running"


@then(parsers.parse('instance "{name}" is running in project "{project}"'))
def check_instance_running(sandbox, name, project):
    result = sandbox.run(
        f"incus list --project {project} --format json 2>/dev/null"
    )
    assert result.returncode == 0
    instances = json.loads(result.stdout)
    running = [i for i in instances if i["name"] == name and i["status"] == "Running"]
    assert running, f"Instance {name} not running in project {project}"


@then("intra-domain connectivity works")
def check_intra_domain(sandbox):
    infra = sandbox.load_infra()
    for domain_name, domain in infra.get("domains", {}).items():
        machines = list(domain.get("machines", {}).items())
        if len(machines) < 2:
            continue
        src_name = machines[0][0]
        dst_ip = machines[1][1].get("ip", "")
        if dst_ip:
            result = sandbox.run(
                f"incus exec {src_name} --project {domain_name} -- "
                f"ping -c1 -W2 {dst_ip} 2>/dev/null"
            )
            assert result.returncode == 0, (
                f"Intra-domain ping failed: {src_name} -> {dst_ip}"
            )


@then("inter-domain connectivity is blocked")
def check_inter_domain_blocked(sandbox):
    for src, dst, dst_ip in sandbox.cross_domain_pairs():
        result = sandbox.run(
            f"incus exec {src} -- ping -c1 -W2 {dst_ip} 2>/dev/null"
        )
        assert result.returncode != 0, (
            f"Inter-domain ping should fail: {src} -> {dst} ({dst_ip})"
        )


@then("no Incus resources were created")
def check_no_resources(sandbox):
    """Verify no new Incus projects/instances were created by the failed command."""
    # This is a best-effort check — verifies no scenario-test projects exist
    result = sandbox.run("incus project list --format json 2>/dev/null")
    if result.returncode == 0:
        try:
            projects = json.loads(result.stdout)
            scenario_projects = [
                p for p in projects if "scenario" in p.get("name", "")
            ]
            assert not scenario_projects, (
                f"Unexpected projects created: {scenario_projects}"
            )
        except (json.JSONDecodeError, TypeError):
            pass


@then(parsers.parse('the managed section in "{filename}" is unchanged'))
def check_managed_unchanged(sandbox, filename):
    """Verify managed section does not contain injected content."""
    path = sandbox.project_dir / filename
    content = path.read_text()
    assert "SCENARIO-INJECTED" not in content, (
        "Managed section still contains injected content after sync"
    )
