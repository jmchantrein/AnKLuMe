#!/usr/bin/env python3
"""Standalone Ollama development assistant for anklume.

Three-step pipeline (plan -> code -> review) using local LLMs via Ollama API.
Zero external dependencies -- stdlib only.

Usage:
    python3 scripts/ollama-dev.py                  # Interactive REPL
    python3 scripts/ollama-dev.py "Add timezone"   # One-shot mode
    python3 scripts/ollama-dev.py --fast            # Use smaller models
    python3 scripts/ollama-dev.py --dry-run         # Preview without writing
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import json
import os
import pathlib
import re
import shutil
import sys
import textwrap
import urllib.error
import urllib.request
from typing import Any

# Readline is optional (missing on some minimal builds)
try:
    import readline
except ImportError:
    readline = None  # type: ignore[assignment]


# ── Constants ────────────────────────────────────────────────────────────────

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

FULL_MODELS = {
    "plan": "qwen3:30b-a3b",
    "code": "qwen2.5-coder:32b",
    "review": "qwen3:30b-a3b",
}
FAST_MODELS = {
    "plan": "qwen3:8b",
    "code": "qwen2.5-coder:7b",
    "review": "qwen3:8b",
}

TOKEN_BUDGET = 12_000
TIMEOUT_SECONDS = 600  # 10 minutes
HISTORY_DIR = pathlib.Path.home() / ".anklume"
HISTORY_FILE = HISTORY_DIR / "ollama-dev-history"


# ── ANSI colors ──────────────────────────────────────────────────────────────

class Colors:
    """ANSI escape codes, disabled when stdout is not a TTY."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled

    def _code(self, code: str) -> str:
        return code if self.enabled else ""

    @property
    def reset(self) -> str:
        return self._code("\033[0m")

    @property
    def bold(self) -> str:
        return self._code("\033[1m")

    @property
    def dim(self) -> str:
        return self._code("\033[2m")

    @property
    def red(self) -> str:
        return self._code("\033[31m")

    @property
    def green(self) -> str:
        return self._code("\033[32m")

    @property
    def yellow(self) -> str:
        return self._code("\033[33m")

    @property
    def cyan(self) -> str:
        return self._code("\033[36m")


C = Colors(enabled=sys.stdout.isatty())


# ── Token estimation ────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough char-to-token heuristic."""
    return int(len(text) / 3.5)


def truncate_to_budget(text: str, budget_tokens: int) -> tuple[str, bool]:
    """Truncate text to fit within token budget. Returns (text, was_truncated)."""
    if estimate_tokens(text) <= budget_tokens:
        return text, False
    target_chars = int(budget_tokens * 3.5)
    truncated = text[:target_chars]
    last_nl = truncated.rfind("\n")
    if last_nl > target_chars * 0.8:
        truncated = truncated[:last_nl]
    return truncated + "\n\n[... TRUNCATED -- file too large for context budget ...]\n", True


# ── Qwen3 think tag stripping ───────────────────────────────────────────────

