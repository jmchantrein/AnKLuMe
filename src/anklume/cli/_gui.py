"""Implémentation des commandes GUI (setup gui, instance gui)."""

from __future__ import annotations

import configparser
import contextlib
import json
import logging
import os
import pwd
import subprocess
from pathlib import Path

import typer

from anklume.engine.gui import GUI_PROFILE_NAME, detect_gui
from anklume.engine.models import TRUST_COLORS

log = logging.getLogger(__name__)

# Compat : TRUST_COLORS_HEX dérivé de la source unique (models.TRUST_COLORS)
TRUST_COLORS_HEX: dict[str, str] = {k: v.hex for k, v in TRUST_COLORS.items()}

# KDE KWin rule constants
_KWIN_MATCH_SUBSTRING = 2
_KWIN_MATCH_REGEX = 3
_KWIN_RULE_FORCE = 2

# Luminance (ITU-R BT.601)
_LUMA_R, _LUMA_G, _LUMA_B = 0.299, 0.587, 0.114
_LUMA_THRESHOLD = 128

# Atténuation pour les couleurs inactives
_INACTIVE_ATTENUATION = 0.78


def _title_prefix(text: str) -> str:
    """Préfixe titre : majuscules simples (lisible, cohérent toutes polices)."""
    return text.upper()


def _hex_to_rgb(h: str) -> str:
    """Convertit #RRGGBB en R,G,B."""
    h = h.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"


def _trust_rgb(trust_level: str) -> str:
    """Retourne le RGB KDE pour un trust level."""
    return _hex_to_rgb(TRUST_COLORS_HEX.get(trust_level, "#ffd700"))


def run_setup_gui() -> None:
    """Diagnostic de l'environnement GUI de l'hôte."""
    gui = detect_gui()

    if not gui.detected:
        typer.echo("GUI non détecté — aucun socket Wayland trouvé.")
        typer.echo("Vérifiez que vous êtes sur une session graphique.")
        raise typer.Exit(1)

    typer.echo(f"UID/GID       : {gui.uid}/{gui.gid}")
    typer.echo(f"Runtime dir   : {gui.runtime_dir}")
    typer.echo(f"iGPU (PCI)    : {gui.igpu_pci or 'non détecté'}")
    typer.echo(f"Groupe video  : {gui.video_gid}")
    typer.echo(f"Groupe render : {gui.render_gid}")
    typer.echo(f"Sockets ({len(gui.sockets)}) :")
    for sock in gui.sockets:
        typer.echo(f"  {sock.name:25s} {sock.host_path}")


def run_setup_gui_fix() -> None:
    """Répare les profils GUI et conteneurs (retirer/recréer/réappliquer)."""
    gui = detect_gui()
    if not gui.detected:
        typer.echo("GUI non détecté — rien à réparer.", err=True)
        raise typer.Exit(1)

    from anklume.cli._common import load_infra
    from anklume.engine.gui import (
        create_gui_profile,
        prepare_gui_dirs,
    )
    from anklume.engine.incus_driver import IncusDriver, IncusError
    from anklume.engine.nesting import detect_nesting_context, prefix_name

    infra = load_infra()
    driver = IncusDriver()
    ctx = detect_nesting_context()
    fixed = 0

    try:
        existing = {p.name for p in driver.project_list()}
    except IncusError as exc:
        typer.echo("Impossible de lister les projets Incus.", err=True)
        raise typer.Exit(1) from exc

    for domain in infra.enabled_domains:
        project_name = prefix_name(domain.name, ctx, infra.config.nesting)

        if project_name not in existing:
            continue

        gui_machines = [m for m in domain.machines.values() if m.gui]
        if not gui_machines:
            continue

        typer.echo(f"[{project_name}] Réparation du profil {GUI_PROFILE_NAME}...")
        profile_exists = driver.profile_exists(GUI_PROFILE_NAME, project_name)

        instances = {i.name: i for i in driver.instance_list(project_name)}
        for inst in instances.values():
            if GUI_PROFILE_NAME in inst.profiles:
                try:
                    driver.instance_profile_remove(
                        inst.name,
                        GUI_PROFILE_NAME,
                        project_name,
                    )
                    typer.echo(f"  Profil retiré de {inst.name}")
                except IncusError:
                    pass

        if profile_exists:
            with contextlib.suppress(IncusError):
                driver.profile_delete(GUI_PROFILE_NAME, project_name)
        create_gui_profile(driver, project_name, gui)
        typer.echo(f"  Profil {GUI_PROFILE_NAME} recréé.")

        for machine in gui_machines:
            incus_name = prefix_name(
                machine.full_name,
                ctx,
                infra.config.nesting,
            )
            if incus_name not in instances:
                continue
            inst = instances[incus_name]
            if inst.status != "Running":
                typer.echo(f"  {incus_name} ignoré (état: {inst.status})")
                continue

            prepare_gui_dirs(driver, incus_name, project_name, gui)
            try:
                driver.instance_profile_add(
                    incus_name,
                    GUI_PROFILE_NAME,
                    project_name,
                )
                typer.echo(f"  {incus_name} : profil réappliqué.")
                fixed += 1
            except IncusError as exc:
                typer.echo(f"  {incus_name} : erreur — {exc}", err=True)

    typer.echo(f"\nRéparation terminée : {fixed} instance(s) corrigée(s).")


