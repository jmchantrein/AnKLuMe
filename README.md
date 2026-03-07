# anklume

Framework déclaratif de compartimentalisation d'infrastructure.

Isolation avec Incus (LXC/KVM) + nftables, sur n'importe quel Linux.

## Démarrage rapide

```bash
pip install anklume
anklume init mon-infra
cd mon-infra
vim domains/pro.yml
anklume apply
```

## Concepts

- **Domaine** — une zone isolée (sous-réseau + projet Incus + N instances)
- **Instance** — un conteneur LXC ou une VM KVM
- **Niveau de confiance** — posture de sécurité encodée dans l'adressage IP

Chaque domaine est décrit dans son propre fichier YAML (`domains/<nom>.yml`),
style docker-compose. `anklume apply` déploie vers Incus.

## Documentation

- [SPEC.md](docs/SPEC.md) — spécification complète
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — décisions d'architecture

## Licence

AGPL-3.0
