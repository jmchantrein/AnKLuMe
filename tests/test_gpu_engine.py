"""Tests unitaires — engine/gpu.py (GPU passthrough Phase 10a)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from anklume.engine.gpu import (
    GpuInfo,
    apply_gpu_profiles,
    detect_gpu,
    validate_gpu_machines,
)
from anklume.engine.models import (
    Domain,
    GlobalConfig,
    GpuPolicyConfig,
    Infrastructure,
    Machine,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _machine(name: str, domain: str = "dom", *, gpu: bool = False) -> Machine:
    return Machine(
        name=name,
        full_name=f"{domain}-{name}",
        description=f"Machine {name}",
        gpu=gpu,
    )


def _domain(
    name: str = "dom",
    machines: list[Machine] | None = None,
) -> Domain:
    machines = machines or []
    return Domain(
        name=name,
        description=f"Domaine {name}",
        machines={m.name: m for m in machines},
    )


def _infra(
    domains: list[Domain] | None = None,
    gpu_policy: GpuPolicyConfig | None = None,
) -> Infrastructure:
    domains = domains or []
    return Infrastructure(
        config=GlobalConfig(gpu_policy=gpu_policy),
        domains={d.name: d for d in domains},
        policies=[],
    )


def _gpu_present(
    model: str = "RTX PRO 5000",
    total: int = 24576,
    used: int = 1024,
) -> GpuInfo:
    return GpuInfo(detected=True, model=model, vram_total_mib=total, vram_used_mib=used)


def _gpu_absent() -> GpuInfo:
    return GpuInfo(detected=False, model="", vram_total_mib=0, vram_used_mib=0)


# ---------------------------------------------------------------------------
# GpuInfo dataclass
# ---------------------------------------------------------------------------


class TestGpuInfo:
    def test_gpu_detected(self):
        info = _gpu_present()
        assert info.detected is True
        assert info.model == "RTX PRO 5000"
        assert info.vram_total_mib == 24576
        assert info.vram_used_mib == 1024

    def test_gpu_absent(self):
        info = _gpu_absent()
        assert info.detected is False
        assert info.model == ""
        assert info.vram_total_mib == 0


# ---------------------------------------------------------------------------
# detect_gpu
# ---------------------------------------------------------------------------


class TestDetectGpu:
    def test_nvidia_smi_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NVIDIA RTX PRO 5000, 24576, 512\n"

        with patch("anklume.engine.gpu.subprocess.run", return_value=mock_result):
            info = detect_gpu()

        assert info.detected is True
        assert info.model == "NVIDIA RTX PRO 5000"
        assert info.vram_total_mib == 24576
        assert info.vram_used_mib == 512

    def test_nvidia_smi_not_found(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "nvidia-smi: not found"

        with patch("anklume.engine.gpu.subprocess.run", return_value=mock_result):
            info = detect_gpu()

        assert info.detected is False
        assert info.model == ""

    def test_nvidia_smi_file_not_found(self):
        with patch(
            "anklume.engine.gpu.subprocess.run",
            side_effect=FileNotFoundError("nvidia-smi"),
        ):
            info = detect_gpu()

        assert info.detected is False

    def test_nvidia_smi_malformed_output(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "garbage output\n"

        with patch("anklume.engine.gpu.subprocess.run", return_value=mock_result):
            info = detect_gpu()

        assert info.detected is False

    def test_nvidia_smi_multiple_gpus_takes_first(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "NVIDIA RTX 4090, 24576, 100\nNVIDIA RTX 3090, 24576, 200\n"

        with patch("anklume.engine.gpu.subprocess.run", return_value=mock_result):
            info = detect_gpu()

        assert info.detected is True
        assert info.model == "NVIDIA RTX 4090"

    def test_nvidia_smi_empty_stdout(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("anklume.engine.gpu.subprocess.run", return_value=mock_result):
            info = detect_gpu()

        assert info.detected is False


# ---------------------------------------------------------------------------
# validate_gpu_machines
# ---------------------------------------------------------------------------


class TestValidateGpuMachines:
    def test_no_gpu_machines_no_errors(self):
        infra = _infra([_domain("dom", [_machine("web")])])
        errors = validate_gpu_machines(infra, _gpu_absent())
        assert errors == []

    def test_gpu_machine_with_gpu_present(self):
        infra = _infra([_domain("ai", [_machine("server", "ai", gpu=True)])])
        errors = validate_gpu_machines(infra, _gpu_present())
        assert errors == []

    def test_gpu_machine_without_gpu_detected(self):
        infra = _infra([_domain("ai", [_machine("server", "ai", gpu=True)])])
        errors = validate_gpu_machines(infra, _gpu_absent())
        assert len(errors) == 1
        assert "gpu: true" in errors[0]
        assert "aucun GPU" in errors[0]

    def test_multiple_gpu_machines_without_gpu(self):
        infra = _infra(
            [
                _domain(
                    "ai",
                    [
                        _machine("server1", "ai", gpu=True),
                        _machine("server2", "ai", gpu=True),
                    ],
                ),
            ]
        )
        errors = validate_gpu_machines(infra, _gpu_absent())
        assert len(errors) == 2

    def test_exclusive_policy_multiple_gpu_machines_same_domain(self):
        """Politique exclusive : plusieurs machines GPU dans le même domaine = erreur."""
        infra = _infra(
            [
                _domain(
                    "ai",
                    [
                        _machine("s1", "ai", gpu=True),
                        _machine("s2", "ai", gpu=True),
                    ],
                )
            ],
            gpu_policy=GpuPolicyConfig(policy="exclusive"),
        )
        errors = validate_gpu_machines(infra, _gpu_present())
        assert len(errors) == 1
        assert "exclusive" in errors[0].lower()

    def test_exclusive_policy_single_gpu_machine(self):
        """Politique exclusive : une seule machine GPU = ok."""
        infra = _infra(
            [_domain("ai", [_machine("server", "ai", gpu=True)])],
            gpu_policy=GpuPolicyConfig(policy="exclusive"),
        )
        errors = validate_gpu_machines(infra, _gpu_present())
        assert errors == []

    def test_exclusive_policy_gpu_in_different_domains(self):
        """Politique exclusive : machines GPU dans des domaines différents = erreur."""
        infra = _infra(
            [
                _domain("ai", [_machine("s1", "ai", gpu=True)]),
                _domain("ml", [_machine("s2", "ml", gpu=True)]),
            ],
            gpu_policy=GpuPolicyConfig(policy="exclusive"),
        )
        errors = validate_gpu_machines(infra, _gpu_present())
        assert len(errors) == 1
        assert "exclusive" in errors[0].lower()

    def test_shared_policy_multiple_gpu_machines(self):
        """Politique shared : plusieurs machines GPU = ok (pas d'erreur)."""
        infra = _infra(
            [
                _domain("ai", [_machine("s1", "ai", gpu=True)]),
                _domain("ml", [_machine("s2", "ml", gpu=True)]),
            ],
            gpu_policy=GpuPolicyConfig(policy="shared"),
        )
        errors = validate_gpu_machines(infra, _gpu_present())
        assert errors == []

    def test_default_policy_is_exclusive(self):
        """Sans gpu_policy configuré, le défaut est exclusive."""
        infra = _infra(
            [
                _domain("ai", [_machine("s1", "ai", gpu=True)]),
                _domain("ml", [_machine("s2", "ml", gpu=True)]),
            ]
        )
        errors = validate_gpu_machines(infra, _gpu_present())
        assert len(errors) == 1
        assert "exclusive" in errors[0].lower()

    def test_disabled_domain_excluded(self):
        """Domaines désactivés exclus de la validation GPU."""
        d = _domain("ai", [_machine("s1", "ai", gpu=True)])
        d.enabled = False
        infra = _infra(
            [
                d,
                _domain("ml", [_machine("s2", "ml", gpu=True)]),
            ]
        )
        errors = validate_gpu_machines(infra, _gpu_present())
        assert errors == []


# ---------------------------------------------------------------------------
# apply_gpu_profiles
# ---------------------------------------------------------------------------


class TestApplyGpuProfiles:
    def test_no_gpu_machines(self):
        infra = _infra([_domain("dom", [_machine("web")])])
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_absent()):
            info = apply_gpu_profiles(infra)
        assert info.detected is False
        # Profils inchangés
        assert infra.domains["dom"].machines["web"].profiles == ["default"]

    def test_gpu_machine_gets_profile(self):
        infra = _infra([_domain("ai", [_machine("server", "ai", gpu=True)])])
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_present()):
            info = apply_gpu_profiles(infra)
        assert info.detected is True
        assert "gpu-passthrough" in infra.domains["ai"].machines["server"].profiles

    def test_non_gpu_machine_unchanged(self):
        infra = _infra(
            [
                _domain(
                    "ai",
                    [
                        _machine("server", "ai", gpu=True),
                        _machine("web", "ai", gpu=False),
                    ],
                )
            ]
        )
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_present()):
            apply_gpu_profiles(infra)
        assert "gpu-passthrough" not in infra.domains["ai"].machines["web"].profiles
        assert "gpu-passthrough" in infra.domains["ai"].machines["server"].profiles

    def test_no_duplicate_profile(self):
        """Si gpu-passthrough déjà dans les profils, pas de doublon."""
        m = _machine("server", "ai", gpu=True)
        m.profiles = ["default", "gpu-passthrough"]
        infra = _infra([_domain("ai", [m])])
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_present()):
            apply_gpu_profiles(infra)
        count = infra.domains["ai"].machines["server"].profiles.count("gpu-passthrough")
        assert count == 1

    def test_gpu_absent_no_profile_added(self):
        """Si GPU absent, les machines gpu: true ne reçoivent pas le profil."""
        infra = _infra([_domain("ai", [_machine("server", "ai", gpu=True)])])
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_absent()):
            apply_gpu_profiles(infra)
        assert "gpu-passthrough" not in infra.domains["ai"].machines["server"].profiles

    def test_multiple_domains(self):
        """Profil ajouté aux machines GPU de chaque domaine."""
        infra = _infra(
            [
                _domain("ai", [_machine("s1", "ai", gpu=True)]),
                _domain("ml", [_machine("s2", "ml", gpu=True)]),
            ]
        )
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_present()):
            apply_gpu_profiles(infra)
        assert "gpu-passthrough" in infra.domains["ai"].machines["s1"].profiles
        assert "gpu-passthrough" in infra.domains["ml"].machines["s2"].profiles

    def test_disabled_domain_skipped(self):
        """Domaines désactivés ignorés."""
        d = _domain("ai", [_machine("s1", "ai", gpu=True)])
        d.enabled = False
        infra = _infra([d])
        with patch("anklume.engine.gpu.detect_gpu", return_value=_gpu_present()):
            apply_gpu_profiles(infra)
        assert "gpu-passthrough" not in infra.domains["ai"].machines["s1"].profiles


