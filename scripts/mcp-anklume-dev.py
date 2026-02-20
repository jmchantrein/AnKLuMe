#!/usr/bin/env python3
"""MCP server exposing AnKLuMe development tools.

Runs in anklume-instance, exposes tools for building, testing, and
managing AnKLuMe infrastructure. Designed to be called by OpenClaw
or any MCP client over SSE transport.

Run with:
    python3 scripts/mcp-anklume-dev.py --sse --port 9090

Or via stdio (for local testing):
    python3 scripts/mcp-anklume-dev.py
"""

import logging
import os
import subprocess
import sys

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = os.environ.get("ANKLUME_PROJECT_DIR", "/root/AnKLuMe")
# Safety: max output size to avoid flooding MCP responses
MAX_OUTPUT = 10000
# Command timeout in seconds
CMD_TIMEOUT = 300

def _parse_args() -> tuple:
    """Parse CLI arguments for transport mode."""
    port = 9090
    use_sse = "--sse" in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = int(sys.argv[i + 1])
    return use_sse, port


_use_sse, _port = _parse_args()

_mcp_kwargs = {"name": "anklume-dev"}
if _use_sse:
    _mcp_kwargs.update(host="0.0.0.0", port=_port)

mcp = FastMCP(**_mcp_kwargs)


