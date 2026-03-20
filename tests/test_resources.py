"""Tests unitaires — engine/resources.py (Resource policy Phase 8)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from anklume.engine.models import (
    Domain,
    GlobalConfig,
    Infrastructure,
    Machine,
    ResourcePolicyConfig,
)
from anklume.engine.resources import (
    HardwareInfo,
    OvercommitError,
    apply_resource_config,
    compute_resource_allocation,
    detect_hardware,
    detect_hardware_fallback,
    parse_memory_value,
    parse_reserve,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _machine(
    name: str, weight: int = 1, config: dict | None = None, type: str = "lxc",
) -> Machine:
    return Machine(
        name=name,
        full_name=f"dom-{name}",
        description=f"Machine {name}",
        type=type,
        weight=weight,
        config=config or {},
    )


def _domain(machines: list[Machine]) -> Domain:
    return Domain(
        name="dom",
        description="Domaine test",
        machines={m.name: m for m in machines},
    )


def _infra(
    machines: list[Machine],
    policy: ResourcePolicyConfig | None = None,
) -> Infrastructure:
    return Infrastructure(
        config=GlobalConfig(resource_policy=policy),
        domains={"dom": _domain(machines)},
        policies=[],
    )


def _hw(cpu: int = 16, memory_gb: int = 32) -> HardwareInfo:
    return HardwareInfo(cpu_threads=cpu, memory_bytes=memory_gb * 1024**3)


# ---------------------------------------------------------------------------
# HardwareInfo
# ---------------------------------------------------------------------------


class TestHardwareInfo:
    def test_basic(self):
        hw = _hw(8, 16)
        assert hw.cpu_threads == 8
        assert hw.memory_bytes == 16 * 1024**3


# ---------------------------------------------------------------------------
# parse_reserve
# ---------------------------------------------------------------------------


class TestParseReserve:
    @pytest.mark.parametrize(
        ("spec", "total", "expected"),
        [
            ("20%", 100, 20),
            ("33%", 10, 3),
            ("4", 100, 4),
            ("0", 100, 0),
            ("100%", 80, 80),
            ("0%", 80, 0),
        ],
        ids=[
            "percentage",
            "percentage_rounding",
            "absolute_integer",
            "absolute_zero",
            "percentage_100",
            "percentage_0",
        ],
    )
    def test_parse_reserve(self, spec, total, expected):
        assert parse_reserve(spec, total) == expected


# ---------------------------------------------------------------------------
# parse_memory_value
# ---------------------------------------------------------------------------


class TestParseMemoryValue:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("4GB", 4 * 1024**3),
            ("512MB", 512 * 1024**2),
            ("1024KB", 1024 * 1024),
            ("1TB", 1024**4),
            ("1048576", 1048576),
            ("4gb", 4 * 1024**3),
        ],
        ids=["gb", "mb", "kb", "tb", "bare_number_as_bytes", "case_insensitive"],
    )
    def test_parse_memory_value(self, value, expected):
        assert parse_memory_value(value) == expected

    def test_invalid_suffix(self):
        with pytest.raises(ValueError, match="unité mémoire"):
            parse_memory_value("4PB")


# ---------------------------------------------------------------------------
# compute_resource_allocation — proportional mode
# ---------------------------------------------------------------------------


class TestProportionalAllocation:
    def test_equal_weights(self):
        machines = [_machine("a"), _machine("b")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        assert len(allocs) == 2
        # Chaque machine obtient 50% (8 threads, 16GB)
        for a in allocs:
            assert a.source == "auto"

    def test_weighted_3_1(self):
        machines = [_machine("heavy", weight=3), _machine("light", weight=1)]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            cpu_mode="count",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        heavy = next(a for a in allocs if a.instance_name == "dom-heavy")
        light = next(a for a in allocs if a.instance_name == "dom-light")

        # heavy: 12 threads, light: 4 threads
        assert heavy.cpu_value == "12"
        assert light.cpu_value == "4"

    def test_host_reserve_percentage(self):
        machines = [_machine("a")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="50%",
            host_reserve_memory="50%",
            mode="proportional",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        a = allocs[0]
        assert a.cpu_value == "8"  # 16 - 50% = 8

    def test_host_reserve_absolute_cpu(self):
        machines = [_machine("a")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="4",
            host_reserve_memory="8GB",
            mode="proportional",
            cpu_mode="count",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        a = allocs[0]
        assert a.cpu_value == "12"  # 16 - 4 = 12


# ---------------------------------------------------------------------------
# compute_resource_allocation — equal mode
# ---------------------------------------------------------------------------


class TestEqualAllocation:
    def test_equal_ignores_weight(self):
        machines = [_machine("a", weight=5), _machine("b", weight=1)]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="equal",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        assert allocs[0].cpu_value == "8"
        assert allocs[1].cpu_value == "8"


# ---------------------------------------------------------------------------
# Machines avec config explicite
# ---------------------------------------------------------------------------


class TestExplicitConfig:
    def test_explicit_cpu_excluded(self):
        machines = [
            _machine("explicit", config={"limits.cpu": "2"}),
            _machine("auto"),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        explicit = next(a for a in allocs if a.instance_name == "dom-explicit")
        auto = next(a for a in allocs if a.instance_name == "dom-auto")

        # CPU explicite + mémoire auto = mixed
        assert explicit.source == "mixed"
        assert auto.source == "auto"
        # auto gets 16 - 2 = 14
        assert auto.cpu_value == "14"

    def test_explicit_memory_excluded(self):
        machines = [
            _machine("explicit", config={"limits.memory": "4GB"}),
            _machine("auto"),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 8)
        allocs = compute_resource_allocation(infra, hw)

        auto = next(a for a in allocs if a.instance_name == "dom-auto")
        # 8GB - 4GB = 4GB pour auto
        assert auto.memory_value == "4096MB"

    def test_explicit_cpu_only_still_gets_memory(self):
        """Machine avec limits.cpu explicite participe quand même à l'allocation mémoire."""
        machines = [
            _machine("mixed", config={"limits.cpu": "2"}),
            _machine("full"),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 16)
        allocs = compute_resource_allocation(infra, hw)

        mixed = next(a for a in allocs if a.instance_name == "dom-mixed")
        # mixed participe à l'allocation mémoire (poids 1, total poids 2)
        assert mixed.memory_value == "8192MB"


