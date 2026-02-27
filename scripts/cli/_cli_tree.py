"""Introspect the anklume Typer app and render CLI decision trees."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from typer.main import get_command

_INTENTS_PATH = Path(__file__).parent / "_intents.yml"


# ── Introspection ─────────────────────────────────────────


def _extract_params(cmd: Any) -> list[dict[str, Any]]:
    """Extract parameter metadata from a Click command."""
    params: list[dict[str, Any]] = []
    for p in getattr(cmd, "params", []):
        kind = type(p).__name__.replace("Typer", "").lower()
        if kind not in ("argument", "option"):
            kind = "argument" if getattr(p, "required", False) else "option"
        entry: dict[str, Any] = {
            "name": p.name,
            "kind": kind,
            "required": getattr(p, "required", False),
            "is_flag": getattr(p, "is_flag", False),
        }
        if p.help:
            entry["help"] = p.help
        default = getattr(p, "default", None)
        if default is not None:
            entry["default"] = default
        params.append(entry)
    return params


def _extract_command(cmd: Any) -> dict[str, Any]:
    """Extract metadata from a single Click command."""
    return {
        "name": cmd.name,
        "help": cmd.help or "",
        "hidden": getattr(cmd, "hidden", False),
        "params": _extract_params(cmd),
    }


def introspect_app(typer_app: Any) -> dict[str, Any]:
    """Walk the Typer app tree and return a structured dict."""
    click_group = get_command(typer_app)
    tree: dict[str, Any] = {
        "name": click_group.name or "anklume",
        "help": click_group.help or "",
        "commands": [],
        "groups": [],
    }
    for name in sorted(click_group.commands):
        cmd = click_group.commands[name]
        if hasattr(cmd, "commands"):
            group: dict[str, Any] = {
                "name": name,
                "help": cmd.help or "",
                "hidden": getattr(cmd, "hidden", False),
                "commands": [],
            }
            for sub_name in sorted(cmd.commands):
                sub = cmd.commands[sub_name]
                group["commands"].append(_extract_command(sub))
            tree["groups"].append(group)
        else:
            tree["commands"].append(_extract_command(cmd))
    return tree


# ── Intent loading ────────────────────────────────────────


def load_intents() -> dict[str, Any]:
    """Load intent categories from _intents.yml."""
    if not _INTENTS_PATH.is_file():
        return {}
    with open(_INTENTS_PATH) as f:
        return yaml.safe_load(f) or {}


def _classify(tree: dict[str, Any], intents: dict[str, Any]) -> dict[str, list]:
    """Classify commands/groups into intent categories."""
    # Build reverse maps: group_name -> intent, command_name -> intent
    cli_tree_group_map: dict[str, str] = {}
    cli_tree_cmd_map: dict[str, str] = {}
    for intent_id, meta in intents.items():
        for g in meta.get("groups", []):
            cli_tree_group_map[g] = intent_id
        for c in meta.get("commands", []):
            cli_tree_cmd_map[c] = intent_id

    buckets: dict[str, list] = {}
    for intent_id in intents:
        buckets[intent_id] = []

    # Classify groups
    for group in tree["groups"]:
        intent_id = cli_tree_group_map.get(group["name"], "other")
        if intent_id not in buckets:
            buckets[intent_id] = []
        buckets[intent_id].append(group)

    # Classify top-level commands
    for cmd in tree["commands"]:
        intent_id = cli_tree_cmd_map.get(cmd["name"], "other")
        if intent_id not in buckets:
            buckets[intent_id] = []
        buckets[intent_id].append(cmd)

    return buckets


# ── Mermaid rendering ─────────────────────────────────────


def _mermaid_id(name: str) -> str:
    """Sanitize a name for Mermaid node IDs."""
    return name.replace("-", "_")


def render_mermaid(tree: dict[str, Any], *, show_hidden: bool = False) -> str:
    """Render the CLI tree as a Mermaid graph."""
    lines = ["graph LR", '    root(["anklume"])']

    # Top-level commands
    for cmd in tree["commands"]:
        if cmd["hidden"] and not show_hidden:
            continue
        nid = _mermaid_id(cmd["name"])
        lines.append(f'    root --> {nid}["{cmd["name"]}"]')

    # Groups
    for group in tree["groups"]:
        if group["hidden"] and not show_hidden:
            continue
        gid = _mermaid_id(group["name"])
        lines.append(f'    root --> {gid}["{group["name"]}"]')
        for sub in group["commands"]:
            if sub["hidden"] and not show_hidden:
                continue
            sid = f"{gid}_{_mermaid_id(sub['name'])}"
            lines.append(f'    {gid} --> {sid}["{sub["name"]}"]')
            # Show required args
            for p in sub["params"]:
                if p["kind"] == "argument":
                    pid = f'{sid}__{_mermaid_id(p["name"])}'
                    label = p["name"].upper()
                    lines.append(f"    {sid} -.- {pid}>{label}]")

    return "\n".join(lines)


# ── Intent Mermaid rendering ──────────────────────────────


def render_intent(
    tree: dict[str, Any], *, show_hidden: bool = False,
) -> str:
    """Render an intent-based decision tree as Mermaid."""
    intents = load_intents()
    if not intents:
        return render_mermaid(tree, show_hidden=show_hidden)

    buckets = _classify(tree, intents)
    lines = [
        "graph LR",
        '    user{{"What do you want to do?"}}',
    ]

    for intent_id, items in buckets.items():
        visible = [
            i for i in items
            if show_hidden or not i.get("hidden", False)
        ]
        if not visible:
            continue
        meta = intents.get(intent_id, {})
        label = meta.get("label", intent_id.title())
        iid = _mermaid_id(intent_id)
        lines.append(f'    user --> {iid}["{label}"]')

        for item in visible:
            is_group = "commands" in item
            nid = f"{iid}_{_mermaid_id(item['name'])}"
            if is_group:
                lines.append(
                    f'    {iid} --> {nid}["{item["name"]}"]',
                )
                for sub in item["commands"]:
                    if sub["hidden"] and not show_hidden:
                        continue
                    sid = f"{nid}_{_mermaid_id(sub['name'])}"
                    lines.append(
                        f'    {nid} --> {sid}["{sub["name"]}"]',
                    )
            else:
                lines.append(
                    f'    {iid} --> {nid}["{item["name"]}"]',
                )

    return "\n".join(lines)


# ── JSON rendering ────────────────────────────────────────


def render_json(tree: dict[str, Any], *, show_hidden: bool = False) -> str:
    """Render the CLI tree as JSON."""
    filtered = _filter_hidden(tree) if not show_hidden else tree
    return json.dumps(filtered, indent=2, ensure_ascii=False)


def _filter_hidden(tree: dict[str, Any]) -> dict[str, Any]:
    """Remove hidden commands and groups from the tree."""
    return {
        "name": tree["name"],
        "help": tree["help"],
        "commands": [c for c in tree["commands"] if not c["hidden"]],
        "groups": [
            {
                **g,
                "commands": [c for c in g["commands"] if not c["hidden"]],
            }
            for g in tree["groups"]
            if not g["hidden"]
        ],
    }
