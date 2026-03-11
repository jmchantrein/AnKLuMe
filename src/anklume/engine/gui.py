"""GUI passthrough — sessions graphiques Wayland dans les conteneurs.

Détecte le iGPU (non-NVIDIA), les sockets Wayland/PipeWire/PulseAudio
de l'hôte, et construit le profil Incus pour l'affichage graphique
des conteneurs sur le bureau hôte.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from anklume.engine.incus_driver import IncusDriver
from anklume.engine.models import Infrastructure

log = logging.getLogger(__name__)

GUI_PROFILE_NAME = "gui"


@dataclass
class GuiSocket:
    """Socket hôte à partager via proxy device."""

    name: str
    host_path: str
    container_path: str


@dataclass
class GuiInfo:
    """Informations GUI détectées sur l'hôte."""

    detected: bool
    igpu_pci: str  # ex: "0000:00:02.0", vide si absent
    uid: int
    gid: int
    video_gid: int
    render_gid: int
    runtime_dir: str
    sockets: list[GuiSocket] = field(default_factory=list)

    @classmethod
    def none(cls) -> GuiInfo:
        """Sentinel : GUI non disponible."""
        return cls(
            detected=False,
            igpu_pci="",
            uid=0,
            gid=0,
            video_gid=0,
            render_gid=0,
            runtime_dir="",
        )


def _find_igpu_pci() -> str:
    """Trouve le PCI address du iGPU (premier GPU non-NVIDIA dans /dev/dri/by-path/)."""
    by_path = Path("/dev/dri/by-path")
    if not by_path.exists():
        return ""

    for link in sorted(by_path.iterdir()):
        if not link.name.endswith("-card"):
            continue
        # pci-0000:00:02.0-card → 0000:00:02.0
        pci_addr = link.name.removesuffix("-card").removeprefix("pci-")
        # Vérifier que ce GPU est bien non-NVIDIA via lspci
        if _is_non_nvidia(pci_addr):
            return pci_addr
    return ""


