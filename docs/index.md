---
title: Home
---

# anklume

QubesOS-like isolation using native Linux kernel features (KVM/LXC),
calmly orchestrated by Ansible, Incus and Molecule.

## What is anklume?

anklume is a declarative infrastructure compartmentalization framework.
Describe your infrastructure in a single YAML file (`infra.yml`), run
`make sync && make apply`, and get isolated, reproducible, disposable
environments.

## Quick links

- [Quick Start](quickstart.md) - Get up and running
- [Core Specification](SPEC.md) - Full technical specification
- [Architecture Decisions](ARCHITECTURE.md) - ADR records
- [Roadmap](ROADMAP.md) - Implementation phases

## Design principles

- **Declarative**: One YAML file describes everything
- **Native**: Uses Linux kernel features (namespaces, cgroups, nftables)
- **Minimal**: Glues standard tools together (Ansible, Incus, nftables)
- **Safe by default**: Trust-zone IP addressing, nftables isolation
- **AI-ready**: Optional integrated AI with domain boundary respect

## License

AGPL-3.0
