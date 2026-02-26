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
