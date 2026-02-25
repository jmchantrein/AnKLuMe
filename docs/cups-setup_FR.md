# Service d'impression

> Note : la version anglaise ([`cups-setup.md`](cups-setup.md)) fait reference en cas de divergence.

La configuration recommandee utilise un domaine `shared` avec
`shared-print` comme nom de conteneur (voir SPEC.md "Naming conventions").

anklume permet de configurer un serveur d'impression CUPS dedie dans
un conteneur. Les imprimantes USB sont passees via le mecanisme de
peripheriques Incus, et les imprimantes reseau sont accessibles via
une interface macvlan donnant au conteneur un acces direct au reseau
local. Les autres domaines impriment via IPP (port 631) controle par
les `network_policies`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         Hote                             │
│                                                          │
│  net-pro ────────────┐                                  │
│    pro-dev           │  IPP :631     ┌───────────────┐  │
│                      ├──────────────▶│ net-print      │  │
│  net-perso ──────────┤               │  shared-print  │  │
│    perso-desktop     │               │  CUPS :631     │  │
│                      │               │                │  │
│                      │               │  USB: printer  │  │
│                      │               │  NIC: macvlan  │  │
│                      │               └────────┬───────┘  │
│                      │                        │          │
│                      │                   Reseau local    │
│                      │                   (imprimantes)   │
└──────────────────────┴───────────────────────────────────┘
```

## Demarrage rapide

### 1. Declarer le service d'impression dans infra.yml

```yaml
domains:
  shared:
    description: "Services partages (impression, DNS, VPN)"
    trust_level: semi-trusted
    machines:
      shared-print:
        description: "Serveur d'impression CUPS"
        type: lxc
        roles:
          - base_system

network_policies:
  - description: "Le domaine pro imprime via CUPS"
    from: pro
    to: shared
    ports: [631]
    protocol: tcp

  - description: "Le domaine perso imprime via CUPS"
    from: perso
    to: shared
    ports: [631]
    protocol: tcp
```

### 2. Deployer l'infrastructure

```bash
make sync
make apply
```

### 3. Configurer CUPS dans le conteneur

```bash
make apply-print I=shared-print
```

### 4. Ajouter des imprimantes

```bash
# Imprimante USB (necessite les IDs vendeur et produit)
scripts/cups-setup.sh add-usb shared-print --vendor 04b8 --product 0005

# Imprimante reseau (NIC macvlan pour acces au reseau local)
scripts/cups-setup.sh add-network shared-print --nic-parent enp3s0
```

### 5. Verifier l'etat

```bash
scripts/cups-setup.sh status shared-print
```

## Commandes

### setup

Installer et configurer CUPS pour l'acces distant :

```bash
scripts/cups-setup.sh setup <instance> [--project PROJET]
```

La commande setup :
1. Installe les paquets `cups` et `cups-filters`
2. Configure CUPS pour l'acces distant (`Listen *:631`, `Allow @LOCAL`)
3. Active l'interface web
4. Active et demarre le service CUPS

### add-usb

Ajouter une imprimante USB via le passthrough de peripherique Incus :

```bash
scripts/cups-setup.sh add-usb <instance> --vendor VID --product PID [--project PROJET]
```

Trouver les IDs vendeur et produit de votre imprimante avec `lsusb`
sur l'hote :

```bash
lsusb
# Bus 001 Device 005: ID 04b8:0005 Seiko Epson Corp. Printer
#                         ^^^^:^^^^
#                         vendeur:produit
```

La commande utilise `incus config device add` pour attacher le
peripherique USB directement au conteneur.

### add-network

Ajouter une interface macvlan pour la decouverte d'imprimantes reseau :

```bash
scripts/cups-setup.sh add-network <instance> --nic-parent IFACE [--project PROJET]
```

Cela donne au conteneur un acces direct au reseau local physique,
lui permettant de decouvrir les imprimantes WiFi et Ethernet. Le
parametre `--nic-parent` doit etre l'interface reseau physique de
l'hote (ex. `eth0`, `enp3s0`, `wlan0`).

Apres l'ajout du NIC, redemarrer l'instance pour prise en compte.

### status

Afficher l'etat du service CUPS et des imprimantes configurees :

```bash
scripts/cups-setup.sh status <instance> [--project PROJET]
```

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `make apply-print I=<instance>` | Configurer le service CUPS dans le conteneur |

Accepte un parametre optionnel `PROJECT=<projet>`.

## Interface web CUPS

Apres la configuration, l'interface web CUPS est accessible a :

```
http://<ip-instance>:631
```

Depuis l'interface web vous pouvez :
- Ajouter et configurer des imprimantes
- Gerer les files d'impression
- Consulter l'historique des travaux d'impression

## Imprimer depuis d'autres domaines

Les conteneurs d'autres domaines peuvent imprimer si les
`network_policies` autorisent le port 631 :

```bash
# Installer le client CUPS dans le conteneur client
incus exec pro-dev --project pro -- apt install -y cups-client

# Ajouter l'imprimante distante
incus exec pro-dev --project pro -- \
    lpadmin -p remote-printer -v ipp://shared-print:631/printers/MyPrinter -E

# Imprimer une page de test
incus exec pro-dev --project pro -- \
    lp -d remote-printer /etc/hostname
```

## Passthrough d'imprimante USB

Le passthrough de peripherique USB d'Incus donne au conteneur un acces
direct au peripherique USB. Points importants :

- Le peripherique doit etre branche quand le conteneur demarre (ou
  branche a chaud apres ajout de la configuration du peripherique)
- Un seul conteneur peut posseder un peripherique USB a la fois
- L'hote n'a pas besoin de pilotes d'imprimante installes

### Trouver les IDs USB

```bash
# Sur l'hote
lsusb
# Bus 001 Device 005: ID 04b8:0005 Seiko Epson Corp. Printer

# Vendor ID: 04b8
# Product ID: 0005
```

### Retirer un peripherique USB

```bash
incus config device remove shared-print printer-04b8-0005 --project shared
```

## Acces imprimante reseau via macvlan

L'interface macvlan donne au conteneur une interface virtuelle sur le
reseau local physique, avec sa propre adresse MAC et IP. Cela permet
au conteneur de decouvrir et communiquer directement avec les
imprimantes reseau.

Avantages :
- Acces direct aux imprimantes WiFi et Ethernet
- La decouverte mDNS/Bonjour fonctionne nativement
- Pas de redirection de port necessaire

Limitations :
- L'hote ne peut pas communiquer avec le conteneur via l'interface
  macvlan (utiliser l'interface bridge a la place)
- Necessite le nom de l'interface physique (varie selon l'hote)

## Depannage

### CUPS ne demarre pas

Verifier les journaux du service :

```bash
incus exec shared-print --project shared -- journalctl -u cups -f
```

### Imprimante USB non detectee

Verifier que le peripherique est attache :

```bash
incus config device show shared-print --project shared
```

Verifier que le peripherique USB est branche sur l'hote :

```bash
lsusb | grep <vendor-id>
```

### Imprimante reseau non trouvee

Apres l'ajout d'une interface macvlan, redemarrer l'instance :

```bash
incus restart shared-print --project shared
```

Verifier que l'interface est active :

```bash
incus exec shared-print --project shared -- ip addr show
```

### Permission refusee a l'impression

CUPS est configure avec `Allow @LOCAL` qui autorise l'acces depuis le
reseau local. Si l'acces est refuse depuis un autre domaine, verifier
que les `network_policies` dans `infra.yml` autorisent le port 631
depuis le domaine client.
