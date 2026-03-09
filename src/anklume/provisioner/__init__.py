"""Provisioner Ansible — génération d'inventaire, playbook, exécution."""

from __future__ import annotations

from pathlib import Path

from anklume.engine.llm_routing import enrich_llm_vars
from anklume.engine.models import Infrastructure
from anklume.provisioner.inventory import write_inventories
from anklume.provisioner.playbook import write_host_vars, write_playbook
from anklume.provisioner.runner import ProvisionResult, ansible_available, run_playbook

PROVISIONER_DIR = Path(__file__).parent
BUILTIN_ROLES_DIR = PROVISIONER_DIR / "roles"
PLUGIN_DIR = PROVISIONER_DIR / "plugins" / "connection"


def has_provisionable_machines(infra: Infrastructure) -> bool:
    """Vérifie si au moins une machine active a des rôles."""
    for domain in infra.enabled_domains:
        for machine in domain.machines.values():
            if machine.roles:
                return True
    return False


def provision(
    infra: Infrastructure,
    project_dir: Path,
) -> ProvisionResult:
    """Pipeline complet : génère fichiers Ansible + exécute ansible-playbook."""
    if not has_provisionable_machines(infra):
        return ProvisionResult(
            success=True,
            skipped=True,
            skip_reason="Aucune machine avec des rôles à provisionner",
        )

    if not ansible_available():
        return ProvisionResult(
            success=True,
            skipped=True,
            skip_reason="Ansible absent du PATH — provisioning ignoré",
        )

    # Enrichir les vars LLM (résout les endpoints avant génération)
    enriched = enrich_llm_vars(infra)

    # Générer les fichiers
    write_inventories(project_dir, enriched)
    write_playbook(project_dir, enriched)
    write_host_vars(project_dir, enriched)

    # Résoudre le répertoire des rôles custom
    custom_roles_dir = project_dir / "ansible_roles_custom"
    if not custom_roles_dir.is_dir():
        custom_roles_dir = None

    return run_playbook(
        project_dir=project_dir,
        builtin_roles_dir=BUILTIN_ROLES_DIR,
        custom_roles_dir=custom_roles_dir,
        plugin_dir=PLUGIN_DIR,
    )
