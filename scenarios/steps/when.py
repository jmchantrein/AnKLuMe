"""When step definitions for anklume E2E scenario tests."""

import yaml
from behave import when


@when('I run "{command}"')
def run_command(context, command):
    """Execute a command in the project directory."""
    context.sandbox.run(command, timeout=600)


@when('I run "{command}" and it may fail')
def run_command_may_fail(context, command):
    """Execute a command that is expected to potentially fail."""
    context.sandbox.run(command, timeout=600)


@when('I add a domain "{domain}" to infra.yml')
def add_domain_to_infra(context, domain):
    """Add a new domain to the current infra.yml.

    Uses auto-assigned IPs (no explicit IP) to work with ADR-038
    addressing convention. Trust level defaults to semi-trusted.
    """
    infra = context.sandbox.load_infra()
    infra.setdefault("domains", {})[domain] = {
        "trust_level": "semi-trusted",
        "machines": {
            f"{domain}-test": {
                "type": "lxc",
            }
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@when('I edit the managed section in "{filename}"')
def edit_managed_section(context, filename):
    """Modify content inside a managed section."""
    path = context.sandbox.project_dir / filename
    content = path.read_text()
    if "=== MANAGED" in content:
        content = content.replace(
            "# === END MANAGED ===",
            "# SCENARIO-INJECTED: this will be overwritten\n# === END MANAGED ===",
        )
        path.write_text(content)


@when('I snapshot the first running instance as "{snap_name}"')
def snapshot_first_instance(context, snap_name):
    """Create a snapshot on the first running instance."""
    name = context.sandbox.first_running_instance()
    assert name, "No running instance found"
    context.sandbox.run(f"scripts/snap.sh create {name} {snap_name}")


@when("I list snapshots of the first running instance")
def list_snapshots_first_instance(context):
    """List snapshots for the first running instance."""
    name = context.sandbox.first_running_instance()
    assert name, "No running instance found"
    context.sandbox.run(f"scripts/snap.sh list {name}")


@when('I delete snapshot "{snap_name}" from the first running instance')
def delete_snapshot_first_instance(context, snap_name):
    """Delete a snapshot from the first running instance."""
    name = context.sandbox.first_running_instance()
    assert name, "No running instance found"
    context.sandbox.run(f"scripts/snap.sh delete {name} {snap_name}")
