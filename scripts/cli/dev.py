"""anklume dev — development and testing tools (hidden in user/student mode)."""

from typing import Annotated

import typer

from scripts.cli._helpers import PROJECT_ROOT, console, is_intensive, run_cmd, run_make, run_script

app = typer.Typer(name="dev", help="Development, testing, and code quality tools.", hidden=True)


def _changed_test_files() -> list[str]:
    """Detect test files related to git-changed source files."""
    import subprocess as sp

    result = sp.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, check=False,
        cwd=str(PROJECT_ROOT),
    )
    changed = result.stdout.strip().splitlines() if result.returncode == 0 else []
    # Also include untracked files
    result2 = sp.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=False,
        cwd=str(PROJECT_ROOT),
    )
    if result2.returncode == 0:
        changed.extend(result2.stdout.strip().splitlines())

    test_files = set()
    for path in changed:
        if path.startswith("tests/") and path.endswith(".py"):
            test_files.add(path)
        elif path.startswith("scripts/"):
            # Map scripts/X.py → tests/test_X.py
            from pathlib import PurePosixPath

            stem = PurePosixPath(path).stem
            candidate = PROJECT_ROOT / "tests" / f"test_{stem}.py"
            if candidate.is_file():
                test_files.add(str(candidate.relative_to(PROJECT_ROOT)))
    return sorted(test_files)


@app.command()
def test(
    generator: Annotated[bool, typer.Option("--generator", help="Run generator tests only")] = False,
    roles: Annotated[bool, typer.Option("--roles", help="Run Molecule role tests")] = False,
    role: Annotated[str | None, typer.Option("--role", "-r", help="Test a specific role")] = None,
    sandboxed: Annotated[bool, typer.Option("--sandboxed", help="Run tests in sandbox VM")] = False,
    fast: Annotated[bool, typer.Option("--fast", "-f", help="Parallel execution (pytest-xdist)")] = False,
    changed: Annotated[bool, typer.Option("--changed", "-c", help="Only test files related to git changes")] = False,
    full: Annotated[bool, typer.Option("--full", help="Force verbose mode (override intensive)")] = False,
) -> None:
    """Run tests (pytest + Molecule)."""
    if sandboxed:
        run_make("test-sandboxed")
        return
    if role:
        run_cmd(["molecule", "test", "-s", "default"], cwd=str(PROJECT_ROOT / "roles" / role))
        return
    if roles:
        run_script("run-tests.sh", "roles")
        return

    # Determine test files
    test_targets = ["tests/"]
    if changed:
        test_targets = _changed_test_files()
        if not test_targets:
            console.print("[green]No test files affected by current changes.[/green]")
            return

    # Determine pytest flags: --fast or intensive mode (unless --full overrides)
    use_parallel = (fast or is_intensive()) and not full
    pytest_args = ["-n", "auto", "-x", "-q", "--tb=short"] if use_parallel else ["-v", "--tb=short"]

    run_cmd(["python3", "-m", "pytest", *test_targets, *pytest_args], cwd=str(PROJECT_ROOT))


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
    elif is_intensive():
        run_cmd(
            ["python3", "-m", "behave", "scenarios/", "--no-capture", "-v", "--stop"],
            cwd=str(PROJECT_ROOT),
        )
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


