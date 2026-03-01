"""Instance step definitions — snapshots and instance operations.

Steps for snapshot create/list/delete and storage backend checks.
"""

import json

from behave import given, when


@given("storage backend supports snapshots")
def storage_supports_snapshots(context):
    """Skip if the default storage pool uses 'dir' backend (snapshots hang)."""
    result = context.sandbox.run("incus storage show default --format json")
    if result.returncode != 0:
        context.scenario.skip("Cannot query storage pool")
        return
    try:
        pool = json.loads(result.stdout)
        driver = pool.get("driver", "dir")
        if driver == "dir":
            context.scenario.skip(
                f"Storage backend '{driver}' does not support reliable snapshots"
            )
    except (json.JSONDecodeError, TypeError):
        context.scenario.skip("Cannot parse storage pool info")


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
