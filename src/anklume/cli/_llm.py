"""Implémentation de `anklume llm status` et `anklume llm bench`."""

from __future__ import annotations

import typer

from anklume.cli._common import load_infra


def run_llm_status() -> None:
    """Affiche l'état dédié LLM : GPU, machines, Ollama."""
    from anklume.engine.llm_ops import compute_llm_status

    infra = load_infra()
    status = compute_llm_status(infra)

    # GPU
    if status.gpu.detected:
        typer.echo(
            f"GPU : {status.gpu.model} — "
            f"{status.gpu.vram_used_mib} / {status.gpu.vram_total_mib} MiB"
        )
    else:
        typer.echo("GPU : aucun détecté")

    # Machines LLM
    if status.machines:
        typer.echo(
            f"\n{'MACHINE':<25s} {'BACKEND':<12s} {'SANITISÉ':<10s} {'URL'}"
        )
        for m in status.machines:
            san = "oui" if m.sanitized else "non"
            typer.echo(
                f"{m.name:<25s} {m.backend:<12s} {san:<10s} {m.url}"
            )
    else:
        typer.echo("\nAucune machine consommatrice LLM configurée.")

    # Ollama
    typer.echo(f"\nOllama : {status.ollama_status}", nl=False)
    if status.ollama_models:
        typer.echo(f" ({', '.join(status.ollama_models)} chargé)")
    else:
        typer.echo("")


def run_llm_bench(*, model: str = "", prompt: str = "") -> None:
    """Lance le benchmark d'inférence Ollama."""
    from anklume.engine.llm_ops import run_llm_bench as _run_bench

    infra = load_infra()

    kwargs: dict = {}
    if model:
        kwargs["model"] = model
    if prompt:
        kwargs["prompt"] = prompt

    try:
        result = _run_bench(infra, **kwargs)
    except ValueError as e:
        typer.echo(f"Erreur : {e}", err=True)
        raise typer.Exit(1) from None

    typer.echo(f"Modèle   : {result.model}")
    typer.echo(f"Prompt   : \"{result.prompt}\"")
    typer.echo(f"Tokens   : {result.tokens}")
    typer.echo(f"Durée    : {result.duration_s}s")
    typer.echo(f"Vitesse  : {result.tokens_per_s} tokens/s")
