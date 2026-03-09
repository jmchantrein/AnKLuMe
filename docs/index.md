# anklume

Framework déclaratif de compartimentalisation d'infrastructure.

Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.

## Démarrage rapide

```bash
# Installer
uv tool install anklume

# Créer un projet
anklume init mon-infra
cd mon-infra

# Déployer
anklume apply all

# Vérifier
anklume status
```

## Documentation

- [Spécification](SPEC.md) — référence complète
- [Architecture](ARCHITECTURE.md) — décisions de design (ADRs)
- [Roadmap](ROADMAP.md) — état et prochaines étapes
