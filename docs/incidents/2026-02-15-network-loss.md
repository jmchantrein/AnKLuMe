# Incident : Perte de connectivité réseau - 2026-02-15

## Résumé

Perte de connectivité internet au niveau de la VM de développement nécessitant l'arrêt d'Incus et un redémarrage pour récupération.

## Symptômes

- Perte de connexion sortante (internet)
- Incus en cours d'exécution au moment de l'incident
- Résolution : `systemctl stop incus` + reboot

## Cause probable

À déterminer - hypothèses :

1. **Conflit de routage** : Incus a créé des bridges qui ont interféré avec la route par défaut
2. **Règles firewall** : Des règles nftables/iptables bloquant le trafic sortant
3. **Session agent teams** : Commandes réseau exécutées avec `--dangerously-skip-permissions`

## Analyse

- Aucune trace claire dans les logs accessibles sans sudo
- Pas de règles nftables résiduelles trouvées
- Historique bash montre plusieurs sessions Claude Code agent teams
- Pas de modifications non commitées dans le repo

## État actuel

- Incus arrêté (inactive/dead)
- Réseau fonctionnel : route par défaut via 10.100.0.254
- Connectivité internet OK

## Mesures préventives mises en place

### 1. Script de sauvegarde réseau (`scripts/network-safety-check.sh`)

- Sauvegarde automatique de l'état réseau avant opérations critiques
- Vérification de connectivité
- Possibilité de consultation des backups

### 2. Intégration Makefile (À FAIRE)

Ajouter des hooks de vérification réseau :

```makefile
# Avant make apply
apply: network-backup
	@scripts/network-safety-check.sh backup
	ansible-playbook site.yml --tags infra,provision
	@scripts/network-safety-check.sh verify || (echo "WARNING: Network check failed after apply"; exit 1)
```

### 3. Restrictions agent teams (À CONSIDÉRER)

Modifier les permissions pour les agents teams :

```json
{
  "permissions": {
    "deny": [
      "Bash(ip route *)",
      "Bash(nft *)",
      "Bash(iptables *)",
      "Bash(systemctl * incus *)"
    ]
  }
}
```

## Actions recommandées

1. ✅ Créer un script de sauvegarde/vérification réseau
2. ⏳ Intégrer les vérifications dans le Makefile
3. ⏳ Ajouter des restrictions sur les commandes réseau pour les agents
4. ⏳ Améliorer le logging des sessions agent teams
5. ⏳ Documenter la procédure de récupération en cas de perte réseau

## Procédure de récupération

Si le problème se reproduit :

1. Sauvegarder l'état actuel :
   ```bash
   ip route show > /tmp/routes-broken.txt
   nft list ruleset > /tmp/nft-broken.txt 2>/dev/null
   ```

2. Consulter la dernière sauvegarde :
   ```bash
   scripts/network-safety-check.sh restore-info
   ```

3. Arrêter Incus :
   ```bash
   sudo systemctl stop incus
   ```

4. Vérifier si la connectivité revient :
   ```bash
   ping -c 3 1.1.1.1
   ```

5. Si OK : redémarrer Incus prudemment
   Si KO : reboot

## Notes

- Cet incident souligne l'importance de ne jamais exécuter d'opérations réseau critiques sans sauvegarde préalable
- Les permissions `--dangerously-skip-permissions` doivent être utilisées avec extrême prudence
- Un monitoring réseau continu pendant les opérations Incus est recommandé