def run_setup_gui_recover() -> None:
    """Récupération d'urgence : force-stop, retrait profil GUI, restart.

    À utiliser quand les conteneurs sont bloqués (état Error/Running mais
    exec impossible) à cause du profil GUI qui empêche le démarrage.

    Bypasse IncusDriver volontairement : en situation d'urgence, le daemon
    peut être instable et on veut des appels directs les plus simples.
    """
    typer.echo("Récupération d'urgence GUI...\n")

    # Lister tous les projets
    result = subprocess.run(
        ["incus", "project", "list", "--format", "csv"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        typer.echo("Incus inaccessible.", err=True)
        raise typer.Exit(1)

    projects = [line.split(",")[0] for line in result.stdout.strip().splitlines()]

    recovered = 0
    for project in projects:
        # Lister les instances avec leurs profils (JSON pour éviter N+1)
        inst_result = subprocess.run(
            ["incus", "list", "--project", project, "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
        if inst_result.returncode != 0:
            continue

        try:
            instances = json.loads(inst_result.stdout)
        except json.JSONDecodeError:
            continue

        for inst in instances:
            name = inst.get("name", "")
            status = inst.get("status", "")
            profiles = inst.get("profiles", [])

            if GUI_PROFILE_NAME not in profiles:
                continue

            typer.echo(f"[{project}] {name} ({status}) — profil gui détecté")

            # 1. Force stop
            if status in ("Running", "Error"):
                typer.echo("  Force stop...")
                subprocess.run(
                    ["incus", "stop", name, "--project", project, "--force"],
                    capture_output=True,
                    check=False,
                    timeout=30,
                )

            # 2. Retirer le profil gui
            typer.echo(f"  Retrait profil {GUI_PROFILE_NAME}...")
            subprocess.run(
                ["incus", "profile", "remove", name, GUI_PROFILE_NAME, "--project", project],
                capture_output=True,
                check=False,
            )

            # 3. Redémarrer
            typer.echo("  Redémarrage...")
            start_result = subprocess.run(
                ["incus", "start", name, "--project", project],
                capture_output=True,
                text=True,
                check=False,
            )
            if start_result.returncode == 0:
                typer.echo(f"  {name} démarré.")
                recovered += 1
            else:
                typer.echo(
                    f"  Échec démarrage : {start_result.stderr.strip()[:100]}",
                    err=True,
                )

    # Supprimer les profils gui orphelins
    for project in projects:
        subprocess.run(
            ["incus", "profile", "delete", GUI_PROFILE_NAME, "--project", project],
            capture_output=True,
            check=False,
        )

    typer.echo(f"\nRécupération terminée : {recovered} instance(s) redémarrée(s).")
    typer.echo("Pour réappliquer le GUI : anklume setup gui --fix")


def _gui_user_home(gui_uid: int) -> Path:
    """Résout le home directory de l'utilisateur graphique."""
    try:
        return Path(pwd.getpwuid(gui_uid).pw_dir)
    except KeyError:
        # Fallback standard : /home/<username> via uid
        # On refuse les UIDs système (< 1000) sans entrée passwd
        if gui_uid < 1000:
            return Path("/root") if gui_uid == 0 else Path("/var/empty")
        return Path(f"/home/user{gui_uid}")


def _chown_for_user(path: Path, uid: int) -> None:
    """Assure le bon ownership d'un fichier pour l'utilisateur GUI."""
    try:
        pw = pwd.getpwuid(uid)
        os.chown(path, pw.pw_uid, pw.pw_gid)
    except (KeyError, OSError):
        pass


# Chemin de la lib LD_PRELOAD sur l'hôte et dans le conteneur
_TITLE_LIB_CONTAINER = "/usr/local/lib/libanklume-title.so"

# Source C — intercepte xdg_toplevel::set_title (opcode 2) via libwayland
# pour préfixer le titre de fenêtre avec ANKLUME_TITLE_PREFIX.
# Compatible GTK3 (marshal_array) et GTK4/Qt6 (marshal_array_flags).
_TITLE_PREFIX_C = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
struct wl_proxy; struct wl_interface;
union wl_argument {
    int32_t i; uint32_t u; int32_t f;
    const char *s; void *o; uint32_t n; void *a; int32_t h;
};
extern const char *wl_proxy_get_class(struct wl_proxy *);
static const char *_pfx(struct wl_proxy *p, uint32_t op,
    union wl_argument *a) {
    if (op != 2 || !a || !a[0].s) return NULL;
    const char *c = wl_proxy_get_class(p);
    if (!c || strcmp(c, "xdg_toplevel")) return NULL;
    return getenv("ANKLUME_TITLE_PREFIX");
}
static char *_mk(const char *pfx, const char *t) {
    size_t l = strlen(pfx) + strlen(t) + 6;
    char *b = malloc(l);
    if (b) snprintf(b, l, "%s \xe2\x80\x94 %s", pfx, t);
    return b;
}
typedef struct wl_proxy *(*fflags_t)(struct wl_proxy *, uint32_t,
    const struct wl_interface *, uint32_t, uint32_t, union wl_argument *);
static fflags_t rf;
struct wl_proxy *wl_proxy_marshal_array_flags(struct wl_proxy *p,
    uint32_t op, const struct wl_interface *i, uint32_t v, uint32_t f,
    union wl_argument *a) {
    if (!rf) rf = (fflags_t)dlsym(RTLD_NEXT, __func__);
    const char *px = _pfx(p, op, a);
    if (px) {
        char *t = _mk(px, a[0].s);
        if (t) {
            const char *o = a[0].s; a[0].s = t;
            struct wl_proxy *r = rf(p, op, i, v, f, a);
            a[0].s = o; free(t); return r;
        }
    }
    return rf(p, op, i, v, f, a);
}
typedef void (*farray_t)(struct wl_proxy *, uint32_t, union wl_argument *);
static farray_t ra;
void wl_proxy_marshal_array(struct wl_proxy *p, uint32_t op,
    union wl_argument *a) {
    if (!ra) ra = (farray_t)dlsym(RTLD_NEXT, __func__);
    const char *px = _pfx(p, op, a);
    if (px) {
        char *t = _mk(px, a[0].s);
        if (t) {
            const char *o = a[0].s; a[0].s = t;
            ra(p, op, a); a[0].s = o; free(t); return;
        }
    }
    ra(p, op, a);
}
"""


def _ensure_title_lib() -> Path | None:
    """Compile la lib LD_PRELOAD pour le préfixe titre (une seule fois).

    La lib intercepte xdg_toplevel::set_title dans libwayland-client
    et préfixe le titre avec la valeur de ANKLUME_TITLE_PREFIX.
    Fonctionne pour toute application Wayland (GTK, Qt, SDL, etc.).
    """
    lib_path = Path.home() / ".local" / "share" / "anklume" / "libtitle-prefix.so"
    if lib_path.exists():
        return lib_path

    import tempfile

    lib_path.parent.mkdir(parents=True, exist_ok=True)
    fd, c_path = tempfile.mkstemp(suffix=".c")
    c_file = Path(c_path)
    os.close(fd)
    try:
        c_file.write_text(_TITLE_PREFIX_C)
        result = subprocess.run(
            ["gcc", "-shared", "-fPIC", "-O2", "-o", str(lib_path), str(c_file), "-ldl"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            log.warning("Compilation libtitle-prefix échouée : %s", result.stderr[:200])
            lib_path.unlink(missing_ok=True)
            return None
        log.info("libtitle-prefix.so compilée : %s", lib_path)
        return lib_path
    finally:
        c_file.unlink(missing_ok=True)


def _push_title_lib(
    driver: object,
    incus_name: str,
    project: str,
    lib_path: Path,
) -> bool:
    """Pousse la lib LD_PRELOAD dans le conteneur via file_push."""
    try:
        driver.instance_exec(  # type: ignore[attr-defined]
            incus_name,
            project,
            ["mkdir", "-p", "/usr/local/lib"],
        )
        driver.file_push(  # type: ignore[attr-defined]
            incus_name,
            project,
            str(lib_path),
            _TITLE_LIB_CONTAINER,
        )
        return True
    except Exception:
        log.debug("Push libtitle-prefix échoué pour %s", incus_name)
        return False


def _ensure_color_scheme(trust_level: str, user_home: Path, gui_uid: int = 0) -> str:
    """Crée le color scheme KDE pour un trust level.

    Copie BreezeLight et remplace [General], [WM], [Colors:Header] avec
    les couleurs trust. KWin utilise Header pour le rendu Breeze et WM
    pour la compatibilité avec d'autres décorations.

    Retourne le nom du color scheme (utilisable dans kwinrulesrc decocolor).
    """
    scheme_name = f"anklume-{trust_level}"
    rgb = _trust_rgb(trust_level)

    # Couleur inactive = même teinte atténuée
    parts = [int(x) for x in rgb.split(",")]
    inactive_rgb = ",".join(str(max(0, int(v * _INACTIVE_ATTENUATION))) for v in parts)
    # Foreground adapté à la luminosité (WCAG AA via TrustColor)
    tc = TRUST_COLORS.get(trust_level)
    fg = tc.fg_rgb if tc else "0,0,0"
    is_light = fg == "0,0,0"
    fg_inactive = "50,50,50" if is_light else "200,200,200"

    schemes_dir = user_home / ".local" / "share" / "color-schemes"
    schemes_dir.mkdir(parents=True, exist_ok=True)
    scheme_file = schemes_dir / f"{scheme_name}.colors"

    # Copier BreezeLight comme base (Breeze decoration lit les couleurs
    # depuis le scheme complet, pas uniquement [WM])
    base = Path("/usr/share/color-schemes/BreezeLight.colors")
    if not base.exists():
        base = Path("/usr/share/color-schemes/BreezeDark.colors")
    lines = base.read_text().splitlines() if base.exists() else ["[General]", f"Name={scheme_name}"]

    # Remplacements par section
    section_replacements: dict[str, dict[str, str]] = {
        "[WM]": {
            "activeBackground": rgb,
            "activeForeground": fg,
            "activeBlend": rgb,
            "inactiveBackground": inactive_rgb,
            "inactiveBlend": inactive_rgb,
            "inactiveForeground": fg_inactive,
        },
        "[Colors:Header]": {
            "BackgroundNormal": rgb,
            "BackgroundAlternate": rgb,
            "ForegroundNormal": fg,
        },
        "[Colors:Header][Inactive]": {
            "BackgroundNormal": inactive_rgb,
            "BackgroundAlternate": inactive_rgb,
            "ForegroundNormal": fg_inactive,
        },
    }

    output: list[str] = []
    current_section = ""
    for line in lines:
        # Détecter les sections
        if line.startswith("["):
            current_section = line.strip()
            output.append(line)
            continue

        # [General] — remplacer Name, ColorScheme, supprimer traductions
        if current_section == "[General]":
            if line.startswith("Name="):
                output.append(f"Name=anklume {trust_level}")
                continue
            if line.startswith("ColorScheme="):
                output.append(f"ColorScheme={scheme_name}")
                continue
            if line.startswith("Name["):
                continue

        # Remplacements par section (WM, Header, Header Inactive)
        repl = section_replacements.get(current_section)
        if repl and "=" in line:
            key = line.split("=")[0]
            if key in repl:
                output.append(f"{key}={repl[key]}")
                continue

        output.append(line)

    scheme_file.write_text("\n".join(output))

    if gui_uid:
        _chown_for_user(scheme_file, gui_uid)
    return scheme_name


def _install_kwin_rule(
    instance_name: str,
    trust_level: str,
    app_id: str,
    gui_uid: int,
    *,
    title_prefix: str | None = None,
) -> None:
    """Installe une règle KDE window pour colorer la barre de titre."""
    user_home = _gui_user_home(gui_uid)

    # Créer le color scheme KDE correspondant au trust level
    scheme_name = _ensure_color_scheme(trust_level, user_home, gui_uid)

    # Fichier kwinrulesrc dans la config KDE de l'utilisateur graphique
    kwin_rules = user_home / ".config" / "kwinrulesrc"

    config = configparser.ConfigParser()
    config.optionxform = str  # préserver la casse
    if kwin_rules.exists():
        config.read(str(kwin_rules))

    section = f"anklume-{instance_name}"

    # Trouver ou créer le numéro de règle
    general = config["General"] if "General" in config else {}
    existing_count = int(general.get("count", "0"))
    rule_ids = general.get("rules", "").split(",") if general.get("rules") else []

    if section not in config:
        # Nouvelle règle
        existing_count += 1
        rule_ids.append(section)
        if "General" not in config:
            config["General"] = {}
        config["General"]["count"] = str(existing_count)
        config["General"]["rules"] = ",".join(rule_ids)

    rule: dict[str, str | int] = {
        "Description": f"anklume: {instance_name} ({trust_level})",
        "wmclass": app_id,
        "wmclassmatch": _KWIN_MATCH_SUBSTRING,
        "decocolor": scheme_name,
        "decocolorrule": _KWIN_RULE_FORCE,
    }
    if title_prefix:
        rule["title"] = title_prefix
        rule["titlematch"] = _KWIN_MATCH_REGEX
    config[section] = rule

    # Écrire au format KDE natif (key=value sans espaces)
    kwin_rules.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for sect in config.sections():
        lines.append(f"[{sect}]")
        for key, val in config[sect].items():
            lines.append(f"{key}={val}")
        lines.append("")
    kwin_rules.write_text("\n".join(lines))

    _chown_for_user(kwin_rules, gui_uid)

    # Recharger kwin via qdbus6 sur le bus dbus de l'utilisateur graphique
    runtime_dir = f"/run/user/{gui_uid}"
    env = {"DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus"}
    subprocess.run(
        ["qdbus6", "org.kde.KWin", "/KWin", "org.kde.KWin.reconfigure"],
        check=False,
        capture_output=True,
        env=env,
    )


def run_instance_gui(instance: str, app: str) -> None:
    """Lance une application graphique dans une instance existante."""
    gui = detect_gui()
    if not gui.detected:
        typer.echo("GUI non détecté sur l'hôte.", err=True)
        raise typer.Exit(1)

    from anklume.cli._common import load_infra
    from anklume.engine.incus_driver import IncusDriver, IncusError
    from anklume.engine.nesting import detect_nesting_context, prefix_name

    infra = load_infra()
    ctx = detect_nesting_context()

    # Trouver la machine, son projet et son trust level
    machine = None
    project_name = None
    trust_level = "semi-trusted"
    for domain in infra.enabled_domains:
        for m in domain.machines.values():
            if m.full_name == instance:
                machine = m
                trust_level = domain.trust_level
                project_name = prefix_name(
                    domain.name,
                    ctx,
                    infra.config.nesting,
                )
                break
        if machine:
            break

    if not machine or not project_name:
        typer.echo(f"Instance '{instance}' introuvable.", err=True)
        raise typer.Exit(1)

    incus_name = prefix_name(machine.full_name, ctx, infra.config.nesting)

    # VM → console SPICE
    if machine.type == "vm":
        typer.echo(f"VM détectée — ouverture console SPICE pour {instance}...")
        subprocess.Popen(
            ["incus", "console", incus_name, "--type=vga", "--project", project_name],
            start_new_session=True,
        )
        typer.echo(f"Console SPICE ouverte pour {instance}.")
        return

    # Conteneur LXC → Wayland proxy
    if GUI_PROFILE_NAME not in machine.profiles and not machine.gui:
        typer.echo(
            f"L'instance '{instance}' n'a pas gui: true. "
            "Ajoutez gui: true dans le domaine et relancez anklume apply.",
            err=True,
        )
        raise typer.Exit(1)

    import shlex

    driver = IncusDriver()
    uid_str = str(int(gui.uid))  # force int → str, refuse non-numériques
    gid_str = str(int(gui.gid))
    rd = shlex.quote(gui.runtime_dir)

    # Résoudre utilisateur et home en une seule commande
    try:
        result = driver.instance_exec(
            incus_name,
            project_name,
            ["getent", "passwd", uid_str],
        )
        passwd_parts = (result.stdout.strip() if result.stdout else "").split(":")
        container_user = passwd_parts[0] if passwd_parts[0] else ""
        container_home = passwd_parts[5] if len(passwd_parts) > 5 else ""
    except (IncusError, AttributeError):
        container_user = ""
        container_home = ""

    if not container_user:
        typer.echo(f"Aucun utilisateur UID {uid_str}, création...")
        try:
            driver.instance_exec(
                incus_name,
                project_name,
                ["useradd", "-m", "-u", uid_str, "-s", "/bin/bash", "user"],
            )
            # Groupes vidéo + runtime dir séparément
            driver.instance_exec(
                incus_name,
                project_name,
                [
                    "sh",
                    "-c",
                    f"usermod -aG video,render user 2>/dev/null; "
                    f"mkdir -p {rd} && chown {uid_str}:{gid_str} {rd}",
                ],
            )
            container_user = "user"
            container_home = f"/home/{container_user}"
        except IncusError as exc:
            typer.echo(f"Impossible de créer l'utilisateur : {exc}", err=True)
            raise typer.Exit(1) from None

    if not container_home:
        container_home = f"/home/{container_user}"

    # Variables d'environnement
    wayland_display = ""
    x_display = ""
    for sock in gui.sockets:
        if "wayland" in sock.name:
            wayland_display = Path(sock.container_path).name
        if sock.name.startswith("x11-"):
            x_display = ":" + sock.name.removeprefix("x11-X")

    app_id = f"anklume.{instance}"
    env_vars = {
        "HOME": container_home,
        "XDG_RUNTIME_DIR": gui.runtime_dir,
        "XDG_CACHE_HOME": f"{container_home}/.cache",
        "XDG_CONFIG_HOME": f"{container_home}/.config",
        "WAYLAND_DISPLAY": wayland_display,
        "XDG_SESSION_TYPE": "wayland",
        "QT_QPA_PLATFORM": "wayland",
        # Forcer les décorations serveur (KWin dessine la barre de titre)
        "MOZ_GTK_TITLEBAR_DECORATION": "server",
        "GTK_CSD": "0",
        # App ID par instance pour discrimination visuelle
        "GDK_PROGRAM_CLASS": app_id,
        "QT_WAYLAND_APP_ID": app_id,
        "SDL_VIDEO_WAYLAND_WMCLASS": app_id,
    }
    if x_display:
        env_vars["DISPLAY"] = x_display

    # Pulse via socket
    pulse_path = f"{gui.runtime_dir}/pulse/native"
    for sock in gui.sockets:
        if sock.name == "pulse-native":
            env_vars["PULSE_SERVER"] = f"unix:{pulse_path}"
            break

    # Préfixe titre générique via LD_PRELOAD (toute app Wayland)
    bold_prefix: str | None = None
    title_lib = _ensure_title_lib()
    if title_lib and _push_title_lib(
        driver,
        incus_name,
        project_name,
        title_lib,
    ):
        bold_prefix = _title_prefix(instance)
        env_vars["LD_PRELOAD"] = _TITLE_LIB_CONTAINER
        env_vars["ANKLUME_TITLE_PREFIX"] = bold_prefix

    # Installer la règle KDE window (couleur trust level)
    # title_prefix permet de ne cibler que les fenêtres du conteneur
    app_wmclass = app.split()[0].split("/")[-1]
    _install_kwin_rule(
        instance,
        trust_level,
        app_wmclass,
        gui.uid,
        title_prefix=bold_prefix,
    )

    # Reconstruire env_args après ajout LD_PRELOAD
    env_args = []
    for key, val in env_vars.items():
        env_args.extend(["--env", f"{key}={val}"])

    # Si pas d'app et rôle desktop → lancer le bureau complet
    if app == "bash" and "desktop" in machine.roles:
        app = "dbus-run-session kwin_wayland --xwayland plasmashell konsole dolphin"

    # Commandes composées (avec espaces) → passer via sh -c
    app_args = ["sh", "-c", app] if " " in app else [app]

    cmd = [
        "incus",
        "exec",
        incus_name,
        "--project",
        project_name,
        "--user",
        uid_str,
        "--group",
        str(gui.gid),
        *env_args,
        "--",
        *app_args,
    ]

    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    color = TRUST_COLORS_HEX.get(trust_level, "#ffd700")
    typer.echo(f"{app} lancé dans {instance} [{trust_level} {color}]")