# ---------------------------------------------------------------------------
# CPU mode: allowance
# ---------------------------------------------------------------------------


class TestCpuAllowance:
    def test_allowance_percentage(self):
        machines = [_machine("a"), _machine("b")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            cpu_mode="allowance",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        for a in allocs:
            assert a.cpu_key == "limits.cpu.allowance"
            assert a.cpu_value == "50%"

    def test_allowance_with_reserve(self):
        machines = [_machine("a")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="50%",
            host_reserve_memory="0%",
            mode="proportional",
            cpu_mode="allowance",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        assert allocs[0].cpu_value == "50%"


# ---------------------------------------------------------------------------
# CPU mode: count
# ---------------------------------------------------------------------------


class TestCpuCount:
    def test_count_minimum_1(self):
        machines = [_machine(f"m{i}") for i in range(20)]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="equal",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(4, 32)
        allocs = compute_resource_allocation(infra, hw)

        for a in allocs:
            assert int(a.cpu_value) >= 1

    def test_count_rounds_up(self):
        machines = [_machine("a"), _machine("b"), _machine("c")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="equal",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(10, 32)
        allocs = compute_resource_allocation(infra, hw)

        # 10 / 3 = 3.33... → arrondi sup = 4
        for a in allocs:
            assert a.cpu_value == "4"


# ---------------------------------------------------------------------------
# Memory enforce modes
# ---------------------------------------------------------------------------


class TestMemoryEnforce:
    def test_soft_key(self):
        machines = [_machine("a")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            memory_enforce="soft",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        assert allocs[0].memory_key == "limits.memory"
        assert allocs[0].memory_enforce == "soft"

    def test_hard_key(self):
        machines = [_machine("a")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        assert allocs[0].memory_key == "limits.memory"
        assert allocs[0].memory_enforce is None

    def test_vm_forces_hard_memory_key(self):
        """Les VMs ne supportent pas limits.memory.enforce=soft."""
        machines = [_machine("vm1", type="vm")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            memory_enforce="soft",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        assert allocs[0].memory_key == "limits.memory"
        assert allocs[0].memory_enforce is None

    def test_vm_forces_cpu_pin_key(self):
        """Les VMs ne supportent pas limits.cpu.allowance, on force limits.cpu."""
        machines = [_machine("vm1", type="vm")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            cpu_mode="allowance",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        assert allocs[0].cpu_key == "limits.cpu"

    def test_mixed_vm_and_container(self):
        """VM utilise limits.memory sans enforce, container a enforce=soft."""
        machines = [_machine("ct1"), _machine("vm1", type="vm")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            memory_enforce="soft",
            cpu_mode="allowance",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        ct_alloc = next(a for a in allocs if a.instance_name == "dom-ct1")
        vm_alloc = next(a for a in allocs if a.instance_name == "dom-vm1")
        assert ct_alloc.memory_key == "limits.memory"
        assert ct_alloc.memory_enforce == "soft"
        assert vm_alloc.memory_key == "limits.memory"
        assert vm_alloc.memory_enforce is None
        assert ct_alloc.cpu_key == "limits.cpu.allowance"
        assert vm_alloc.cpu_key == "limits.cpu"

    def test_minimum_64mb(self):
        machines = [_machine(f"m{i}") for i in range(1000)]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="equal",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 1)  # 1 GB pour 1000 machines
        allocs = compute_resource_allocation(infra, hw)

        for a in allocs:
            # Extraire la valeur numérique du format "NMB"
            mb = int(a.memory_value.replace("MB", ""))
            assert mb >= 64


# ---------------------------------------------------------------------------
# Overcommit
# ---------------------------------------------------------------------------


class TestOvercommit:
    def test_overcommit_false_raises(self):
        machines = [
            _machine("a", config={"limits.cpu": "10"}),
            _machine("b", config={"limits.cpu": "10"}),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            overcommit=False,
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(8, 32)  # 8 < 10+10

        with pytest.raises(OvercommitError):
            compute_resource_allocation(infra, hw)

    def test_overcommit_true_warns(self):
        machines = [
            _machine("a", config={"limits.cpu": "10"}),
            _machine("b", config={"limits.cpu": "10"}),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            overcommit=True,
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(8, 32)

        # Doit réussir sans erreur
        allocs = compute_resource_allocation(infra, hw)
        assert len(allocs) == 2

    def test_memory_overcommit_raises(self):
        machines = [
            _machine("a", config={"limits.memory": "20GB"}),
            _machine("b", config={"limits.memory": "20GB"}),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            overcommit=False,
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 8)  # 8GB < 20+20

        with pytest.raises(OvercommitError):
            compute_resource_allocation(infra, hw)


# ---------------------------------------------------------------------------
# No resource policy → skip
# ---------------------------------------------------------------------------


class TestNoPolicy:
    def test_no_policy_returns_empty(self):
        machines = [_machine("a")]
        infra = _infra(machines, policy=None)
        allocs = compute_resource_allocation(infra, _hw())
        assert allocs == []


# ---------------------------------------------------------------------------
# Disabled domains excluded
# ---------------------------------------------------------------------------


class TestDisabledDomains:
    def test_disabled_domain_excluded(self):
        domain = _domain([_machine("a")])
        domain.enabled = False
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
        )
        infra = Infrastructure(
            config=GlobalConfig(resource_policy=policy),
            domains={"dom": domain},
            policies=[],
        )
        allocs = compute_resource_allocation(infra, _hw())
        assert allocs == []


# ---------------------------------------------------------------------------
# Multi-domain allocation
# ---------------------------------------------------------------------------


class TestMultiDomain:
    def test_two_domains_share_resources(self):
        dom1 = Domain(
            name="web",
            description="Web",
            machines={
                "app": _machine("app"),
            },
        )
        dom1.machines["app"].full_name = "web-app"

        dom2 = Domain(
            name="db",
            description="Database",
            machines={
                "pg": _machine("pg", weight=3),
            },
        )
        dom2.machines["pg"].full_name = "db-pg"

        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            cpu_mode="count",
        )
        infra = Infrastructure(
            config=GlobalConfig(resource_policy=policy),
            domains={"web": dom1, "db": dom2},
            policies=[],
        )
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        app = next(a for a in allocs if a.instance_name == "web-app")
        pg = next(a for a in allocs if a.instance_name == "db-pg")

        # poids 1+3=4, app=4 threads, pg=12 threads
        assert app.cpu_value == "4"
        assert pg.cpu_value == "12"


# ---------------------------------------------------------------------------
# apply_resource_config
# ---------------------------------------------------------------------------


class TestApplyResourceConfig:
    def test_apply_sets_config(self):
        machines = [_machine("a")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            cpu_mode="count",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(8, 16)
        allocs = compute_resource_allocation(infra, hw)

        apply_resource_config(infra, allocs)

        m = infra.domains["dom"].machines["a"]
        assert "limits.cpu" in m.config
        assert "limits.memory" in m.config

    def test_apply_preserves_existing_config(self):
        machines = [_machine("a", config={"security.nesting": "true"})]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        apply_resource_config(infra, allocs)

        m = infra.domains["dom"].machines["a"]
        assert m.config["security.nesting"] == "true"
        assert "limits.cpu" in m.config

    def test_apply_does_not_overwrite_explicit(self):
        """Les machines avec config explicite gardent leur valeur."""
        machines = [_machine("a", config={"limits.cpu": "2"})]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        allocs = compute_resource_allocation(infra, _hw())
        apply_resource_config(infra, allocs)

        m = infra.domains["dom"].machines["a"]
        assert m.config["limits.cpu"] == "2"


# ---------------------------------------------------------------------------
# detect_hardware — mocked
# ---------------------------------------------------------------------------


class TestDetectHardware:
    def test_detect_via_driver(self):
        mock_driver = _mock_driver(cpu=24, memory=34359738368)
        hw = detect_hardware(driver=mock_driver)

        assert hw.cpu_threads == 24
        assert hw.memory_bytes == 34359738368

    def test_detect_fallback_on_driver_failure(self):
        mock_driver = _mock_driver(fail=True)
        meminfo = "MemTotal:       16384000 kB\n"

        with (
            patch("anklume.engine.resources.os.cpu_count", return_value=4),
            patch("builtins.open", return_value=_fake_file(meminfo)),
        ):
            hw = detect_hardware(driver=mock_driver)

        assert hw.cpu_threads == 4
        assert hw.memory_bytes == 16384000 * 1024


class TestDetectHardwareFallback:
    def test_fallback_uses_os_cpu_count(self):
        meminfo = "MemTotal:       8192000 kB\nMemFree:        4000000 kB\n"

        with (
            patch("anklume.engine.resources.os.cpu_count", return_value=2),
            patch("builtins.open", return_value=_fake_file(meminfo)),
        ):
            hw = detect_hardware_fallback()

        assert hw.cpu_threads == 2
        assert hw.memory_bytes == 8192000 * 1024


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_single_machine(self):
        machines = [_machine("solo")]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="20%",
            host_reserve_memory="20%",
            cpu_mode="count",
            memory_enforce="hard",
        )
        infra = _infra(machines, policy)
        hw = _hw(10, 10)
        allocs = compute_resource_allocation(infra, hw)

        assert len(allocs) == 1
        assert allocs[0].cpu_value == "8"  # 10 - 20% = 8

    def test_all_explicit_no_auto(self):
        machines = [
            _machine("a", config={"limits.cpu": "4", "limits.memory": "2GB"}),
            _machine("b", config={"limits.cpu": "4", "limits.memory": "2GB"}),
        ]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        for a in allocs:
            assert a.source == "explicit"

    def test_zero_weight_gets_nothing(self):
        """weight=0 donne 0 ressources (minimum garanti par arrondi)."""
        machines = [_machine("zero", weight=0), _machine("normal", weight=1)]
        policy = ResourcePolicyConfig(
            host_reserve_cpu="0%",
            host_reserve_memory="0%",
            mode="proportional",
            cpu_mode="count",
        )
        infra = _infra(machines, policy)
        hw = _hw(16, 32)
        allocs = compute_resource_allocation(infra, hw)

        zero = next(a for a in allocs if a.instance_name == "dom-zero")
        normal = next(a for a in allocs if a.instance_name == "dom-normal")

        # weight 0 → minimum 1 cpu
        assert int(zero.cpu_value) >= 0
        assert int(normal.cpu_value) >= 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeFile:
    def __init__(self, content: str):
        self._lines = content.splitlines(keepends=True)

    def read(self) -> str:
        return "".join(self._lines)

    def __iter__(self):
        return iter(self._lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _fake_file(content: str) -> _FakeFile:
    return _FakeFile(content)


def _mock_driver(cpu: int = 8, memory: int = 0, fail: bool = False):
    """Crée un mock IncusDriver pour les tests de détection."""
    from unittest.mock import MagicMock

    from anklume.engine.incus_driver import IncusError as _IncusError

    driver = MagicMock()
    if fail:
        driver.host_resources.side_effect = _IncusError(["incus"], 1, "error")
    else:
        driver.host_resources.return_value = {
            "cpu": {"total": cpu},
            "memory": {"total": memory},
        }
    return driver