def strip_think_tags(text: str) -> str:
    """Remove Qwen3 <think>...</think> reasoning blocks from output."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ── Ollama HTTP client ──────────────────────────────────────────────────────

class OllamaClient:
    """Minimal Ollama API client using urllib (no dependencies)."""

    def __init__(self, base_url: str = OLLAMA_URL) -> None:
        self.base_url = base_url.rstrip("/")

    def _request(self, path: str, data: dict[str, Any] | None = None, timeout: int = 30) -> Any:
        url = f"{self.base_url}{path}"
        if data is not None:
            payload = json.dumps(data).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        else:
            req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.URLError as e:
            msg = f"Cannot reach Ollama at {self.base_url}: {e}"
            raise ConnectionError(msg) from e
        except TimeoutError as e:
            msg = f"Ollama request timed out after {timeout}s"
            raise TimeoutError(msg) from e

    def check_health(self) -> bool:
        """Return True if Ollama is reachable."""
        try:
            self._request("/api/tags", timeout=5)
        except (ConnectionError, TimeoutError, OSError):
            return False
        return True

    def list_models(self) -> list[str]:
        """List available model names."""
        resp = self._request("/api/tags", timeout=10)
        return [m["name"] for m in resp.get("models", [])]

    def generate(self, model: str, system: str, prompt: str, timeout: int = TIMEOUT_SECONDS) -> str:
        """Send a chat completion request. Returns the assistant content."""
        data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"num_ctx": 16384},
        }
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode())
                content = result.get("message", {}).get("content", "")
                return strip_think_tags(content)
        except urllib.error.URLError as e:
            msg = f"Ollama API error: {e}"
            raise ConnectionError(msg) from e
        except TimeoutError as e:
            msg = f"Request timed out after {timeout}s. Try @fast for smaller models."
            raise TimeoutError(msg) from e


# ── File context manager ────────────────────────────────────────────────────

class FileContext:
    """Manages @file inclusions for the pipeline."""

    def __init__(self, project_root: pathlib.Path) -> None:
        self.project_root = project_root
        self.files: dict[str, str] = {}

    def add(self, path: str) -> str:
        """Add a file to context. Returns a status message."""
        resolved = self.project_root / path
        if not resolved.exists():
            return f"{C.red}File not found: {path}{C.reset}"
        if not resolved.is_file():
            return f"{C.red}Not a file: {path}{C.reset}"
        try:
            content = resolved.read_text()
        except (OSError, UnicodeDecodeError) as e:
            return f"{C.red}Cannot read {path}: {e}{C.reset}"
        self.files[path] = content
        tokens = estimate_tokens(content)
        return f"{C.green}+ {path}{C.reset} ({tokens} tokens est.)"

    def remove(self, path: str) -> str:
        """Remove a file from context."""
        if path in self.files:
            del self.files[path]
            return f"{C.yellow}- {path}{C.reset}"
        return f"{C.red}Not in context: {path}{C.reset}"

    def clear(self) -> str:
        """Clear all files from context."""
        count = len(self.files)
        self.files.clear()
        return f"{C.yellow}Cleared {count} file(s) from context{C.reset}"

    def list_files(self) -> str:
        """List files currently in context with token estimates."""
        if not self.files:
            return f"{C.dim}No files in context{C.reset}"
        lines = []
        total = 0
        for path, content in self.files.items():
            tokens = estimate_tokens(content)
            total += tokens
            lines.append(f"  {C.cyan}{path}{C.reset} ({tokens} tok)")
        lines.append(f"  {C.bold}Total: {total} tokens est.{C.reset}")
        return "\n".join(lines)

    def build_context(self, budget_tokens: int) -> tuple[str, list[str]]:
        """Build file context string within token budget.

        Returns (context_string, warnings).
        """
        if not self.files:
            return "", []
        warnings: list[str] = []
        parts: list[str] = []
        remaining = budget_tokens
        for path, content in self.files.items():
            content, truncated = truncate_to_budget(content, remaining)
            if truncated:
                warnings.append(f"  {C.yellow}Warning: {path} truncated to fit budget{C.reset}")
            remaining -= estimate_tokens(content)
            parts.append(f"### File: {path}\n```\n{content}\n```\n")
            if remaining <= 0:
                break
        return "\n".join(parts), warnings


# ── System prompts ──────────────────────────────────────────────────────────

def load_claude_md(project_root: pathlib.Path) -> str:
    """Load CLAUDE.md from project root."""
    path = project_root / "CLAUDE.md"
    if path.exists():
        return path.read_text()
    return ""


def load_reviewer_checklist(project_root: pathlib.Path) -> str:
    """Load reviewer checklist from .claude/agents/reviewer.md."""
    path = project_root / ".claude" / "agents" / "reviewer.md"
    if not path.exists():
        return ""
    content = path.read_text()
    parts = content.split("---", 2)
    if len(parts) >= 3:
        return parts[2].strip()
    return content


PLAN_SYSTEM = """\
You are a senior infrastructure architect planning changes to the anklume framework.

## Project conventions
{claude_md}

