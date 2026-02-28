"""anklume dev — development and testing tools (hidden in user/student mode)."""

from typing import Annotated

import typer

from scripts.cli._helpers import PROJECT_ROOT, run_cmd, run_make, run_script

app = typer.Typer(name="dev", help="Development, testing, and code quality tools.", hidden=True)


@app.command()
def test(
    generator: Annotated[bool, typer.Option("--generator", help="Run generator tests only")] = False,
    roles: Annotated[bool, typer.Option("--roles", help="Run Molecule role tests")] = False,
    role: Annotated[str | None, typer.Option("--role", "-r", help="Test a specific role")] = None,
    sandboxed: Annotated[bool, typer.Option("--sandboxed", help="Run tests in sandbox VM")] = False,
) -> None:
    """Run tests (pytest + Molecule)."""
    if sandboxed:
        run_make("test-sandboxed")
    elif role:
        run_cmd(["molecule", "test", "-s", "default"], cwd=str(PROJECT_ROOT / "roles" / role))
    elif generator:
        run_cmd(["python3", "-m", "pytest", "tests/", "-v", "--tb=short"], cwd=str(PROJECT_ROOT))
    elif roles:
        run_script("run-tests.sh", "roles")
    else:
        run_cmd(["python3", "-m", "pytest", "tests/", "-v", "--tb=short"], cwd=str(PROJECT_ROOT))


@app.command()
def lint(
    yaml_: Annotated[bool, typer.Option("--yaml", help="YAML only")] = False,
    ansible: Annotated[bool, typer.Option("--ansible", help="Ansible only")] = False,
    shell: Annotated[bool, typer.Option("--shell", help="Shell only")] = False,
    python: Annotated[bool, typer.Option("--python", help="Python only")] = False,
) -> None:
    """Run linters (all by default)."""
    if yaml_:
        run_cmd(["yamllint", "-c", ".yamllint.yml", "."], cwd=str(PROJECT_ROOT))
    elif ansible:
        run_cmd(["ansible-lint"], cwd=str(PROJECT_ROOT))
    elif shell:
        run_script("run-tests.sh", "shell")
    elif python:
        run_cmd(["ruff", "check", "."], cwd=str(PROJECT_ROOT))
    else:
        run_cmd(["make", "-C", str(PROJECT_ROOT), "lint"])


@app.command()
def matrix(
    generate: Annotated[bool, typer.Option("--generate", help="Generate tests for uncovered cells")] = False,
) -> None:
    """Show behavior matrix coverage."""
    if generate:
        run_cmd(["python3", str(PROJECT_ROOT / "scripts" / "matrix-coverage.py"), "--generate"], cwd=str(PROJECT_ROOT))
    else:
        run_cmd(["python3", str(PROJECT_ROOT / "scripts" / "matrix-coverage.py")], cwd=str(PROJECT_ROOT))


