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

import json
import logging
import os
import re
import subprocess
import sys
import time

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = os.environ.get("ANKLUME_PROJECT_DIR", "/root/AnKLuMe")
# Safety: max output size to avoid flooding MCP responses
MAX_OUTPUT = 10000
# Command timeout in seconds
CMD_TIMEOUT = 300
# Claude Code session timeout (seconds) — sessions older than this are auto-cleaned
CLAUDE_SESSION_TTL = 3600

# ── Claude Code session store ──────
# Maps session_name → {"session_id": str, "created": float, "last_used": float, "turns": int}
_claude_sessions: dict[str, dict] = {}

# ── Usage tracking ──────
# Accumulates cost and token counts across all Claude Code calls
_usage_stats: dict = {
    "started_at": None,         # ISO timestamp of first call
    "total_cost_usd": 0.0,
    "total_input_tokens": 0,
    "total_output_tokens": 0,
    "total_cache_read_tokens": 0,
    "total_cache_creation_tokens": 0,
    "total_calls": 0,
    "calls_by_session": {},     # session_name → {"cost_usd": float, "calls": int}
}

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


PURE_DIR = "/root/.claude-pure"


def _run(cmd: list[str], timeout: int = CMD_TIMEOUT, cwd: str = PROJECT_DIR) -> dict:
    """Run a command and return structured result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
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


def _track_usage(data: dict, session: str = "") -> None:
    """Accumulate usage stats from a Claude Code JSON response."""
    cost = data.get("total_cost_usd", 0)
    usage = data.get("usage", {})
    if not _usage_stats["started_at"]:
        _usage_stats["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    _usage_stats["total_cost_usd"] += cost
    _usage_stats["total_input_tokens"] += usage.get("input_tokens", 0)
    _usage_stats["total_output_tokens"] += usage.get("output_tokens", 0)
    _usage_stats["total_cache_read_tokens"] += usage.get("cache_read_input_tokens", 0)
    _usage_stats["total_cache_creation_tokens"] += usage.get("cache_creation_input_tokens", 0)
    _usage_stats["total_calls"] += 1
    if session:
        s = _usage_stats["calls_by_session"].setdefault(session, {"cost_usd": 0.0, "calls": 0})
        s["cost_usd"] += cost
        s["calls"] += 1


def _clean_stale_sessions() -> None:
    """Remove sessions older than CLAUDE_SESSION_TTL."""
    now = time.time()
    stale = [k for k, v in _claude_sessions.items() if now - v["last_used"] > CLAUDE_SESSION_TTL]
    for k in stale:
        logger.info("Cleaning stale Claude session: %s", k)
        del _claude_sessions[k]


@mcp.tool()
def claude_chat(prompt: str, session: str = "default", max_turns: int = 10,
                context: str = "anklume") -> str:
    """Send a message to Claude Code, with persistent session support.

    The session is kept alive between calls. Use the same session name
    to continue a conversation.

    Args:
        prompt: Your message or task for Claude Code
        session: Session name to create or continue (default: "default")
        max_turns: Maximum agentic turns per call (default: 10, max: 50)
        context: "anklume" = full AnKLuMe project context (codebase, git, make),
                 "pure" = general-purpose assistant, no project context
    """
    _clean_stale_sessions()
    max_turns = min(max_turns, 50)

    # Choose working directory based on context mode
    if context == "pure":
        os.makedirs(PURE_DIR, exist_ok=True)
        work_dir = PURE_DIR
    else:
        work_dir = PROJECT_DIR

    existing = _claude_sessions.get(session)

    base_cmd = [
        "claude",
        "-p", prompt,
        "--max-turns", str(max_turns),
        "--output-format", "json",
    ]

    if existing:
        cmd = [
            "claude",
            "--resume", existing["session_id"],
            "-p", prompt,
            "--max-turns", str(max_turns),
            "--output-format", "json",
        ]
    else:
        cmd = list(base_cmd)

    r = _run(cmd, timeout=600, cwd=work_dir)

    # Detect auth errors (expired OAuth token)
    output = r.get("stdout", "") + r.get("stderr", "")
    if "authentication_error" in output or "OAuth token has expired" in output:
        logger.error("Claude Code OAuth token expired — run sync-claude-credentials.sh on host")
        return (
            "Mon token d'authentification Claude a expiré. "
            "Demande à jmc de lancer sur l'hôte : "
            "`host/boot/sync-claude-credentials.sh`"
        )

    if r["exit_code"] != 0 and not r["stdout"].strip():
        # If resume failed, try without resume (session may have expired)
        if existing:
            logger.warning("Resume failed for session '%s', starting fresh", session)
            del _claude_sessions[session]
            cmd = list(base_cmd)
            r = _run(cmd, timeout=600, cwd=work_dir)

            # Check auth again on retry
            output = r.get("stdout", "") + r.get("stderr", "")
            if "authentication_error" in output or "OAuth token has expired" in output:
                return (
                    "Mon token d'authentification Claude a expiré. "
                    "Demande à jmc de lancer sur l'hôte : "
                    "`host/boot/sync-claude-credentials.sh`"
                )

            if r["exit_code"] != 0 and not r["stdout"].strip():
                return r["stderr"] or f"Claude Code failed (exit {r['exit_code']})"

    # Parse JSON output to extract session_id, result text, and usage stats
    result_text = ""
    session_id = None
    try:
        data = json.loads(r["stdout"])
        session_id = data.get("session_id")
        result_text = data.get("result", "")
        if not result_text:
            result_text = data.get("content", r["stdout"])
        # Accumulate usage stats
        _track_usage(data, session)
    except (json.JSONDecodeError, TypeError):
        result_text = r["stdout"]

    # Store/update session
    if session_id:
        now = time.time()
        if session in _claude_sessions:
            _claude_sessions[session]["session_id"] = session_id
            _claude_sessions[session]["last_used"] = now
            _claude_sessions[session]["turns"] += 1
        else:
            _claude_sessions[session] = {
                "session_id": session_id,
                "created": now,
                "last_used": now,
                "turns": 1,
            }

    if r["stderr"] and r["exit_code"] != 0:
        result_text += f"\n--- stderr ---\n{r['stderr']}"

    return result_text[:MAX_OUTPUT] or "(no response)"


@mcp.tool()
def claude_sessions() -> str:
    """List active Claude Code sessions.

    Shows all persistent sessions with their age and turn count.
    """
    _clean_stale_sessions()
    if not _claude_sessions:
        return "No active sessions. Use claude_chat to start one."
    lines = []
    now = time.time()
    for name, info in _claude_sessions.items():
        age_min = int((now - info["created"]) / 60)
        lines.append(
            f"  {name}: {info['turns']} turns, "
            f"age {age_min}min, id={info['session_id'][:12]}..."
        )
    return "Active Claude sessions:\n" + "\n".join(lines)


@mcp.tool()
def claude_session_clear(session: str = "") -> str:
    """Clear a Claude Code session or all sessions.

    Args:
        session: Session name to clear (empty = clear all sessions)
    """
    if not session:
        count = len(_claude_sessions)
        _claude_sessions.clear()
        return f"Cleared {count} session(s)."
    if session in _claude_sessions:
        del _claude_sessions[session]
        return f"Session '{session}' cleared."
    return f"Session '{session}' not found."


@mcp.tool()
def usage() -> str:
    """Show cumulative Claude Code usage stats for this proxy session.

    Includes total cost (USD), token counts, and per-session breakdown.
    Note: this tracks proxy-level usage only, not the global Max plan quota.
    """
    s = _usage_stats
    if s["total_calls"] == 0:
        return "Aucun appel Claude Code enregistré depuis le démarrage du proxy."
    uptime = ""
    if s["started_at"]:
        uptime = f"Depuis : {s['started_at']}\n"
    lines = [
        f"📊 Utilisation Claude Code (session proxy)\n",
        uptime,
        f"Coût total : ${s['total_cost_usd']:.4f} USD",
        f"Appels : {s['total_calls']}",
        f"Tokens entrée : {s['total_input_tokens']:,}",
        f"Tokens sortie : {s['total_output_tokens']:,}",
        f"Tokens cache (lecture) : {s['total_cache_read_tokens']:,}",
        f"Tokens cache (création) : {s['total_cache_creation_tokens']:,}",
    ]
    if s["calls_by_session"]:
        lines.append("\nPar session :")
        for name, info in s["calls_by_session"].items():
            lines.append(f"  {name}: ${info['cost_usd']:.4f} ({info['calls']} appels)")
    lines.append(
        "\n⚠️ Ces stats couvrent uniquement les appels via ce proxy. "
        "Le quota global du plan Max n'est pas accessible par API."
    )
    return "\n".join(lines)


@mcp.tool()
def claude_code(prompt: str, max_turns: int = 10) -> str:
    """Run Claude Code CLI with a prompt (stateless, no session).

    For persistent conversations, use claude_chat instead.
    This launches a fresh Claude Code instance each time.

    Args:
        prompt: Task description for Claude Code
        max_turns: Maximum number of agentic turns (default: 10, max: 50)
    """
    max_turns = min(max_turns, 50)
    cmd = [
        "claude",
        "-p", prompt,
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


# ── OpenClaw brain switching ──────
# Mode → (model primary string, description)
_BRAIN_MODES = {
    "anklume": ("claude-code/anklume", "Claude Opus — expert AnKLuMe (infra, réseau, Ansible)"),
    "assistant": ("claude-code/assistant", "Claude Opus — assistant général polyvalent"),
    "local": ("ollama/qwen3:30b-a3b", "LLM local qwen3 MoE (gratuit, rapide)"),
}

# llama-server service to activate per mode (in the ollama container)
# Claude modes use the 32B coder model (for MCP coding tools)
# Local mode uses qwen3:30b-a3b MoE (3B active params → fast, good at chat)
_LLAMA_SERVICES = {
    "anklume": "llama-server",       # qwen2.5-coder:32b
    "assistant": "llama-server",     # qwen2.5-coder:32b
    "local": "llama-server-chat",    # qwen3:30b-a3b
}
OLLAMA_CONTAINER = "ollama"

OPENCLAW_CONTAINER = "openclaw"
OPENCLAW_PROJECT = "ai-tools"
OPENCLAW_CONFIG = "/root/.openclaw/openclaw.json"

# Wake-up messages per mode (Ada's voice, includes mode list)
_MODE_LIST = (
    "\n\nModes disponibles : "
    "**anklume** (expert infra), "
    "**assistant** (général), "
    "**local** (gratuit & rapide)."
)
_WAKEUP_MESSAGES = {
    "anklume": "Me revoilà en mode **anklume** — prête à bosser sur l'infra." + _MODE_LIST,
    "assistant": "De retour en mode **assistant** — à ton service." + _MODE_LIST,
    "local": "Revenue en mode **local** (qwen3 MoE) — réponses gratuites et rapides." + _MODE_LIST,
}


def _send_telegram_wakeup(mode: str) -> None:
    """Send a wake-up message on Telegram after brain switch + OpenClaw restart.

    Runs in a background thread: waits for OpenClaw to restart, then sends
    a message via Telegram Bot API directly (bypassing OpenClaw).
    """
    import threading
    import urllib.request
    import urllib.parse

    def _do_send():
        # Wait for OpenClaw to restart.
        # local mode takes longer (llama-server model swap + OpenClaw restart)
        wait = 15 if mode == "local" else 6
        time.sleep(wait)
        # Read bot token and chat ID from OpenClaw config
        try:
            r = _run([
                "incus", "exec", OPENCLAW_CONTAINER, "--project", OPENCLAW_PROJECT, "--",
                "python3", "-c",
                "import json; c=json.load(open('" + OPENCLAW_CONFIG + "')); "
                "print(c['channels']['telegram']['botToken']); "
                "print(list(c.get('tools',{}).get('elevated',{}).get('allowFrom',{}).get('telegram',[]))[0])",
            ])
            lines = r["stdout"].strip().split("\n")
            if len(lines) < 2:
                logger.warning("Could not read Telegram config for wakeup")
                return
            bot_token = lines[0].strip()
            chat_id = lines[1].strip()
        except Exception as e:
            logger.warning("Failed to read Telegram config: %s", e)
            return

        msg = _WAKEUP_MESSAGES.get(mode, f"Revenue en mode **{mode}**.")
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": msg,
            "parse_mode": "Markdown",
        }).encode()
        try:
            req = urllib.request.Request(url, data=data)
            urllib.request.urlopen(req, timeout=10)
            logger.info("Telegram wakeup sent for mode '%s'", mode)
        except Exception as e:
            logger.warning("Failed to send Telegram wakeup: %s", e)

    t = threading.Thread(target=_do_send, daemon=True)
    t.start()


@mcp.tool()
def switch_brain(mode: str) -> str:
    """Switch OpenClaw's brain mode. Available modes:

    - "anklume" — Claude Opus with AnKLuMe project context (infra expert)
    - "assistant" — Claude Opus general assistant (no project context)
    - "local" — Local LLM (qwen2.5-coder:32b), free, latence plus élevée

    Use "status" to check the current mode.

    Args:
        mode: One of "anklume", "assistant", "local", or "status"
    """
    if mode == "status":
        r = _run([
            "incus", "exec", OPENCLAW_CONTAINER, "--project", OPENCLAW_PROJECT, "--",
            "python3", "-c",
            "import json; c=json.load(open('" + OPENCLAW_CONFIG + "')); "
            "print(c['agents']['defaults']['model']['primary'])",
        ])
        current = r["stdout"].strip()
        for name, (model_str, desc) in _BRAIN_MODES.items():
            if current == model_str:
                return f"Current mode: **{name}** — {desc}"
        return f"Current model: {current} (custom)"

    if mode not in _BRAIN_MODES:
        modes = ", ".join(_BRAIN_MODES.keys())
        return f"Unknown mode '{mode}'. Available: {modes}, status"

    model_str, desc = _BRAIN_MODES[mode]

    # Update the config JSON in the openclaw container
    # Use semicolons instead of newlines (avoids shell escaping issues with incus exec)
    update_script = (
        "import json; "
        "c = json.load(open('" + OPENCLAW_CONFIG + "')); "
        "c['agents']['defaults']['model']['primary'] = '" + model_str + "'; "
        "json.dump(c, open('" + OPENCLAW_CONFIG + "', 'w'), indent=2); "
        "print('ok')"
    )
    r = _run([
        "incus", "exec", OPENCLAW_CONTAINER, "--project", OPENCLAW_PROJECT, "--",
        "python3", "-c", update_script,
    ])
    if "ok" not in r["stdout"]:
        return f"Failed to update config: {r['stderr']}"

    # Switch llama-server model in the ollama container
    target_svc = _LLAMA_SERVICES.get(mode, "llama-server")
    _run([
        "incus", "exec", OLLAMA_CONTAINER, "--project", OPENCLAW_PROJECT, "--",
        "bash", "-c",
        f"systemctl is-active --quiet {target_svc} || "
        f"{{ systemctl stop llama-server llama-server-chat 2>/dev/null; "
        f"systemctl start {target_svc}; }}",
    ])
    logger.info("llama-server switched to %s for mode '%s'", target_svc, mode)

    # Delayed restart: OpenClaw gets the response before being killed
    _run([
        "incus", "exec", OPENCLAW_CONTAINER, "--project", OPENCLAW_PROJECT, "--",
        "bash", "-c", "nohup bash -c 'sleep 2 && systemctl restart openclaw' &>/dev/null &",
    ])

    return f"Switched to **{mode}** — {desc}. Restarting..."


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
    "claude_chat": claude_chat,
    "claude_sessions": claude_sessions,
    "claude_session_clear": claude_session_clear,
    "claude_code": claude_code,
    "lint": lint,
    "switch_brain": switch_brain,
    "usage": usage,
}


def _add_rest_routes(app):
    """Add REST API routes to the Starlette app."""
    import uuid as _uuid

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
        # Trigger Telegram wake-up when switch_brain is called via REST API
        if tool_name == "switch_brain" and body.get("mode") in _BRAIN_MODES:
            _send_telegram_wakeup(body["mode"])
        return PlainTextResponse(result)

    # ── OpenAI-compatible /v1/chat/completions ──────
    # Allows OpenClaw (or any client) to use Claude Code as a model provider.
    # Messages are forwarded to Claude Code CLI with session persistence.

    async def v1_models(request: Request):
        """GET /v1/models — list available models."""
        return JSONResponse({
            "object": "list",
            "data": [
                {
                    "id": "anklume",
                    "object": "model",
                    "created": 0,
                    "owned_by": "anthropic",
                },
                {
                    "id": "assistant",
                    "object": "model",
                    "created": 0,
                    "owned_by": "anthropic",
                },
            ],
        })

    async def v1_chat_completions(request: Request):
        """POST /v1/chat/completions — OpenAI-compatible chat endpoint.

        Extracts the last user message and forwards it to Claude Code
        with persistent session support. Supports both streaming (SSE)
        and non-streaming responses.
        """
        from starlette.responses import StreamingResponse

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        messages = body.get("messages", [])
        model = body.get("model", "anklume")
        stream = body.get("stream", False)
        max_turns = body.get("max_turns", 10)  # non-standard but useful

        # Determine context from model name
        context = "pure" if model == "assistant" else "anklume"

        # Extract system message (OpenClaw persona: SOUL.md, AGENTS.md, etc.)
        system_parts = []
        for msg in messages:
            if msg.get("role") == "system":
                c = msg.get("content", "")
                if isinstance(c, list):
                    c = "\n".join(p.get("text", "") for p in c if p.get("type") == "text")
                if c:
                    system_parts.append(c)
        system_prompt = "\n\n".join(system_parts)

        # Extract last user message
        last_user_msg = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    parts = [p.get("text", "") for p in content if p.get("type") == "text"]
                    content = "\n".join(parts)
                last_user_msg = content
                break

        if not last_user_msg:
            return JSONResponse({
                "error": "No user message found in messages array"
            }, status_code=400)

        # Use separate sessions per context to avoid cross-contamination
        session_name = "openclaw-anklume" if context == "anklume" else "openclaw-assistant"

        # Detect new conversation: if messages has only 1-2 entries
        # (system + user), start a fresh session
        user_msg_count = sum(1 for m in messages if m.get("role") == "user")
        is_new_session = session_name not in _claude_sessions
        if user_msg_count <= 1 and not is_new_session:
            logger.info("New conversation detected, clearing session '%s'", session_name)
            del _claude_sessions[session_name]
            is_new_session = True

        # For new sessions, prepend system prompt + switch instructions
        if is_new_session and system_prompt:
            switch_info = (
                "\n\n## Brain switching\n"
                "The user can ask you to switch brain mode. Available modes:\n"
                "- **anklume** — Claude Opus expert AnKLuMe (infra, Ansible, Incus)\n"
                "- **assistant** — Claude Opus assistant général (Ada)\n"
                "- **local** — LLM local gratuit et rapide (qwen3 MoE)\n\n"
                "When the user asks to switch mode (e.g. 'passe en mode anklume', "
                "'switch to local', 'mode assistant'), include the marker "
                "`[SWITCH:MODE]` in your response (e.g. `[SWITCH:anklume]`). "
                "The proxy will detect it and handle the switch automatically.\n"
                "After the marker, tell the user you're switching and will "
                "restart in a few seconds."
            )
            prompt = f"{system_prompt}{switch_info}\n\n---\n\n{last_user_msg}"
        else:
            prompt = last_user_msg

        # Inject usage stats when user asks about consumption/costs
        _usage_keywords = re.compile(
            r'(?:consomm|conso|usage|co[uû]t|combien|forfait|quota|'
            r'utilisation|credits?|tokens?|billing|dépens)',
            re.IGNORECASE,
        )
        if _usage_keywords.search(last_user_msg):
            usage_data = usage()  # call our own usage() tool
            prompt += (
                f"\n\n---\n[USAGE DATA — injected by proxy, present these stats "
                f"to the user in a clear, friendly way]\n{usage_data}"
            )

        # Forward to Claude Code with session persistence
        result = claude_chat(prompt, session=session_name,
                             max_turns=max_turns, context=context)

        # Detect [SWITCH:mode] marker in response and trigger brain switch
        switch_match = re.search(r'\[SWITCH:(anklume|assistant|local)\]', result)
        if switch_match:
            target_mode = switch_match.group(1)
            logger.info("Brain switch marker detected: [SWITCH:%s]", target_mode)
            # Strip the marker from the response text
            result = re.sub(r'\[SWITCH:(?:anklume|assistant|local)\]', '', result).strip()
            # Trigger the switch (delayed restart inside)
            switch_result = switch_brain(target_mode)
            logger.info("switch_brain result: %s", switch_result)
            # Schedule a Telegram wake-up message after OpenClaw restarts
            _send_telegram_wakeup(target_mode)

        completion_id = f"chatcmpl-{_uuid.uuid4().hex[:12]}"

        if stream:
            # SSE streaming response — send the full result as a single chunk
            # (Claude Code CLI doesn't support true token streaming, so we
            # simulate it by sending the complete response as one SSE event)
            def generate_sse():
                chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "role": "assistant",
                            "content": result,
                        },
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(chunk)}\n\n"
                # Send stop chunk
                stop_chunk = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }],
                }
                yield f"data: {json.dumps(stop_chunk)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(
                generate_sse(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )

        # Non-streaming response
        return JSONResponse({
            "id": completion_id,
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result,
                },
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        })

    app.routes.insert(0, Route("/api", api_index))
    app.routes.insert(1, Route("/api/{tool}", api_call, methods=["POST", "GET"]))
    app.routes.insert(2, Route("/v1/models", v1_models, methods=["GET"]))
    app.routes.insert(3, Route("/v1/chat/completions", v1_chat_completions, methods=["POST"]))


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
