"""Dynamic shell completions for the anklume CLI."""

from scripts.cli._helpers import load_infra_safe


def complete_domain(incomplete: str) -> list[str]:
    """Return domain names matching the incomplete string."""
    try:
        infra = load_infra_safe()
    except SystemExit:
        return []
    domains = infra.get("domains") or {}
    return [d for d in domains if d.startswith(incomplete)]


def complete_instance(incomplete: str) -> list[str]:
    """Return machine names matching the incomplete string."""
    try:
        infra = load_infra_safe()
    except SystemExit:
        return []
    names = []
    for dconf in (infra.get("domains") or {}).values():
        for m in (dconf.get("machines") or {}):
            names.append(m)
    return [n for n in names if n.startswith(incomplete)]


def complete_lab(incomplete: str) -> list[str]:
    """Return lab IDs matching the incomplete string."""
    from scripts.cli._helpers import PROJECT_ROOT

    labs_dir = PROJECT_ROOT / "labs"
    if not labs_dir.is_dir():
        return []
    labs = [p.name for p in sorted(labs_dir.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    return [lab for lab in labs if lab.startswith(incomplete)]
