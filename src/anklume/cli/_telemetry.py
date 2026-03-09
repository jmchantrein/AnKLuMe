"""CLI telemetry — métriques d'usage (§33)."""

from __future__ import annotations

import typer


def run_telemetry_on() -> None:
    """Active la télémétrie."""
    from anklume.engine.telemetry import enable
    from anklume.i18n import t

    enable()
    typer.echo(t("cli.telemetry.enabled"))


def run_telemetry_off() -> None:
    """Désactive la télémétrie."""
    from anklume.engine.telemetry import disable
    from anklume.i18n import t

    disable()
    typer.echo(t("cli.telemetry.disabled"))


def run_telemetry_status() -> None:
    """Affiche l'état et le résumé des métriques."""
    from anklume.engine.telemetry import get_stats, is_enabled
    from anklume.i18n import t

    if not is_enabled():
        typer.echo(t("cli.telemetry.status_off"))
        return

    stats = get_stats()
    typer.echo(t("cli.telemetry.status_on", count=stats.total_events))

    if stats.commands:
        typer.echo(t("cli.telemetry.top_commands"))
        for cmd, count in sorted(stats.commands.items(), key=lambda x: -x[1]):
            typer.echo(f"  {cmd:<20} {count}")

    if stats.total_events > 0:
        typer.echo(t("cli.telemetry.success_rate", rate=f"{stats.success_rate:.1%}"))

    if stats.last_event:
        typer.echo(t("cli.telemetry.last_event", timestamp=stats.last_event))