## Your task
Analyze the user's request and produce a structured plan:
1. **Approach**: How to implement the change
2. **Files to modify/create**: List each file with what changes are needed
3. **Risks**: Potential issues or side effects
4. **Testing**: How to validate the change

Be specific and actionable. Reference existing patterns from the included files.
Output in English."""

CODE_SYSTEM = """\
You are an expert coder implementing changes to the anklume framework.

## Conventions
- YAML: Ansible best practices, FQCN, task names as "RoleName | Description"
- Python: stdlib only where possible, ruff-clean, type hints
- Shell: shellcheck-clean, set -euo pipefail
- All code and comments in English

## Output format
For EACH file you modify or create, use this exact format:

### FILE: <relative/path/to/file>
```<language>
<complete file content>
```

Include the COMPLETE file content, not just the changed parts.
If multiple files are needed, repeat the format for each file."""

REVIEW_SYSTEM = """\
You are the quality reviewer of the anklume framework.

## Review checklist
{reviewer_checklist}

## Instructions
Review the generated code against the checklist above.
Produce a structured report:
1. **Verdict**: PASS, WARN (approve with warnings), or FAIL (must fix)
2. **Compliant**: What follows conventions correctly
3. **Warnings**: Non-blocking issues (if any)
4. **Errors**: Blocking issues that must be fixed (if any)
5. **Suggestions**: Optional improvements

Be concise and specific. Reference file names and line numbers."""


# ── File extraction from code output ────────────────────────────────────────

def extract_files(code_output: str) -> dict[str, str]:
    """Extract file paths and contents from ### FILE: markers."""
    files: dict[str, str] = {}
    pattern = r"###\s*FILE:\s*(.+?)\s*\n```\w*\n(.*?)```"
    for match in re.finditer(pattern, code_output, re.DOTALL):
        path = match.group(1).strip()
        content = match.group(2)
        if content.endswith("\n\n"):
            content = content[:-1]
        files[path] = content
    return files


# ── Pipeline ────────────────────────────────────────────────────────────────

