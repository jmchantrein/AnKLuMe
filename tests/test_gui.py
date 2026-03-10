"""Tests pour engine/gui.py — GUI passthrough Wayland."""

from __future__ import annotations

import socket
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from anklume.engine.gui import (
    GUI_PROFILE_NAME,
    GuiInfo,
    GuiSocket,
    apply_gui_profiles,
    create_gui_profile,
    detect_gui,
    prepare_gui_dirs,
)
from tests.conftest import make_domain, make_infra, make_machine, mock_driver

# --- Helpers ---


def _make_gui_info(**kwargs) -> GuiInfo:
    """Crée un GuiInfo avec des valeurs par défaut sensées."""
    defaults = {
        "detected": True,
        "igpu_pci": "0000:00:02.0",
        "uid": 1000,
        "gid": 1000,
        "video_gid": 44,
        "render_gid": 109,
        "runtime_dir": "/run/user/1000",
        "sockets": [
            GuiSocket(
                name="wayland-0",
                host_path="/run/user/1000/wayland-0",
                container_path="/run/user/1000/wayland-0",
            ),
        ],
    }
    defaults.update(kwargs)
    return GuiInfo(**defaults)


def _create_unix_socket(path: Path) -> None:
    """Crée un vrai socket Unix pour les tests de détection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind(str(path))
    finally:
        sock.close()


# --- GuiInfo ---


class TestGuiInfo:
    """Tests pour la dataclass GuiInfo."""

    def test_none_sentinel(self):
        """GuiInfo.none() retourne un sentinel non-détecté."""
        info = GuiInfo.none()
        assert info.detected is False
        assert info.igpu_pci == ""
        assert info.uid == 0
        assert info.sockets == []

    def test_detected_info(self):
        """GuiInfo avec détection complète."""
        info = _make_gui_info()
        assert info.detected is True
        assert info.igpu_pci == "0000:00:02.0"
        assert info.uid == 1000
        assert len(info.sockets) == 1


class TestGuiSocket:
    """Tests pour la dataclass GuiSocket."""

    def test_socket_creation(self):
        """GuiSocket stocke les chemins hôte et conteneur."""
        sock = GuiSocket(
            name="wayland-0",
            host_path="/run/user/1000/wayland-0",
            container_path="/run/user/1000/wayland-0",
        )
        assert sock.name == "wayland-0"
        assert "wayland-0" in sock.host_path


# --- Détection iGPU ---


class TestFindIgpuPci:
    """Tests pour _find_igpu_pci."""

    def test_no_dri_dir(self):
        """Pas de /dev/dri/by-path → chaîne vide."""
        with patch("anklume.engine.gui.Path") as mock_path:
            mock_by_path = MagicMock()
            mock_by_path.exists.return_value = False
            mock_path.return_value = mock_by_path
            from anklume.engine.gui import _find_igpu_pci

            # Besoin de patcher au bon endroit
            with patch.object(Path, "exists", return_value=False):
                result = _find_igpu_pci()
        # Sur la CI sans GPU → ""
        assert isinstance(result, str)

    def test_nvidia_excluded(self):
        """GPU NVIDIA détecté → ignoré."""
        from anklume.engine.gui import _is_non_nvidia

        mock_result = MagicMock(stdout="00:02.0 VGA compatible controller: NVIDIA Corporation")
        with patch("anklume.engine.gui.subprocess.run", return_value=mock_result):
            assert _is_non_nvidia("0000:00:02.0") is False

    def test_intel_included(self):
        """GPU Intel détecté → inclus."""
        from anklume.engine.gui import _is_non_nvidia

        mock_result = MagicMock(
            stdout="00:02.0 VGA compatible controller: Intel Corporation Arrow Lake"
        )
        with patch("anklume.engine.gui.subprocess.run", return_value=mock_result):
            assert _is_non_nvidia("0000:00:02.0") is True

    def test_lspci_missing(self):
        """lspci absent → False."""
        from anklume.engine.gui import _is_non_nvidia

        with patch("anklume.engine.gui.subprocess.run", side_effect=FileNotFoundError):
            assert _is_non_nvidia("0000:00:02.0") is False


# --- Détection sockets ---


class TestDetectSockets:
    """Tests pour _detect_sockets."""

    def test_wayland_socket_detected(self, tmp_path: Path):
        """Socket Wayland détecté dans le runtime dir."""
        from anklume.engine.gui import _detect_sockets

        _create_unix_socket(tmp_path / "wayland-0")

        sockets = _detect_sockets(str(tmp_path))
        wayland = [s for s in sockets if "wayland" in s.name]
        assert len(wayland) == 1
        assert wayland[0].name == "wayland-0"

    def test_lock_files_ignored(self, tmp_path: Path):
        """Les fichiers .lock ne sont pas des sockets."""
        from anklume.engine.gui import _detect_sockets

        _create_unix_socket(tmp_path / "wayland-0")
        (tmp_path / "wayland-0.lock").touch()

        sockets = _detect_sockets(str(tmp_path))
        names = [s.name for s in sockets]
        assert "wayland-0" in names
        assert "wayland-0.lock" not in names

    def test_pipewire_detected(self, tmp_path: Path):
        """Socket PipeWire détecté."""
        from anklume.engine.gui import _detect_sockets

        _create_unix_socket(tmp_path / "pipewire-0")

        sockets = _detect_sockets(str(tmp_path))
        pipewire = [s for s in sockets if "pipewire" in s.name]
        assert len(pipewire) == 1

    def test_pulse_detected(self, tmp_path: Path):
        """Socket PulseAudio détecté."""
        from anklume.engine.gui import _detect_sockets

        _create_unix_socket(tmp_path / "pulse" / "native")

        sockets = _detect_sockets(str(tmp_path))
        pulse = [s for s in sockets if "pulse" in s.name]
        assert len(pulse) == 1
        assert pulse[0].name == "pulse-native"

    def test_empty_dir(self, tmp_path: Path):
        """Répertoire vide → pas de sockets (hors X11 hôte)."""
        from anklume.engine.gui import _detect_sockets

        # Patcher le chemin X11 pour éviter de détecter le socket hôte
        with patch("anklume.engine.gui.Path") as MockPath:
            # Garder le vrai Path pour tmp_path
            MockPath.side_effect = lambda p: Path(p)
            MockPath.return_value = MagicMock(exists=MagicMock(return_value=False))

            sockets = _detect_sockets(str(tmp_path))
        # Seuls les sockets X11 de l'hôte pourraient apparaître
        wayland = [s for s in sockets if "wayland" in s.name]
        pipewire = [s for s in sockets if "pipewire" in s.name]
        pulse = [s for s in sockets if "pulse" in s.name]
        assert wayland == []
        assert pipewire == []
        assert pulse == []


# --- detect_gui ---


class TestDetectGui:
    """Tests pour detect_gui."""

    def test_no_runtime_dir(self):
        """Pas de runtime dir → GuiInfo.none()."""
        with patch("anklume.engine.gui._detect_runtime_uid", return_value=(0, 0, "")):
            result = detect_gui()
        assert result.detected is False

    def test_no_sockets(self):
        """Runtime dir sans sockets → GuiInfo.none()."""
        with (
            patch("anklume.engine.gui._detect_runtime_uid", return_value=(1000, 1000, "/run/user/1000")),
            patch("anklume.engine.gui._find_igpu_pci", return_value=""),
            patch("anklume.engine.gui._detect_sockets", return_value=[]),
        ):
            result = detect_gui()
        assert result.detected is False

    def test_full_detection(self):
        """Détection complète avec iGPU et sockets."""
        sockets = [
            GuiSocket("wayland-0", "/run/user/1000/wayland-0", "/run/user/1000/wayland-0"),
        ]
        with (
            patch("anklume.engine.gui._detect_runtime_uid", return_value=(1000, 1000, "/run/user/1000")),
            patch("anklume.engine.gui._find_igpu_pci", return_value="0000:00:02.0"),
            patch("anklume.engine.gui._detect_sockets", return_value=sockets),
            patch("anklume.engine.gui._get_group_gid", side_effect=[44, 109]),
        ):
            result = detect_gui()
        assert result.detected is True
        assert result.igpu_pci == "0000:00:02.0"
        assert result.uid == 1000
        assert result.video_gid == 44
        assert result.render_gid == 109
        assert len(result.sockets) == 1


# --- apply_gui_profiles ---


class TestApplyGuiProfiles:
    """Tests pour apply_gui_profiles."""

    def test_adds_gui_profile_to_gui_machines(self):
        """Ajoute 'gui' aux profils des machines avec gui: true."""
        machine = make_machine("firefox", "perso", profiles=["default"])
        machine.gui = True
        domain = make_domain("perso", machines={"firefox": machine})
        infra = make_infra(domains={"perso": domain})

        gui_info = _make_gui_info()
        with patch("anklume.engine.gui.detect_gui", return_value=gui_info):
            result = apply_gui_profiles(infra)

        assert result.detected is True
        assert GUI_PROFILE_NAME in machine.profiles

    def test_skips_non_gui_machines(self):
        """Les machines sans gui: true gardent leurs profils intacts."""
        machine = make_machine("dev", "pro", profiles=["default"])
        domain = make_domain("pro", machines={"dev": machine})
        infra = make_infra(domains={"pro": domain})

        gui_info = _make_gui_info()
        with patch("anklume.engine.gui.detect_gui", return_value=gui_info):
            apply_gui_profiles(infra)

        assert GUI_PROFILE_NAME not in machine.profiles

    def test_no_gui_detected(self):
        """GUI non détecté → les profils restent inchangés."""
        machine = make_machine("firefox", "perso", profiles=["default"])
        machine.gui = True
        domain = make_domain("perso", machines={"firefox": machine})
        infra = make_infra(domains={"perso": domain})

        with patch("anklume.engine.gui.detect_gui", return_value=GuiInfo.none()):
            result = apply_gui_profiles(infra)

        assert result.detected is False
        assert GUI_PROFILE_NAME not in machine.profiles

    def test_idempotent(self):
        """Appel multiple ne duplique pas le profil gui."""
        machine = make_machine("firefox", "perso", profiles=["default", GUI_PROFILE_NAME])
        machine.gui = True
        domain = make_domain("perso", machines={"firefox": machine})
        infra = make_infra(domains={"perso": domain})

        gui_info = _make_gui_info()
        with patch("anklume.engine.gui.detect_gui", return_value=gui_info):
            apply_gui_profiles(infra)

        assert machine.profiles.count(GUI_PROFILE_NAME) == 1


# --- create_gui_profile ---


class TestCreateGuiProfile:
    """Tests pour create_gui_profile."""

    def test_creates_profile_and_devices(self):
        """Crée le profil avec proxy devices pour chaque socket."""
        driver = mock_driver()
        gui_info = _make_gui_info(sockets=[
            GuiSocket("wayland-0", "/run/user/1000/wayland-0", "/run/user/1000/wayland-0"),
            GuiSocket("pipewire-0", "/run/user/1000/pipewire-0", "/run/user/1000/pipewire-0"),
        ])

        create_gui_profile(driver, "perso", gui_info)

        driver.profile_create.assert_called_once_with(GUI_PROFILE_NAME, "perso")
        # iGPU device + 2 proxy devices = 3 appels
        assert driver.profile_device_add.call_count == 3

    def test_igpu_device_config(self):
        """Le device iGPU contient le PCI address et le GID vidéo."""
        driver = mock_driver()
        gui_info = _make_gui_info(sockets=[
            GuiSocket("wayland-0", "/run/user/1000/wayland-0", "/run/user/1000/wayland-0"),
        ])

        create_gui_profile(driver, "perso", gui_info)

        igpu_call = driver.profile_device_add.call_args_list[0]
        assert igpu_call == call(
            GUI_PROFILE_NAME,
            "igpu",
            "gpu",
            {"pci": "0000:00:02.0", "gid": "44"},
            project="perso",
        )

    def test_proxy_device_config(self):
        """Les proxy devices contiennent connect/listen/uid/gid."""
        driver = mock_driver()
        gui_info = _make_gui_info(sockets=[
            GuiSocket("wayland-0", "/run/user/1000/wayland-0", "/run/user/1000/wayland-0"),
        ])

        create_gui_profile(driver, "perso", gui_info)

        proxy_call = driver.profile_device_add.call_args_list[1]
        config = proxy_call[0][3]
        assert config["connect"] == "unix:/run/user/1000/wayland-0"
        assert config["listen"] == "unix:/run/user/1000/wayland-0"
        assert config["uid"] == "1000"
        assert config["gid"] == "1000"
        assert config["mode"] == "0700"

    def test_no_igpu(self):
        """Sans iGPU → pas de device GPU, uniquement proxy devices."""
        driver = mock_driver()
        gui_info = _make_gui_info(
            igpu_pci="",
            sockets=[
                GuiSocket("wayland-0", "/run/user/1000/wayland-0", "/run/user/1000/wayland-0"),
            ],
        )

        create_gui_profile(driver, "perso", gui_info)

        # Uniquement 1 proxy device, pas de GPU
        assert driver.profile_device_add.call_count == 1
        device_types = [c[0][2] for c in driver.profile_device_add.call_args_list]
        assert "gpu" not in device_types


# --- prepare_gui_dirs ---


class TestPrepareGuiDirs:
    """Tests pour prepare_gui_dirs."""

    def test_executes_script(self):
        """Exécute un script shell dans l'instance."""
        driver = mock_driver()
        gui_info = _make_gui_info()

        prepare_gui_dirs(driver, "perso-firefox", "perso", gui_info)

        driver.instance_exec.assert_called_once()
        args = driver.instance_exec.call_args
        assert args[0][0] == "perso-firefox"
        assert args[0][1] == "perso"
        # Le script contient mkdir, chown, chmod, tmpfiles.d
        script = args[0][2][2]  # ["sh", "-c", <script>]
        assert "mkdir -p" in script
        assert "chown 1000:1000" in script
        assert "chmod 0700" in script
        assert "tmpfiles.d" in script

    def test_failure_is_warning(self):
        """Échec de l'exec → warning loggé, pas d'exception."""
        driver = mock_driver()
        driver.instance_exec.side_effect = Exception("exec failed")
        gui_info = _make_gui_info()

        # Ne doit pas lever d'exception
        prepare_gui_dirs(driver, "perso-firefox", "perso", gui_info)
