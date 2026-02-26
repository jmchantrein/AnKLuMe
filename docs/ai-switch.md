# Exclusive AI-Tools Network Access (ai-switch)

anklume supports an exclusive AI access mode where only one domain at
a time can reach the `ai-tools` domain. This prevents data leakage
between domains through shared AI services and enables VRAM flushing
between access switches to clear residual model state.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         Host                             │
│                                                          │
│  net-pro ──────┐                                        │
│                │ ✓ (current)      ┌──────────────┐      │
│  net-perso ────┤ ✗ (blocked)  ──▶│ net-ai-tools │      │
│                │                  │  gpu-server   │      │
│  net-anklume ──┘ ✗ (blocked)     │  ai-webui    │      │
│                                   └──────────────┘      │
│  nftables: only net-pro <-> net-ai-tools allowed        │
└─────────────────────────────────────────────────────────┘
```

At any time, exactly one domain bridge has nftables accept rules to
`net-ai-tools`. All other domains are blocked. Switching domains
optionally flushes GPU VRAM to prevent cross-domain data leakage
through residual model weights or inference cache.

## Configuration

### Enable exclusive mode in infra.yml

```yaml
global:
  addressing:
    base_octet: 10
    zone_base: 100
  ai_access_policy: exclusive    # Only one domain accesses ai-tools
  ai_access_default: pro         # Default domain with AI access

domains:
  ai-tools:
    trust_level: semi-trusted
    machines:
      gpu-server:
        type: lxc
        gpu: true
        roles: [base_system, ollama_server]
  pro:
    trust_level: trusted
    machines:
      pro-dev:
        type: lxc
  perso:
    trust_level: trusted
    machines:
      perso-desktop:
        type: lxc
```

Running `anklume sync` with `ai_access_policy: exclusive` auto-creates a
bidirectional network policy from the default domain to `ai-tools`.

### Validation rules

The PSOT generator enforces:

| Condition | Result |
|-----------|--------|
| `ai_access_policy` not `exclusive` or `open` | Error |
| `exclusive` without `ai_access_default` | Error |
| `ai_access_default` is `ai-tools` | Error |
| `ai_access_default` not a known domain | Error |
| `exclusive` without `ai-tools` domain | Error |
| More than 1 network policy targeting `ai-tools` | Error |

## Usage

### Switch AI access to a different domain

```bash
anklume ai switch DOMAIN=perso       # Switch access + flush VRAM
anklume ai switch DOMAIN=pro NO_FLUSH=1  # Switch without VRAM flush
```

Or use the script directly:

```bash
scripts/ai-switch.sh --domain perso
scripts/ai-switch.sh --domain pro --no-flush
scripts/ai-switch.sh --domain pro --dry-run
```

### What happens during a switch

1. GPU services (ollama, speaches) are stopped in the ai-tools domain
2. VRAM is flushed: GPU processes killed, GPU reset attempted
3. nftables rules are updated: old domain blocked, new domain allowed
4. GPU services are restarted
5. Current state is recorded in `/opt/anklume/ai-access-current`
6. Switch is logged to `/var/log/anklume/ai-switch.log`

### Check current access

```bash
cat /opt/anklume/ai-access-current
```

### View switch history

```bash
cat /var/log/anklume/ai-switch.log
```

## VRAM flush

When `--no-flush` is NOT specified (default), the switch:

1. Stops GPU services (ollama, speaches)
2. Kills any remaining GPU compute processes via `nvidia-smi`
3. Attempts `nvidia-smi --gpu-reset` (may not be supported on all GPUs)
4. Restarts GPU services

This prevents the new domain from reading residual data from the
previous domain's model inference through GPU memory.

Use `--no-flush` only when speed matters more than isolation (e.g.,
switching between trusted domains).

## Troubleshooting

### Switch fails with "Domain not found"

Verify the domain exists in `infra.yml`:

```bash
python3 scripts/generate.py infra.yml --dry-run 2>&1 | head
```

### nftables update fails

The switch uses `ansible-playbook` internally. Check that:
- `site.yml` is present at the project root
- The `incus_nftables` role is functional: `anklume network rules`
- Incus bridges exist: `incus network list | grep net-`

### GPU reset not supported

Some NVIDIA GPUs don't support `nvidia-smi --gpu-reset`. This is
non-fatal — the switch continues. GPU processes are still killed,
which clears most VRAM allocations.

### Services don't restart

Check service status inside the ai-tools container:

```bash
incus exec gpu-server --project ai-tools -- systemctl status ollama
incus exec gpu-server --project ai-tools -- systemctl status speaches
```
