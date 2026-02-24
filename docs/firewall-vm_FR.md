# VM Pare-feu Dediee (sys-firewall)

> Traduction francaise de [`firewall-vm.md`](firewall-vm.md). En cas de divergence, la version anglaise fait foi.

anklume supporte deux modes de pare-feu pour l'isolation inter-domaines :

- **Mode `host`** (defaut) : regles nftables sur le noyau de l'hote (Phase 8)
- **Mode `vm`** : trafic route a travers une VM pare-feu dediee

Le mode `vm` fournit une isolation plus forte : le pare-feu fonctionne dans
son propre noyau, avec une journalisation centralisee et un controle complet
de nftables dans la VM.

## Architecture

```
+----------------------------------------------------------+
| Hote                                                      |
|                                                           |
|  net-anklume    net-perso    net-pro    net-homelab         |
|    |              |           |           |                |
|    +------+-------+-------+--+           |                |
|           |               |              |                |
|    +------+---------------+--------------+------+        |
|    |         sys-firewall (VM KVM)               |        |
|    |  eth0=anklume  eth1=perso  eth2=pro  eth3=hl |        |
|    |                                              |        |
|    |  nftables : tout inter-domaine rejete         |        |
|    |            anklume utilise le socket Incus     |        |
|    |            journalisation centralisee          |        |
|    +----------------------------------------------+        |
+----------------------------------------------------------+
```

La VM pare-feu a une carte reseau par bridge de domaine. Elle agit comme
un routeur de couche 3 entre les domaines, appliquant les regles nftables
sur le trafic transmis.

## Demarrage rapide (creation automatique)

Le moyen le plus simple d'activer la VM pare-feu est de definir `firewall_mode: vm`
dans `infra.yml`. Le generateur PSOT cree automatiquement la machine `sys-firewall`
dans le domaine anklume si vous n'en avez pas declare une vous-meme :

```yaml
# infra.yml -- ajoutez simplement firewall_mode: vm
global:
  base_subnet: "10.100"
  firewall_mode: vm

domains:
  anklume:
    subnet_id: 0
    machines:
      anklume-instance:
        type: lxc
        ip: "10.100.0.10"
        roles: [base_system]
  # ... autres domaines ...
```

```bash
make sync    # Cree automatiquement sys-firewall (10.100.0.253) dans le domaine anklume
make apply   # Cree l'infrastructure + provisionne la VM pare-feu
```

Le generateur affiche un message informatif lors de la creation automatique :

```
INFO: firewall_mode is 'vm' — auto-created sys-firewall in anklume domain (ip: 10.100.0.253)
```

La `sys-firewall` creee automatiquement a : type `vm`, IP `.253` dans le
sous-reseau anklume, 2 vCPU, 2 Gio de memoire, roles `[base_system, firewall_router]`,
et `ephemeral: false`.

Pour personnaliser la VM pare-feu (IP differente, plus de ressources, roles
supplementaires), declarez-la explicitement dans `infra.yml` et le generateur
utilisera votre definition a la place. Voir la section configuration manuelle
ci-dessous.

## Configuration (manuelle)

### 1. Definir le mode pare-feu dans infra.yml

```yaml
global:
  base_subnet: "10.100"
  firewall_mode: vm  # Activer le mode VM pare-feu
```

### 2. Declarer la VM pare-feu (optionnel -- creee automatiquement si omise)

Pour surcharger les valeurs par defaut, ajoutez `sys-firewall` au domaine anklume :

```yaml
domains:
  anklume:
    subnet_id: 0
    machines:
      anklume-instance:
        type: lxc
        ip: "10.100.0.10"
        roles: [base_system]
      sys-firewall:
        description: "VM pare-feu centralisee"
        type: vm
        ip: "10.100.0.253"
        config:
          limits.cpu: "4"
          limits.memory: "4GiB"
        roles:
          - base_system
          - firewall_router
```

### 3. Deployer

```bash
make sync          # Generer les fichiers Ansible
make apply         # Creer l'infrastructure + provisionner
```

Le role `incus_firewall_vm` automatiquement :
1. Decouvre tous les bridges anklume
2. Cree un profil `firewall-multi-nic` avec une carte reseau par bridge
3. Attache le profil a la VM sys-firewall

