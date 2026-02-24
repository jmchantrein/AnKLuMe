# Service d'impression (sys-print)

> Note : En cas de divergence, la version anglaise (`sys-print.md`)
> fait foi.

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
│  net-perso ──────────┤               │  sys-print     │  │
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
  print-service:
    description: "Domaine dedie au service d'impression"
    subnet_id: 7
    trust_level: trusted
    machines:
      sys-print:
        description: "Serveur d'impression CUPS"
        type: lxc
        ip: "10.100.7.10"
        roles:
          - base_system

network_policies:
  - description: "Le domaine pro imprime via CUPS"
    from: pro
    to: print-service
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
make apply-print I=sys-print
```

### 4. Ajouter des imprimantes

```bash
# Imprimante USB (necessite les IDs vendeur et produit)
scripts/sys-print.sh add-usb sys-print --vendor 04b8 --product 0005

# Imprimante reseau (NIC macvlan pour acces au reseau local)
scripts/sys-print.sh add-network sys-print --nic-parent enp3s0
```

### 5. Verifier l'etat

```bash
scripts/sys-print.sh status sys-print
```

## Commandes

### setup

Installer et configurer CUPS pour l'acces distant :

```bash
scripts/sys-print.sh setup <instance> [--project PROJET]
```

### add-usb

Ajouter une imprimante USB via le passthrough de peripherique Incus :

```bash
scripts/sys-print.sh add-usb <instance> --vendor VID --product PID [--project PROJET]
```

### add-network

Ajouter une interface macvlan pour la decouverte d'imprimantes reseau :

```bash
scripts/sys-print.sh add-network <instance> --nic-parent IFACE [--project PROJET]
```

### status

Afficher l'etat du service CUPS et des imprimantes configurees :

```bash
scripts/sys-print.sh status <instance> [--project PROJET]
```

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `make apply-print I=<instance>` | Configurer le service CUPS |

Accepte un parametre optionnel `PROJECT=<projet>`.

## Trouver les IDs USB

```bash
# Sur l'hote
lsusb
# Bus 001 Device 005: ID 04b8:0005 Seiko Epson Corp. Printer
#                         ^^^^:^^^^
#                         vendeur:produit
```

## Imprimer depuis d'autres domaines

Les conteneurs d'autres domaines peuvent imprimer si les
`network_policies` autorisent le port 631 :

```bash
# Installer le client CUPS
incus exec pro-dev --project pro -- apt install -y cups-client

# Ajouter l'imprimante distante
incus exec pro-dev --project pro -- \
    lpadmin -p imprimante -v ipp://10.100.7.10:631/printers/MaImprimante -E

# Imprimer une page de test
incus exec pro-dev --project pro -- \
    lp -d imprimante /etc/hostname
```

## Depannage

### CUPS ne demarre pas

Verifier les journaux du service :

```bash
incus exec sys-print --project print-service -- journalctl -u cups -f
```

### Imprimante USB non detectee

Verifier que le peripherique est attache :

```bash
incus config device show sys-print --project print-service
```

### Imprimante reseau non trouvee

Apres l'ajout d'une interface macvlan, redemarrer l'instance :

```bash
incus restart sys-print --project print-service
```
