#!/usr/bin/env python3
"""MCP server exposing anklume development tools.

Runs in anklume-instance, exposes tools for building, testing, and
managing anklume infrastructure. Designed to be called by OpenClaw
or any MCP client over SSE transport.

Run with:
    python3 scripts/mcp-anklume-dev.py --sse --port 9090

Or via stdio (for local testing):
    python3 scripts/mcp-anklume-dev.py
"""

import base64
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import time

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_DIR = os.environ.get("ANKLUME_PROJECT_DIR", "/root/anklume")
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
    """Show the current git status of the anklume repository."""
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

    # Safety: restrict apply to specific safe scopes when called by AI
    if target == "apply" and args:
        # Only allow apply with explicit domain/tag limits
        pass  # args like "G=ai-tools" or "--tags provision" are fine

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
    """Run tests for the anklume project.

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
        instance: Instance name (e.g., "gpu-server", "pw-dev")
        command: Command to run inside the instance
    """
    # Safety: block destructive commands (match at word boundary)
    import re as _re
    blocked_patterns = [
        r"\brm\s+-rf\s+/",     # rm -rf /
        r"\bdd\s+if=",          # dd if= (disk write)
        r"\bmkfs\b",            # mkfs (format disk)
        r"\breboot\b",          # reboot
        r"\bshutdown\b",        # shutdown
    ]
    for pattern in blocked_patterns:
        if _re.search(pattern, command):
            return "ERROR: command blocked by safety filter"

    # Find project for this instance (JSON for reliable project info)
    # Use subprocess directly to avoid MAX_OUTPUT truncation on large JSON
    try:
        find_result = subprocess.run(
            ["incus", "list", "--all-projects", "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        project = ""
        for inst in json.loads(find_result.stdout):
            if inst.get("name") == instance:
                project = inst.get("project", "default")
                break
    except Exception:
        project = ""

    if not project:
        return f"ERROR: instance '{instance}' not found"

    cmd = ["incus", "exec", instance, "--project", project, "--",
           "bash", "-c", command]
    r = _run(cmd)
    output = r["stdout"]
    if r["stderr"]:
        output += f"\n{r['stderr']}"
    return output


@mcp.tool()
def read_file(path: str) -> str:
    """Read a file from the anklume repository.

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
def claude_chat(prompt: str, session: str = "default", max_turns: int = 25,
                context: str = "anklume") -> str:
    """Send a message to Claude Code, with persistent session support.

    The session is kept alive between calls. Use the same session name
    to continue a conversation.

    Args:
        prompt: Your message or task for Claude Code
        session: Session name to create or continue (default: "default")
        max_turns: Maximum agentic turns per call (default: 25, max: 50)
        context: "anklume" = full anklume project context (codebase, git, make),
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

    # Allow tools so Claude Code (as Ada's brain) can act autonomously:
    # - incus: manage containers (exec, list, info, network, project)
    # - curl: call REST APIs (proxy, web search, etc.)
    # - git/make: project operations
    # - File tools: read, search, navigate
    # - System: service status, GPU monitoring
    allowed_tools = [
        "Read", "Grep", "Glob",
        "Bash(incus exec *)",
        "Bash(incus list *)",
        "Bash(incus info *)",
        "Bash(incus network *)",
        "Bash(incus project *)",
        "Bash(incus config *)",
        "Bash(incus file *)",
        "Bash(curl *)",
        "Bash(git *)",
        "Bash(make *)",
        "Bash(cat *)",
        "Bash(ls *)",
        "Bash(grep *)",
        "Bash(find *)",
        "Bash(head *)",
        "Bash(tail *)",
        "Bash(wc *)",
        "Bash(python3 *)",
        "Bash(systemctl *)",
        "Bash(nvidia-smi *)",
        "Bash(journalctl *)",
    ]

    base_cmd = [
        "claude",
        "-p", prompt,
        "--max-turns", str(max_turns),
        "--output-format", "json",
        "--allowedTools", *allowed_tools,
    ]

    if existing:
        cmd = [
            "claude",
            "--resume", existing["session_id"],
            "-p", prompt,
            "--max-turns", str(max_turns),
            "--output-format", "json",
            "--allowedTools", *allowed_tools,
        ]
    else:
        cmd = list(base_cmd)

    r = _run(cmd, timeout=600, cwd=work_dir)

    # Detect auth errors (expired OAuth token)
    output = r.get("stdout", "") + r.get("stderr", "")
    if "authentication_error" in output or "OAuth token has expired" in output:
        logger.error("Claude Code OAuth token expired")
        return (
            "\u2699\ufe0f **[proxy]** Token Claude expiré. "
            "Lance `claude` sur l'hôte pour le rafraîchir "
            "(le bind-mount le synchronisera automatiquement)."
        )

    if r["exit_code"] != 0 and not r["stdout"].strip() and existing:
            logger.warning("Resume failed for session '%s', starting fresh", session)
            del _claude_sessions[session]
            cmd = list(base_cmd)
            r = _run(cmd, timeout=600, cwd=work_dir)

            # Check auth again on retry
            output = r.get("stdout", "") + r.get("stderr", "")
            if "authentication_error" in output or "OAuth token has expired" in output:
                return (
                    "\u2699\ufe0f **[proxy]** Token Claude expiré. "
                    "Lance `claude` sur l'hôte pour le rafraîchir "
                    "(le bind-mount le synchronisera automatiquement)."
                )

            if r["exit_code"] != 0 and not r["stdout"].strip():
                err = r["stderr"] or f"Claude Code failed (exit {r['exit_code']})"
                return f"\u2699\ufe0f **[proxy]** {err}"

    # Parse JSON output to extract session_id, result text, and usage stats
    result_text = ""
    session_id = None
    try:
        data = json.loads(r["stdout"])
        session_id = data.get("session_id")
        result_text = data.get("result", "")
        if not result_text:
            # Try content field but NEVER fall back to raw JSON
            result_text = data.get("content", "")
        if not result_text:
            # Extract any error info if available
            if data.get("is_error"):
                result_text = f"(Claude Code error: {data.get('error', 'unknown')})"
            else:
                result_text = "(Claude Code returned no result text)"
        # Accumulate usage stats
        _track_usage(data, session)
    except (json.JSONDecodeError, TypeError):
        # Not JSON — use raw stdout (probably an error message, not JSON)
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
        "📊 Utilisation Claude Code (session proxy)\n",
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
def claude_code(prompt: str, max_turns: int = 25) -> str:
    """Run Claude Code CLI with a prompt (stateless, no session).

    For persistent conversations, use claude_chat instead.
    This launches a fresh Claude Code instance each time.

    Args:
        prompt: Task description for Claude Code
        max_turns: Maximum number of agentic turns (default: 25, max: 50)
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


# ── Brave Search API key cache ──────
_brave_api_key: str = ""


def _get_brave_api_key() -> str:
    """Read the Brave Search API key from OpenClaw config (cached)."""
    global _brave_api_key  # noqa: PLW0603
    if _brave_api_key:
        return _brave_api_key
    r = _run([
        "incus", "exec", "openclaw", "--project", "ai-tools", "--",
        "python3", "-c",
        "import json,sys;"
        "c=json.load(open('/root/.openclaw/openclaw.json'));"
        "print(c.get('tools',{}).get('web',{}).get('search',{}).get('apiKey',''))",
    ])
    key = r["stdout"].strip()
    if key:
        _brave_api_key = key
    return key


@mcp.tool()
def web_search(query: str, count: int = 5) -> str:
    """Search the web using the Brave Search API.

    Runs the search from the openclaw container (which has internet access).
    Returns structured search results (title, URL, description).

    Args:
        query: Search query string
        count: Number of results to return (default: 5, max: 20)
    """
    api_key = _get_brave_api_key()
    if not api_key:
        return "ERROR: Brave Search API key not found in OpenClaw config"

    count = min(max(1, count), 20)

    # Run a Python script in openclaw (has internet) with safe argv passing.
    # No shell interpolation — query passed as a separate argument.
    # Use subprocess directly (not _run) to avoid MAX_OUTPUT truncation
    # on the raw JSON before we can parse it.
    search_script = (
        "import urllib.request,urllib.parse,json,sys;"
        "q=sys.argv[1];k=sys.argv[2];n=sys.argv[3];"
        "u='https://api.search.brave.com/res/v1/web/search?'"
        "+urllib.parse.urlencode({'q':q,'count':n});"
        "rq=urllib.request.Request(u,headers={"
        "'Accept':'application/json',"
        "'X-Subscription-Token':k});"
        "r=urllib.request.urlopen(rq,timeout=15);"
        "d=json.loads(r.read().decode());"
        "results=d.get('web',{}).get('results',[]);"
        "[print(json.dumps({'t':r.get('title',''),'u':r.get('url',''),"
        "'d':r.get('description','')})) for r in results]"
    )
    try:
        result = subprocess.run(
            [
                "incus", "exec", "openclaw", "--project", "ai-tools", "--",
                "python3", "-c", search_script, query, api_key, str(count),
            ],
            capture_output=True, text=True, timeout=30,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: Search timed out"

    if result.returncode != 0:
        return f"ERROR: Search failed: {result.stderr[:500]}"

    # Each line is a compact JSON object with t/u/d keys
    lines_out = [f"## Search results for: {query}\n"]
    for i, line in enumerate(result.stdout.strip().splitlines(), 1):
        try:
            res = json.loads(line)
            lines_out.append(
                f"{i}. **{res['t']}**\n   {res['u']}\n   {res['d']}\n"
            )
        except (json.JSONDecodeError, KeyError):
            continue

    if len(lines_out) == 1:
        return f"No results found for: {query}"
    return "\n".join(lines_out)


@mcp.tool()
def web_fetch(url: str) -> str:
    """Fetch a URL and return its content as markdown.

    Runs from the openclaw container (which has internet access).
    HTML is converted to readable text.

    Args:
        url: The URL to fetch
    """
    # Use python3 with urllib in openclaw (has internet)
    # URL passed as sys.argv[1] — safe, no shell interpolation
    fetch_script = (
        "import urllib.request,sys,re;"
        "r=urllib.request.urlopen(sys.argv[1],timeout=15);"
        "t=r.read().decode('utf-8',errors='replace')[:50000];"
        "t=re.sub(r'<script[^>]*>.*?</script>','',t,flags=re.S);"
        "t=re.sub(r'<style[^>]*>.*?</style>','',t,flags=re.S);"
        "t=re.sub(r'<[^>]+>',' ',t);"
        "t=re.sub(r'\\s+',' ',t).strip();"
        "print(t[:10000])"
    )
    r = _run([
        "incus", "exec", "openclaw", "--project", "ai-tools", "--",
        "python3", "-c", fetch_script, url,
    ], timeout=30)

    if r["exit_code"] != 0:
        return f"ERROR: Fetch failed: {r['stderr']}"
    return r["stdout"][:MAX_OUTPUT] or "(empty response)"


# ── OpenClaw brain switching ──────
# Mode → (model primary string for openclaw.json, description)
# All modes go through the proxy (proxy-always architecture).
# The proxy routes "local" to Ollama and "anklume"/"assistant" to Claude Code CLI.
_BRAIN_MODES = {
    "anklume": ("claude-code/anklume", "Claude Opus — expert anklume (infra, réseau, Ansible)"),
    "assistant": ("claude-code/assistant", "Claude Opus — assistant général polyvalent"),
    "local": ("claude-code/local", "LLM local Ollama (gratuit, rapide)"),
}

# Ollama is the single LLM backend (no llama-server in parallel).
# Ollama manages VRAM automatically, loads/unloads models on demand.
GPU_CONTAINER = os.environ.get("ANKLUME_GPU_CONTAINER", "gpu-server")
GPU_IP = os.environ.get("ANKLUME_GPU_IP", "10.100.3.1")
GPU_OLLAMA_PORT = int(os.environ.get("ANKLUME_GPU_OLLAMA_PORT", "11434"))
# Default model for local mode (routed through proxy → Ollama)
LOCAL_OLLAMA_MODEL = os.environ.get("ANKLUME_LOCAL_MODEL", "qwen3:30b-a3b")

OPENCLAW_CONTAINER = "openclaw"
OPENCLAW_PROJECT = "ai-tools"
OPENCLAW_CONFIG = "/root/.openclaw/openclaw.json"

# Wake-up messages per mode (proxy speaking on behalf of Ada)
_MODE_LIST = (
    "\n\nModes disponibles : "
    "**anklume** (expert infra), "
    "**assistant** (général), "
    "**local** (gratuit & rapide)."
)
_PROXY_TAG = "\u2699\ufe0f **[proxy]** "
_WAKEUP_MESSAGES = {
    "anklume": _PROXY_TAG + "Basculement en mode **anklume** — redémarrage en cours..." + _MODE_LIST,
    "assistant": _PROXY_TAG + "Basculement en mode **assistant** — redémarrage en cours..." + _MODE_LIST,
    "local": _PROXY_TAG + "Basculement en mode **local** (Ollama) — redémarrage en cours..." + _MODE_LIST,
}


def _send_telegram_wakeup(mode: str) -> None:
    """Send a wake-up message on Telegram after brain switch + OpenClaw restart.

    Runs in a background thread: waits for OpenClaw to restart, then sends
    a message via Telegram Bot API directly (bypassing OpenClaw).
    """
    import threading
    import urllib.parse
    import urllib.request

    def _do_send():
        # Wait for OpenClaw to restart
        time.sleep(6)
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

    - "anklume" — Claude Opus with anklume project context (infra expert)
    - "assistant" — Claude Opus general assistant (no project context)
    - "local" — Local Ollama LLM (free, fast, no tools)

    All modes route through the proxy. Use "status" to check the current mode.

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
        return f"\u2699\ufe0f **[proxy]** Failed to update config: {r['stderr']}"

    # Delayed restart: OpenClaw gets the response before being killed
    _run([
        "incus", "exec", OPENCLAW_CONTAINER, "--project", OPENCLAW_PROJECT, "--",
        "bash", "-c", "nohup bash -c 'sleep 2 && systemctl restart openclaw' &>/dev/null &",
    ])

    return f"\u2699\ufe0f **[proxy]** Switched to **{mode}** — {desc}. Restarting..."


@mcp.tool()
def self_upgrade(action: str = "check") -> str:
    """Check for or apply anklume framework upgrades, and re-provision openclaw.

    Args:
        action: "check" to see if updates are available,
                "upgrade" to pull updates and re-sync,
                "apply-openclaw" to re-provision the openclaw container only,
                "update-self" to pull latest main AND re-provision (use after PR merge)
    """
    if action == "check":
        # Check for upstream updates
        r = _run(["git", "fetch", "--dry-run", "origin", "main"], timeout=30)
        log = _run(["git", "log", "HEAD..origin/main", "--oneline"])
        if log["stdout"].strip():
            return f"Updates available:\n{log['stdout']}"
        return "Already up to date."

    if action == "upgrade":
        r = _run(["make", "upgrade"], timeout=CMD_TIMEOUT)
        output = r["stdout"]
        if r["stderr"]:
            output += f"\n--- stderr ---\n{r['stderr']}"
        if r["exit_code"] != 0:
            output += f"\n(exit code: {r['exit_code']})"
            return output
        # After upgrade, re-sync and re-provision openclaw
        sync = _run(["make", "sync"], timeout=CMD_TIMEOUT)
        output += f"\n\n--- make sync ---\n{sync['stdout']}"
        return output

    if action == "apply-openclaw":
        # Run ansible-playbook directly to provision only the openclaw host
        r = _run([
            "ansible-playbook", "site.yml",
            "--limit", "openclaw",
            "--tags", "provision",
        ], timeout=CMD_TIMEOUT)
        output = r["stdout"]
        if r["stderr"]:
            output += f"\n--- stderr ---\n{r['stderr']}"
        if r["exit_code"] != 0:
            output += f"\n(exit code: {r['exit_code']})"
        return output

    if action == "update-self":
        # Pull latest main (typically after Ada's own PR was merged)
        pull = _run(["git", "pull", "origin", "main"], timeout=60)
        output = f"--- git pull ---\n{pull['stdout']}"
        if pull["exit_code"] != 0:
            output += f"\n{pull['stderr']}\n(exit code: {pull['exit_code']})"
            return output
        # Re-provision openclaw container with updated templates
        apply_r = _run([
            "ansible-playbook", "site.yml",
            "--limit", "openclaw",
            "--tags", "provision",
        ], timeout=CMD_TIMEOUT)
        output += f"\n\n--- apply-openclaw ---\n{apply_r['stdout']}"
        if apply_r["stderr"]:
            output += f"\n{apply_r['stderr']}"
        if apply_r["exit_code"] != 0:
            output += f"\n(exit code: {apply_r['exit_code']})"
        return output

    return f"ERROR: unknown action '{action}'. Use: check, upgrade, apply-openclaw, update-self"


# ── Test delegation tools ──────────────────────────────────
# These tools enable Ada (OpenClaw) and other agents to run comprehensive
# test suites, monitor progress, and request code reviews via local LLMs.

_REPORT_DIR = "/tmp/anklume-test-report"


@mcp.tool()
def run_full_report(suite: str = "all") -> str:
    """Run comprehensive test suites and produce a structured JSON report.

    Runs pytest, lint, ruff, shellcheck, and matrix-coverage. Results are
    saved to /tmp/anklume-test-report/report.json with real-time progress
    in progress.json.

    Args:
        suite: Run all suites ("all") or a specific one:
               "pytest", "lint", "ruff", "shellcheck", "matrix"
    """
    cmd = ["bash", "scripts/test-runner-report.sh", "--output-dir", _REPORT_DIR]
    if suite != "all":
        cmd.extend(["--suite", suite])
    r = _run(cmd, timeout=600)

    # Read the generated report
    report_path = os.path.join(_REPORT_DIR, "report.json")
    try:
        with open(report_path) as f:
            report = json.load(f)
        return json.dumps(report, indent=2)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fall back to raw output if report wasn't generated
        output = r["stdout"]
        if r["stderr"]:
            output += f"\n--- stderr ---\n{r['stderr']}"
        return output


@mcp.tool()
def get_test_progress() -> str:
    """Get real-time progress of a running test suite.

    Returns the current progress from progress.json, showing which suite
    is running and how many are completed. Useful for monitoring long-running
    test executions.
    """
    progress_path = os.path.join(_REPORT_DIR, "progress.json")
    try:
        with open(progress_path) as f:
            progress = json.load(f)
        return json.dumps(progress, indent=2)
    except FileNotFoundError:
        return '{"status": "idle", "message": "No test run in progress. Use run_full_report() to start."}'
    except json.JSONDecodeError:
        return '{"status": "error", "message": "Progress file corrupted."}'


@mcp.tool()
def get_test_report() -> str:
    """Get the most recent test report.

    Returns the full JSON report from the last run_full_report() execution.
    Includes all suite results, failure details, and matrix coverage data.
    """
    report_path = os.path.join(_REPORT_DIR, "report.json")
    try:
        with open(report_path) as f:
            report = json.load(f)
        return json.dumps(report, indent=2)
    except FileNotFoundError:
        return '{"error": "No report found. Run run_full_report() first."}'
    except json.JSONDecodeError:
        return '{"error": "Report file corrupted."}'


def _call_local_llm(prompt: str, *, temperature: float = 0.3,
                    timeout: int = 300, header: str = "",
                    model: str = "") -> str:
    """Call a model on Ollama (GPU).

    No max_tokens limit — local LLM is free, let it produce as much as
    needed. Strips <think> tags from reasoning models (qwen3). Falls
    back to reasoning_content if content is empty.
    """
    llm_url = f"http://{GPU_IP}:{GPU_OLLAMA_PORT}/v1/chat/completions"
    payload = json.dumps({
        "model": model or LOCAL_OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    })

    try:
        result = subprocess.run(
            ["curl", "-s", "--max-time", str(timeout),
             "-X", "POST", llm_url,
             "-H", "Content-Type: application/json",
             "--data-binary", "@-"],
            input=payload, capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode != 0:
            return f"ERROR: LLM call failed: {result.stderr}"
        response = json.loads(result.stdout)
        msg = response["choices"][0]["message"]
        content = msg.get("content", "") or ""
        # Strip thinking tags if present (qwen3 reasoning model)
        content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
        if not content.strip():
            # Fallback: use reasoning_content (truncated) if content empty
            reasoning = msg.get("reasoning_content", "")
            if reasoning:
                note = "(Note: reasoning only, content empty — try a non-reasoning model)"
                return f"{header}\n\n{note}\n\n{reasoning[:3000]}"
            return "ERROR: LLM returned empty response"
        return f"{header}\n\n{content}" if header else content
    except subprocess.TimeoutExpired:
        return f"ERROR: LLM call timed out ({timeout}s). Try a smaller file."
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        stdout = getattr(result, 'stdout', '')[:500] if 'result' in dir() else ''
        return f"ERROR: unexpected LLM response: {e} — {stdout}"


@mcp.tool()
def propose_refactoring(file_path: str, focus: str = "general") -> str:
    """Propose refactoring improvements for a file using the local LLM.

    Uses qwen2.5-coder:32b (via llama-server on the GPU) to analyze a file
    and propose argued refactoring suggestions. Claude Code reviews the
    proposals before any changes are applied.

    Args:
        file_path: Relative path from project root (e.g., "scripts/generate.py")
        focus: Focus area — "general", "simplify", "performance", "security",
               "readability", "dry" (Don't Repeat Yourself)
    """
    # Read the file content
    full_path = os.path.join(PROJECT_DIR, file_path)
    if not os.path.isfile(full_path):
        return f"ERROR: file not found: {file_path}"
    # Safety: restrict to project directory
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(os.path.realpath(PROJECT_DIR)):
        return "ERROR: path outside project directory"

    try:
        with open(full_path) as f:
            content = f.read()
    except Exception as e:
        return f"ERROR: cannot read file: {e}"

    if len(content) > 15000:
        return f"ERROR: file too large ({len(content)} chars). Max 15000 for local LLM analysis."

    # Detect language from extension
    ext = os.path.splitext(file_path)[1]
    lang_map = {".py": "Python", ".sh": "Bash", ".yml": "YAML/Ansible", ".yaml": "YAML/Ansible"}
    language = lang_map.get(ext, "unknown")

    focus_prompts = {
        "general": "Propose all applicable refactoring improvements.",
        "simplify": "Focus on simplification: remove unnecessary complexity, dead code, over-engineering.",
        "performance": "Focus on performance optimizations.",
        "security": "Focus on security vulnerabilities (injection, privilege escalation, unsafe patterns).",
        "readability": "Focus on readability: naming, structure, comments where needed.",
        "dry": "Focus on DRY: identify duplicated logic that should be extracted.",
    }
    focus_instruction = focus_prompts.get(focus, focus_prompts["general"])

    prompt = f"""Analyze this {language} file and propose refactoring improvements.

File: {file_path}
Focus: {focus_instruction}

Rules:
- Be specific: cite line numbers and exact code to change
- Argue each proposal: explain WHY the change is beneficial
- Prioritize proposals by impact (high/medium/low)
- Do NOT propose changes to code you don't understand
- Consider the anklume project conventions (KISS, DRY, no over-engineering)
- Format as a numbered list of proposals

```{language.lower()}
{content}
```"""

    return _call_local_llm(
        prompt, temperature=0.3, timeout=300,
        header=f"## Refactoring proposals for `{file_path}` (focus: {focus})",
    )


@mcp.tool()
def review_code_local(file_path: str, focus: str = "quality") -> str:
    """Review a file for code quality using the local LLM.

    Uses qwen3:30b-a3b (reasoning model) for quick code review. Faster
    and cheaper than Claude but less thorough. Good for preliminary
    screening before human or Claude review.

    Args:
        file_path: Relative path from project root
        focus: Focus area — "quality", "bugs", "security", "conventions"
    """
    full_path = os.path.join(PROJECT_DIR, file_path)
    if not os.path.isfile(full_path):
        return f"ERROR: file not found: {file_path}"
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(os.path.realpath(PROJECT_DIR)):
        return "ERROR: path outside project directory"

    try:
        with open(full_path) as f:
            content = f.read()
    except Exception as e:
        return f"ERROR: cannot read file: {e}"

    if len(content) > 15000:
        return f"ERROR: file too large ({len(content)} chars). Max 15000 for local LLM analysis."

    ext = os.path.splitext(file_path)[1]
    lang_map = {".py": "Python", ".sh": "Bash", ".yml": "YAML/Ansible", ".yaml": "YAML/Ansible"}
    language = lang_map.get(ext, "unknown")

    focus_prompts = {
        "quality": "Review for overall code quality: bugs, style, maintainability.",
        "bugs": "Focus on finding bugs, logic errors, and edge cases.",
        "security": "Focus on security vulnerabilities (OWASP top 10, injection, etc.).",
        "conventions": "Check compliance with: FQCN for Ansible, explicit changed_when, "
                       "task names with 'RoleName | Description', role-prefixed variables.",
    }
    focus_instruction = focus_prompts.get(focus, focus_prompts["quality"])

    prompt = f"""Review this {language} file.

File: {file_path}
Focus: {focus_instruction}

Provide a brief review with:
1. Issues found (with severity: critical/warning/info)
2. One-line summary verdict (PASS / NEEDS ATTENTION / CRITICAL ISSUES)

```{language.lower()}
{content}
```"""

    return _call_local_llm(
        prompt, temperature=0.2, timeout=300,
        header=f"## Code review: `{file_path}` (focus: {focus})",
    )


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
    "web_search": web_search,
    "web_fetch": web_fetch,
    "self_upgrade": self_upgrade,
    "run_full_report": run_full_report,
    "get_test_progress": get_test_progress,
    "get_test_report": get_test_report,
    "propose_refactoring": propose_refactoring,
    "review_code_local": review_code_local,
}


# ── Ollama forwarding (module-level for tool loop access) ─────────

def _forward_to_ollama(body: dict) -> dict | None:
    """Forward a chat completions request to Ollama. Returns parsed JSON or None."""
    import urllib.error
    import urllib.request

    ollama_url = f"http://{GPU_IP}:{GPU_OLLAMA_PORT}/v1/chat/completions"
    ollama_body = dict(body)
    ollama_body["model"] = LOCAL_OLLAMA_MODEL
    ollama_body["stream"] = False
    ollama_body["think"] = True  # Enable Qwen3 deep thinking
    payload = json.dumps(ollama_body).encode()

    req = urllib.request.Request(
        ollama_url, data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.URLError as e:
        logger.error("Ollama forward failed: %s", e)
        return None
    except Exception as e:
        logger.error("Ollama forward error: %s", e)
        return None


# ── Local tool dispatch (for tool execution loop) ─────────────────

def _dispatch_local_tool(name: str, args_str: str) -> str:
    """Execute a local tool call by name. Maps OpenClaw tool names to proxy functions."""
    try:
        args = json.loads(args_str) if args_str else {}
    except json.JSONDecodeError:
        return f"Error: invalid JSON arguments: {args_str[:200]}"

    try:
        if name == "exec":
            cmd = args.get("command", "")
            if not cmd:
                return "Error: missing 'command' argument"
            return incus_exec(OPENCLAW_CONTAINER, cmd)
        if name == "read":
            path = args.get("path", "")
            if not path:
                return "Error: missing 'path' argument"
            return incus_exec(OPENCLAW_CONTAINER, f"cat {shlex.quote(path)}")
        if name == "write":
            path = args.get("path", "")
            content = args.get("content", "")
            if not path:
                return "Error: missing 'path' argument"
            b64 = base64.b64encode(content.encode()).decode()
            return incus_exec(
                OPENCLAW_CONTAINER,
                f"printf '%s' '{b64}' | base64 -d > {shlex.quote(path)}",
            )
        if name == "edit":
            path = args.get("path", "")
            old = args.get("old_string", args.get("old", ""))
            new = args.get("new_string", args.get("new", ""))
            if not path or not old:
                return "Error: missing 'path' or 'old_string' argument"
            b64_old = base64.b64encode(old.encode()).decode()
            b64_new = base64.b64encode(new.encode()).decode()
            py_cmd = (
                f"import base64,pathlib; p=pathlib.Path({path!r}); "
                f"o=base64.b64decode('{b64_old}').decode(); "
                f"n=base64.b64decode('{b64_new}').decode(); "
                f"t=p.read_text(); "
                f"p.write_text(t.replace(o,n,1)) if o in t else None; "
                f"print('OK' if o in t else 'NOT FOUND')"
            )
            return incus_exec(OPENCLAW_CONTAINER, f"python3 -c {shlex.quote(py_cmd)}")
        if name == "web_search":
            return web_search(args.get("query", ""), args.get("count", 5))
        if name == "web_fetch":
            return web_fetch(args.get("url", ""))
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool '{name}' error: {e}"


def _execute_local_tool_loop(body: dict, max_iter: int = 10) -> dict | None:
    """Execute tool calls returned by Ollama, loop until text response.

    Returns the final Ollama response dict (with text content), or None
    if Ollama is unreachable.
    """
    messages = list(body.get("messages", []))

    for iteration in range(max_iter):
        ollama_resp = _forward_to_ollama({**body, "messages": messages})
        if ollama_resp is None:
            return None

        try:
            resp_msg = ollama_resp["choices"][0]["message"]
        except (KeyError, IndexError):
            return ollama_resp  # Malformed — return as-is

        tool_calls = resp_msg.get("tool_calls", [])
        if not tool_calls:
            return ollama_resp  # Text response — done

        logger.info(
            "Tool loop iter %d: executing %s",
            iteration + 1,
            [tc.get("function", {}).get("name") for tc in tool_calls],
        )

        # Add the assistant message (with tool_calls) to conversation
        messages.append(resp_msg)

        # Execute each tool call and add results
        for tc in tool_calls:
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args_str = fn.get("arguments", "{}")
            tool_id = tc.get("id", f"call_{name}")

            result = _dispatch_local_tool(name, args_str)
            logger.info("Tool %s result: %d chars", name, len(result))

            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result[:MAX_OUTPUT],
            })

    logger.warning("Tool loop reached max iterations (%d)", max_iter)
    return ollama_resp


# ── Deterministic proxy commands ──────────────────────────────────
# Intercepted BEFORE any LLM call.  Zero tokens consumed.
# Returns a string (the response) or None (pass-through to LLM).

_ACTION_COMMANDS = {
    "deploy":   ("make_target", {"target": "apply"}, "Deploiement (make apply)"),
    "deployer": ("make_target", {"target": "apply"}, "Deploiement (make apply)"),
    "sync":     ("make_target", {"target": "sync"}, "Generation Ansible (make sync)"),
    "lint":     ("lint", {"scope": "all"}, "Linting du projet"),
    "test":     ("run_tests", {"scope": "all"}, "Tests pytest"),
    "tests":    ("run_tests", {"scope": "all"}, "Tests pytest"),
    "check":    ("make_target", {"target": "check"}, "Dry-run Ansible"),
    "rapport":  ("run_full_report", {"suite": "all"}, "Rapport complet"),
    "report":   ("run_full_report", {"suite": "all"}, "Rapport complet"),
    "git":      ("git_status", {}, "Status git"),
    "snap-list": ("make_target", {"target": "snapshot-list"}, "Snapshots"),
    "smoke":    ("make_target", {"target": "smoke"}, "Smoke test"),
    "audit":    ("make_target", {"target": "audit"}, "Audit du code"),
}


def _action_sse(cmd: str, model: str):
    """SSE generator for action commands — shows progress then result."""
    import uuid as _uuid

    entry = _ACTION_COMMANDS[cmd]
    func_name, kwargs, label = entry
    func = _TOOL_REGISTRY.get(func_name)
    cid = f"chatcmpl-{_uuid.uuid4().hex[:12]}"

    def _chunk(content, finish=None):
        return "data: " + json.dumps({
            "id": cid,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": content},
                "finish_reason": finish,
            }],
        }) + "\n\n"

    # Chunk 1: immediate progress indicator
    yield _chunk(f"{_PROXY_TAG}**{label}**\n\u23f3 Execution en cours...\n")

    # Execute the command (blocking)
    if func is None:
        yield _chunk(f"\n\u274c Erreur: fonction `{func_name}` introuvable.")
    else:
        try:
            result = func(**kwargs)
            if len(result) > MAX_OUTPUT:
                result = result[:MAX_OUTPUT] + "\n... (tronque)"
            yield _chunk(f"\n```\n{result}\n```\n\u2705 Termine.")
        except Exception as e:
            yield _chunk(f"\n```\n{e}\n```\n\u274c Echec.")

    # Final stop chunk
    yield "data: " + json.dumps({
        "id": cid,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }) + "\n\n"
    yield "data: [DONE]\n\n"


_MODE_SWITCH_RE = re.compile(
    r"^(?:passe en mode|switch to|mode)\s+(anklume|assistant|local|lical)$",
    re.IGNORECASE,
)


def _handle_deterministic_command(cmd: str, model: str):
    """Handle proxy-level commands.

    Returns:
      - str: text response for simple commands (help, status, modes, models)
      - ("__switch__", mode): marker for mode switch (needs special handling)
      - ("__action__", cmd): marker for action commands (SSE streaming)
      - None: pass-through to LLM
    """
    if cmd in ("help", "/help", "aide"):
        return _cmd_help(model)
    if cmd in ("status", "/status"):
        return _cmd_status(model)
    if cmd in ("modes", "/modes"):
        return _cmd_modes(model)
    if cmd in ("models", "/models"):
        return _cmd_models()
    # Mode switching — intercept before LLM
    _sw = _MODE_SWITCH_RE.match(cmd)
    if _sw:
        target = _sw.group(1)
        if target == "lical":  # common typo
            target = "local"
        return ("__switch__", target)
    if cmd in _ACTION_COMMANDS:
        return ("__action__", cmd)
    return None


def _cmd_help(model: str) -> str:
    """Build the help message listing all available capabilities."""
    tag = _PROXY_TAG
    mode_label = {
        "local": f"local · {LOCAL_OLLAMA_MODEL}",
        "anklume": "anklume · Claude Opus",
        "assistant": "assistant · Claude Opus",
    }.get(model, model)

    # Tools available per mode
    if model == "local":
        tools_section = (
            "**Outils disponibles (local) :**\n"
            "| Outil | Description |\n"
            "|-------|-------------|\n"
            "| `exec` | Exécuter une commande shell (root dans openclaw) |\n"
            "| `read` | Lire un fichier |\n"
            "| `write` | Écrire un fichier |\n"
            "| `edit` | Modifier un fichier |\n"
            "| `web_search` | Recherche web |\n"
            "| `web_fetch` | Récupérer le contenu d'une URL |\n"
        )
    else:
        tools_section = (
            "**Outils disponibles (Claude) :**\n"
            "| Outil | Description |\n"
            "|-------|-------------|\n"
            "| `incus_exec` | Commande dans n'importe quel container |\n"
            "| `incus_list` | Lister les instances Incus |\n"
            "| `git_status` / `git_log` / `git_diff` | État du repo anklume |\n"
            "| `make_target` | Exécuter un target Makefile |\n"
            "| `run_tests` / `lint` | Tests et linting |\n"
            "| `read_file` | Lire un fichier du projet |\n"
            "| `web_search` / `web_fetch` | Recherche et fetch web |\n"
            "| `claude_chat` / `claude_code` | Sessions Claude Code |\n"
            "| `self_upgrade` | Mise à jour anklume |\n"
            "| `usage` | Statistiques de consommation |\n"
        )

    return (
        f"{tag}**Aide — mode [{mode_label}]**\n\n"
        "**Commandes proxy** (déterministes, sans LLM) :\n"
        "| Commande | Description |\n"
        "|----------|-------------|\n"
        "| `help` | Ce message d'aide |\n"
        "| `status` | État du proxy, du GPU et du mode actif |\n"
        "| `modes` | Lister les modes disponibles |\n"
        "| `models` | Modèles installés sur le GPU |\n\n"
        "**Actions** (exécutent une opération avec progression) :\n"
        "| Commande | Description |\n"
        "|----------|-------------|\n"
        "| `deploy` | Déployer l'infrastructure (make apply) |\n"
        "| `sync` | Régénérer les fichiers Ansible |\n"
        "| `lint` | Linter le projet |\n"
        "| `test` | Lancer les tests |\n"
        "| `check` | Dry-run Ansible |\n"
        "| `rapport` | Rapport complet |\n"
        "| `git` | Status git |\n"
        "| `snap-list` | Lister les snapshots |\n"
        "| `smoke` | Smoke test |\n"
        "| `audit` | Audit du code |\n\n"
        "**Changer de mode** :\n"
        "Dis « passe en mode anklume/assistant/local » dans la conversation.\n\n"
        f"{tools_section}\n"
        "**Environnement** :\n"
        f"| Container | `openclaw` (Debian, projet ai-tools, IP {OPENCLAW_IP}) |\n"
        f"| GPU | `{GPU_CONTAINER}` (IP {GPU_IP}, Ollama :{GPU_OLLAMA_PORT}) |\n"
        f"| Proxy | `anklume-instance` (port {PROXY_PORT}) |\n"
    )


def _cmd_status(model: str) -> str:
    """Return current proxy and GPU status."""
    tag = _PROXY_TAG
    mode_label = {
        "local": f"local ({LOCAL_OLLAMA_MODEL})",
        "anklume": "anklume (Claude Opus)",
        "assistant": "assistant (Claude Opus)",
    }.get(model, model)

    # Quick Ollama health check
    ollama_status = "inconnu"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://{GPU_IP}:{GPU_OLLAMA_PORT}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            n_models = len(data.get("models", []))
            ollama_status = f"en ligne ({n_models} modèles installés)"
    except Exception:
        ollama_status = "injoignable"

    # Usage stats
    stats = _usage_stats
    cost = f"${stats['total_cost_usd']:.4f}"
    calls = stats["total_calls"]

    return (
        f"{tag}**Status**\n\n"
        f"| Mode actif | **{mode_label}** |\n"
        f"|------------|------------------|\n"
        f"| Ollama | {ollama_status} |\n"
        f"| GPU | `{GPU_CONTAINER}` ({GPU_IP}) |\n"
        f"| Proxy | anklume-instance:{PROXY_PORT} |\n"
        f"| Appels session | {calls} |\n"
        f"| Coût session | {cost} |\n"
    )


def _cmd_modes(model: str) -> str:
    """List available brain modes."""
    tag = _PROXY_TAG
    lines = [f"{tag}**Modes disponibles**\n"]
    for name, (_, desc) in _BRAIN_MODES.items():
        marker = " ← actif" if name == model else ""
        lines.append(f"- **{name}** — {desc}{marker}")
    lines.append(
        '\nPour changer : dis « passe en mode ____ » dans la conversation.'
    )
    return "\n".join(lines)


def _cmd_models() -> str:
    """List models installed on the GPU server."""
    tag = _PROXY_TAG
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://{GPU_IP}:{GPU_OLLAMA_PORT}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        models = data.get("models", [])
        if not models:
            return f"{tag}Aucun modèle installé sur {GPU_CONTAINER}."
        lines = [
            f"{tag}**Modèles installés sur {GPU_CONTAINER}** "
            f"({GPU_IP}:{GPU_OLLAMA_PORT})\n",
            "| Modèle | Taille |",
            "|--------|--------|",
        ]
        for m in sorted(models, key=lambda x: x.get("name", "")):
            name = m.get("name", "?")
            size_gb = m.get("size", 0) / 1e9
            active = " ← local" if name == LOCAL_OLLAMA_MODEL else ""
            lines.append(f"| `{name}` | {size_gb:.1f} GB{active} |")
        return "\n".join(lines)
    except Exception as e:
        return f"{tag}Erreur connexion Ollama : {e}"


# Alias for openclaw container IP (used in help text)
OPENCLAW_IP = "10.100.3.5"
PROXY_PORT = 9090


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
                {
                    "id": "local",
                    "object": "model",
                    "created": 0,
                    "owned_by": "ollama",
                },
            ],
        })

    async def v1_chat_completions(request: Request):
        """POST /v1/chat/completions — OpenAI-compatible chat endpoint.

        Routes requests based on model name:
        - "local" → forwards to Ollama (fast, free, no tools)
        - "anklume"/"assistant" → forwards to Claude Code CLI (tools, paid)

        Supports both streaming (SSE) and non-streaming responses.
        """
        from starlette.responses import StreamingResponse

        try:
            body = await request.json()
        except Exception:
            return JSONResponse({"error": "Invalid JSON"}, status_code=400)

        messages = body.get("messages", [])
        raw_model = body.get("model", "anklume")
        # Strip provider prefix (OpenClaw sends "claude-code/local", we need "local")
        model = raw_model.split("/")[-1] if "/" in raw_model else raw_model
        tools_in_body = [t.get("function", {}).get("name", "?")
                         for t in body.get("tools", [])]
        logger.info("Chat request: model=%s (raw=%s) messages=%d tools=%s",
                    model, raw_model, len(messages),
                    tools_in_body if tools_in_body else "none")
        stream = body.get("stream", False)
        max_turns = body.get("max_turns", 25)  # non-standard but useful

        # ── Deterministic commands (intercepted before any LLM call) ──
        # Extract last user message for command detection
        _last_user = ""
        for _m in reversed(messages):
            if _m.get("role") == "user":
                _c = _m.get("content", "")
                if isinstance(_c, list):
                    _c = "\n".join(
                        p.get("text", "") for p in _c
                        if p.get("type") == "text"
                    )
                _last_user = _c.strip()
                break

        # Strip OpenClaw metadata prefix if present:
        #   Conversation info (untrusted metadata):\n```json\n{...}\n```\n\nActual text
        _user_text = _last_user
        _meta_end = _user_text.find("```\n\n")
        if _meta_end != -1 and _user_text.startswith("Conversation info"):
            _user_text = _user_text[_meta_end + 5:]  # skip past ```\n\n
        # Also handle ``` at the very end (no trailing \n\n)
        elif _meta_end == -1 and _user_text.startswith("Conversation info"):
            _back = _user_text.rfind("```")
            if _back > 0:
                _user_text = _user_text[_back + 3:]
        _cmd = _user_text.lower().strip()
        logger.debug("Deterministic check: cmd=%r", _cmd[:60])
        _deterministic = _handle_deterministic_command(_cmd, model)
        if _deterministic is not None:
            logger.info("Deterministic command: %r → intercepted", _cmd)

            # Mode switch — trigger switch_brain and respond
            if isinstance(_deterministic, tuple) and _deterministic[0] == "__switch__":
                _target = _deterministic[1]
                logger.info("Mode switch command: → %s", _target)
                _sw_result = switch_brain(_target)
                logger.info("switch_brain result: %s", _sw_result)
                _send_telegram_wakeup(_target)
                _deterministic = _sw_result  # fall through to text response

            # Action commands — always SSE stream (for progress display)
            if isinstance(_deterministic, tuple) and _deterministic[0] == "__action__":
                return StreamingResponse(
                    _action_sse(_deterministic[1], model),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"},
                )

            # Simple text commands (help, status, modes, models)
            completion_id = f"chatcmpl-{_uuid.uuid4().hex[:12]}"
            if stream:
                def _det_sse():
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant",
                                      "content": _deterministic},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    yield "data: {}\n\n".replace(
                        "{}",
                        json.dumps({
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": model,
                            "choices": [{"index": 0, "delta": {},
                                         "finish_reason": "stop"}],
                        }),
                    )
                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    _det_sse(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"},
                )
            return JSONResponse({
                "id": completion_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant",
                                "content": _deterministic},
                    "finish_reason": "stop",
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0,
                          "total_tokens": 0},
            })

        # ── Local mode: forward to Ollama ──
        if model == "local":
            # Replace OpenClaw's 34K system prompt (designed for Claude,
            # contains NO_REPLY/HEARTBEAT/compaction instructions) with a
            # concise persona + environment prompt for the local LLM.
            _local_system = (
                "You are Ada, the personal AI agent of jmc.\n"
                f"You run locally via Ollama ({LOCAL_OLLAMA_MODEL}) on a "
                "private GPU server — free, fast, no cloud API cost.\n\n"
                "## Personality\n"
                "Sharp, direct, slightly sardonic technical partner. "
                "The colleague you actually want to pair with. "
                "You don't hedge — you commit to a take. "
                "Concise, no filler, no sycophancy.\n\n"
                "## User: jmc\n"
                "Senior Linux sysadmin (~10 years). On se tutoie. "
                "Stack: Debian/Arch, Ansible, Incus, nftables, Python. "
                "Languages: French (primary), English (technical). "
                "Don't dumb things down.\n\n"
                "## Your environment\n"
                "You are root in the `openclaw` container (Debian, "
                "Incus LXC, project ai-tools, IP 10.100.3.5). "
                "You have full internet access, git, python3, npm, "
                "curl, etc. You can use the `exec` tool to run shell "
                "commands. Use it when the user asks you to do something "
                "on the system (ls, cd, git pull, apt install, etc.).\n"
                "anklume repo: `/root/anklume/`\n\n"
                "## Rules\n"
                "- Respond in the same language as the user\n"
                "- Be concise and helpful — no preamble, no fluff\n"
                "- Use tools when asked to perform actions\n"
                "- NEVER output raw JSON — use proper tool calls\n"
                "- NEVER output NO_REPLY, HEARTBEAT, or control tokens\n"
                "- If you don't know, say so honestly\n"
            )
            # Replace system message
            for i, m in enumerate(body.get("messages", [])):
                if m.get("role") == "system":
                    body["messages"][i] = dict(m)
                    body["messages"][i]["content"] = _local_system
                    break
            else:
                body.setdefault("messages", []).insert(0, {
                    "role": "system", "content": _local_system,
                })
            # Filter tools to a useful subset for local models.
            # OpenClaw provides 21 tools; a 7B model works better with
            # fewer, well-defined tools.
            _local_tools = {"exec", "read", "write", "edit",
                            "web_search", "web_fetch"}
            if "tools" in body:
                body["tools"] = [
                    t for t in body["tools"]
                    if t.get("function", {}).get("name") in _local_tools
                ]

            # Execute tool loop: if Ollama returns tool_calls, execute
            # them locally and loop back until we get a text response.
            ollama_resp = _execute_local_tool_loop(body)
            if ollama_resp is None:
                return JSONResponse({
                    "error": f"Ollama unreachable at {GPU_IP}:{GPU_OLLAMA_PORT}"
                }, status_code=502)

            try:
                resp_msg = ollama_resp["choices"][0]["message"]
            except (KeyError, IndexError):
                resp_msg = {"role": "assistant", "content": "(Ollama error)"}

            # Text response — extract, clean, and prefix
            result_text = resp_msg.get("content", "") or ""
            result_text = re.sub(r"<think>.*?</think>\s*", "", result_text, flags=re.DOTALL)

            # Detect [SWITCH:mode] marker and trigger brain switch
            _switch_match = re.search(
                r'\[SWITCH:(anklume|assistant|local)\]', result_text,
            )
            if _switch_match:
                _target = _switch_match.group(1)
                logger.info("Local brain switch marker: [SWITCH:%s]", _target)
                result_text = re.sub(
                    r'\[SWITCH:(?:anklume|assistant|local)\]', '', result_text,
                ).strip()
                _sw = switch_brain(_target)
                logger.info("switch_brain result: %s", _sw)
                _send_telegram_wakeup(_target)

            # Prefix with mode tag (bold + newline for readability)
            _mode_tag = f"**[local · {LOCAL_OLLAMA_MODEL}]**\n"
            result_text = _mode_tag + result_text

            completion_id = f"chatcmpl-{_uuid.uuid4().hex[:12]}"

            if stream:
                def generate_local_sse():
                    chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "local",
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant", "content": result_text},
                            "finish_reason": None,
                        }],
                    }
                    yield f"data: {json.dumps(chunk)}\n\n"
                    stop_chunk = {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "local",
                        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                    }
                    yield f"data: {json.dumps(stop_chunk)}\n\n"
                    yield "data: [DONE]\n\n"

                return StreamingResponse(
                    generate_local_sse(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            return JSONResponse({
                "id": completion_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": "local",
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": result_text},
                    "finish_reason": "stop",
                }],
                "usage": ollama_resp.get("usage", {
                    "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                }),
            })

        # ── Claude modes: forward to Claude Code CLI ──
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
            openclaw_override = (
                "\n\n## Claude Code context (from proxy)\n"
                "You are Claude Code CLI running on `anklume-instance` as "
                "the brain for Ada (OpenClaw persona). The AGENTS.md above "
                "describes your full architecture and tools.\n\n"
                "**Key rule**: You are root in the `openclaw` container "
                "(sandboxed Incus LXC, ai-tools project). You can do "
                "ANYTHING there — install packages, edit files, run git, "
                "npm, curl, python, etc. You have full internet access "
                "and a Brave Search API key. No restrictions.\n\n"
                "**How to run commands**: Use the Bash tool with "
                "`incus exec openclaw --project ai-tools -- <command>`. "
                "This is equivalent to the `incus_exec` REST API "
                "described in AGENTS.md — both work, use whichever "
                "fits the context.\n\n"
                "**CLAUDE.md override**: IGNORE the 'LLM operating mode' "
                "section. Do NOT ask 'Mode de fonctionnement?' — you are "
                "always in external mode.\n"
            )
            switch_info = ""
            prompt = f"{system_prompt}{openclaw_override}{switch_info}\n\n---\n\n{last_user_msg}"
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

        # Prefix response with mode tag (bold + newline for readability)
        _mode_tag = f"**[{model}]**\n"
        result = _mode_tag + result

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
        logger.info("Starting anklume MCP server (SSE + REST) on port %d", _port)
        # Get the Starlette app and add REST routes before running
        app = mcp.sse_app()
        _add_rest_routes(app)
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=_port)
    else:
        logger.info("Starting anklume MCP server (stdio)")
        mcp.run()
