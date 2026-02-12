#!/usr/bin/env bash
# Shared configuration for AI-assisted testing and development.
# Sourced by ai-test-loop.sh and ai-develop.sh.
#
# Priority: environment variables > anklume.conf.yml > defaults
# See docs/ai-testing.md for configuration reference.

# ── Defaults ─────────────────────────────────────────────────
AI_MODE="${ANKLUME_AI_MODE:-none}"
AI_OLLAMA_URL="${ANKLUME_AI_OLLAMA_URL:-http://homelab-llm:11434}"
AI_OLLAMA_MODEL="${ANKLUME_AI_OLLAMA_MODEL:-qwen2.5-coder:32b}"
AI_ANTHROPIC_KEY="${ANTHROPIC_API_KEY:-}"
AI_MAX_RETRIES="${ANKLUME_AI_MAX_RETRIES:-3}"
AI_AUTO_PR="${ANKLUME_AI_AUTO_PR:-false}"
AI_DRY_RUN="${ANKLUME_AI_DRY_RUN:-true}"
AI_LOG_DIR="${ANKLUME_AI_LOG_DIR:-logs}"

# ── Load optional config file ────────────────────────────────
_ai_conf="${ANKLUME_CONF:-anklume.conf.yml}"

_yaml_get() {
    # Extract a value from the YAML config file using python3+PyYAML.
    # Usage: _yaml_get "ai.mode" "default_value"
    local key_path="$1"
    local default="${2:-}"
    python3 -c "
import yaml, sys
try:
    c = yaml.safe_load(open('${_ai_conf}'))
    keys = '${key_path}'.split('.')
    v = c
    for k in keys:
        v = v[k]
    print(v)
except Exception:
    print('${default}')
" 2>/dev/null
}

if [ -f "$_ai_conf" ]; then
    # Only override if env var was NOT set (env takes precedence)
    [ -z "${ANKLUME_AI_MODE+x}" ] \
        && AI_MODE="$(_yaml_get ai.mode "$AI_MODE")"
    [ -z "${ANKLUME_AI_OLLAMA_URL+x}" ] \
        && AI_OLLAMA_URL="$(_yaml_get ai.ollama_url "$AI_OLLAMA_URL")"
    [ -z "${ANKLUME_AI_OLLAMA_MODEL+x}" ] \
        && AI_OLLAMA_MODEL="$(_yaml_get ai.ollama_model "$AI_OLLAMA_MODEL")"
    [ -z "${ANTHROPIC_API_KEY+x}" ] \
        && AI_ANTHROPIC_KEY="$(_yaml_get ai.anthropic_api_key "$AI_ANTHROPIC_KEY")"
    [ -z "${ANKLUME_AI_MAX_RETRIES+x}" ] \
        && AI_MAX_RETRIES="$(_yaml_get ai.max_retries "$AI_MAX_RETRIES")"
    [ -z "${ANKLUME_AI_AUTO_PR+x}" ] \
        && AI_AUTO_PR="$(_yaml_get ai.auto_pr "$AI_AUTO_PR")"
    [ -z "${ANKLUME_AI_DRY_RUN+x}" ] \
        && AI_DRY_RUN="$(_yaml_get ai.dry_run "$AI_DRY_RUN")"
fi

# ── Validation ───────────────────────────────────────────────
ai_validate_config() {
    case "$AI_MODE" in
        none|local|remote|claude-code|aider) ;;
        *) die "Invalid AI_MODE: '${AI_MODE}'. Must be: none, local, remote, claude-code, aider" ;;
    esac

    if [ "$AI_MODE" = "local" ] && ! command -v curl &>/dev/null; then
        die "AI_MODE=local requires curl"
    fi

    if [ "$AI_MODE" = "remote" ] && [ -z "$AI_ANTHROPIC_KEY" ]; then
        die "AI_MODE=remote requires ANTHROPIC_API_KEY"
    fi

    if [ "$AI_MODE" = "claude-code" ] && ! command -v claude &>/dev/null; then
        die "AI_MODE=claude-code requires Claude Code CLI (npm install -g @anthropic-ai/claude-code)"
    fi

    if [ "$AI_MODE" = "aider" ] && ! command -v aider &>/dev/null; then
        die "AI_MODE=aider requires Aider CLI (pip install aider-chat)"
    fi
}

# ── Logging ──────────────────────────────────────────────────
_ai_session_id=""
_ai_log_file=""

ai_init_session() {
    local prefix="${1:-ai}"
    _ai_session_id="${prefix}-$(date +%Y%m%d-%H%M%S)"
    mkdir -p "$AI_LOG_DIR"
    _ai_log_file="${AI_LOG_DIR}/${_ai_session_id}.log"
    ai_log "Session started: ${_ai_session_id}"
    ai_log "AI_MODE=${AI_MODE} DRY_RUN=${AI_DRY_RUN} AUTO_PR=${AI_AUTO_PR}"
    ai_log "MAX_RETRIES=${AI_MAX_RETRIES}"
}

ai_log() {
    local msg
    msg="[$(date '+%Y-%m-%d %H:%M:%S')] $*"
    echo "$msg" >> "$_ai_log_file"
    echo "$msg"
}

ai_log_quiet() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$_ai_log_file"
}

# ── Backend dispatch ─────────────────────────────────────────
# Each backend receives: $1=context_file (failure log + relevant code)
# and $2=instruction (what to fix/implement).
# Returns 0 if fix was applied, 1 if no fix available.

