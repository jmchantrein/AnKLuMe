# Convention d'adressage

> Traduction francaise de [`addressing-convention.md`](addressing-convention.md). En cas de divergence, la version anglaise fait foi.

anklume encode les zones de confiance dans les adresses IP afin qu'un
administrateur puisse determiner la posture de securite de n'importe
quelle machine a partir de son IP seule.

## Schema

```
10.<zone_base + zone_offset>.<domain_seq>.<host>/24
```

- **Premier octet** (10) : plage privee RFC 1918
- **Deuxieme octet** : zone de confiance (zone_base + zone_offset)
- **Troisieme octet** : sequence du domaine dans la zone
- **Quatrieme octet** : adresse de l'hote dans le domaine

## Correspondance des zones

| trust_level    | zone_offset | Deuxieme octet par defaut | Nom de zone | Couleur |
|----------------|-------------|---------------------------|-------------|---------|
| admin          | 0           | 100                       | MGMT        | bleu    |
| trusted        | 10          | 110                       | TRUSTED     | vert    |
| semi-trusted   | 20          | 120                       | SERVICES    | jaune   |
| untrusted      | 40          | 140                       | SANDBOX     | rouge   |
| disposable     | 50          | 150                       | GATEWAY     | magenta |

Les intervalles (130, 160-199) sont reserves pour de futures sous-zones
ou des zones definies par l'utilisateur. La plage 200-249 est disponible
pour un usage personnalise.

## Configuration

```yaml
global:
  addressing:
    base_octet: 10     # Premier octet (defaut : 10, seul /8 RFC 1918)
    zone_base: 100     # Deuxieme octet de depart (defaut : 100)
    zone_step: 10      # Ecart entre les zones (defaut : 10)
```

### Pourquoi zone_base=100 ?

La plage `10.0-60.x.x` est fortement utilisee par les VPN d'entreprise,
les routeurs domestiques (`10.0.0.x`, `10.0.1.x`), Kubernetes
(`10.96.x.x`, `10.244.x.x`) et d'autres outils. Commencer a 100 evite
a la fois les conflits de routage reels et la confusion cognitive
(« est-ce mon laptop ou le reseau de l'entreprise ? »).

## Sequence de domaine (troisieme octet)

Au sein de chaque zone, les domaines se voient attribuer un numero de
sequence (troisieme octet) automatiquement par ordre alphabetique.
Cela peut etre remplace par un `subnet_id` explicite sur le domaine.

Exemple avec deux domaines trusted :
- `perso` → alphabetiquement premier → domain_seq = 0 → `10.110.0.0/24`
- `pro` → alphabetiquement second → domain_seq = 1 → `10.110.1.0/24`

Pour forcer `pro` comme primaire (seq 0), utilisez `subnet_id: 0` sur
`pro` et `subnet_id: 1` sur `perso`.

## Reservation d'IP par sous-reseau /24

| Plage       | Usage                                         |
|-------------|-----------------------------------------------|
| `.0`        | Adresse reseau (reservee)                     |
| `.1-.99`    | Affectation statique (machines dans infra.yml)|
| `.100-.199` | Plage DHCP (geree par Incus)                  |
| `.200-.249` | Disponible pour usage futur                   |
| `.250`      | Sonde de monitoring (reservee)                |
| `.251-.253` | Infrastructure (firewall .253, etc.)          |
| `.254`      | Gateway (convention immuable)                 |
| `.255`      | Broadcast (reservee)                          |

## Attribution automatique d'IP

Les machines sans champ `ip:` explicite recoivent une adresse attribuee
automatiquement a partir de `.1` dans le sous-reseau de leur domaine,
incrementee pour chaque machine dans l'ordre de declaration. Les IP
auto-attribuees restent dans la plage `.1-.99`.

```yaml
machines:
  ai-gpu:       # → .1 (auto)
    type: lxc
  ai-webui:     # → .2 (auto)
    type: lxc
  ai-chat:
    ip: "10.120.0.30"  # explicite → .30
  ai-code:      # → .3 (auto, saute .30)
    type: lxc
```

## Imbrication (nesting)

Chaque niveau d'imbrication utilise des adresses IP identiques.
L'isolation reseau entre les niveaux est assuree par la virtualisation
Incus (bridges separes, daemons Incus separes), pas par la
differenciation d'IP. Le parametre global `nesting_prefix` n'affecte
que les noms de ressources Incus (`001-net-pro`, etc.).

Cela signifie que le meme `infra.yml` produit des resultats identiques
a n'importe quel niveau d'imbrication — le framework est entierement
reproductible.

## Convention de nommage des machines

Schema recommande : `<domaine>-<role>` ou `<abrev_domaine>-<role>`.

| Domaine     | Machine         | Role                       |
|-------------|-----------------|----------------------------|
| anklume     | anklume-instance| Controleur Ansible         |
| pro         | pro-dev         | Espace de developpement    |
| perso       | perso-desktop   | Bureau personnel           |
| ai-tools    | ai-gpu          | Serveur GPU (Ollama+STT)   |
| ai-tools    | ai-webui        | Interface Open WebUI       |
| tor-gateway | torgw-proxy     | Proxy transparent Tor      |
| anonymous   | anon-browser    | Navigateur isole           |

Les machines d'infrastructure du domaine anklume utilisent le prefixe
`anklume-` : `anklume-firewall`, `anklume-instance`. Les autres services
systeme utilisent le prefixe de leur domaine : `shared-dns`, `shared-vpn`.

## Convention de nommage des domaines

Les noms de domaines doivent etre courts, en anglais, descriptifs de
l'usage :

| Bon           | Mauvais          | Pourquoi                    |
|---------------|------------------|-----------------------------|
| `pro`         | `domain-02`      | Pas semantique              |
| `ai-tools`    | `gpu-stuff`      | Pas assez descriptif        |
| `tor-gateway` | `torgw`          | Trop abrege                 |
| `lab-01`      | `student-dupont` | Donnee personnelle dans nom |

## Exemple complet

Infrastructure anklume canonique :

```
IP               Machine           Domaine      Zone       trust_level
───────────────────────────────────────────────────────────────────────
10.100.0.10      anklume-instance  anklume      MGMT       admin
10.110.0.10      pro-dev           pro          TRUSTED    trusted
10.110.1.10      perso-desktop     perso        TRUSTED    trusted
10.120.0.10      ai-gpu            ai-tools     SERVICES   semi-trusted
10.120.0.20      ai-webui          ai-tools     SERVICES   semi-trusted
10.120.0.30      ai-chat           ai-tools     SERVICES   semi-trusted
10.120.0.40      ai-code           ai-tools     SERVICES   semi-trusted
10.140.0.1       anon-browser      anonymous    SANDBOX    untrusted
10.150.0.1       torgw-proxy       tor-gateway  GATEWAY    disposable
```

Lecture de `10.120.0.30` : deuxieme octet 120 = 100+20 → semi-trusted
(zone SERVICES). Troisieme octet 0 → premier domaine de la zone. Hote 30.
