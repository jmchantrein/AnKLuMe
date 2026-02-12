# decisions-log.md — Implementation Decisions

Lightweight decisions made during implementation. For architecture-level
decisions, see [ARCHITECTURE.md](ARCHITECTURE.md) (ADR-001 to ADR-019).

---

## D-007: nftables priority -1 (coexist with Incus chains)

**Phase**: 8 (nftables inter-bridge isolation)

**Context**: Incus manages its own nftables chains at priority 0 for NAT
and per-bridge filtering. We need isolation rules that run before Incus
chains without disabling or conflicting with them.

**Decision**: Use `priority -1` in the AnKLuMe `inet anklume` table's
forward chain. This ensures our isolation rules are evaluated before
Incus chains. We do NOT disable the Incus firewall (`security.ipv4_firewall`)
because Incus chains provide useful per-bridge NAT and DHCP rules.

**Consequence**: AnKLuMe and Incus nftables coexist peacefully. Non-matching
traffic falls through to Incus chains with `policy accept`.

---

## D-008: Two-step deployment (generate in admin, deploy on host)

**Phase**: 8

**Context**: AnKLuMe runs inside the admin container (ADR-004: Ansible
does not modify the host). However, nftables rules must be applied on
the host kernel, not inside a container.

**Decision**: Split into two steps:
1. `make nftables` — runs inside admin container, generates rules to
   `/opt/anklume/nftables-isolation.nft`
2. `make nftables-deploy` — runs `scripts/deploy-nftables.sh` on the
   host, pulls rules from admin container via `incus file pull`,
   validates syntax, installs to `/etc/nftables.d/`, and applies

**Consequence**: The operator can review generated rules before deploying.
The admin container never needs host-level privileges. This is a documented
exception to ADR-004.

---

## D-009: br_netfilter same-bridge handling

**Phase**: 8

**Context**: When `br_netfilter` is loaded (required for nftables to
see bridge traffic), intra-bridge traffic (same bridge, different ports)
also passes through the `forward` chain. Without explicit accept rules,
same-bridge traffic between containers in the same domain would be
dropped by the inter-bridge drop rule.

**Decision**: Add explicit same-bridge accept rules for every AnKLuMe
bridge before the inter-bridge drop rule:
```nft
iifname "net-admin" oifname "net-admin" accept
iifname "net-perso" oifname "net-perso" accept
...
```

**Consequence**: Containers within the same domain can communicate freely.
The rules are generated dynamically from the list of discovered bridges.

---

## D-010: .gitignore root-anchor patterns

**Phase**: 8

**Context**: Generated files (like nftables rules) should not be committed
to the repository. The `.gitignore` file uses root-anchored patterns
(e.g., `/opt/`) to avoid accidentally ignoring files in subdirectories
with similar names.

**Decision**: Use root-anchored patterns in `.gitignore` where possible.
For generated artifacts like nftables rules, the output path
(`/opt/anklume/`) is inside the container filesystem and does not appear
in the repository, so no `.gitignore` entry is needed.

**Consequence**: Clean git status. No generated artifacts leak into the
repository.