class Pipeline:
    """Three-step plan -> code -> review pipeline."""

    def __init__(self, client: OllamaClient, project_root: pathlib.Path, *, fast: bool = False) -> None:
        self.client = client
        self.project_root = project_root
        self.models = FAST_MODELS if fast else FULL_MODELS
        self.fast = fast
        self.claude_md = load_claude_md(project_root)
        self.reviewer_checklist = load_reviewer_checklist(project_root)
        self.last_plan: str = ""
        self.last_code: str = ""
        self.last_review: str = ""
        self.last_files: dict[str, str] = {}

    def set_fast(self, *, fast: bool) -> None:
        """Toggle between fast (7b/8b) and full (30b/32b) models."""
        self.fast = fast
        self.models = FAST_MODELS if fast else FULL_MODELS

    def _step(self, step_name: str, step_num: int, total: int, model_key: str,
              system: str, prompt: str) -> str:
        """Execute one pipeline step with progress display."""
        model = self.models[model_key]
        label = f"[Step {step_num}/{total}: {step_name.upper()}]"
        print(f"  {C.cyan}{label}{C.reset} Using {C.bold}{model}{C.reset}...", end=" ", flush=True)
        try:
            result = self.client.generate(model, system, prompt)
        except TimeoutError:
            print(f"{C.red}Timeout{C.reset}")
            print(f"  {C.yellow}Hint: try @fast for smaller, faster models{C.reset}")
            return ""
        except ConnectionError as e:
            print(f"{C.red}Error: {e}{C.reset}")
            return ""
        if not result.strip():
            print(f"{C.yellow}Empty response (try @retry){C.reset}")
            return ""
        print(f"{C.green}OK{C.reset}")
        return result

    def _file_budget(self) -> int:
        """Compute the token budget available for file context."""
        claude_md_tokens = estimate_tokens(self.claude_md)
        overhead = 2000  # system prompt + user prompt framing
        return TOKEN_BUDGET - claude_md_tokens - overhead

    def run(self, task: str, file_context: FileContext) -> bool:
        """Run the full plan -> code -> review pipeline.

        Returns True if all steps produced output.
        """
        budget = self._file_budget()
        context_str, warnings = file_context.build_context(budget)
        for w in warnings:
            print(w)

        # Step 1: PLAN
        plan_system = PLAN_SYSTEM.format(claude_md=self.claude_md)
        plan_prompt = f"## Task\n{task}\n"
        if context_str:
            plan_prompt += f"\n## Reference files\n{context_str}"

        self.last_plan = self._step("plan", 1, 3, "plan", plan_system, plan_prompt)
        if not self.last_plan:
            return False

        # Step 2: CODE
        code_prompt = f"## Plan to implement\n{self.last_plan}\n\n## Task\n{task}\n"
        if context_str:
            code_prompt += f"\n## Existing files (for reference)\n{context_str}"

        self.last_code = self._step("code", 2, 3, "code", CODE_SYSTEM, code_prompt)
        if not self.last_code:
            return False

        self.last_files = extract_files(self.last_code)

        # Step 3: REVIEW
        review_system = REVIEW_SYSTEM.format(reviewer_checklist=self.reviewer_checklist)
        plan_summary = self.last_plan[:2000] if len(self.last_plan) > 2000 else self.last_plan
        review_prompt = f"## Plan summary\n{plan_summary}\n\n## Generated code\n{self.last_code}\n"

        self.last_review = self._step("review", 3, 3, "review", review_system, review_prompt)
        return True

    def run_step(self, step: str, task: str, file_context: FileContext) -> bool:
        """Re-run a single pipeline step."""
        budget = self._file_budget()
        context_str, warnings = file_context.build_context(budget)
        for w in warnings:
            print(w)

        if step == "code":
            if not self.last_plan:
                print(f"  {C.red}No plan available. Run full pipeline first.{C.reset}")
                return False
            code_prompt = f"## Plan to implement\n{self.last_plan}\n\n## Task\n{task}\n"
            if context_str:
                code_prompt += f"\n## Existing files\n{context_str}"
            self.last_code = self._step("code", 2, 3, "code", CODE_SYSTEM, code_prompt)
            if self.last_code:
                self.last_files = extract_files(self.last_code)
            return bool(self.last_code)

        if step == "review":
            if not self.last_code:
                print(f"  {C.red}No code available. Run code step first.{C.reset}")
                return False
            review_system = REVIEW_SYSTEM.format(reviewer_checklist=self.reviewer_checklist)
            plan_summary = self.last_plan[:2000] if len(self.last_plan) > 2000 else self.last_plan
            review_prompt = f"## Plan summary\n{plan_summary}\n\n## Generated code\n{self.last_code}\n"
            self.last_review = self._step("review", 3, 3, "review", review_system, review_prompt)
            return bool(self.last_review)

        print(f"  {C.red}Unknown step: {step}. Use 'code' or 'review'.{C.reset}")
        return False


# ── Colored diff output ─────────────────────────────────────────────────────