@app.command()
def nesting(
    mode: Annotated[str, typer.Option("--mode", "-m", help="Nesting mode: lxc, vm, or both")] = "lxc",
    max_depth: Annotated[int, typer.Option("--max-depth", "-d", help="Max nesting depth (1-5)")] = 3,
    full: Annotated[bool, typer.Option("--full", "-f", help="Run pytest at each nesting level")] = False,
    behave: Annotated[bool, typer.Option("--behave", "-b", help="Run behave scenarios at each level")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n", help="Validate structure only")] = False,
) -> None:
    """Run nesting integration test (LXC/VM containers-in-containers)."""
    args = ["--mode", mode, "--max-depth", str(max_depth)]
    if full:
        args.append("--full")
    if behave:
        args.append("--behave")
    if dry_run:
        args.append("--dry-run")
    run_script("test-nesting.sh", *args)


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


@app.command()
def intensive(
    state: Annotated[str | None, typer.Argument(help="on or off (omit to show status)")] = None,
) -> None:
    """Toggle intensive development mode (parallel tests, fail-fast)."""
    from pathlib import Path

    flag_file = Path.home() / ".anklume" / "intensive"

    if state is None:
        current = "on" if is_intensive() else "off"
        console.print(f"Intensive mode: [bold]{current}[/bold]")
        if current == "on":
            console.print("[dim]  pytest: -n auto -x -q --tb=short[/dim]")
            console.print("[dim]  behave: --stop[/dim]")
        return

    if state not in ("on", "off"):
        console.print(f"[red]Invalid state:[/red] {state}. Use: on, off")
        raise typer.Exit(1)

    flag_file.parent.mkdir(parents=True, exist_ok=True)
    flag_file.write_text(state + "\n")
    if state == "on":
        console.print("[green]Intensive mode ON[/green] — parallel tests, fail-fast")
    else:
        console.print("[yellow]Intensive mode OFF[/yellow] — verbose sequential tests")


@app.command("9p")
def ninep(
    action: Annotated[str, typer.Argument(help="mount, umount, status, push, or restart")],
    service: Annotated[str | None, typer.Argument(help="Service to restart (e.g. platform_server)")] = None,
) -> None:
    """Hot-reload development via 9p virtfs (run inside the VM).

    The host shares the project read-only via QEMU -virtfs.
    Run these commands inside the VM to mount, push changes,
    and restart services — no ISO rebuild, no SSH.

    \b
    Actions:
      mount    Mount 9p share at /mnt/anklume
      umount   Unmount the 9p share
      status   Show mount status and diff vs embedded copy
      push     Copy changed files from 9p mount to /opt/anklume
      restart  Restart a service (e.g. platform_server)
    """
    import subprocess as sp

    mount_point = "/mnt/anklume"
    target_dir = "/opt/anklume"

    if action == "mount":
        run_cmd(["sudo", "mkdir", "-p", mount_point])
        run_cmd(["sudo", "mount", "-t", "9p", "-o", "trans=virtio,ro",
                 "anklume-src", mount_point])
        console.print(f"[green]9p share mounted at {mount_point}[/green]")
    elif action == "umount":
        run_cmd(["sudo", "umount", mount_point], check=False)
        console.print("[yellow]9p share unmounted[/yellow]")
    elif action == "status":
        rc = sp.run(["mountpoint", "-q", mount_point],
                    capture_output=True, check=False).returncode
        if rc == 0:
            console.print(f"[green]9p: mounted at {mount_point}[/green]")
            # Show diff summary
            result = sp.run(
                ["diff", "-rq", "--exclude=__pycache__", "--exclude=.git",
                 f"{mount_point}/scripts", f"{target_dir}/scripts"],
                capture_output=True, text=True, check=False,
            )
            if result.stdout.strip():
                console.print("[yellow]Changed files:[/yellow]")
                for line in result.stdout.strip().splitlines():
                    console.print(f"  {line}")
            else:
                console.print("[dim]No differences[/dim]")
        else:
            console.print("[red]9p: not mounted[/red]")
    elif action == "push":
        rc = sp.run(["mountpoint", "-q", mount_point],
                    capture_output=True, check=False).returncode
        if rc != 0:
            console.print("[red]Not mounted. Run: anklume dev 9p mount[/red]")
            raise typer.Exit(1)
        run_cmd(["sudo", "rsync", "-a", "--exclude=__pycache__",
                 "--exclude=.git",
                 f"{mount_point}/scripts/", f"{target_dir}/scripts/"])
        run_cmd(["sudo", "rsync", "-a",
                 f"{mount_point}/host/", f"{target_dir}/host/"])
        console.print(f"[green]Pushed scripts/ and host/ to {target_dir}[/green]")
    elif action == "restart":
        if not service:
            console.print("[red]Specify a service (e.g. platform_server)[/red]")
            raise typer.Exit(1)
        sp.run(["sudo", "pkill", "-f", service],
               capture_output=True, check=False)
        import time
        time.sleep(0.5)
        sp.Popen(
            ["sudo", "python3", f"{target_dir}/scripts/{service}.py",
             "--host", "0.0.0.0", "--port", "8890"],
            stdout=sp.DEVNULL, stderr=sp.DEVNULL,
        )
        console.print(f"[green]{service} restarted[/green]")
    else:
        console.print(
            f"[red]Unknown action:[/red] {action}. "
            "Use: mount, umount, status, push, restart",
        )
        raise typer.Exit(1)


# Register graph commands from extracted module
from scripts.cli._dev_graph import register as _register_graph  # noqa: E402

_register_graph(app)