def _run(cmd: list[str], timeout: int = CMD_TIMEOUT) -> dict:
    """Run a command and return structured result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=PROJECT_DIR,
        )
        stdout = result.stdout[:MAX_OUTPUT]
        stderr = result.stderr[:MAX_OUTPUT]
        if len(result.stdout) > MAX_OUTPUT:
            stdout += f"\n... (truncated, {len(result.stdout)} total chars)"
        if len(result.stderr) > MAX_OUTPUT:
            stderr += f"\n... (truncated, {len(result.stderr)} total chars)"
        return {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"exit_code": -1, "stdout": "", "stderr": str(e)}


@mcp.tool()
def git_status() -> str:
    """Show the current git status of the AnKLuMe repository."""
    r = _run(["git", "status", "--short", "--branch"])
    return r["stdout"] or r["stderr"]


@mcp.tool()
def git_log(count: int = 10) -> str:
    """Show recent git commits.

    Args:
        count: Number of commits to show (default: 10, max: 50)
    """
    count = min(count, 50)
    r = _run(["git", "log", "--oneline", f"-{count}"])
    return r["stdout"] or r["stderr"]


@mcp.tool()
def git_diff(staged: bool = False) -> str:
    """Show current changes in the repository.

    Args:
        staged: If true, show staged changes. If false, show unstaged changes.
    """
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    r = _run(cmd)
    return r["stdout"] or "(no changes)"


@mcp.tool()
def make_target(target: str, args: str = "") -> str:
    """Run a Makefile target.

    Common targets: sync, sync-dry, lint, check, apply, test,
    smoke, console, help, matrix-coverage.

    Args:
        target: The make target to run (e.g., "sync-dry", "lint")
        args: Additional arguments (e.g., "G=pro" for apply-limit)
    """
    # Safety: block dangerous targets
    blocked = {"flush", "nftables-deploy", "claude-host"}
    if target in blocked:
        return f"ERROR: target '{target}' is blocked for safety. Run it manually."

    cmd = ["make", target]
    if args:
        cmd.extend(args.split())
    r = _run(cmd, timeout=CMD_TIMEOUT)
    output = r["stdout"]
    if r["stderr"]:
        output += f"\n--- stderr ---\n{r['stderr']}"
    if r["exit_code"] != 0:
        output += f"\n(exit code: {r['exit_code']})"
    return output


@mcp.tool()
def run_tests(scope: str = "all") -> str:
    """Run tests for the AnKLuMe project.

    Args:
        scope: "all" for all pytest tests, "generator" for generate.py tests,
               or a specific test file path (e.g., "tests/test_generate.py::TestClass")
    """
    if scope == "all":
        cmd = ["python3", "-m", "pytest", "tests/", "-v", "--tb=short"]
    elif scope == "generator":
        cmd = ["python3", "-m", "pytest", "tests/test_generate.py", "-v", "--tb=short"]
    else:
        cmd = ["python3", "-m", "pytest", scope, "-v", "--tb=short"]
    r = _run(cmd, timeout=CMD_TIMEOUT)
    output = r["stdout"]
    if r["stderr"]:
        output += f"\n--- stderr ---\n{r['stderr']}"
    return output


@mcp.tool()
def incus_list(project: str = "") -> str:
    """List Incus instances, optionally filtered by project.

    Args:
        project: Incus project name (empty for all projects)
    """
    cmd = ["incus", "list", "--format", "csv", "-c", "nstp4"]
    if project:
        cmd.extend(["--project", project])
    else:
        cmd.append("--all-projects")
    r = _run(cmd)
    return r["stdout"] or r["stderr"]


@mcp.tool()
def incus_exec(instance: str, command: str) -> str:
    """Execute a command inside an Incus instance.

    Args:
        instance: Instance name (e.g., "ollama", "pw-dev")
        command: Command to run inside the instance
    """
    # Safety: block destructive commands
    blocked_patterns = ["rm -rf /", "dd ", "mkfs", "reboot", "shutdown"]
    for pattern in blocked_patterns:
        if pattern in command:
            return f"ERROR: command contains blocked pattern '{pattern}'"

    # Find project for this instance
    find_r = _run(["incus", "list", "--all-projects", "--format", "csv", "-c", "nP"])
    project = ""
    for line in find_r["stdout"].splitlines():
        parts = line.split(",")
        if len(parts) >= 2 and parts[0].strip() == instance:
            project = parts[1].strip()
            break

    if not project:
        return f"ERROR: instance '{instance}' not found"

    cmd = ["incus", "exec", instance, "--project", project, "--"]
    cmd.extend(command.split())
    r = _run(cmd)
    output = r["stdout"]
    if r["stderr"]:
        output += f"\n{r['stderr']}"
    return output


@mcp.tool()
def read_file(path: str) -> str:
    """Read a file from the AnKLuMe repository.

    Args:
        path: Relative path from the project root (e.g., "infra.yml", "docs/SPEC.md")
    """
    full_path = os.path.join(PROJECT_DIR, path)
    # Safety: prevent directory traversal
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(os.path.realpath(PROJECT_DIR)):
        return "ERROR: path outside project directory"
    try:
        with open(real_path) as f:
            content = f.read(MAX_OUTPUT)
            if len(content) == MAX_OUTPUT:
                content += "\n... (truncated)"
            return content
    except FileNotFoundError:
        return f"ERROR: file not found: {path}"
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def claude_code(prompt: str, max_turns: int = 10) -> str:
    """Run Claude Code CLI with a prompt for complex development tasks.

    This launches Claude Code in non-interactive mode. It has full access
    to the AnKLuMe codebase, git, make, ansible, and the Incus socket.

    Args:
        prompt: Task description for Claude Code
        max_turns: Maximum number of agentic turns (default: 10, max: 50)
    """
    max_turns = min(max_turns, 50)
    cmd = [
        "claude",
        "--prompt", prompt,
        "--max-turns", str(max_turns),
        "--output-format", "text",
    ]
    r = _run(cmd, timeout=600)
    output = r["stdout"]
    if r["stderr"]:
        output += f"\n--- stderr ---\n{r['stderr']}"
    if r["exit_code"] != 0:
        output += f"\n(exit code: {r['exit_code']})"
    return output


@mcp.tool()
def lint(scope: str = "all") -> str:
    """Run linters on the codebase.

    Args:
        scope: "all" for full lint, or a specific linter:
               "ansible-lint", "yamllint", "shellcheck", "ruff"
    """
    if scope == "all":
        return make_target("lint")
    cmd_map = {
        "ansible-lint": ["ansible-lint"],
        "yamllint": ["yamllint", "."],
        "shellcheck": ["bash", "-c", "shellcheck scripts/*.sh"],
        "ruff": ["ruff", "check", "."],
    }
    if scope not in cmd_map:
        return f"ERROR: unknown linter '{scope}'. Use: {', '.join(cmd_map.keys())}"
    r = _run(cmd_map[scope])
    output = r["stdout"]
    if r["stderr"]:
        output += f"\n{r['stderr']}"
    return output or "(clean)"


# ── REST API layer (for clients without MCP support) ──────
# POST /api/<tool> with JSON body → plain text response
# GET /api → list available tools

_TOOL_REGISTRY = {
    "git_status": git_status,
    "git_log": git_log,
    "git_diff": git_diff,
    "make_target": make_target,
    "run_tests": run_tests,
    "incus_list": incus_list,
    "incus_exec": incus_exec,
    "read_file": read_file,
    "claude_code": claude_code,
    "lint": lint,
}


def _add_rest_routes(app):
    """Add REST API routes to the Starlette app."""
    from starlette.requests import Request
    from starlette.responses import JSONResponse, PlainTextResponse
    from starlette.routing import Route

    async def api_index(request: Request):
        tools = []
        for name, fn in _TOOL_REGISTRY.items():
            doc = fn.__doc__ or ""
            tools.append({"name": name, "description": doc.split("\n")[0]})
        return JSONResponse({"tools": tools})

    async def api_call(request: Request):
        tool_name = request.path_params["tool"]
        if tool_name not in _TOOL_REGISTRY:
            return PlainTextResponse(f"Unknown tool: {tool_name}", status_code=404)
        try:
            body = await request.json()
        except Exception:
            body = {}
        try:
            result = _TOOL_REGISTRY[tool_name](**body)
        except TypeError as e:
            return PlainTextResponse(f"Bad arguments: {e}", status_code=400)
        return PlainTextResponse(result)

    app.routes.insert(0, Route("/api", api_index))
    app.routes.insert(1, Route("/api/{tool}", api_call, methods=["POST", "GET"]))


if __name__ == "__main__":
    if _use_sse:
        logger.info("Starting AnKLuMe MCP server (SSE + REST) on port %d", _port)
        # Get the Starlette app and add REST routes before running
        app = mcp.sse_app()
        _add_rest_routes(app)
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=_port)
    else:
        logger.info("Starting AnKLuMe MCP server (stdio)")
        mcp.run()
