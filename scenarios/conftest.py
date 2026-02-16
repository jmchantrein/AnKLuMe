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
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import yaml
from pytest_bdd import given, parsers, then, when

logger = logging.getLogger("anklume.scenarios")

PROJECT_DIR = Path(__file__).resolve().parent.parent

# Skip host subnet conflict detection — examples use 10.100 which may
# conflict with host interfaces.  The env var is checked by generate.py.
os.environ["ANKLUME_SKIP_HOST_SUBNET_CHECK"] = "1"

# Skip network safety checks — scenario tests may run in sandboxes without
# internet connectivity.  The env var is checked by the Makefile.
os.environ["ANKLUME_SKIP_NETWORK_CHECK"] = "1"

# Persistent backup directory — survives crashes so next run can restore.
SESSION_BACKUP_DIR = PROJECT_DIR / ".scenario-session-backup"

# Directories and files that scenarios may modify.
PROTECTED_FILES = ["infra.yml"]
PROTECTED_DIRS = ["inventory", "group_vars", "host_vars"]


def _backup_state(src_root: Path, dest_root: Path) -> None:
    """Copy protected files and dirs from src_root to dest_root."""
    dest_root.mkdir(parents=True, exist_ok=True)
    for name in PROTECTED_FILES:
        src = src_root / name
        if src.exists():
            shutil.copy2(src, dest_root / name)
    for name in PROTECTED_DIRS:
        src = src_root / name
        dest = dest_root / name
        if src.exists():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)


def _restore_state(backup_root: Path, dest_root: Path) -> None:
    """Restore protected files and dirs from backup_root into dest_root."""
    for name in PROTECTED_FILES:
        backup = backup_root / name
        dest = dest_root / name
        if backup.exists():
            shutil.copy2(backup, dest)
        elif dest.exists():
            dest.unlink()
    for name in PROTECTED_DIRS:
        backup = backup_root / name
        dest = dest_root / name
        if backup.exists():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(backup, dest)
        elif dest.exists():
            shutil.rmtree(dest)


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

    def has_incus(self) -> bool:
        """Check if Incus daemon is available."""
        result = self.run("incus info 2>/dev/null")
        return result.returncode == 0


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def _session_backup():
    """Session-level crash-safe backup of project state.

    On session start: if a leftover backup exists (previous crash), restore it.
    Then create a fresh backup. On session end: restore from backup.
    """
    # Crash recovery: restore from previous session if backup exists
    if SESSION_BACKUP_DIR.exists():
        logger.warning("Restoring from previous scenario session crash backup")
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)
        shutil.rmtree(SESSION_BACKUP_DIR)

    # Create session backup
    _backup_state(PROJECT_DIR, SESSION_BACKUP_DIR)

    yield

    # Session teardown: always restore original state
    if SESSION_BACKUP_DIR.exists():
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)
        shutil.rmtree(SESSION_BACKUP_DIR)


@pytest.fixture()
def sandbox(_session_backup):
    """Provide a sandbox instance for scenario steps."""
    return Sandbox(project_dir=PROJECT_DIR)


@pytest.fixture(autouse=True)
def scenario_state_restore(_session_backup):
    """Per-test state restoration from session backup.

    After each test, restore files from the session backup so the next
    test starts clean.  No per-test backup needed — the session backup
    is the reference.
    """
    yield
    # Clean up any stash directories left by test steps.
    stash = PROJECT_DIR / ".scenario-stash-inventory"
    if stash.exists():
        shutil.rmtree(stash)
    # Restore from session backup (not per-test — session backup is the
    # single source of truth for pre-test state).
    if SESSION_BACKUP_DIR.exists():
        _restore_state(SESSION_BACKUP_DIR, PROJECT_DIR)


@pytest.fixture()
def infra_backup():
    """Legacy fixture — now handled by scenario_state_restore (autouse)."""
    yield


@pytest.fixture()
def clean_generated_files(sandbox):
    """Remove all generated files (inventory, group_vars, host_vars).

    Use this fixture for scenarios that need a clean slate, e.g. to verify
    that sync-dry does NOT create files.
    """
    for dirname in PROTECTED_DIRS:
        d = sandbox.project_dir / dirname
        if d.exists():
            shutil.rmtree(d)
    yield


# ── Helpers ──────────────────────────────────────────────────────


