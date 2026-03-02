#!/usr/bin/env bash
# nest-worker.sh — Inner worker for nesting tests (pushed into containers)
#
# Called by test-nesting.sh at each nesting level. Installs Incus,
# creates a child container, writes context files, and recurses.
# With FULL=1, also installs test deps and runs pytest at each level.
#
# Args: LEVEL MAX_DEPTH IMAGE FULL(0|1) BEHAVE(0|1)

set -euo pipefail

LEVEL=$1; MAX=$2; IMG=$3; FULL=${4:-0}; BEHAVE=${5:-0}
NEXT=$((LEVEL + 1)); CHILD="nest-l${NEXT}"

if [ "$LEVEL" -ge "$MAX" ]; then
    echo "[STOP] max depth reached (level=$LEVEL)"; exit 0
fi

# ── Install Incus at this level ──────────────────────────────
echo "[WORKER] Level $LEVEL: installing Incus (~60s)..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq >/dev/null 2>&1
apt-get install -y -qq incus >/dev/null 2>&1
grep -q "^root:" /etc/subuid 2>/dev/null \
    || echo "root:100000:1000000000" >> /etc/subuid
grep -q "^root:" /etc/subgid 2>/dev/null \
    || echo "root:100000:1000000000" >> /etc/subgid
incus admin init --minimal >/dev/null 2>&1 || true
if ! incus info >/dev/null 2>&1; then
    echo "[FAIL] Level $LEVEL: Incus daemon not running"; exit 1
fi
echo "[PASS] Level $LEVEL: Incus daemon running"

# ── Full mode: install test deps + run pytest ────────────────
if [ "$FULL" = "1" ]; then
    echo "[WORKER] Level $LEVEL: installing test dependencies (~30s)..."
    apt-get install -y -qq python3-pip python3-yaml git make \
        shellcheck >/dev/null 2>&1
    pip3 install --break-system-packages -q \
        pytest behave typer rich hypothesis ruff \
        pexpect pillow pixelmatch \
        uvicorn fastapi httpx websockets >/dev/null 2>&1
    echo "[WORKER] Level $LEVEL: running pytest..."
    # Hide nesting context so generator tests don't apply the
    # nesting prefix (tests expect bare host-level names)
    mv /etc/anklume /etc/anklume.bak 2>/dev/null || true
    # Exclude GUI tests (need display/screenshots, not in headless container)
    if (cd /opt/anklume && python3 -m pytest tests/ -x -q --tb=short \
            --ignore=tests/test_gui_automation.py \
            > /tmp/pytest.log 2>&1); then
        echo "[PASS] Level $LEVEL: pytest $(tail -1 /tmp/pytest.log)"
    else
        tail -20 /tmp/pytest.log | while IFS= read -r fl; do
            echo "[DETAIL] $fl"; done
        echo "[FAIL] Level $LEVEL: pytest $(tail -1 /tmp/pytest.log)"
    fi
    mv /etc/anklume.bak /etc/anklume 2>/dev/null || true
fi

# ── Behave mode: run behave scenarios ─────────────────────
if [ "$BEHAVE" = "1" ] && [ "$FULL" = "1" ]; then
    echo "[WORKER] Level $LEVEL: running behave..."
    mv /etc/anklume /etc/anklume.bak 2>/dev/null || true
    if (cd /opt/anklume && python3 -m behave scenarios/ \
            --tags='~@vision' -q > /tmp/behave.log 2>&1); then
        echo "[PASS] Level $LEVEL: behave $(tail -1 /tmp/behave.log)"
    else
        tail -10 /tmp/behave.log | while IFS= read -r fl; do
            echo "[DETAIL] $fl"; done
        echo "[FAIL] Level $LEVEL: behave $(tail -1 /tmp/behave.log)"
    fi
    mv /etc/anklume.bak /etc/anklume 2>/dev/null || true
fi

# ── Create child container ───────────────────────────────────
echo "[WORKER] Level $LEVEL: launching $CHILD..."
incus launch "$IMG" "$CHILD" \
    -c security.privileged=true -c security.nesting=true \
    -c security.syscalls.intercept.mknod=true \
    -c security.syscalls.intercept.setxattr=true 2>/dev/null

WAIT=$((30 + LEVEL * 15))
for _i in $(seq 1 "$WAIT"); do
    incus exec "$CHILD" -- true 2>/dev/null && break; sleep 2
done
if ! incus exec "$CHILD" -- true 2>/dev/null; then
    echo "[FAIL] Level $NEXT: container not ready"; exit 1
fi

# ── Write context files ─────────────────────────────────────
incus exec "$CHILD" -- mkdir -p /etc/anklume
incus exec "$CHILD" -- bash -c "echo $NEXT > /etc/anklume/absolute_level"
incus exec "$CHILD" -- bash -c "echo $((NEXT - 1)) > /etc/anklume/relative_level"
incus exec "$CHILD" -- bash -c "echo false > /etc/anklume/vm_nested"

LVL=$(incus exec "$CHILD" -- cat /etc/anklume/absolute_level)
if [ "$LVL" = "$NEXT" ]; then
    echo "[PASS] Level $NEXT: absolute_level=$NEXT"
else
    echo "[FAIL] Level $NEXT: absolute_level=$LVL (expected $NEXT)"
fi

# ── Behave: GPU network test from nested level ────────────────
if [ "$BEHAVE" = "1" ] && [ "$LEVEL" -ge 2 ]; then
    OLLAMA_HOST="${OLLAMA_HOST:-10.100.3.1:11434}"
    if curl -s --connect-timeout 5 "http://$OLLAMA_HOST/api/version" >/dev/null 2>&1; then
        echo "[PASS] Level $LEVEL: GPU network reachable ($OLLAMA_HOST)"
    else
        echo "[INFO] Level $LEVEL: GPU network NOT reachable ($OLLAMA_HOST)"
    fi
fi

# ── Full mode: copy repo into child ─────────────────────────
if [ "$FULL" = "1" ]; then
    incus exec "$CHILD" -- mkdir -p /opt/anklume
    tar -C /opt/anklume -cf - . 2>/dev/null | \
        incus exec "$CHILD" -- tar -C /opt/anklume -xf -
fi

# ── Push worker and recurse ─────────────────────────────────
cat /tmp/nest-worker.sh | incus exec "$CHILD" -- \
    tee /tmp/nest-worker.sh > /dev/null
incus exec "$CHILD" -- chmod +x /tmp/nest-worker.sh
incus exec "$CHILD" -- bash /tmp/nest-worker.sh "$NEXT" "$MAX" "$IMG" "$FULL" "$BEHAVE"
