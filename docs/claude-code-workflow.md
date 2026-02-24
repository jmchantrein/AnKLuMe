# Claude Code Workflow

How to work on anklume with Claude Code effectively.

## Architecture (Phase 35)

The development workflow uses Claude Code directly on the host, with
two complementary mechanisms for local LLM delegation:

| Component | Role |
|---|---|
| **Claude Code** | Primary orchestrator (terminal/IDE), runs on host |
| **mcp-ollama-coder** | MCP tools for explicit delegation to local GPU (generate, review, fix, test, explain) |
| **claude-code-router** | Optional: routes background tasks to Ollama via `ANTHROPIC_BASE_URL` |

No proxy server is needed. The previous MCP proxy
(`scripts/mcp-anklume-dev.py`) was archived in Phase 35. See
`docs/vision-ai-integration.md` for the rationale.

## Starting a session

Claude Code automatically reads `CLAUDE.md` at session start. For deeper
context on a specific task, load the relevant doc:

```
@docs/SPEC.md           # Full spec — formats, roles, architecture
@docs/ARCHITECTURE.md   # ADRs — decisions you must not override
@docs/ROADMAP.md        # What to work on next
```

## Development cycle (spec-driven, test-driven)

1. **Check the spec**: Before implementing anything, read the relevant
   section of SPEC.md. If the spec is missing or unclear, update it first.

2. **Write tests**: Before writing code, write the tests:
   - Roles: Molecule test (`roles/<n>/molecule/default/`)
   - Generator: pytest (`tests/test_generate.py`)

3. **Implement**: Write code until tests pass.

4. **Validate**: Run `make lint` (chains all validators).

5. **Review**: Invoke the reviewer agent:
   ```
   @.claude/agents/reviewer.md Review the changes in roles/incus_networks/
   ```

6. **Commit**: Only when `make lint && make test` pass.

## Local LLM delegation

Use the `mcp-ollama-coder` MCP tools when you want to delegate work to
the local GPU (free, no API cost):

- `generate_code` -- generate code from a natural language prompt
- `review_code` -- review code for quality, bugs, security
- `fix_code` -- fix code based on an error message
- `generate_tests` -- generate tests for given code
- `explain_code` -- explain code in plain language
- `list_models` -- list available Ollama models

These tools are configured in Claude Code's MCP settings and call Ollama
on the local GPU server directly.

## Using agents

### Architect
For structural decisions, design questions, new ADRs:
```
@.claude/agents/architect.md Should we split incus_instances into
separate roles for LXC and VM, or keep them together?
```

### Reviewer
Before committing, for quality checks:
```
@.claude/agents/reviewer.md Review all changes since last commit
```

## Using skills

The `incus-ansible` skill is auto-loaded when working on files in `roles/`.
It provides the reconciliation pattern template and common Incus commands.

## Tips

- **Keep context focused**: Load only what is relevant to the current task.
- **Use subagents for distinct tasks**: Avoid context pollution.
- **Run `make lint` frequently**: Catch issues early.
- **Check ROADMAP.md**: Know what phase you are in.
- **Local mode is default**: Use `mcp-ollama-coder` tools for code
  generation and review to save API tokens.
