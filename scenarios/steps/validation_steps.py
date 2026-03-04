"""Validation step definitions — infra.yml error detection.

Steps that create deliberately invalid infra.yml configurations
to test the generator's validation logic (duplicate IPs, invalid
schedules, bad trust levels, shared volume errors, etc.).
"""

import yaml
from behave import given


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


@given('infra.yml with duplicate machine "{name}" in two domains')
def infra_with_duplicate_machine(context, name):
    """Create infra.yml with a duplicate machine name across domains."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
        },
        "domains": {
            "dom-a": {
                "trust_level": "semi-trusted",
                "machines": {
                    name: {"type": "lxc"},
                },
            },
            "dom-b": {
                "trust_level": "semi-trusted",
                "machines": {
                    name: {"type": "lxc"},
                },
            },
        },
    }
    dst = context.sandbox.project_dir / "infra.yml"
    dst.write_text(yaml.dump(infra, sort_keys=False))


@given("infra.yml with no domains section")
def infra_with_no_domains(context):
    """Create infra.yml without a domains section."""
    infra = {
        "project_name": "scenario-test",
        "global": {
            "addressing": {"base_octet": 10, "zone_base": 100},
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
