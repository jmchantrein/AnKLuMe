"""Implémentation de `anklume doctor`."""

from __future__ import annotations

import json

import typer

from anklume.engine.doctor import run_doctor
from anklume.engine.incus_driver import IncusDriver


def run_doctor_cmd(fix: bool = False, json_output: bool = False) -> None:
    """Diagnostic automatique de l'infrastructure."""
    # Charger l'infra si possible (optionnel)
    infra = None
    try:
        from anklume.cli._common import load_infra

        infra = load_infra()
    except Exception:  # noqa: S110
        pass  # Infra optionnelle — doctor fonctionne sans

    # Driver optionnel
    driver = None
    try:
        driver = IncusDriver()
    except Exception:  # noqa: S110
        pass  # Driver optionnel — checks système uniquement

    report = run_doctor(driver=driver, infra=infra, fix=fix)

    if json_output:
        data = [
            {
                "name": c.name,
                "status": c.status,
                "message": c.message,
                "fix_command": c.fix_command,
            }
            for c in report.checks
        ]
        typer.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    status_icons = {"ok": "✓", "warning": "⚠", "error": "✗"}

    for check in report.checks:
        icon = status_icons.get(check.status, "?")
        typer.echo(f"{icon} {check.name:<25s} {check.message}")
        if check.fix_command and check.status != "ok":
            typer.echo(f"  → {check.fix_command}")

    typer.echo(
        f"\nRésultat : {report.ok_count} ok, "
        f"{report.warning_count} warning, "
        f"{report.error_count} erreur"
    )