# ---------------------------------------------------------------------------
# GpuPolicyConfig model
# ---------------------------------------------------------------------------


class TestGpuPolicyConfig:
    def test_default_values(self):
        config = GpuPolicyConfig()
        assert config.policy == "exclusive"

    def test_shared_policy(self):
        config = GpuPolicyConfig(policy="shared")
        assert config.policy == "shared"


# ---------------------------------------------------------------------------
# Intégration driver — profile methods
# ---------------------------------------------------------------------------


class TestDriverProfileMethods:
    def test_profile_exists_true(self):
        from anklume.engine.incus_driver import IncusDriver

        driver = MagicMock(spec=IncusDriver)
        driver.profile_list.return_value = ["default", "gpu-passthrough"]
        driver.profile_exists.side_effect = lambda n, p: n in ["default", "gpu-passthrough"]
        assert driver.profile_exists("gpu-passthrough", "ai") is True

    def test_profile_exists_false(self):
        from anklume.engine.incus_driver import IncusDriver

        driver = MagicMock(spec=IncusDriver)
        driver.profile_exists.side_effect = lambda n, p: n in ["default"]
        assert driver.profile_exists("gpu-passthrough", "ai") is False


# ---------------------------------------------------------------------------
# Parser — gpu_policy parsing
# ---------------------------------------------------------------------------


class TestParserGpuPolicy:
    def test_parse_gpu_policy_from_yaml(self, tmp_path):
        from anklume.engine.parser import parse_project

        # anklume.yml avec gpu_policy
        (tmp_path / "anklume.yml").write_text("schema_version: 1\ngpu_policy: shared\n")
        (tmp_path / "domains").mkdir()

        infra = parse_project(tmp_path)
        assert infra.config.gpu_policy is not None
        assert infra.config.gpu_policy.policy == "shared"

    def test_parse_gpu_policy_absent(self, tmp_path):
        from anklume.engine.parser import parse_project

        (tmp_path / "anklume.yml").write_text("schema_version: 1\n")
        (tmp_path / "domains").mkdir()

        infra = parse_project(tmp_path)
        assert infra.config.gpu_policy is None

    def test_parse_gpu_policy_exclusive(self, tmp_path):
        from anklume.engine.parser import parse_project

        (tmp_path / "anklume.yml").write_text("schema_version: 1\ngpu_policy: exclusive\n")
        (tmp_path / "domains").mkdir()

        infra = parse_project(tmp_path)
        assert infra.config.gpu_policy is not None
        assert infra.config.gpu_policy.policy == "exclusive"
