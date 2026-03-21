# Environnement sandbox anklume

Tu es root dans une instance anklume isolée. Ce fichier t'explique
ce que tu peux faire et ce que tu ne peux pas faire.

## Ce que tu PEUX faire (en toute sécurité)

- Installer des paquets système (`apt install`, `pacman -S`, etc.)
- Modifier la configuration système (`/etc/`, systemd, cron, etc.)
- Créer/supprimer des utilisateurs, modifier les permissions
- Lancer des services (nginx, postgres, redis, etc.)
- Exécuter des tests E2E, BDD, d'intégration en situation réelle
- Compiler du code, lancer des benchmarks
- Modifier le réseau local de l'instance
- Utiliser anklume pour créer des sous-instances (nesting)
- Écrire sur tout le filesystem sans restriction
- Tuer des processus, redémarrer des services

L'environnement est **jetable**. Tu ne peux rien casser de permanent.
Si quelque chose ne marche pas, on détruit et on recommence.

## Ce que tu NE PEUX PAS faire

- Accéder au réseau de l'hôte (nftables bloque le trafic inter-domaines)
- Accéder aux fichiers de l'hôte (isolation filesystem)
- Communiquer avec d'autres domaines (sauf politiques explicites)
- Pousser du code vers des remotes git (pas de credentials hôte)
- Accéder aux secrets de l'hôte (SSH keys, API keys, etc.)

## Contexte technique

- **Type d'isolation** : conteneur LXC ou VM KVM via Incus
- **Réseau** : sous-réseau dédié, NAT vers internet, drop-all inter-domaines
- **Nesting** : si Incus est installé dans cette instance, tu peux créer
  des sous-conteneurs (`anklume apply` fonctionne ici)
- **Snapshots** : des snapshots automatiques sont pris avant chaque
  `anklume apply`. Rollback possible avec `anklume rollback`.

## Stratégie recommandée

1. **Explore librement** — installe ce dont tu as besoin, modifie la config
2. **Teste en réel** — lance les vrais tests (pas de mocks quand c'est possible)
3. **Itère vite** — si ça casse, c'est normal, corrige et recommence
4. **Ne demande pas la permission** — tu es root, l'environnement est jetable