Le role `firewall_router` provisionne la VM :
1. Active le forwarding IP (`net.ipv4.ip_forward = 1`)
2. Installe nftables
3. Deploie les regles d'isolation avec journalisation

## Regles de pare-feu

Les regles nftables generees dans la VM appliquent :

| Source | Destination | Action |
|--------|------------|--------|
| tout domaine | domaine different | DROP (journalise) |
| tout | tout (ICMP) | ACCEPT |
| tout | tout (connexion etablie) | ACCEPT |

Le domaine anklume est traite comme n'importe quel autre domaine. Le container
anklume communique avec toutes les instances via le socket Incus, pas le reseau,
donc il n'a pas besoin d'exception au niveau reseau.

Toutes les decisions sont journalisees avec des prefixes :
- `FW-DENY-<DOMAINE>` : trafic inter-domaines bloque
- `FW-INVALID` : etat de paquet invalide
- `FW-DROP` : rejet par defaut
- `FW-INPUT-DROP` : tentative de connexion a la VM pare-feu elle-meme

### Consulter les journaux

```bash
incus exec sys-firewall --project anklume -- journalctl -kf | grep "FW-"
```

## Defense en profondeur

Les modes `host` et `vm` peuvent coexister pour une securite en couches :

1. **nftables hote** (Phase 8) : bloque le forwarding direct bridge-a-bridge
2. **VM pare-feu** (Phase 11) : route le trafic autorise + journalise

Meme si la VM pare-feu est compromise, les regles nftables au niveau de
l'hote empechent toujours le trafic direct inter-bridges.

## Routage des instances

Pour que les instances routent le trafic inter-domaines a travers la VM
pare-feu, configurez des routes statiques. Deux approches :

### Via la configuration d'instance (cloud-init)

```yaml
# Dans host_vars/<instance>.yml (manuellement, hors section geree)
instance_config:
  cloud-init.network-config: |
    version: 2
    ethernets:
      eth0:
        addresses:
          - 10.100.1.10/24
        routes:
          - to: 10.100.0.0/16
            via: 10.100.1.253
          - to: default
            via: 10.100.1.254
```

### Via le provisionnement Ansible

Ajoutez une tache de configuration de route dans le role `base_system` ou un role personnalise :

```yaml
- name: Add route to firewall VM for inter-domain traffic
  ansible.builtin.command:
    cmd: ip route add 10.100.0.0/16 via {{ firewall_vm_ip }}
  when: firewall_mode == 'vm'
```

## Personnalisation

### Valeurs par defaut du role

| Variable | Defaut | Description |
|----------|--------|-------------|
| `firewall_router_logging` | `true` | Activer la journalisation nftables |
| `firewall_router_log_prefix` | `FW` | Prefixe des messages de journal |
| `incus_firewall_vm_bridge_pattern` | `net-` | Patron de decouverte des bridges |
| `incus_firewall_vm_profile` | `firewall-multi-nic` | Nom du profil |

### Ajouter des regles personnalisees

Editez les regles de pare-feu dans la VM :

```bash
incus exec sys-firewall --project anklume -- \
  vi /etc/nftables.d/anklume-firewall.nft

# Recharger
incus exec sys-firewall --project anklume -- \
  systemctl restart nftables
```

## Depannage

### La VM pare-feu n'a qu'une seule carte reseau

Le role `incus_firewall_vm` ajoute des cartes reseau dynamiquement en
fonction des bridges decouverts. Verifiez que les bridges existent :

```bash
incus network list | grep net-
```

Verifiez le profil :

```bash
incus profile show firewall-multi-nic --project anklume
```

### Le trafic ne passe pas par la VM pare-feu

1. Verifier le forwarding IP : `incus exec sys-firewall -- sysctl net.ipv4.ip_forward`
2. Verifier les regles nftables : `incus exec sys-firewall -- nft list ruleset`
3. Verifier les routes des instances : `incus exec <instance> -- ip route show`

### La VM pare-feu ne demarre pas

Les VMs necessitent plus de ressources que les containers. Assurez-vous
d'avoir au moins 2 vCPU et 2 Gio de memoire dans la configuration.
