# Passerelle Tor

VM routeur transparent Tor pour anonymiser le trafic d'un domaine.

## Architecture

```mermaid
graph LR
    M["Machines du domaine"] -->|"trafic réseau"| TOR["tor-gateway<br/>VM routeur"]
    TOR -->|"réseau Tor"| Internet

    style TOR fill:#8b5cf6,color:#fff
    style M fill:#3b82f6,color:#fff
```

## Configuration

Déclarer une machine avec le rôle `tor_gateway` :

```yaml
# domains/anonymous.yml
description: "Navigation anonyme"
trust_level: untrusted

machines:
  tor-gw:
    description: "Passerelle Tor transparente"
    type: vm
    roles: [base, tor_gateway]
```

## Rôle Ansible `tor_gateway`

- Installation et configuration de Tor
- Template `torrc.j2` (TransPort, DNSPort, SOCKSPort)
- Règles nftables pour le routage transparent (`nftables-tor.conf.j2`)
- Service systemd avec handlers de reload

## Commande

```bash
# État des passerelles Tor
anklume tor status
```