def colored_diff(old_lines: list[str], new_lines: list[str], path: str) -> str:
    """Generate a colored unified diff."""
    diff = difflib.unified_diff(old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
    result: list[str] = []
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            result.append(f"{C.bold}{line}{C.reset}")
        elif line.startswith("@@"):
            result.append(f"{C.cyan}{line}{C.reset}")
        elif line.startswith("+"):
            result.append(f"{C.green}{line}{C.reset}")
        elif line.startswith("-"):
            result.append(f"{C.red}{line}{C.reset}")
        else:
            result.append(line)
    return "\n".join(result)


# ── File writer (with safety) ───────────────────────────────────────────────

def write_file(project_root: pathlib.Path, rel_path: str, content: str, *, dry_run: bool = False) -> bool:
    """Write a file with backup, diff display, and confirmation.

    Returns True if the file was written.
    """
    full_path = project_root / rel_path

    if full_path.exists():
        old_content = full_path.read_text()
        if old_content == content:
            print(f"  {C.dim}No changes: {rel_path}{C.reset}")
            return False
        diff_str = colored_diff(old_content.splitlines(), content.splitlines(), rel_path)
        print(f"\n{diff_str}\n")
    else:
        print(f"  {C.green}New file: {rel_path}{C.reset}")
        preview = content.splitlines()[:20]
        for line in preview:
            print(f"  {C.green}+ {line}{C.reset}")
        total_lines = len(content.splitlines())
        if total_lines > 20:
            print(f"  {C.dim}... ({total_lines - 20} more lines){C.reset}")

    if dry_run:
        print(f"  {C.yellow}[DRY RUN] Would write: {rel_path}{C.reset}")
        return False

    try:
        answer = input(f"  Write {C.bold}{rel_path}{C.reset}? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer != "y":
        print(f"  {C.dim}Skipped{C.reset}")
        return False

    # Backup existing file
    if full_path.exists():
        backup_path = full_path.with_suffix(full_path.suffix + ".bak")
        shutil.copy2(full_path, backup_path)
        print(f"  {C.dim}Backup: {backup_path.name}{C.reset}")

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content)
    print(f"  {C.green}Written{C.reset}")
    return True


# ── Display helpers ─────────────────────────────────────────────────────────

def display_results(pipeline: Pipeline) -> None:
    """Display all pipeline results."""
    separator = "=" * 60
    print(f"\n{C.bold}{separator}{C.reset}")

    if pipeline.last_plan:
        print(f"\n{C.bold}=== PLAN ==={C.reset}\n{pipeline.last_plan}")
    if pipeline.last_code:
        print(f"\n{C.bold}=== CODE ==={C.reset}\n{pipeline.last_code}")
    if pipeline.last_review:
        print(f"\n{C.bold}=== REVIEW ==={C.reset}\n{pipeline.last_review}")

    print(f"\n{C.bold}{separator}{C.reset}")

    if pipeline.last_files:
        print(f"\n{C.cyan}Generated files:{C.reset}")
        for path in pipeline.last_files:
            print(f"  {path}")
        print(f"\n{C.dim}Use @accept to write, @accept <path> for a specific file{C.reset}")


HELP_TEXT = """\
{bold}anklume Local Dev Assistant{reset}

{cyan}Context:{reset}
  @file <path>     Add file to context
  @rm <path>       Remove file from context
  @clear           Clear all files from context
  @files           List files in context

{cyan}Pipeline:{reset}
  <any text>       Run full pipeline (plan -> code -> review)
  @plan            Show last plan
  @code            Show last generated code
  @review          Show last review

{cyan}Actions:{reset}
  @accept [path]   Write generated file(s) (with confirmation)
  @retry [step]    Retry full pipeline or single step (code|review)

{cyan}Settings:{reset}
  @fast            Switch to fast models (7b/8b)
  @full            Switch to full models (30b/32b)

{cyan}Other:{reset}
  @help            Show this help
  @quit            Exit
"""


# ── Readline setup ──────────────────────────────────────────────────────────

REPL_COMMANDS = [
    "@file", "@rm", "@clear", "@files",
    "@plan", "@code", "@review",
    "@accept", "@retry",
    "@fast", "@full",
    "@help", "@quit",
]


def setup_readline() -> None:
    """Configure readline with history and tab completion."""
    if readline is None:
        return
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(FileNotFoundError):
        readline.read_history_file(str(HISTORY_FILE))
    readline.set_history_length(500)

    def completer(text: str, state: int) -> str | None:
        matches = [c for c in REPL_COMMANDS if c.startswith(text)]
        if state < len(matches):
            return matches[state]
        return None

    readline.set_completer(completer)
    readline.parse_and_bind("tab: complete")


def save_readline() -> None:
    """Save readline history to disk."""
    if readline is None:
        return
    with contextlib.suppress(OSError):
        readline.write_history_file(str(HISTORY_FILE))


# ── REPL command dispatch ───────────────────────────────────────────────────

def handle_command(cmd: str, arg: str, ctx: FileContext, pipeline: Pipeline,
                   last_task: str, dry_run: bool) -> str | None:
    """Handle an @command. Returns updated last_task or None."""
    if cmd == "@quit":
        raise SystemExit(0)

    if cmd == "@help":
        print(HELP_TEXT.format(bold=C.bold, reset=C.reset, cyan=C.cyan))
        return last_task

    if cmd == "@file":
        if not arg:
            print(f"  {C.red}Usage: @file <path>{C.reset}")
        else:
            print(ctx.add(arg))
        return last_task

    if cmd == "@rm":
        if not arg:
            print(f"  {C.red}Usage: @rm <path>{C.reset}")
        else:
            print(ctx.remove(arg))
        return last_task

    if cmd == "@clear":
        print(ctx.clear())
        return last_task

    if cmd == "@files":
        print(ctx.list_files())
        return last_task

    if cmd == "@plan":
        if pipeline.last_plan:
            print(f"\n{C.bold}=== PLAN ==={C.reset}\n{pipeline.last_plan}\n")
        else:
            print(f"  {C.dim}No plan yet{C.reset}")
        return last_task

    if cmd == "@code":
        if pipeline.last_code:
            print(f"\n{C.bold}=== CODE ==={C.reset}\n{pipeline.last_code}\n")
        else:
            print(f"  {C.dim}No code yet{C.reset}")
        return last_task

    if cmd == "@review":
        if pipeline.last_review:
            print(f"\n{C.bold}=== REVIEW ==={C.reset}\n{pipeline.last_review}\n")
        else:
            print(f"  {C.dim}No review yet{C.reset}")
        return last_task

    if cmd == "@accept":
        _handle_accept(pipeline, ctx.project_root if hasattr(ctx, "project_root") else pipeline.project_root,
                       arg, dry_run)
        return last_task

    if cmd == "@retry":
        if not last_task:
            print(f"  {C.red}No previous task. Run a pipeline first.{C.reset}")
        elif arg in ("code", "review"):
            pipeline.run_step(arg, last_task, ctx)
        else:
            print("\n  Retrying full pipeline...")
            if pipeline.run(last_task, ctx):
                display_results(pipeline)
        return last_task

    if cmd == "@fast":
        pipeline.set_fast(fast=True)
        print(f"  {C.green}Switched to fast models (7b/8b){C.reset}")
        return last_task

    if cmd == "@full":
        pipeline.set_fast(fast=False)
        print(f"  {C.green}Switched to full models (30b/32b){C.reset}")
        return last_task

    print(f"  {C.red}Unknown command: {cmd}. Type @help for help.{C.reset}")
    return last_task


def _handle_accept(pipeline: Pipeline, project_root: pathlib.Path, arg: str, dry_run: bool) -> None:
    """Handle @accept command."""
    if not pipeline.last_files:
        print(f"  {C.red}No generated files to write{C.reset}")
        return

    if arg:
        if arg in pipeline.last_files:
            written = write_file(project_root, arg, pipeline.last_files[arg], dry_run=dry_run)
            if written:
                print(f"  {C.dim}Run 'make lint' to validate.{C.reset}")
        else:
            print(f"  {C.red}File not in output: {arg}{C.reset}")
            print(f"  {C.dim}Available: {', '.join(pipeline.last_files.keys())}{C.reset}")
        return

    any_written = False
    for path, content in pipeline.last_files.items():
        if write_file(project_root, path, content, dry_run=dry_run):
            any_written = True
    if any_written:
        print(f"\n  {C.dim}Run 'make lint' to validate.{C.reset}")


# ── Startup checks ─────────────────────────────────────────────────────────

def check_ollama(client: OllamaClient, models: dict[str, str]) -> bool:
    """Verify Ollama connectivity and model availability. Returns True if OK."""
    if not client.check_health():
        print(f"\n{C.red}Cannot connect to Ollama at {client.base_url}{C.reset}")
        print(f"Start Ollama with: {C.bold}ollama serve{C.reset}")
        print("Or set OLLAMA_URL environment variable.")
        return False
    print(f"{C.green}Ollama connected{C.reset}")

    available = client.list_models()
    missing: list[str] = []
    for role, model in models.items():
        found = any(model == m or m.startswith(model.split(":")[0] + ":") for m in available)
        if not found:
            missing.append(f"  {role}: {model}")

    if missing:
        print(f"\n{C.yellow}Missing models:{C.reset}")
        for m in missing:
            print(m)
        print(f"\n{C.dim}Available: {', '.join(available)}{C.reset}")
        print(f"Pull with: {C.bold}ollama pull <model>{C.reset}")
        return False
    print(f"{C.green}Models available{C.reset}")
    return True


# ── REPL ────────────────────────────────────────────────────────────────────

def repl(args: argparse.Namespace) -> None:
    """Main interactive REPL."""
    project_root = pathlib.Path(args.project_root).resolve()
    if not project_root.exists():
        print(f"{C.red}Project root not found: {project_root}{C.reset}")
        sys.exit(1)

    client = OllamaClient(args.ollama_url)
    models = FAST_MODELS if args.fast else FULL_MODELS

    print(f"{C.bold}anklume Local Dev Assistant{C.reset}")
    print(f"{C.dim}Project: {project_root}{C.reset}")
    print(f"{C.dim}Ollama:  {args.ollama_url}{C.reset}")

    if not check_ollama(client, models):
        sys.exit(1)

    mode_label = "fast" if args.fast else "full"
    print(f"{C.dim}Mode: {mode_label} | dry-run: {args.dry_run}{C.reset}")
    print(f"{C.dim}Type @help for commands{C.reset}\n")

    ctx = FileContext(project_root)
    pipeline = Pipeline(client, project_root, fast=args.fast)
    setup_readline()
    last_task = ""

    try:
        while True:
            try:
                line = input(f"{C.cyan}anklume-dev>{C.reset} ").strip()
            except EOFError:
                print()
                break

            if not line:
                continue

            save_readline()

            if line.startswith("@"):
                parts = line.split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1].strip() if len(parts) > 1 else ""
                result = handle_command(cmd, arg, ctx, pipeline, last_task, args.dry_run)
                if result is not None:
                    last_task = result
                continue

            # Regular text -> run full pipeline
            last_task = line
            print()
            if pipeline.run(line, ctx):
                display_results(pipeline)

    except KeyboardInterrupt:
        print(f"\n{C.dim}Interrupted{C.reset}")
    finally:
        save_readline()
        print(f"{C.dim}Goodbye.{C.reset}")


