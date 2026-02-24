# Passerelle Tor

> Note : En cas de divergence, la version anglaise (`tor-gateway.md`)
> fait foi.

anklume permet de configurer un proxy transparent Tor dans un conteneur.
Le trafic de domaines choisis peut etre route via la passerelle pour un
acces internet anonyme, controle par `network_policies` dans `infra.yml`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         Hote                             │
│                                                          │
│  net-anonymous ────┐                                    │
│                    │      ┌───────────────────┐         │
│                    ├─────▶│ net-tor-gateway    │         │
│                    │      │  tor-gw            │         │
│                    │      │  TransPort 9040    │         │
│                    │      │  DNSPort 5353      │         │
│  net-anklume ──────┘      │  nftables redirect │         │
│    (bloque)               └────────┬──────────┘         │
│                                    │                     │
│                              Reseau Tor                  │
│                                    │                     │
│                               Internet                   │
└─────────────────────────────────────────────────────────┘
```

Le conteneur passerelle Tor execute Tor en proxy transparent. A
l'interieur du conteneur, des regles nftables redirigent tout le trafic
TCP et DNS a travers Tor. Les autres domaines accedent a la passerelle
via `network_policies`.

## Demarrage rapide

### 1. Declarer la passerelle Tor dans infra.yml

```yaml
domains:
  tor-gateway:
    description: "Passerelle proxy transparent Tor"
    subnet_id: 5
    trust_level: untrusted
    ephemeral: true
    machines:
      tor-gw:
        description: "Proxy transparent Tor"
        type: lxc
        ip: "10.100.5.10"
        roles:
          - base_system

  anonymous:
    description: "Domaine route via Tor"
    subnet_id: 6
    trust_level: untrusted
    ephemeral: true
    machines:
      anon-browser:
        type: lxc
        ip: "10.100.6.10"
        roles:
          - base_system

network_policies:
  - description: "Domaine anonyme route via passerelle Tor"
    from: anonymous
    to: tor-gateway
    ports: all
    bidirectional: true
```

### 2. Deployer l'infrastructure

```bash
make sync
make apply
```

### 3. Configurer Tor dans le conteneur passerelle

```bash
make apply-tor I=tor-gw
```

Cela installe Tor, le configure en proxy transparent, cree les regles
nftables de redirection et demarre le service.

### 4. Verifier la connectivite Tor

```bash
scripts/tor-gateway.sh verify tor-gw
```

## Commandes

### setup

Installer et configurer Tor en proxy transparent :

```bash
scripts/tor-gateway.sh setup <instance> [--project PROJET]
```

### status

Afficher l'etat du service Tor et des regles nftables :

```bash
scripts/tor-gateway.sh status <instance> [--project PROJET]
```

### verify

Verifier la connectivite Tor et l'etablissement du circuit :

```bash
scripts/tor-gateway.sh verify <instance> [--project PROJET]
```

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `make apply-tor I=<instance>` | Configurer le proxy transparent Tor |

Accepte un parametre optionnel `PROJECT=<projet>`.

## Depannage

### Tor ne s'initialise pas

Verifier les journaux Tor dans le conteneur :

```bash
incus exec tor-gw --project tor-gateway -- journalctl -u tor -f
```

### Le trafic ne passe pas par Tor

Verifier depuis l'interieur du conteneur Tor :

```bash
incus exec tor-gw --project tor-gateway -- curl -s https://check.torproject.org/api/ip
```
