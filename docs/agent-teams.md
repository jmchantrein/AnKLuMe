# Claude Code Agent Teams — Autonomous Development

anklume supports fully autonomous development and testing using Claude
Code Agent Teams. Multiple Claude Code instances work in parallel inside
an Incus-in-Incus sandbox, with human oversight at the PR merge level.

## Architecture

```
+----------------------------------------------------------------+
| Container: anklume (Incus-in-Incus, Phase 12)                   |
| security.nesting: true                                          |
| CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1                          |
| --dangerously-skip-permissions (safe: isolated sandbox)         |
|                                                                 |
|  Claude Code Agent Teams                                        |
|                                                                 |
|  Team Lead: orchestrator                                        |
|  +-- reads ROADMAP / task description                           |
|  +-- decomposes work into shared task list                      |
|  +-- assigns tasks to teammates                                 |
|  +-- synthesizes results, creates PR                            |
|                                                                 |
|  Teammate "Builder": feature implementation                     |
|  Teammate "Tester": continuous testing                          |
|  Teammate "Reviewer": code quality and ADR compliance           |
|                                                                 |
|  Nested Incus (Molecule test targets run here)                  |
+----------------------------------------------------------------+
```

## Quick start

### Prerequisites

1. Runner container (Phase 12): `make runner-create`
2. Claude Code installed in runner: `make agent-runner-setup`
3. Anthropic API key: `export ANTHROPIC_API_KEY=sk-ant-...`

### Fix mode

Fix failing Molecule tests autonomously:

```bash
# Fix all roles
make agent-fix

# Fix a specific role
make agent-fix R=base_system
```

### Develop mode

Implement a feature autonomously:

```bash
make agent-develop TASK="Add monitoring role with Prometheus node exporter"
```

## Setup

### 1. Create the runner container

```bash
make runner-create     # Creates Incus-in-Incus sandbox
```

### 2. Install Claude Code in the runner

```bash
make agent-runner-setup
```

This runs the `dev_agent_runner` role inside the runner container:
- Installs Node.js 22 and tmux
- Installs Claude Code CLI globally
- Configures Claude Code settings (permissions, Agent Teams flag)
- Deploys the audit hook script
- Sets up git identity

### 3. Set your API key

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Operational modes

### Fix mode (`make agent-fix`)

```
1. Launch Claude Code in the runner container
2. Run molecule test for all (or specified) roles
3. On failure: spawn Fixer + Tester teammates
4. Fixer analyzes logs + source, applies fix
5. Tester re-runs tests after each fix
6. Loop until pass or max retries (3)
7. Commit fixes, optionally create PR
```

### Develop mode (`make agent-develop TASK="..."`)

```
1. Launch Claude Code with the task description
2. Agent reads ROADMAP.md and CLAUDE.md
3. Spawns Builder, Tester, and Reviewer teammates
4. Builder implements, Tester validates, Reviewer checks
5. Iterate until all approve
6. Commit to feature branch, create PR
```

## Permission model

| Layer | Control |
|-------|---------|
| Sandbox | Incus-in-Incus = total isolation |
| Claude Code | bypassPermissions (safe in sandbox) + audit hook |
| Git workflow | Agents work on feature/fix branches, never main |
| Human gate | PR merge = human decision |

The key principle: full autonomy inside the sandbox, human approval
at the production boundary (PR merge).

## Audit hook

Every tool invocation is logged by the PreToolUse audit hook:

```bash
# View audit log
cat logs/agent-session-20260212.jsonl | jq .
```

Each entry contains:
- Timestamp
- Tool name (Edit, Bash, Read, etc.)
- Tool arguments

## Role configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `dev_agent_runner_node_version` | `22` | Node.js version |
| `dev_agent_runner_permissions_mode` | `bypassPermissions` | Claude Code mode |
| `dev_agent_runner_git_user` | `anklume Agent` | Git commit author |
| `dev_agent_runner_git_email` | `agent@anklume.local` | Git commit email |
| `dev_agent_runner_enable_teams` | `true` | Enable Agent Teams |
| `dev_agent_runner_audit_hook` | `true` | Enable audit logging |

## Cost considerations

Agent Teams consume more tokens than single sessions:

| Mode | Estimated cost |
|------|---------------|
| `agent-fix` (single role) | ~$3-8 |
| `agent-fix` (all roles) | ~$15-40 |
| `agent-develop` (small task) | ~$20-60 |
| `agent-develop` (full phase) | ~$50-150 |

Use `agent-fix` for targeted fixes (lower cost) and `agent-develop`
for full feature implementation (higher cost, higher value).

## Relationship with Phase 13

Phase 13 (`ai-test-loop.sh`, `ai-develop.sh`) provides lightweight,
backend-agnostic AI assistance via shell scripts. Phase 15 provides
full-power autonomous development via Claude Code Agent Teams.

| Feature | Phase 13 | Phase 15 |
|---------|----------|----------|
| Backends | Ollama, Claude API, Claude Code, Aider | Claude Code only |
| Multi-agent | No | Yes (Agent Teams) |
| Direct file editing | Only Claude Code + Aider | Yes |
| Sandbox isolation | Optional | Required |
| Cost | Low-medium | Medium-high |
| Autonomy level | Single task, single agent | Multi-task, team |

Both phases coexist. Use Phase 13 for quick fixes and Phase 15 for
complex development tasks.

## Troubleshooting

### Runner not found

```bash
make runner-create     # Create the sandbox container
```

### Claude Code not installed

```bash
make agent-runner-setup  # Install Claude Code in runner
```

### API key not set

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

### Agent Teams not working

Verify the feature flag:

```bash
incus exec anklume -- cat /root/.claude/settings.json | jq .env
```

Should show `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"`.
