"""anklume init — créer un nouveau projet."""

from pathlib import Path

import typer

_ANKLUME_YML = {
    "en": """\
# anklume.yml — Global configuration
# Domain files go in domains/

schema_version: 1

defaults:
  os_image: images:debian/13
  trust_level: semi-trusted

addressing:
  base: "10.100"
  zone_step: 10

nesting:
  prefix: true
""",
    "fr": """\
# anklume.yml — Configuration globale
# Les fichiers domaine vont dans domains/

schema_version: 1

defaults:
  os_image: images:debian/13
  trust_level: semi-trusted

addressing:
  base: "10.100"
  zone_step: 10

nesting:
  prefix: true
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

_AI_TOOLS_DOMAIN = {
    "en": """\
# ai-tools domain — AI services (GPU, LLM, STT)
# Uncomment 'enabled: true' when a GPU is available.
description: "AI services"
trust_level: trusted
enabled: false

machines:
  gpu-server:
    description: "LLM and STT server with GPU"
    type: lxc
    gpu: true
    roles: [base, ollama_server, stt_server]
    vars:
      ollama_default_model: ""
      stt_language: "en"

  # ai-webui:
  #   description: "Ollama web interface (Open WebUI)"
  #   type: lxc
  #   roles: [base, open_webui]
  #   vars:
  #     open_webui_ollama_url: "http://gpu-server:11434"

  # ai-chat:
  #   description: "Multi-provider chat (LobeChat)"
  #   type: lxc
  #   roles: [base, lobechat]
  #   vars:
  #     lobechat_ollama_url: "http://gpu-server:11434"

  # ai-assistant:
  #   description: "OpenClaw AI assistant"
  #   type: lxc
  #   roles: [base, admin_bootstrap, openclaw_server]
  #   vars:
  #     openclaw_channels: [telegram]
  #     openclaw_llm_provider: ollama
""",
    "fr": """\
# Domaine ai-tools — services IA (GPU, LLM, STT)
# Activer enabled: true quand un GPU est disponible.
description: "Services IA"
trust_level: trusted
enabled: false

machines:
  gpu-server:
    description: "Serveur LLM et STT avec GPU"
    type: lxc
    gpu: true
    roles: [base, ollama_server, stt_server]
    vars:
      ollama_default_model: ""
      stt_language: "fr"

  # ai-webui:
  #   description: "Interface web Ollama (Open WebUI)"
  #   type: lxc
  #   roles: [base, open_webui]
  #   vars:
  #     open_webui_ollama_url: "http://gpu-server:11434"

  # ai-chat:
  #   description: "Chat multi-providers (LobeChat)"
  #   type: lxc
  #   roles: [base, lobechat]
  #   vars:
  #     lobechat_ollama_url: "http://gpu-server:11434"

  # ai-assistant:
  #   description: "Assistant IA OpenClaw"
  #   type: lxc
  #   roles: [base, admin_bootstrap, openclaw_server]
  #   vars:
  #     openclaw_channels: [telegram]
  #     openclaw_llm_provider: ollama
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
  # - from: work
  #   to: ai-tools
  #   ports: [8000]
  #   description: "Work accesses Speaches (STT)"
  # - from: work
  #   to: ai-tools
  #   ports: [3000]
  #   description: "Work accesses Open WebUI"
  # - from: work
  #   to: ai-tools
  #   ports: [3210]
  #   description: "Work accesses LobeChat"
""",
    "fr": """\
# Politiques réseau — règles d'accès inter-domaines
# Tout le trafic inter-domaines est bloqué par défaut.

policies: []
  # - from: pro
  #   to: ai-tools
  #   ports: [11434]
  #   description: "Pro accède à Ollama"
  # - from: pro
  #   to: ai-tools
  #   ports: [8000]
  #   description: "Pro accède à Speaches (STT)"
  # - from: pro
  #   to: ai-tools
  #   ports: [3000]
  #   description: "Pro accède à Open WebUI"
  # - from: pro
  #   to: ai-tools
  #   ports: [3210]
  #   description: "Pro accède à LobeChat"
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

    # Domaine ai-tools (désactivé par défaut)
    ai_content = _AI_TOOLS_DOMAIN.get(lang, _AI_TOOLS_DOMAIN["fr"])
    (domains_dir / "ai-tools.yml").write_text(ai_content)

    # Créer policies.yml
    policies_content = _POLICIES_EXAMPLE.get(lang, _POLICIES_EXAMPLE["fr"])
    (project_dir / "policies.yml").write_text(policies_content)

    # Répertoire rôles personnalisés
    roles_dir = project_dir / "ansible_roles_custom"
    roles_dir.mkdir(exist_ok=True)
    (roles_dir / ".gitkeep").touch()

    typer.echo(f"Projet anklume créé dans {project_dir}")
    typer.echo("Prochaine étape : éditer domains/pro.yml, puis : anklume apply")