@app.command()
def audit(
    json_: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Produce a code audit report."""
    if json_:
        run_script("code-audit.py", "--json")
    else:
        run_script("code-audit.py")


@app.command()
def smoke() -> None:
    """Run real-world smoke test."""
    run_cmd(["make", "-C", str(PROJECT_ROOT), "smoke"])


@app.command()
def scenario(
    best: Annotated[bool, typer.Option("--best", help="Best-practice scenarios only")] = False,
    bad: Annotated[bool, typer.Option("--bad", help="Bad-practice scenarios only")] = False,
) -> None:
    """Run end-to-end scenarios."""
    if best:
        run_make("scenario-test-best")
    elif bad:
        run_make("scenario-test-bad")
    else:
        run_make("scenario-test")


@app.command()
def syntax() -> None:
    """Check playbook syntax (ansible-playbook --syntax-check)."""
    run_cmd(["ansible-playbook", str(PROJECT_ROOT / "site.yml"), "--syntax-check"])


@app.command("chain-test")
def chain_test(
    target: Annotated[str | None, typer.Option("--target", "-t", help="Test a specific target")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Preview without executing")] = False,
    json_: Annotated[bool, typer.Option("--json", help="Output as JSON")] = False,
) -> None:
    """Run chained integration tests."""
    if target:
        run_make("chain-test-one", f"T={target}")
    elif dry_run:
        run_make("chain-test-dry")
    elif json_:
        run_make("chain-test-json")
    else:
        run_make("chain-test")


@app.command("test-summary")
def test_summary(
    quick: Annotated[bool, typer.Option("--quick", help="Quick summary")] = False,
) -> None:
    """Show test execution summary."""
    if quick:
        run_make("test-summary-quick")
    else:
        run_make("test-summary")


@app.command("test-report")
def test_report() -> None:
    """Generate detailed test report."""
    run_make("test-report")


@app.command()
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


@app.command("cli-tree")
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

    graph = build_dep_graph(tree)

    if use_llm:
        llm_edges = _infer_llm_deps(tree)
        if llm_edges:
            merge_llm_deps(graph, llm_edges)
            console.print(f"[dim]Merged {len(llm_edges)} LLM-inferred edges[/dim]\n")

    console.print("[bold]Dependency graph (Mermaid):[/bold]\n")
    print(render_deps_mermaid(graph))
    console.print("\n[bold]Dependency graph (JSON):[/bold]\n")
    print(render_deps_json(graph))


def _infer_llm_deps(tree: dict) -> list[dict[str, str]]:
    """Call local LLM to infer semantic dependencies."""
    import yaml as _yaml

    from scripts.cli._helpers import console

    # Build a summary of commands for the LLM
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
        import subprocess

        from scripts.cli._helpers import PROJECT_ROOT  # noqa: F811

        result = subprocess.run(
            [
                "ollama", "run", "qwen2.5-coder:32b",
                "--nowordwrap", prompt,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode != 0:
            console.print("[yellow]LLM inference failed, skipping[/yellow]")
            return []

        # Extract YAML from response
        raw = result.stdout.strip()
        # Strip markdown fences if present
        if "```" in raw:
            parts = raw.split("```")
            for part in parts[1:]:
                cleaned = part.strip()
                if cleaned.startswith("yaml"):
                    cleaned = cleaned[4:].strip()
                if cleaned.startswith("- from:"):
                    raw = cleaned
                    break

        edges = _yaml.safe_load(raw)
        if not isinstance(edges, list):
            return []
        # Validate structure
        valid = []
        for edge in edges:
            if isinstance(edge, dict) and "from" in edge and "to" in edge:
                valid.append({
                    "from": str(edge["from"]),
                    "to": str(edge["to"]),
                    "reason": str(edge.get("reason", "LLM-inferred")),
                })
        return valid[:10]
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception) as exc:
        console.print(f"[yellow]LLM inference skipped: {exc}[/yellow]")
        return []


@app.command("bdd-stubs")
def bdd_stubs(
    write: Annotated[bool, typer.Option("--write", help="Write stubs to file")] = False,
) -> None:
    """Detect missing BDD step definitions and generate stubs."""
    args = ["python3", str(PROJECT_ROOT / "scripts" / "generate-bdd-stubs.py")]
    if write:
        args.append("--write")
    run_cmd(args, cwd=str(PROJECT_ROOT))


@app.command("generate-scenarios")
def generate_scenarios(
    write: Annotated[bool, typer.Option("--write", help="Write generated feature files")] = False,
) -> None:
    """Generate BDD scenarios from the CLI dependency graph."""
    args = ["python3", str(PROJECT_ROOT / "scripts" / "generate-dep-scenarios.py")]
    if write:
        args.append("--write")
    run_cmd(args, cwd=str(PROJECT_ROOT))


@app.command("runner")
def runner(
    action: Annotated[str, typer.Argument(help="Action: create or destroy")],
) -> None:
    """Manage the test runner VM."""
    if action == "create":
        run_make("runner-create")
    elif action == "destroy":
        run_make("runner-destroy")
    else:
        from scripts.cli._helpers import console

        console.print(f"[red]Unknown action:[/red] {action}. Use: create, destroy")
        raise typer.Exit(1)
