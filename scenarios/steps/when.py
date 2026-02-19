"""When step definitions for anklume E2E scenario tests."""

import yaml
from pytest_bdd import parsers, when


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


@when(parsers.parse('I snapshot the first running instance as "{snap_name}"'))
def snapshot_first_instance(sandbox, snap_name):
    """Create a snapshot on the first running instance."""
    name = sandbox.first_running_instance()
    assert name, "No running instance found"
    sandbox.run(f"scripts/snap.sh create {name} {snap_name}")


@when("I list snapshots of the first running instance")
def list_snapshots_first_instance(sandbox):
    """List snapshots for the first running instance."""
    name = sandbox.first_running_instance()
    assert name, "No running instance found"
    sandbox.run(f"scripts/snap.sh list {name}")


@when(parsers.parse('I delete snapshot "{snap_name}" from the first running instance'))
def delete_snapshot_first_instance(sandbox, snap_name):
    """Delete a snapshot from the first running instance."""
    name = sandbox.first_running_instance()
    assert name, "No running instance found"
    sandbox.run(f"scripts/snap.sh delete {name} {snap_name}")