def _clean_incus_state(sandbox: Sandbox) -> None:
    """Remove all AnKLuMe Incus resources (instances, profiles, projects, networks).

    Used by deploy scenarios to ensure a clean starting state.
    Follows the correct deletion order: instances → images → profiles → projects → networks.
    """
    # Get non-default projects
    result = sandbox.run("incus project list --format csv -c n 2>/dev/null")
    if result.returncode != 0:
        return
    projects = [
        p.replace(" (current)", "").strip()
        for p in result.stdout.strip().splitlines()
        if p.strip() and "default" not in p
    ]

    for proj in projects:
        # Delete instances
        r = sandbox.run(f"incus list --project {proj} --format csv -c n 2>/dev/null")
        for inst in r.stdout.strip().splitlines():
            inst = inst.strip()
            if inst:
                sandbox.run(f"incus delete -f {inst} --project {proj}")
        # Delete images
        r = sandbox.run(f"incus image list --project {proj} --format csv -c f 2>/dev/null")
        for img in r.stdout.strip().splitlines():
            img = img.strip()
            if img:
                sandbox.run(f"incus image delete {img} --project {proj}")
        # Delete custom profiles
        r = sandbox.run(f"incus profile list --project {proj} --format csv -c n 2>/dev/null")
        for profile in r.stdout.strip().splitlines():
            profile = profile.strip()
            if profile and profile != "default":
                sandbox.run(f"incus profile delete {profile} --project {proj}")
        # Reset default profile devices
        r = sandbox.run(f"incus profile device list default --project {proj} 2>/dev/null")
        for dev in r.stdout.strip().splitlines():
            dev = dev.strip()
            if dev:
                sandbox.run(f"incus profile device remove default {dev} --project {proj}")
        # Delete project
        sandbox.run(f"incus project delete {proj}")

    # Delete net-* bridges
    result = sandbox.run("incus network list --format csv -c n 2>/dev/null")
    for net in result.stdout.strip().splitlines():
        net = net.strip()
        if net.startswith("net-"):
            sandbox.run(f"incus network delete {net}")

    # Clean generated Ansible files
    for dirname in ["inventory", "group_vars", "host_vars"]:
        d = sandbox.project_dir / dirname
        if d.exists():
            shutil.rmtree(d)


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
    if not sandbox.has_incus():
        pytest.skip("No Incus daemon available")


@given("Incus daemon is available")
def incus_available(sandbox):
    """Skip if no Incus daemon is accessible."""
    if not sandbox.has_incus():
        pytest.skip("No Incus daemon available")


@given("we are in a sandbox environment")
def in_sandbox(sandbox):
    """Skip if not inside an Incus-in-Incus sandbox.

    Deploy scenarios that run 'make apply' with example infra.yml files
    must only run in a sandbox to avoid creating conflicting bridges on
    the host (e.g. 10.100.* bridges when the host is on 10.100.0.0/24).

    Also cleans Incus state so each deploy scenario starts fresh.
    """
    marker = Path("/etc/anklume/absolute_level")
    if not marker.exists():
        pytest.skip("Not in a sandbox — deploy scenarios skipped to avoid network conflicts")
    try:
        level = int(marker.read_text().strip())
        if level < 1:
            pytest.skip("Not nested — deploy scenarios skipped to avoid network conflicts")
    except (ValueError, OSError):
        pytest.skip("Cannot read nesting level")

    # Clean Incus state so deploy starts from scratch
    _clean_incus_state(sandbox)


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
        # Move files to a temp location outside inventory/ — renaming
        # within the dir still lets Ansible discover them.
        stash = sandbox.project_dir / ".scenario-stash-inventory"
        stash.mkdir(exist_ok=True)
        for f in inv_dir.glob("*.yml"):
            shutil.move(str(f), str(stash / f.name))


@given("a running infrastructure")
def running_infra(sandbox):
    """Verify that instances are running; rebuild if destroyed (e.g. by flush test)."""
    if not sandbox.has_incus():
        pytest.skip("No Incus daemon available")
    result = sandbox.run("incus list --all-projects --format json 2>/dev/null")
    if result.returncode != 0:
        pytest.skip("No Incus daemon available")
    try:
        instances = json.loads(result.stdout)
        running = [i for i in instances if i.get("status") == "Running"]
        if running:
            return  # Infrastructure is up
    except (json.JSONDecodeError, TypeError):
        pass
    # No running instances — rebuild from current infra.yml.
    # The session backup fixture ensures infra.yml is the original one
    # (safe 10.200 subnets), not a modified test copy.
    logger.info("No running instances — rebuilding infrastructure via make sync && make apply")
    r = sandbox.run("make sync", timeout=120)
    if r.returncode != 0:
        pytest.skip(f"Cannot rebuild: make sync failed (rc={r.returncode})")
    r = sandbox.run("make apply", timeout=600)
    if r.returncode != 0:
        pytest.skip(f"Cannot rebuild: make apply failed (rc={r.returncode})")


@given(parsers.parse('infra.yml with two machines sharing "{ip}"'))
def infra_with_duplicate_ip(sandbox, ip):
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


@given("no generated files exist")
def no_generated_files(sandbox, clean_generated_files):
    """Remove all generated Ansible files."""


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
    base = infra.get("global", {}).get("base_subnet", "10.200")
    max_subnet = max(
        d.get("subnet_id", 0) for d in infra.get("domains", {}).values()
    )
    infra.setdefault("domains", {})[domain] = {
        "subnet_id": max_subnet + 1,
        "machines": {
            f"{domain}-test": {
                "type": "lxc",
                "ip": f"{base}.{max_subnet + 1}.10",
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