def _is_non_nvidia(pci_addr: str) -> bool:
    """Vérifie qu'un device PCI n'est pas NVIDIA."""
    try:
        result = subprocess.run(
            ["lspci", "-s", pci_addr],
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout.lower()
        return "nvidia" not in output and ("vga" in output or "display" in output)
    except FileNotFoundError:
        return False


def _detect_runtime_uid() -> tuple[int, int, str]:
    """Détecte UID, GID et XDG_RUNTIME_DIR de l'utilisateur graphique.

    Cherche le premier /run/user/<uid> contenant un socket Wayland.
    """
    run_user = Path("/run/user")
    if not run_user.exists():
        return 0, 0, ""

    for uid_dir in sorted(run_user.iterdir()):
        if not uid_dir.is_dir():
            continue
        try:
            uid = int(uid_dir.name)
        except ValueError:
            continue
        if uid < 1000:
            continue
        # Chercher un socket wayland-*
        wayland_sockets = list(uid_dir.glob("wayland-*"))
        wayland_sockets = [s for s in wayland_sockets if not s.name.endswith(".lock")]
        if wayland_sockets:
            stat = uid_dir.stat()
            return uid, stat.st_gid, str(uid_dir)
    return 0, 0, ""


def _get_group_gid(name: str) -> int:
    """Récupère le GID d'un groupe système."""
    try:
        import grp

        return grp.getgrnam(name).gr_gid
    except KeyError:
        return 0


def _detect_sockets(runtime_dir: str) -> list[GuiSocket]:
    """Détecte les sockets GUI disponibles dans le runtime dir."""
    sockets: list[GuiSocket] = []
    rd = Path(runtime_dir)

    # Wayland
    for sock in sorted(rd.glob("wayland-*")):
        if sock.name.endswith(".lock"):
            continue
        if _is_socket(sock):
            sockets.append(
                GuiSocket(
                    name=sock.name,
                    host_path=str(sock),
                    container_path=f"{runtime_dir}/{sock.name}",
                )
            )

    # PipeWire
    for name in ("pipewire-0", "pipewire-0-manager"):
        sock = rd / name
        if _is_socket(sock):
            sockets.append(
                GuiSocket(
                    name=name,
                    host_path=str(sock),
                    container_path=f"{runtime_dir}/{name}",
                )
            )

    # PulseAudio
    pulse_sock = rd / "pulse" / "native"
    if _is_socket(pulse_sock):
        sockets.append(
            GuiSocket(
                name="pulse-native",
                host_path=str(pulse_sock),
                container_path=f"{runtime_dir}/pulse/native",
            )
        )

    # X11 (fallback pour apps non-Wayland)
    x11_dir = Path("/tmp/.X11-unix")  # noqa: S108
    if x11_dir.exists():
        for sock in sorted(x11_dir.glob("X*")):
            if _is_socket(sock):
                sockets.append(
                    GuiSocket(
                        name=f"x11-{sock.name}",
                        host_path=str(sock),
                        container_path=f"/tmp/.X11-unix/{sock.name}",  # noqa: S108
                    )
                )
                break  # Premier display uniquement

    return sockets


def _is_socket(path: Path) -> bool:
    """Vérifie qu'un path est bien un socket Unix."""
    try:
        return path.is_socket()
    except OSError:
        return False


def detect_gui() -> GuiInfo:
    """Détecte l'environnement graphique de l'hôte."""
    uid, gid, runtime_dir = _detect_runtime_uid()
    if not runtime_dir:
        log.debug("Aucun runtime dir avec socket Wayland trouvé")
        return GuiInfo.none()

    igpu_pci = _find_igpu_pci()
    sockets = _detect_sockets(runtime_dir)

    if not sockets:
        log.debug("Aucun socket GUI détecté dans %s", runtime_dir)
        return GuiInfo.none()

    video_gid = _get_group_gid("video")
    render_gid = _get_group_gid("render")

    info = GuiInfo(
        detected=True,
        igpu_pci=igpu_pci,
        uid=uid,
        gid=gid,
        video_gid=video_gid,
        render_gid=render_gid,
        runtime_dir=runtime_dir,
        sockets=sockets,
    )
    log.info(
        "GUI détecté : iGPU=%s, uid=%d, %d sockets",
        igpu_pci or "aucun",
        uid,
        len(sockets),
    )
    return info


def apply_gui_profiles(infra: Infrastructure) -> GuiInfo:
    """Détecte le GUI et enrichit les profils des machines gui: true.

    Ajoute 'gui' aux profils de chaque machine avec gui: true dans les
    domaines activés, si un environnement graphique est détecté.
    """
    # Court-circuit : éviter la détection système si aucune machine GUI
    has_gui = any(m.gui for d in infra.enabled_domains for m in d.machines.values())
    if not has_gui:
        return GuiInfo.none()

    gui_info = detect_gui()

    if not gui_info.detected:
        return gui_info

    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if machine.gui and GUI_PROFILE_NAME not in machine.profiles:
                machine.profiles.append(GUI_PROFILE_NAME)

    return gui_info


def create_gui_profile(
    driver: IncusDriver,
    project: str,
    gui_info: GuiInfo,
) -> None:
    """Crée le profil GUI complet dans un projet Incus.

    Ajoute les proxy devices pour chaque socket détecté,
    le GPU intégré, et le mapping UID/GID.
    """
    driver.profile_create(GUI_PROFILE_NAME, project)

    uid_str = str(gui_info.uid)
    gid_str = str(gui_info.gid)

    # iGPU (si détecté)
    if gui_info.igpu_pci:
        driver.profile_device_add(
            GUI_PROFILE_NAME,
            "igpu",
            "gpu",
            {
                "pci": gui_info.igpu_pci,
                "gid": str(gui_info.video_gid) if gui_info.video_gid else gid_str,
            },
            project=project,
        )

    # Proxy devices pour chaque socket
    for sock in gui_info.sockets:
        driver.profile_device_add(
            GUI_PROFILE_NAME,
            sock.name,
            "proxy",
            {
                "bind": "instance",
                "connect": f"unix:{sock.host_path}",
                "listen": f"unix:{sock.container_path}",
                "uid": uid_str,
                "gid": gid_str,
                "security.uid": uid_str,
                "security.gid": gid_str,
                "mode": "0700",
            },
            project=project,
        )


def prepare_gui_dirs(
    driver: IncusDriver,
    instance: str,
    project: str,
    gui_info: GuiInfo,
) -> None:
    """Crée les répertoires nécessaires aux sockets dans le conteneur.

    Doit être appelé avant d'appliquer le profil GUI à une instance,
    sinon les proxy devices échouent au bind.
    """
    import shlex

    uid_str = str(int(gui_info.uid))  # force int → str, refuse non-numériques
    gid_str = str(int(gui_info.gid))
    runtime_dir = shlex.quote(gui_info.runtime_dir)

    # Créer les répertoires + installer un tmpfiles.d pour le boot
    script = (
        f"mkdir -p {runtime_dir}/pulse /tmp/.X11-unix && "
        f"chown {uid_str}:{gid_str} {runtime_dir} && "
        f"chmod 0700 {runtime_dir} && "
        f"mkdir -p /etc/tmpfiles.d && "
        f"printf 'd {runtime_dir} 0700 {uid_str} {gid_str} -\\n"
        f"d {runtime_dir}/pulse 0700 {uid_str} {gid_str} -\\n"
        f"d /tmp/.X11-unix 1777 root root -\\n'"
        f" > /etc/tmpfiles.d/anklume-gui.conf"
    )
    try:
        driver.instance_exec(instance, project, ["sh", "-c", script])
    except Exception:
        log.warning("Préparation des répertoires GUI échouée pour %s", instance)
