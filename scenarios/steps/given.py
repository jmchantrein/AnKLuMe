"""Given step definitions for anklume E2E scenario tests."""

import json
import shutil

import pytest
import yaml
from pytest_bdd import given, parsers

from scenarios.conftest import _clean_incus_state


@given("a clean sandbox environment")
def clean_sandbox(sandbox):
    """Verify we're in a working anklume directory."""
    assert (sandbox.project_dir / "scripts" / "generate.py").exists(), (
        "Not in an anklume project directory"
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


@given("storage backend supports snapshots")
def storage_supports_snapshots(sandbox):
    """Skip if the default storage pool uses 'dir' backend (snapshots hang)."""
    result = sandbox.run("incus storage show default --format json")
    if result.returncode != 0:
        pytest.skip("Cannot query storage pool")
    try:
        pool = json.loads(result.stdout)
        driver = pool.get("driver", "dir")
        if driver == "dir":
            pytest.skip(
                f"Storage backend '{driver}' does not support reliable snapshots"
            )
    except (json.JSONDecodeError, TypeError):
        pytest.skip("Cannot parse storage pool info")


@given("we are in a sandbox environment")
def in_sandbox(sandbox):
    """Skip if not inside an Incus-in-Incus sandbox.

    Deploy scenarios that run 'make apply' with example infra.yml files
    must only run in a sandbox to avoid creating conflicting bridges on
    the host (e.g. 10.100.* bridges when the host is on 10.100.0.0/24).

    Also cleans Incus state so each deploy scenario starts fresh.
    """
    from pathlib import Path

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
        stash = sandbox.project_dir / ".scenario-stash-inventory"
        stash.mkdir(exist_ok=True)
        for f in inv_dir.glob("*.yml"):
            shutil.move(str(f), str(stash / f.name))


@given("a running infrastructure")
def running_infra(sandbox):
    """Verify that instances are running; rebuild if destroyed."""
    import logging

    logger = logging.getLogger("anklume.scenarios")
    if not sandbox.has_incus():
        pytest.skip("No Incus daemon available")
    result = sandbox.run("incus list --all-projects --format json")
    if result.returncode != 0:
        pytest.skip("No Incus daemon available")
    try:
        instances = json.loads(result.stdout)
        running = [i for i in instances if i.get("status") == "Running"]
        if running:
            logger.info("Found %d running instances", len(running))
            return
    except (json.JSONDecodeError, TypeError):
        pass
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


@given(parsers.parse('infra.yml with invalid snapshots_schedule "{schedule}"'))
def infra_with_invalid_schedule(sandbox, schedule):
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
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given(parsers.parse('infra.yml with invalid snapshots_expiry "{expiry}"'))
def infra_with_invalid_expiry(sandbox, expiry):
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
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given(parsers.parse("infra.yml with boot_priority {priority:d}"))
def infra_with_invalid_boot_priority(sandbox, priority):
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
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given(parsers.parse('infra.yml with shared_volume consumer "{consumer}"'))
def infra_with_invalid_sv_consumer(sandbox, consumer):
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
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given(parsers.parse('infra.yml with shared_volume relative path "{path}"'))
def infra_with_relative_sv_path(sandbox, path):
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
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given(parsers.parse('infra.yml with invalid trust_level "{level}"'))
def infra_with_invalid_trust_level(sandbox, level):
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
    dst = sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given("no generated files exist")
def no_generated_files(sandbox, clean_generated_files):
    """Remove all generated Ansible files."""
