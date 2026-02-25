"""Given step definitions for anklume E2E scenario tests."""

import json
import logging
import shutil
from pathlib import Path

import yaml
from behave import given

from scenarios.support import PROTECTED_DIRS, _clean_incus_state

logger = logging.getLogger("anklume.scenarios")


@given("a clean sandbox environment")
def clean_sandbox(context):
    """Verify we're in a working anklume directory."""
    assert (context.sandbox.project_dir / "scripts" / "generate.py").exists(), (
        "Not in an anklume project directory"
    )


@given("images are pre-cached via shared repository")
def precache_images(context):
    """Ensure images are available locally (skip if no Incus)."""
    if not context.sandbox.has_incus():
        context.scenario.skip("No Incus daemon available")


@given("Incus daemon is available")
def incus_available(context):
    """Skip if no Incus daemon is accessible."""
    if not context.sandbox.has_incus():
        context.scenario.skip("No Incus daemon available")


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

    # Clean Incus state so deploy starts from scratch.
    _clean_incus_state(context.sandbox)


@given('infra.yml from "{example}"')
def load_infra_from_example(context, example):
    """Copy an example infra.yml into place."""
    src = context.sandbox.project_dir / "examples" / example / "infra.yml"
    if not src.exists():
        src = context.sandbox.project_dir / "examples" / f"{example}.infra.yml"
    assert src.exists(), f"Example not found: {src}"
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(src.read_text())


@given("infra.yml exists but no inventory files")
def infra_without_inventory(context):
    """Ensure infra.yml exists but inventory/ is empty."""
    sandbox = context.sandbox
    infra_path = sandbox.project_dir / "infra.yml"
    if not infra_path.exists():
        example = sandbox.project_dir / "examples" / "student-sysadmin" / "infra.yml"
        if example.exists():
            infra_path.write_text(example.read_text())
    inv_dir = sandbox.project_dir / "inventory"
    if inv_dir.exists():
        stash = sandbox.project_dir / ".scenario-stash-inventory"
        stash.mkdir(exist_ok=True)
        for f in inv_dir.glob("*.yml"):
            shutil.move(str(f), str(stash / f.name))


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
    logger.info("No running instances -- rebuilding infrastructure via make sync && make apply")
    r = sandbox.run("make sync", timeout=120)
    if r.returncode != 0:
        context.scenario.skip(f"Cannot rebuild: make sync failed (rc={r.returncode})")
        return
    r = sandbox.run("make apply", timeout=600)
    if r.returncode != 0:
        context.scenario.skip(f"Cannot rebuild: make apply failed (rc={r.returncode})")


@given('infra.yml with two machines sharing "{ip}"')
def infra_with_duplicate_ip(context, ip):
    """Create an infra.yml with duplicate IPs."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test-a": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-a-one": {"type": "lxc", "ip": ip},
                },
            },
            "test-b": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-b-one": {"type": "lxc", "ip": ip},
                },
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given('infra.yml with managed section content in "{filename}"')
def infra_with_managed_content(context, filename):
    """Verify a generated file with managed sections exists."""
    path = context.sandbox.project_dir / filename
    assert path.exists(), f"File not found: {path}"


@given('infra.yml with invalid snapshots_schedule "{schedule}"')
def infra_with_invalid_schedule(context, schedule):
    """Create infra.yml with an invalid snapshots_schedule."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-vm": {
                        "type": "lxc",
                        "snapshots_schedule": schedule,
                    },
                },
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given('infra.yml with invalid snapshots_expiry "{expiry}"')
def infra_with_invalid_expiry(context, expiry):
    """Create infra.yml with an invalid snapshots_expiry."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-vm": {
                        "type": "lxc",
                        "snapshots_expiry": expiry,
                    },
                },
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given("infra.yml with boot_priority {priority:d}")
def infra_with_invalid_boot_priority(context, priority):
    """Create infra.yml with an out-of-range boot_priority."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-vm": {
                        "type": "lxc",
                        "boot_priority": priority,
                    },
                },
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given('infra.yml with shared_volume consumer "{consumer}"')
def infra_with_invalid_sv_consumer(context, consumer):
    """Create infra.yml with an unknown shared_volume consumer."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-vm": {"type": "lxc"},
                },
            },
        },
        "shared_volumes": {
            "docs": {
                "path": "/shared/docs",
                "consumers": {consumer: "ro"},
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given('infra.yml with shared_volume relative path "{path}"')
def infra_with_relative_sv_path(context, path):
    """Create infra.yml with a relative shared_volume path."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test": {
                "trust_level": "semi-trusted",
                "machines": {
                    "test-vm": {"type": "lxc"},
                },
            },
        },
        "shared_volumes": {
            "docs": {
                "path": path,
                "consumers": {"test": "ro"},
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given('infra.yml with invalid trust_level "{level}"')
def infra_with_invalid_trust_level(context, level):
    """Create infra.yml with an invalid trust_level."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "test": {
                "trust_level": level,
                "machines": {
                    "test-vm": {"type": "lxc"},
                },
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given("no generated files exist")
def no_generated_files(context):
    """Remove all generated Ansible files."""
    for dirname in PROTECTED_DIRS:
        d = context.sandbox.project_dir / dirname
        if d.exists():
            shutil.rmtree(d)
