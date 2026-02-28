"""CLI dependency graph: resolve command prerequisites from resource flow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

_DEPS_PATH = Path(__file__).parent / "_cli_deps.yml"


# ── Loading ──────────────────────────────────────────────


def load_deps() -> dict[str, Any]:
    """Load resource flow declarations from _cli_deps.yml."""
    if not _DEPS_PATH.is_file():
        return {}
    with open(_DEPS_PATH) as f:
        data = yaml.safe_load(f) or {}
    return data.get("resources", {})


def _all_commands(tree: dict[str, Any]) -> set[str]:
    """Extract all dotted command names from the introspected tree."""
    names: set[str] = set()
    for cmd in tree.get("commands", []):
        names.add(cmd["name"])
    for group in tree.get("groups", []):
        for cmd in group.get("commands", []):
            names.add(f"{group['name']}.{cmd['name']}")
    return names


# ── Dependency resolution ────────────────────────────────


def build_dep_graph(
    tree: dict[str, Any],
    resources: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build a dependency graph from resource flow declarations.

    Returns a dict keyed by command name, each value containing:
      - depends_on: list of {command, resource, source} dicts
      - dependents: list of command names that depend on this command
    """
    if resources is None:
        resources = load_deps()

    known = _all_commands(tree)
    graph: dict[str, dict[str, Any]] = {}

    # Initialise all known commands
    for cmd in known:
        graph[cmd] = {"depends_on": [], "dependents": []}

    # Resolve: if C consumes R and P produces R, then C depends on P
    for res_name, res in resources.items():
        producers = res.get("producers", [])
        consumers = res.get("consumers", [])
        for consumer in consumers:
            if consumer not in known:
                continue
            for producer in producers:
                if producer not in known:
                    continue
                if producer == consumer:
                    continue
                # Avoid duplicate edges
                edge = {
                    "command": producer,
                    "resource": res_name,
                    "source": "deterministic",
                }
                existing = graph[consumer]["depends_on"]
                if not any(
                    e["command"] == producer and e["resource"] == res_name
                    for e in existing
                ):
                    existing.append(edge)
                if consumer not in graph[producer]["dependents"]:
                    graph[producer]["dependents"].append(consumer)

    return graph


def merge_llm_deps(
    graph: dict[str, dict[str, Any]],
    llm_edges: list[dict[str, str]],
) -> None:
    """Merge LLM-inferred edges into an existing dependency graph.

    Each edge is {from: producer, to: consumer, reason: description}.
    Mutates graph in place.
    """
    for edge in llm_edges:
        producer = edge.get("from", "")
        consumer = edge.get("to", "")
        reason = edge.get("reason", "")
        if producer not in graph or consumer not in graph:
            continue
        if producer == consumer:
            continue
        dep = {
            "command": producer,
            "resource": reason,
            "source": "llm",
        }
        existing = graph[consumer]["depends_on"]
        if not any(
            e["command"] == producer and e["source"] == "llm"
            for e in existing
        ):
            existing.append(dep)
        if consumer not in graph[producer]["dependents"]:
            graph[producer]["dependents"].append(consumer)


def has_cycle(graph: dict[str, dict[str, Any]]) -> bool:
    """Check if the dependency graph contains a cycle (Kahn's algorithm)."""
    in_degree: dict[str, int] = {cmd: 0 for cmd in graph}
    for cmd, info in graph.items():
        for dep in info["depends_on"]:
            if dep["command"] in in_degree:
                in_degree[cmd] += 1

    queue = [cmd for cmd, deg in in_degree.items() if deg == 0]
    visited = 0
    while queue:
        node = queue.pop(0)
        visited += 1
        for dependent in graph[node]["dependents"]:
            if dependent in in_degree:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

    return visited != len(graph)


# ── Rendering ────────────────────────────────────────────


def _mermaid_id(name: str) -> str:
    """Sanitize a dotted command name for Mermaid node IDs."""
    return name.replace("-", "_").replace(".", "__")


def render_deps_mermaid(
    graph: dict[str, dict[str, Any]],
) -> str:
    """Render the dependency graph as a Mermaid flowchart."""
    lines = ["graph LR"]

    # Collect all commands that have at least one edge
    active: set[str] = set()
    edges: list[tuple[str, str, str, str]] = []
    for cmd, info in graph.items():
        for dep in info["depends_on"]:
            producer = dep["command"]
            active.add(cmd)
            active.add(producer)
            edges.append((producer, cmd, dep["resource"], dep["source"]))

    if not edges:
        lines.append("    empty[No dependencies found]")
        return "\n".join(lines)

    # Emit node declarations
    for name in sorted(active):
        nid = _mermaid_id(name)
        lines.append(f'    {nid}["{name}"]')

    # Emit edges
    for producer, consumer, resource, source in sorted(edges):
        pid = _mermaid_id(producer)
        cid = _mermaid_id(consumer)
        label = resource.replace("_", " ")
        if source == "llm":
            lines.append(f"    {pid} -.->|{label}| {cid}")
        else:
            lines.append(f"    {pid} -->|{label}| {cid}")

    return "\n".join(lines)


def render_deps_json(
    graph: dict[str, dict[str, Any]],
) -> str:
    """Render the dependency graph as JSON."""
    # Only include commands with edges
    output: dict[str, Any] = {}
    for cmd in sorted(graph):
        info = graph[cmd]
        if info["depends_on"] or info["dependents"]:
            output[cmd] = {
                "depends_on": info["depends_on"],
                "dependents": sorted(info["dependents"]),
            }
    return json.dumps(output, indent=2, ensure_ascii=False)
