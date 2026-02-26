# Isolation Reseau avec nftables

> Traduction francaise de [`network-isolation.md`](network-isolation.md). En cas de divergence, la version anglaise fait foi.

anklume utilise nftables pour appliquer l'isolation inter-bridges sur l'hote.
Par defaut, les bridges Incus permettent le forwarding entre eux, ce qui
signifie qu'un container dans un domaine peut atteindre les containers
d'autres domaines. Le role `incus_nftables` genere des regles qui bloquent
ce trafic inter-domaines tout en preservant l'acces anklume.

## Fonctionnement de l'isolation des domaines

Chaque domaine anklume a son propre bridge (ex. `net-anklume`, `net-pro`,
`net-perso`, `net-homelab`). Sans regles d'isolation, le noyau Linux
fait transiter les paquets entre ces bridges librement.

Les regles nftables appliquent :

1. **Trafic intra-bridge** : autorise (les containers au sein d'un domaine
   peuvent communiquer)
2. **Tout trafic inter-bridges** : rejete (ex. `net-perso` ne peut pas
   atteindre `net-pro`, et `net-anklume` ne peut pas atteindre les autres
   domaines non plus)
4. **Acces Internet** : non affecte (les regles NAT d'Incus sont preservees)
5. **Trafic retour** : le suivi d'etat permet aux paquets de reponse de
   revenir via les connexions etablies

## Conception des regles nftables

### Table et chaine

Les regles resident dans `table inet anklume` avec une seule chaine `isolation` :

```nft
table inet anklume {
    chain isolation {
        type filter hook forward priority -1; policy accept;
        ...
    }
}
```

Choix de conception :

- **Famille `inet`** : gere a la fois IPv4 et IPv6 dans une seule table
- **Hook `forward`** : filtre le trafic route entre les bridges
- **`priority -1`** : s'execute avant les chaines gerees par Incus (priorite 0),
  garantissant que les regles d'isolation sont evaluees en premier
- **`policy accept`** : acceptation par defaut, avec des regles de rejet explicites
  pour le trafic inter-bridges. Cela evite d'interferer avec le trafic non-anklume

### Remplacement atomique

Le jeu de regles utilise `table inet anklume; delete table inet anklume;` suivi
de la definition complete de la table. Cela garantit que les regles sont remplacees
atomiquement sans intervalle ou aucune regle n'est active.

### Coexistence avec Incus

Les regles anklume utilisent une table separee (`inet anklume`), priorite -1
(avant les chaines Incus), et `policy accept`. Le trafic non correspondant
tombe dans les chaines NAT et par bridge gerees par Incus sans interference.

### Suivi d'etat

`ct state established,related accept` autorise le trafic retour des connexions
etablies. Les paquets invalides sont rejetes.

## Flux de travail en deux etapes

La generation et le deploiement des regles nftables est un processus en deux
etapes car anklume s'execute dans le container anklume mais les regles nftables
doivent etre appliquees sur l'hote.

### Etape 1 : Generer les regles (dans le container anklume)

```bash
anklume network rules
```

Cela execute le role Ansible `incus_nftables`, qui :

1. Interroge `incus network list` pour decouvrir tous les bridges
2. Filtre les bridges anklume (noms commencant par `net-`)
3. Genere les regles nftables dans `/opt/anklume/nftables-isolation.nft`

Le fichier genere est stocke dans le container anklume et peut etre
examine avant le deploiement.

### Etape 2 : Deployer les regles (sur l'hote)

```bash
anklume network deploy
```

Cela execute `scripts/deploy-nftables.sh` **sur l'hote** (pas dans le
container). Le script :

1. Recupere le fichier de regles depuis le container anklume via `incus file pull`
2. Valide la syntaxe avec `nft -c -f` (execution a blanc)
3. Copie vers `/etc/nftables.d/anklume-isolation.nft`
4. Applique les regles avec `nft -f`

Utilisez `--dry-run` pour valider sans installer :

```bash
scripts/deploy-nftables.sh --dry-run
```

### Pourquoi deux etapes ?

anklume suit l'ADR-004 : Ansible ne modifie pas l'hote directement.
Le container anklume pilote Incus via le socket, mais nftables doit etre
applique sur le noyau de l'hote. Separer la generation (sure, dans le container)
du deploiement (necessite un acces hote) maintient cette frontiere tout en
donnant a l'operateur l'occasion d'examiner les regles avant de les appliquer.

## Configuration

Variables dans `roles/incus_nftables/defaults/main.yml` :

| Variable | Defaut | Description |
|----------|--------|-------------|
| `incus_nftables_bridge_pattern` | `net-` | Prefixe utilise pour identifier les bridges anklume |
| `incus_nftables_output_path` | `/opt/anklume/nftables-isolation.nft` | Ou ecrire les regles generees |
| `incus_nftables_apply` | `false` | Appliquer les regles immediatement (a utiliser avec precaution) |

Definir `incus_nftables_apply: true` fait que le role applique les regles directement.
Cela ne fonctionne que si le role s'execute sur l'hote (pas dans un container).

## Verification

Apres le deploiement, verifiez que les regles sont actives :

```bash
# Lister la table anklume
nft list table inet anklume

# Tester l'isolation : depuis un container non-anklume, essayer de pinger un autre domaine
incus exec perso-desktop -- ping -c1 10.100.2.10   # Devrait echouer (pro)
incus exec perso-desktop -- ping -c1 10.100.1.254  # Devrait fonctionner (sa propre passerelle)

# Tester l'isolation anklume : anklume ne peut pas atteindre les autres domaines via le reseau
incus exec anklume-instance -- ping -c1 10.100.2.10   # Devrait echouer (rejete)

# Verifier qu'anklume peut toujours gerer les instances via le socket Incus
incus exec anklume-instance -- incus list             # Devrait fonctionner (socket, pas reseau)

# Tester Internet : depuis n'importe quel container
incus exec perso-desktop -- ping -c1 1.1.1.1       # Devrait fonctionner
```

## Depannage

### Les regles ne prennent pas effet

1. Verifier que la table existe : `nft list tables | grep anklume`
2. Verifier que `br_netfilter` est charge : `lsmod | grep br_netfilter`
3. Si `br_netfilter` n'est pas charge, le trafic des bridges contourne
   entierement nftables. Chargez-le avec : `modprobe br_netfilter`
4. Verifier `net.bridge.bridge-nf-call-iptables = 1` dans sysctl

### Acces Internet coupe depuis les containers

Les regles anklume n'affectent que le trafic de la chaine `forward` entre les bridges.
Les regles NAT (masquerade) gerees par Incus utilisent des chaines separees. Si Internet
est coupe :

1. Verifier les regles NAT d'Incus : `nft list ruleset | grep masquerade`
2. Verifier que le bridge a `ipv4.nat: "true"` : `incus network show net-<domaine>`
3. La `policy accept` d'anklume ne devrait pas bloquer le trafic non correspondant

### Supprimer les regles d'isolation

```bash
nft delete table inet anklume           # Supprimer les regles actives
rm /etc/nftables.d/anklume-isolation.nft  # Supprimer le fichier installe
```

### Regenerer apres l'ajout d'un domaine

```bash
anklume sync && anklume domain apply --tags infra    # Creer les ressources du nouveau domaine
anklume network rules                    # Regenerer les regles (dans anklume)
anklume network deploy             # Deployer les regles mises a jour (sur l'hote)
```
