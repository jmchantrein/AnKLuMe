"""anklume dev env — générer un environnement de développement."""

from __future__ import annotations

from pathlib import Path

import typer

from anklume.engine.dev_env import DevEnvConfig, generate_dev_domain, generate_dev_policies
from anklume.engine.llm_routing import validate_llm_config


def run_dev_env(config: DevEnvConfig, *, output: str = ".") -> None:
    """Générer un domaine d'environnement de développement."""
    # Validation LLM via le validateur existant
    errors = validate_llm_config(
        config.llm_backend,
        config.sanitize,
        config.llm_api_url,
        config.llm_api_key,
    )
    if errors:
        for err in errors:
            typer.echo(f"Erreur : {err}", err=True)
        raise typer.Exit(1)

    # Générer le YAML
    domain_yaml = generate_dev_domain(config)
    policies_yaml = generate_dev_policies(config)

    # Déterminer le répertoire de sortie
    output_dir = Path(output).resolve()
    domains_dir = output_dir / "domains"

    if not domains_dir.exists():
        typer.echo(f"Répertoire domains/ introuvable dans {output_dir}", err=True)
        typer.echo("Exécuter d'abord : anklume init", err=True)
        raise typer.Exit(1)

    # Écrire le domaine
    domain_file = domains_dir / f"{config.name}.yml"
    if domain_file.exists():
        typer.echo(f"Le domaine {config.name} existe déjà : {domain_file}")
        raise typer.Exit(1)

    domain_file.write_text(domain_yaml)
    typer.echo(f"Domaine créé : {domain_file}")

    # Ajouter les politiques si nécessaire
    if policies_yaml:
        policies_file = output_dir / "policies.yml"
        typer.echo(f"\nPolitiques réseau suggérées (à ajouter dans {policies_file}) :")
        typer.echo(policies_yaml)

    # Résumé
    typer.echo(f"\nProchaine étape : anklume apply domain {config.name}")
