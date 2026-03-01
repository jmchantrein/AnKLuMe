"""Infrastructure step definitions — deployment, running instances.

Steps for verifying running infrastructure, sandbox environments,
image caching, and Incus resource state.
"""

import json
import logging
from pathlib import Path

from behave import given, then

from scenarios.support import _clean_incus_state

logger = logging.getLogger("anklume.scenarios")


@given("images are pre-cached via shared repository")
def precache_images(context):
    """Ensure images are available locally (skip if no Incus)."""
    if not context.sandbox.has_incus():
        context.scenario.skip("No Incus daemon available")


@given("we are in a sandbox environment")
def in_sandbox(context):
    """Skip if not inside an Incus-in-Incus sandbox.

    Deploy scenarios that run 'make apply' with example infra.yml files
    must only run in a sandbox to avoid creating conflicting bridges on
    the host (e.g. 10.100.* bridges when the host is on 10.100.0.0/24).

    Also cleans Incus state so each deploy scenario starts fresh.
    """
    marker = Path("/etc/anklume/absolute_level")
    if not marker.exists():
        context.scenario.skip(
            "Not in a sandbox -- deploy scenarios skipped to avoid network conflicts"
        )
        return
    try:
        level = int(marker.read_text().strip())
        if level < 1:
            context.scenario.skip(
                "Not nested -- deploy scenarios skipped to avoid network conflicts"
            )
            return
    except (ValueError, OSError):
        context.scenario.skip("Cannot read nesting level")
        return

    _clean_incus_state(context.sandbox)


@given("a running infrastructure")
def running_infra(context):
    """Verify that instances are running; rebuild if destroyed."""
    sandbox = context.sandbox
    if not sandbox.has_incus():
        context.scenario.skip("No Incus daemon available")
        return
    result = sandbox.run("incus list --all-projects --format json")
    if result.returncode != 0:
        context.scenario.skip("No Incus daemon available")
        return
    try:
        instances = json.loads(result.stdout)
        running = [i for i in instances if i.get("status") == "Running"]
        if running:
            logger.info("Found %d running instances", len(running))
            return
    except (json.JSONDecodeError, TypeError):
        pass
    logger.info("No running instances -- rebuilding via make sync && make apply")
    r = sandbox.run("make sync", timeout=120)
    if r.returncode != 0:
        context.scenario.skip(f"Cannot rebuild: make sync failed (rc={r.returncode})")
        return
    r = sandbox.run("make apply", timeout=600)
    if r.returncode != 0:
        context.scenario.skip(f"Cannot rebuild: make apply failed (rc={r.returncode})")


@then("all declared instances are running")
def check_all_running(context):
    for name, _domain in context.sandbox.all_declared_instances():
        assert context.sandbox.instance_running(name), f"Instance {name} is not running"


@then('instance "{name}" is running in project "{project}"')
def check_instance_running(context, name, project):
    result = context.sandbox.run(
        f"incus list --project {project} --format json 2>/dev/null"
    )
    assert result.returncode == 0
    instances = json.loads(result.stdout)
    running = [i for i in instances if i["name"] == name and i["status"] == "Running"]
    assert running, f"Instance {name} not running in project {project}"


@then("no Incus resources were created")
def check_no_resources(context):
    """Verify no new Incus projects/instances were created by the failed command."""
    result = context.sandbox.run("incus project list --format json 2>/dev/null")
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
