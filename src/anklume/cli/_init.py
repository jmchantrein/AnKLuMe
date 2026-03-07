"""anklume init — créer un nouveau projet."""

from pathlib import Path

import typer

_ANKLUME_YML = {
    "en": """\
# anklume.yml — Global configuration
# Domain files go in domains/

project: my-infra

defaults:
  os_image: images:debian/13
  trust_level: semi-trusted

addressing:
  base: "10.100"
  zone_step: 10
""",
    "fr": """\
# anklume.yml — Configuration globale
# Les fichiers domaine vont dans domains/

project: mon-infra

defaults:
  os_image: images:debian/13
  trust_level: semi-trusted

addressing:
  base: "10.100"
  zone_step: 10
""",
}

_DOMAIN_EXAMPLE = {
    "en": """\
# Work domain — professional workspace
description: "Professional workspace"
trust_level: semi-trusted

machines:
  dev:
    description: "Development"
    type: lxc
    roles: [base]

  desktop:
    description: "Desktop with GPU"
    type: lxc
    gpu: true
    roles: [base, desktop]
""",
    "fr": """\
# Domaine pro — espace professionnel
description: "Espace professionnel"
trust_level: semi-trusted

machines:
  dev:
    description: "Développement"
    type: lxc
    roles: [base]

  desktop:
    description: "Bureau avec GPU"
    type: lxc
    gpu: true
    roles: [base, desktop]
""",
}

_POLICIES_EXAMPLE = {
    "en": """\
# Network policies — inter-domain access rules
# All inter-domain traffic is blocked by default.

policies: []
  # - from: work
  #   to: ai-tools
  #   ports: [11434]
  #   description: "Work accesses Ollama"
""",
    "fr": """\
# Politiques réseau — règles d'accès inter-domaines
# Tout le trafic inter-domaines est bloqué par défaut.

policies: []
  # - from: pro
  #   to: ai-tools
  #   ports: [11434]
  #   description: "Pro accède à Ollama"
""",
}


def run_init(directory: str, *, lang: str = "fr") -> None:
    """Créer un répertoire projet anklume."""
    project_dir = Path(directory).resolve()

    if directory != ".":
        if project_dir.exists() and any(project_dir.iterdir()):
            typer.echo(f"Le répertoire {project_dir} n'est pas vide.")
            raise typer.Exit(1)
        project_dir.mkdir(parents=True, exist_ok=True)

    anklume_yml = project_dir / "anklume.yml"
    if anklume_yml.exists():
        typer.echo(f"anklume.yml existe déjà dans {project_dir}")
        raise typer.Exit(0)

    content = _ANKLUME_YML.get(lang, _ANKLUME_YML["fr"])
    anklume_yml.write_text(content)

    # Créer domains/ avec un exemple
    domains_dir = project_dir / "domains"
    domains_dir.mkdir(exist_ok=True)

    domain_name = "work" if lang == "en" else "pro"
    domain_content = _DOMAIN_EXAMPLE.get(lang, _DOMAIN_EXAMPLE["fr"])
    (domains_dir / f"{domain_name}.yml").write_text(domain_content)

    # Créer policies.yml
    policies_content = _POLICIES_EXAMPLE.get(lang, _POLICIES_EXAMPLE["fr"])
    (project_dir / "policies.yml").write_text(policies_content)

    # Répertoire rôles personnalisés
    roles_dir = project_dir / "roles_custom"
    roles_dir.mkdir(exist_ok=True)
    (roles_dir / ".gitkeep").touch()

    typer.echo(f"Projet anklume créé dans {project_dir}")
    typer.echo("Prochaine étape : éditer domains/pro.yml, puis : anklume apply")
