#!/usr/bin/env bash
# doctor-checks.sh — Instance, config and dependency checks for anklume doctor
#
# Sourced by doctor.sh. Requires: result_ok, result_warn, result_err,
# verbose, FIX (from parent).

# ── Instance checks (no privilege needed) ───────────────────

check_incus_running() {
    # Retry up to 5 seconds — on live ISO, Incus may still be starting
    local attempt=0 err_msg
    while [ $attempt -lt 5 ]; do
        if err_msg="$(incus list --format csv -c n 2>&1)"; then
            result_ok "Incus daemon reachable"
            return 0
        fi
        # Distinguish permission errors from daemon not running
        if echo "$err_msg" | grep -qi "permission"; then
            result_err "Incus daemon running but user lacks permission (add to incus-admin group)"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done
    result_err "Incus daemon not reachable (after ${attempt}s)"
}

check_anklume_running() {
    local status
    status="$(incus list anklume-instance --project anklume --format csv -c s 2>/dev/null)" || status=""
    if [[ "$status" == *"RUNNING"* ]]; then
        result_ok "anklume-instance is running"
    elif [[ -z "$status" ]]; then
        # Instance does not exist — expected on dev hosts without infrastructure
        result_warn "anklume-instance not found (no anklume infrastructure deployed)"
    else
        result_err "anklume-instance not running (status: ${status})"
    fi
}

check_container_connectivity() {
    local fail_count=0 total=0 skip_count=0
    local json
    json="$(incus list --all-projects --format json 2>/dev/null)" || return 0

    while IFS=$'\t' read -r name project status; do
        [[ -z "$name" || "$name" == "anklume-doctor"* ]] && continue
        [[ "$status" != "Running" ]] && continue
        ((total++)) || true
        local gw
        gw="$(incus exec "$name" --project "$project" -- \
            ip route 2>/dev/null | awk '/^default/{print $3}' | head -1)" || gw=""
        if [[ -z "$gw" ]]; then
            ((skip_count++)) || true
            verbose "$name ($project): no default route, skipped"
            continue
        fi
        if ! incus exec "$name" --project "$project" -- \
            ping -c1 -W2 "$gw" &>/dev/null; then
            ((fail_count++)) || true
            result_warn "$name ($project): cannot reach gateway $gw"
        else
            verbose "$name ($project): gateway $gw reachable"
        fi
    done < <(echo "$json" | python3 -c "
import json, sys
for i in json.loads(sys.stdin.read()):
    print(f\"{i['name']}\t{i.get('project','default')}\t{i['status']}\")
" 2>/dev/null)

    if [[ $fail_count -eq 0 ]]; then
        local tested=$((total - skip_count))
        result_ok "All $tested/$total running containers can reach their gateway"
    fi
}

# ── Config checks ───────────────────────────────────────────

check_ip_drift() {
    [[ ! -f infra.yml ]] && { verbose "No infra.yml found, skipping"; return 0; }
    local drift=0 data
    data="$(incus list --all-projects --format csv -c ns4p 2>/dev/null)" || return 0

    while IFS=, read -r name status ipv4 project; do
        [[ "$status" != "RUNNING" || -z "$ipv4" ]] && continue
        local actual_ip="${ipv4%% *}"
        actual_ip="${actual_ip%%/*}"
        [[ -z "$actual_ip" ]] && continue
        local expected
        expected="$(grep -F -A5 "${name}:" infra.yml 2>/dev/null | grep 'ip:' | head -1 | grep -oP '"\K[^"]+' || true)"
        if [[ -n "$expected" && "$actual_ip" != "$expected" ]]; then
            ((drift++)) || true
            result_warn "$name: IP $actual_ip (expected $expected from infra.yml)"
        fi
    done <<< "$data"

    [[ $drift -eq 0 ]] && result_ok "No IP drift detected"
}

# ── Dependency checks ───────────────────────────────────────

check_container_deps() {
    # Skip if anklume-instance does not exist (dev host without infrastructure)
    local inst_status
    inst_status="$(incus list anklume-instance --project anklume --format csv -c s 2>/dev/null)" || inst_status=""
    if [[ -z "$inst_status" ]]; then
        result_warn "anklume-instance not found — skipping dependency checks"
        return 0
    fi
    if [[ "$inst_status" != *"RUNNING"* ]]; then
        result_warn "anklume-instance not running — skipping dependency checks"
        return 0
    fi

    local missing=()
    for dep in tmux python3 make; do
        if ! incus exec anklume-instance --project anklume -- \
            which "$dep" &>/dev/null; then
            missing+=("$dep")
        fi
    done

    if [[ ${#missing[@]} -gt 0 ]]; then
        result_warn "Missing in anklume-instance: ${missing[*]} — fixable"
        if $FIX; then
            incus exec anklume-instance --project anklume -- \
                apt-get update -qq &>/dev/null
            if incus exec anklume-instance --project anklume -- \
                apt-get install -y -qq "${missing[@]}" &>/dev/null; then
                result_ok "Installed ${missing[*]}"
            else
                result_err "Failed to install ${missing[*]}"
            fi
        fi
    else
        result_ok "Dependencies present in anklume-instance (tmux, python3, make)"
    fi
}