# ── One-shot mode ───────────────────────────────────────────────────────────

def one_shot(args: argparse.Namespace) -> None:
    """Run a single task and exit."""
    project_root = pathlib.Path(args.project_root).resolve()
    client = OllamaClient(args.ollama_url)
    models = FAST_MODELS if args.fast else FULL_MODELS

    if not check_ollama(client, models):
        sys.exit(1)

    pipeline = Pipeline(client, project_root, fast=args.fast)
    ctx = FileContext(project_root)
    success = pipeline.run(args.task, ctx)
    if success:
        display_results(pipeline)
    sys.exit(0 if success else 1)


# ── CLI entrypoint ──────────────────────────────────────────────────────────

def main() -> None:
    """Parse arguments and dispatch to REPL or one-shot mode."""
    parser = argparse.ArgumentParser(
        description="anklume local dev assistant -- plan/code/review with Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              %(prog)s                          Interactive REPL
              %(prog)s "Add timezone task"       One-shot mode
              %(prog)s --fast                    Use smaller, faster models
              %(prog)s --dry-run                 Preview without writing files
        """),
    )
    parser.add_argument("task", nargs="?", help="Task to run (skips REPL if provided)")
    parser.add_argument("--fast", action="store_true", help="Use fast models (7b/8b instead of 30b/32b)")
    parser.add_argument("--dry-run", action="store_true", help="Show diffs but never write files")
    parser.add_argument("--ollama-url", default=OLLAMA_URL, help=f"Ollama API URL (default: {OLLAMA_URL})")
    parser.add_argument("--project-root", default=".", help="Project root directory (default: .)")
    args = parser.parse_args()

    if args.task:
        one_shot(args)
    else:
        repl(args)


if __name__ == "__main__":
    main()