ai_fix_ollama() {
    local context_file="$1"
    local instruction="$2"
    local context
    context="$(cat "$context_file")"

    local prompt
    prompt="You are an Ansible/infrastructure expert fixing a test failure.

${instruction}

Here is the context (test log and relevant source code):

${context}

Respond ONLY with a unified diff (patch format) that fixes the issue.
Start with --- and +++ lines. No explanations before or after the diff."

    local response_file="${AI_LOG_DIR}/${_ai_session_id}-response.patch"

    ai_log "Querying Ollama (${AI_OLLAMA_MODEL})..."
    if ! curl -sf "${AI_OLLAMA_URL}/api/generate" \
        -d "$(python3 -c "import json; print(json.dumps({'model':'${AI_OLLAMA_MODEL}','prompt':open('${context_file}').read(),'stream':False}))")" \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['response'])" \
        > "$response_file" 2>/dev/null; then
        ai_log "ERROR: Ollama query failed"
        return 1
    fi

    _ai_apply_patch "$response_file"
}

ai_fix_claude_code() {
    local context_file="$1"
    local instruction="$2"

    ai_log "Launching Claude Code CLI..."
    local prompt
    prompt="Read CLAUDE.md for project conventions. ${instruction}

Failure context:
$(cat "$context_file")

Fix the issue. Make minimal changes."

    if [ "$AI_DRY_RUN" = "true" ]; then
        ai_log "DRY_RUN: would run: claude -p '${instruction}'"
        echo "$prompt" > "${AI_LOG_DIR}/${_ai_session_id}-prompt.txt"
        return 1
    fi

    claude -p "$prompt" --dangerously-skip-permissions \
        >> "$_ai_log_file" 2>&1
}

ai_fix_aider() {
    local context_file="$1"
    local instruction="$2"

    ai_log "Launching Aider..."
    local msg
    msg="${instruction}

Failure context:
$(cat "$context_file")"

    if [ "$AI_DRY_RUN" = "true" ]; then
        ai_log "DRY_RUN: would run: aider --message '${instruction}'"
        return 1
    fi

    local model_arg=""
    if [ "$AI_MODE" = "aider" ]; then
        model_arg="--model ollama_chat/${AI_OLLAMA_MODEL}"
    fi

    # shellcheck disable=SC2086
    aider $model_arg --yes --message "$msg" >> "$_ai_log_file" 2>&1
}

ai_fix_remote() {
    local context_file="$1"
    local instruction="$2"
    local context
    context="$(cat "$context_file")"

    local prompt="${instruction}

Context:
${context}

Respond ONLY with a unified diff (patch format). No explanations."

    local response_file="${AI_LOG_DIR}/${_ai_session_id}-response.patch"

    ai_log "Querying Claude API..."
    local payload
    payload="$(python3 -c "
import json
print(json.dumps({
    'model': 'claude-sonnet-4-5-20250929',
    'max_tokens': 4096,
    'messages': [{'role': 'user', 'content': '''${prompt}'''}]
}))
")"

    if ! curl -sf "https://api.anthropic.com/v1/messages" \
        -H "x-api-key: ${AI_ANTHROPIC_KEY}" \
        -H "anthropic-version: 2023-06-01" \
        -H "content-type: application/json" \
        -d "$payload" \
        | python3 -c "import json,sys; r=json.load(sys.stdin); print(r['content'][0]['text'])" \
        > "$response_file" 2>/dev/null; then
        ai_log "ERROR: Claude API query failed"
        return 1
    fi

    _ai_apply_patch "$response_file"
}

# ── Patch application ────────────────────────────────────────
_ai_apply_patch() {
    local patch_file="$1"

    if [ ! -s "$patch_file" ]; then
        ai_log "ERROR: Empty or missing patch file"
        return 1
    fi

    ai_log_quiet "Patch content:"
    ai_log_quiet "$(cat "$patch_file")"

    if [ "$AI_DRY_RUN" = "true" ]; then
        ai_log "DRY_RUN: Patch saved to ${patch_file} (not applied)"
        echo "--- Proposed patch ---"
        cat "$patch_file"
        echo "--- End patch ---"
        return 1
    fi

    if patch -p1 --dry-run < "$patch_file" &>/dev/null; then
        patch -p1 < "$patch_file"
        ai_log "Patch applied successfully"
        return 0
    else
        ai_log "ERROR: Patch does not apply cleanly"
        return 1
    fi
}

# ── Git helpers ──────────────────────────────────────────────
ai_create_branch() {
    local branch="$1"
    git checkout -b "$branch" 2>/dev/null \
        || git checkout "$branch" 2>/dev/null \
        || die "Cannot create or switch to branch: ${branch}"
    ai_log "On branch: ${branch}"
}

ai_commit_fix() {
    local message="$1"
    git add -A
    if git diff --cached --quiet; then
        ai_log "No changes to commit"
        return 1
    fi
    git commit -m "${message}

Co-Authored-By: AI-assisted (${AI_MODE}) <noreply@anklume.local>"
    ai_log "Committed: ${message}"
}

ai_create_pr() {
    local title="$1"
    local body="$2"

    if [ "$AI_AUTO_PR" != "true" ]; then
        ai_log "AUTO_PR=false: skipping PR creation"
        return 0
    fi

    if ! command -v gh &>/dev/null; then
        ai_log "WARNING: gh CLI not found, cannot create PR"
        return 1
    fi

    git push -u origin HEAD
    gh pr create --title "$title" --body "$body" --label "ai-generated"
    ai_log "PR created: ${title}"
}
