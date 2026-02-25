"""Shared support classes and helpers for anklume E2E scenario tests.

Contains data classes (CommandResult, Sandbox), backup/restore helpers,
and Incus cleanup functions used by behave environment hooks and step
definitions.
"""

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger("anklume.scenarios")

PROJECT_DIR = Path(__file__).resolve().parent.parent

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


def _clean_incus_state(sandbox) -> None:
    """Remove all anklume Incus resources (instances, profiles, projects, networks).

    Used by deploy scenarios to ensure a clean starting state.
    Follows the correct deletion order: instances -> images -> profiles -> projects -> networks.
    """
    result = sandbox.run("incus project list --format csv -c n 2>/dev/null")
    if result.returncode != 0:
        return
    projects = [
        p.replace(" (current)", "").strip()
        for p in result.stdout.strip().splitlines()
        if p.strip() and "default" not in p
    ]

    for proj in projects:
        r = sandbox.run(f"incus list --project {proj} --format csv -c n 2>/dev/null")
        for inst in r.stdout.strip().splitlines():
            inst = inst.strip()
            if inst:
                sandbox.run(f"incus delete -f {inst} --project {proj}")
        r = sandbox.run(f"incus image list --project {proj} --format csv -c f 2>/dev/null")
        for img in r.stdout.strip().splitlines():
            img = img.strip()
            if img:
                sandbox.run(f"incus image delete {img} --project {proj}")
        r = sandbox.run(f"incus profile list --project {proj} --format csv -c n 2>/dev/null")
        for profile in r.stdout.strip().splitlines():
            profile = profile.strip()
            if profile and profile != "default":
                sandbox.run(f"incus profile delete {profile} --project {proj}")
        r = sandbox.run(f"incus profile device list default --project {proj} 2>/dev/null")
        for dev in r.stdout.strip().splitlines():
            dev = dev.strip()
            if dev:
                sandbox.run(f"incus profile device remove default {dev} --project {proj}")
        sandbox.run(f"incus project delete {proj}")

    result = sandbox.run("incus network list --format csv -c n 2>/dev/null")
    for net in result.stdout.strip().splitlines():
        net = net.strip()
        if net.startswith("net-"):
            sandbox.run(f"incus network delete {net}")

    for dirname in ["inventory", "group_vars", "host_vars"]:
        d = sandbox.project_dir / dirname
        if d.exists():
            shutil.rmtree(d)


# -- Data classes ------------------------------------------------------


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

    def first_running_instance(self) -> str | None:
        """Return the name of the first running instance."""
        result = self.run(
            "incus list --all-projects --format json 2>/dev/null"
        )
        if result.returncode != 0:
            return None
        try:
            instances = json.loads(result.stdout)
            for i in sorted(instances, key=lambda x: x.get("name", "")):
                if i.get("status") == "Running":
                    return i["name"]
        except (json.JSONDecodeError, TypeError):
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
