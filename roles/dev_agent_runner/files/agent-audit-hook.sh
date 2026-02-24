#!/usr/bin/env bash
# PreToolUse audit hook for Claude Code Agent Teams.
# Logs every tool invocation with timestamp, tool name, and arguments.
# Stored in logs/agent-session-<timestamp>.jsonl for post-hoc audit.
#
# Install: configure as a PreToolUse hook in .claude/settings.json
set -euo pipefail

LOG_DIR="${ANKLUME_AGENT_LOG_DIR:-/root/anklume/logs}"
SESSION_LOG="${LOG_DIR}/agent-session-$(date +%Y%m%d).jsonl"

mkdir -p "$LOG_DIR"

# Read hook input from stdin (JSON with tool_name, tool_input)
if [ -t 0 ]; then
    exit 0
fi

INPUT="$(cat)"

# Append to session log with timestamp
echo "{\"ts\":\"$(date -Iseconds)\",\"hook\":\"PreToolUse\",\"data\":${INPUT}}" \
    >> "$SESSION_LOG"

# Allow the tool call (exit 0 = approve)
exit 0
