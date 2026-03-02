"""Graph and CLI tree commands extracted from dev.py."""

from typing import Annotated

import typer

from scripts.cli._helpers import PROJECT_ROOT, run_make


def register(app: typer.Typer) -> None:
    """Register graph and cli-tree commands on the given Typer app."""
    app.command()(graph)
    app.command("cli-tree")(cli_tree)


def graph(
    type_: Annotated[str, typer.Option("--type", "-t", help="Graph type: call, dep, code, dead")] = "call",
) -> None:
    """Generate code analysis graphs."""
    graph_targets = {
        "call": "call-graph",
        "dep": "dep-graph",
        "code": "code-graph",
        "dead": "dead-code",
    }
    target = graph_targets.get(type_)
    if not target:
        from scripts.cli._helpers import console

        console.print(f"[red]Unknown graph type:[/red] {type_}. Use: call, dep, code, dead")
        raise typer.Exit(1)
    run_make(target)


def cli_tree(
    format_: Annotated[
        str, typer.Option("--format", "-f", help="Output format: mermaid, json, intent, deps")
    ] = "mermaid",
    hidden: Annotated[
        bool, typer.Option("--hidden", help="Include hidden (dev-only) commands")
    ] = False,
    llm: Annotated[
        bool, typer.Option("--llm", help="Enrich deps with LLM-inferred edges")
    ] = False,
) -> None:
    """Generate the CLI decision tree."""
    from scripts.cli import app as root_app
    from scripts.cli._cli_tree import (
        introspect_app,
        render_intent,
        render_json,
        render_mermaid,
    )

    tree = introspect_app(root_app)

    if format_ == "deps":
        _render_deps(tree, use_llm=llm)
        return

    renderers = {
        "mermaid": lambda: render_mermaid(tree, show_hidden=hidden),
        "json": lambda: render_json(tree, show_hidden=hidden),
        "intent": lambda: render_intent(tree, show_hidden=hidden),
    }
    renderer = renderers.get(format_)
    if not renderer:
        from scripts.cli._helpers import console

        console.print(f"[red]Unknown format:[/red] {format_}. Use: mermaid, json, intent, deps")
        raise typer.Exit(1)
    print(renderer())


def _render_deps(tree: dict, *, use_llm: bool = False) -> None:
    """Build and print the dependency graph (Mermaid + JSON)."""
    from scripts.cli._cli_deps import (
        build_dep_graph,
        merge_llm_deps,
        render_deps_json,
        render_deps_mermaid,
    )
    from scripts.cli._helpers import console

    dep_graph = build_dep_graph(tree)

    if use_llm:
        llm_edges = _infer_llm_deps(tree)
        if llm_edges:
            merge_llm_deps(dep_graph, llm_edges)
            console.print(f"[dim]Merged {len(llm_edges)} LLM-inferred edges[/dim]\n")

    console.print("[bold]Dependency graph (Mermaid):[/bold]\n")
    print(render_deps_mermaid(dep_graph))
    console.print("\n[bold]Dependency graph (JSON):[/bold]\n")
    print(render_deps_json(dep_graph))


def _infer_llm_deps(tree: dict) -> list[dict[str, str]]:
    """Call local LLM to infer semantic dependencies."""
    import subprocess

    import yaml

    from scripts.cli._helpers import console

    cmds: list[str] = []
    for cmd in tree.get("commands", []):
        cmds.append(f"- {cmd['name']}: {cmd.get('help', '')}")
    for group in tree.get("groups", []):
        for sub in group.get("commands", []):
            cmds.append(f"- {group['name']}.{sub['name']}: {sub.get('help', '')}")
    cmd_list = "\n".join(cmds)

    prompt = (
        "Given these CLI commands and descriptions, infer prerequisite "
        "relationships that are semantically obvious but NOT captured by "
        "file I/O. For example: 'setup.init should run before domain.apply "
        "to ensure dependencies are installed'.\n\n"
        "Output ONLY a YAML list of edges:\n"
        "- from: <producer command>\n"
        "  to: <consumer command>\n"
        "  reason: <short description>\n\n"
        f"Commands:\n{cmd_list}\n\n"
        "Rules:\n"
        "- Only include edges NOT already obvious from resource flow\n"
        "- Use dotted names for subcommands (e.g., setup.init)\n"
        "- Keep reason under 40 characters\n"
        "- Maximum 10 edges\n"
    )

    try:
        result = subprocess.run(
            ["ollama", "run", "qwen2.5-coder:32b", "--nowordwrap", prompt],
            capture_output=True, text=True, timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            console.print("[yellow]LLM inference failed, skipping[/yellow]")
            return []

        raw = result.stdout.strip()
        if "```" in raw:
            parts = raw.split("```")
            for part in parts[1:]:
                cleaned = part.strip()
                if cleaned.startswith("yaml"):
                    cleaned = cleaned[4:].strip()
                if cleaned.startswith("- from:"):
                    raw = cleaned
                    break

        edges = yaml.safe_load(raw)
        if not isinstance(edges, list):
            return []
        valid = []
        for edge in edges:
            if isinstance(edge, dict) and "from" in edge and "to" in edge:
                valid.append({
                    "from": str(edge["from"]),
                    "to": str(edge["to"]),
                    "reason": str(edge.get("reason", "LLM-inferred")),
                })
        return valid[:10]
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError) as exc:
        console.print(f"[yellow]LLM inference skipped: {exc}[/yellow]")
        return []
