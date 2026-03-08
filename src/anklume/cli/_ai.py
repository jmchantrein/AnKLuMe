"""Implémentation de `anklume ai status`, `anklume ai flush`, `anklume ai switch`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra


def run_ai_status() -> None:
    """Affiche l'état des services IA."""
    from anklume.engine.ai import compute_ai_status, read_ai_access

    infra = load_infra()
    status = compute_ai_status(infra)

    # GPU
    typer.echo("GPU:")
    if status.gpu.detected:
        typer.echo(f"  Détecté : oui ({status.gpu.model})")
        typer.echo(
            f"  VRAM : {status.gpu.vram_used_mib} / {status.gpu.vram_total_mib} MiB"
        )
    else:
        typer.echo("  Détecté : non")

    # Accès GPU courant
    access = read_ai_access()
    if access.domain:
        typer.echo(f"  Accès GPU : {access.domain}")
    else:
        typer.echo("  Accès GPU : aucun domaine assigné")

    # Services
    if not status.services:
        typer.echo("\nAucun service IA configuré.")
        return

    for svc in status.services:
        typer.echo(f"\n{svc.name.upper()}:")
        if svc.reachable:
            detail = f" ({svc.detail})" if svc.detail else ""
            typer.echo(f"  État : actif{detail}")
            typer.echo(f"  URL  : {svc.url}")
        else:
            typer.echo(f"  État : injoignable ({svc.url})")


def run_ai_flush() -> None:
    """Libère la VRAM GPU."""
    from anklume.engine.ai import flush_vram

    infra = load_infra()
    result = flush_vram(infra)

    if not result.models_unloaded and not result.llama_server_stopped:
        typer.echo("Rien à libérer.")
        return

    if result.models_unloaded:
        models = ", ".join(result.models_unloaded)
        typer.echo(f"Modèles déchargés : {models}")

    if result.llama_server_stopped:
        typer.echo("llama-server arrêté.")

    typer.echo(
        f"VRAM : {result.vram_before_mib} → {result.vram_after_mib} MiB"
    )


def run_ai_switch(domain: str) -> None:
    """Bascule l'accès GPU vers un domaine."""
    from anklume.engine.ai import switch_ai_access

    infra = load_infra()

    try:
        state = switch_ai_access(infra, domain)
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None

    previous = state.previous or "aucun"
    typer.echo(f"Accès GPU : {state.domain} (précédent : {previous})")
