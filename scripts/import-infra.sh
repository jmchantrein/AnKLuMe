#!/usr/bin/env bash
# import-infra.sh — Generate infra.yml from existing Incus state
# Usage: scripts/import-infra.sh [-o output_file]
#
# Scans running Incus infrastructure and generates a matching infra.yml.
# The user edits the result, then runs 'make sync && make apply'.

set -euo pipefail

OUTPUT="infra.imported.yml"
for arg in "$@"; do
    case "$arg" in
        -o) shift; OUTPUT="$1"; shift ;;
        --help|-h) echo "Usage: $0 [-o output_file]"; exit 0 ;;
    esac
done

echo "=== AnKLuMe Import Infrastructure ==="
echo "Scanning Incus state..."

# Collect all projects
PROJECTS=$(incus project list --format json 2>/dev/null)
if [ -z "$PROJECTS" ] || [ "$PROJECTS" = "null" ]; then
    echo "No Incus projects found."
    exit 0
fi

# Start building YAML
cat > "$OUTPUT" <<'HEADER'
# infra.yml — Imported from existing Incus state
# Review and edit this file, then run: make sync && make apply
#
# WARNING: This is a best-effort import. Review carefully:
# - Verify subnet assignments and IP addresses
# - Add missing roles and profiles
# - Adjust config values as needed

HEADER

{
    echo "project_name: imported-infra"
    echo ""
    echo "global:"
    echo "  base_subnet: \"10.100\""
    echo "  default_os_image: \"images:debian/13\""
    echo ""
    echo "domains:"
} >> "$OUTPUT"

SUBNET_ID=0

# Process each non-default project as a domain
for project in $(echo "$PROJECTS" | python3 -c "
import sys, json
projects = json.load(sys.stdin)
for p in projects:
    name = p.get('name', '')
    if name != 'default':
        print(name)
" 2>/dev/null); do
    echo "  Importing project: $project"

    # Get instances in this project
    INSTANCES=$(incus list --project "$project" --format json 2>/dev/null)
    if [ -z "$INSTANCES" ] || [ "$INSTANCES" = "null" ] || [ "$INSTANCES" = "[]" ]; then
        continue
    fi

    {
        echo "  $project:"
        echo "    description: \"Imported from Incus project $project\""
        echo "    subnet_id: $SUBNET_ID"
        echo "    machines:"
    } >> "$OUTPUT"

    python3 -c "
import sys, json
instances = json.loads('''$INSTANCES''')
for inst in instances:
    name = inst.get('name', 'unknown')
    itype = inst.get('type', 'container')
    inst_type = 'vm' if itype == 'virtual-machine' else 'lxc'
    state = inst.get('state', {}) or {}
    network = state.get('network', {}) or {}

    # Try to find an IP
    ip = ''
    for nic_name, nic_info in network.items():
        if nic_name in ('lo',):
            continue
        for addr in nic_info.get('addresses', []):
            if addr.get('family') == 'inet' and not addr.get('address', '').startswith('127.'):
                ip = addr['address']
                break
        if ip:
            break

    print(f'      {name}:')
    print(f'        description: \"Imported instance\"')
    print(f'        type: {inst_type}')
    if ip:
        print(f'        ip: \"{ip}\"')
    print(f'        roles: [base_system]')
" >> "$OUTPUT"

    SUBNET_ID=$((SUBNET_ID + 1))
done

echo ""
echo "Import complete: $OUTPUT"
echo "Review the file, then run:"
echo "  cp $OUTPUT infra.yml"
echo "  make sync && make apply"
