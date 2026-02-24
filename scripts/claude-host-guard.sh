#!/usr/bin/env bash
# PreToolUse guard hook for Claude Code running with host root access.
# anklume-specific: allows infrastructure operations, blocks destructive ones.
#
# Exit codes:
#   0 = allow (auto-approve)
#   1 = ask user (prompt for confirmation)
#   2 = block (reject)
#
# Reads JSON from stdin: {"tool_name":"Bash","tool_input":{"command":"..."}}
set -euo pipefail

LOG_DIR="${HOME}/.anklume/host-audit"
SESSION_LOG="${LOG_DIR}/session-$(date +%Y%m%d).jsonl"
mkdir -p "$LOG_DIR"

# Read hook input
if [ -t 0 ]; then
    exit 0
fi

INPUT="$(cat)"
TOOL_NAME="$(echo "$INPUT" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_name",""))' 2>/dev/null || echo "")"

# Non-Bash tools: always allow (Edit, Read, Glob, Grep, Write, etc.)
if [ "$TOOL_NAME" != "Bash" ]; then
    echo "{\"ts\":\"$(date -Iseconds)\",\"tool\":\"$TOOL_NAME\",\"action\":\"allow\"}" >> "$SESSION_LOG"
    exit 0
fi

# Extract command
CMD="$(echo "$INPUT" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")"

# Log every command
echo "{\"ts\":\"$(date -Iseconds)\",\"tool\":\"Bash\",\"cmd\":$(echo "$CMD" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))'),\"action\":\"pending\"}" >> "$SESSION_LOG"

# === BLOCK LIST (exit 2 = reject) ===
# Catastrophic operations that should never happen
BLOCK_PATTERNS=(
    '^rm -rf /$'
    '^rm -rf /\s'
    '^rm -rf /boot'
    '^rm -rf /etc$'
    '^rm -rf /var$'
    '^rm -rf /home$'
    '^dd .* of=/dev/[a-z]'
    '^mkfs\.'
    '^shred '
    '^wipefs '
    'curl .* \| .*bash'
    'wget .* \| .*sh'
    'curl .* \| .*sh'
    ':\(\)\{ :\|:& \};:'
    '^chmod -R 777 /'
    '^chown -R .* /$'
    'passwd'
    'visudo'
    'userdel'
    'groupdel'
    '^reboot$'
    '^shutdown '
    '^poweroff$'
    '^init 0$'
    '^init 6$'
    'pacman -R.*incus'
    'apt.*remove.*incus'
    'rm.*/var/lib/incus/database'
    '^git push.*--force.*main'
    '^git push.*--force.*master'
    '^git reset --hard'
)

for pattern in "${BLOCK_PATTERNS[@]}"; do
    if echo "$CMD" | grep -qE "$pattern"; then
        echo "{\"ts\":\"$(date -Iseconds)\",\"tool\":\"Bash\",\"cmd\":$(echo "$CMD" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read().strip()))'),\"action\":\"BLOCKED\",\"pattern\":\"$pattern\"}" >> "$SESSION_LOG"
        echo "BLOCKED by anklume host guard: matches dangerous pattern '$pattern'" >&2
        exit 2
    fi
done

# === ALLOW LIST (exit 0 = auto-approve) ===
# anklume infrastructure commands
ALLOW_PATTERNS=(
    # Incus operations
    '^incus '
    '^sudo incus '

    # nftables (read and deploy)
    '^nft '
    '^sudo nft '
    'deploy-nftables'
    'incus-guard'

    # Systemd (anklume and Incus services only)
    '^systemctl .* incus'
    '^systemctl .* anklume'
    '^systemctl .* llama-server'
    '^systemctl .* ollama'
    '^systemctl .* speaches'
    '^sudo systemctl .* incus'
    '^sudo systemctl .* anklume'
    '^journalctl'
    '^sudo journalctl'
    '^systemctl status'
    '^systemctl is-active'
    '^systemctl list-units'

    # Network diagnostics
    '^ip link'
    '^ip addr'
    '^ip route'
    '^ip -j '
    '^sudo ip '
    '^ping '
    '^ss '
    '^curl '
    '^wget '

    # anklume make targets
    '^make '

    # Ansible
    '^ansible'
    '^molecule '

    # Development tools
    '^git '
    '^python3 '
    '^pytest '
    '^ruff '
    '^shellcheck '
    '^yamllint '

    # File operations (safe in project context)
    '^ls '
    '^cat '
    '^head '
    '^tail '
    '^wc '
    '^diff '
    '^find '
    '^grep '
    '^rg '
    '^stat '
    '^file '
    '^which '
    '^type '
    '^readlink '
    '^realpath '
    '^basename '
    '^dirname '
    '^mkdir '
    '^cp '
    '^mv '
    '^touch '
    '^chmod '
    '^tee '
    '^sort '
    '^uniq '
    '^tr '
    '^sed '
    '^awk '
    '^cut '
    '^jq '
    '^echo '
    '^printf '
    '^true$'
    '^false$'
    '^test '
    '^\['

    # System info (read-only)
    '^uname '
    '^lsb_release '
    '^nvidia-smi'
    '^lspci '
    '^lsmod'
    '^modinfo '
    '^sysctl '
    '^free '
    '^df '
    '^du '
    '^top '
    '^ps '
    '^pgrep '
    '^id$'
    '^whoami$'
    '^hostname$'
    '^date'
    '^env$'
    '^printenv'
    '^lsblk'
    '^blkid'
    '^mount$'
    '^mount .*--fake'

    # Package info (read-only)
    '^pacman -Q'
    '^pacman -S.*--info'
    '^dpkg -l'
    '^apt list'
    '^pip list'
    '^pip show'
    '^npm list'
    '^node '
    '^npm '

    # Tmux
    '^tmux '

    # Sleep/wait
    '^sleep '
    '^wait'

    # anklume scripts
    'scripts/'
    'host/'

    # Sudo wrappers for allowed commands (incus, nft, ip, systemctl)
    '^sudo /usr/lib/incus/'
    '^sudo modprobe '
    '^sudo sysctl '
    '^sudo kill '
    '^sudo mkdir '
    '^sudo tee '
    '^sudo cp '
    '^sudo mv '
    '^sudo chmod '
    '^sudo chown '
    '^sudo ln '
    '^sudo rm /tmp/'
    '^sudo rm /var/log/anklume/'
    '^sudo rm /etc/nftables.d/anklume'
    '^sudo cat '
    '^sudo ls '
    '^sudo tail '
    '^sudo head '
    '^sudo pgrep '
)

for pattern in "${ALLOW_PATTERNS[@]}"; do
    if echo "$CMD" | grep -qE "$pattern"; then
        # Update log with allow
        sed -i '$ s/"action":"pending"/"action":"allow"/' "$SESSION_LOG"
        exit 0
    fi
done

# === ASK USER (exit 1 = prompt for confirmation) ===
# Unknown command — let the user decide
sed -i '$ s/"action":"pending"/"action":"ask"/' "$SESSION_LOG"
exit 1
