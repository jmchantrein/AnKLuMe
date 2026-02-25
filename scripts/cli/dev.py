"""anklume dev — development and testing tools (hidden in user/student mode)."""

from typing import Annotated

import typer

from scripts.cli._helpers import PROJECT_ROOT, run_cmd, run_script

app = typer.Typer(name="dev", help="Development, testing, and code quality tools.", hidden=True)


@app.command()
def test(
    generator: Annotated[bool, typer.Option("--generator", help="Run generator tests only")] = False,
    roles: Annotated[bool, typer.Option("--roles", help="Run Molecule role tests")] = False,
    role: Annotated[str | None, typer.Option("--role", "-r", help="Test a specific role")] = None,
) -> None:
    """Run tests (pytest + Molecule)."""
    if role:
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
        run_cmd(["make", "-C", str(PROJECT_ROOT), "scenario-test-best"])
    elif bad:
        run_cmd(["make", "-C", str(PROJECT_ROOT), "scenario-test-bad"])
    else:
        run_cmd(["make", "-C", str(PROJECT_ROOT), "scenario-test"])
