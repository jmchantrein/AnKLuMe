# Inspection Reseau et Surveillance de Securite (Phase 40)

> Traduction francaise de [`network-inspection.md`](network-inspection.md). En cas de divergence, la version anglaise fait foi.

Inspection reseau assistee par LLM, par domaine, via des skills OpenClaw
personnalises et des scripts de collecte.

## Architecture : pipeline a 3 niveaux

L'inspection reseau suit un pipeline a trois niveaux, de la collecte de
donnees brutes a l'analyse assistee par LLM :

```
Level 1: Collection        Level 2: Diffing          Level 3: Triage
 nmap scan                  nmap-diff.sh               anklume-network-triage
 tshark capture             anklume-inventory-diff     anklume-pcap-summary
                            anklume-network-diff
```

**Niveau 1 (Collecte)** : Acquisition de donnees reseau brutes a l'aide
d'outils standard (nmap, tshark). S'execute dans les containers du
domaine via `incus exec`. Les resultats sont stockes dans des repertoires
specifiques au domaine.

**Niveau 2 (Comparaison)** : Comparaison avec une ligne de reference
pour detecter les changements depuis le dernier scan. Utilise
`scripts/nmap-diff.sh` pour une utilisation autonome ou le skill
`anklume-inventory-diff` pour les workflows pilotes par OpenClaw.

**Niveau 3 (Triage)** : Classification des decouvertes assistee par LLM
en categories normal/suspect/critique. Le skill `anklume-network-triage`
utilise Ollama pour analyser les resultats de scan avec le contexte du
domaine.

## Skills OpenClaw

Tous les skills sont des templates Jinja2 deployes par le role
`openclaw_server` (ADR-036). Chaque skill est lie a un domaine : il
n'opere que dans le projet Incus qui lui est assigne.

### anklume-network-triage

Analyse les sorties nmap ou tshark et classifie les anomalies par
analyse LLM via Ollama. Niveaux de classification :

| Niveau | Signification |
|--------|---------------|
| normal | Services attendus sur des hotes connus |
| suspect | Inattendu mais pas necessairement malveillant |
| critical | Necessite une attention immediate |

### anklume-inventory-diff

Compare le scan de detection de services nmap actuel avec une ligne
de reference stockee. Detecte les nouveaux hotes, les hotes manquants,
les ports ouverts/fermes et les changements de version de service.

### anklume-pcap-summary

Condense les fichiers de capture de paquets en resumes lisibles.
Extrait la distribution des protocoles, les conversations principales,
les requetes DNS et signale les schemas de trafic anormaux.

## nmap-diff.sh

Script shell autonome pour le scan nmap par domaine avec comparaison
a une ligne de reference.

```bash
scripts/nmap-diff.sh <domain> [--subnet <cidr>] [--baseline-dir <dir>]
```

**Detection automatique** : Lorsque `--subnet` n'est pas specifie,
le script interroge `incus network get net-<domain> ipv4.address` pour
determiner le sous-reseau automatiquement.

**Gestion de la ligne de reference** : Le premier lancement sauvegarde
le scan comme reference. Les lancements suivants comparent avec la
reference et la mettent a jour.

**Format de sortie** : Diff unifie des resumes hote/port.

## Patterns d'anonymisation

La Phase 40 ajoute des patterns specifiques au reseau dans le
sanitiseur LLM (`roles/llm_sanitizer/templates/patterns.yml.j2`) :

| Pattern | Correspond a | Remplacement |
|---------|-------------|--------------|
| `mac_address` | `aa:bb:cc:dd:ee:ff` | `XX:XX:XX:XX:XX:XX` |
| `mac_address_dash` | `aa-bb-cc-dd-ee-ff` | `XX-XX-XX-XX-XX-XX` |
| `linux_interface` | `eth0`, `veth123`, `enp5s0` | `IFACE_REDACTED` |
| `arp_entry` | Lignes de table ARP | Entierement masquees |
| `nmap_host_report` | En-tetes de rapport de scan Nmap | `REDACTED_HOST` |

Ces patterns garantissent que les sorties de scan reseau envoyees aux
LLMs cloud (lorsque `ai_sanitize: true`) ne divulguent pas les adresses
MAC, les noms d'interfaces ou le contenu des tables ARP.

## Configuration

Nouvelles valeurs par defaut dans `roles/openclaw_server/defaults/main.yml` :

```yaml
# Enable periodic network scanning via cron
openclaw_server_network_scan_enabled: false

# Network scan interval in seconds (default: 1 hour)
openclaw_server_network_scan_interval: 3600

# Directory for nmap baseline storage
openclaw_server_nmap_baseline_dir: "/var/lib/openclaw/baselines"
```

Lorsque `openclaw_server_network_scan_enabled: true`, le template CRON.md
inclut une entree de scan d'inventaire reseau qui s'execute a l'intervalle
configure.

## Prerequis

Les outils suivants doivent etre installes dans les containers ou
l'inspection reseau est utilisee :

- **nmap** : Scan reseau (`apt install nmap`)
- **tshark** : Analyse de capture de paquets (`apt install wireshark-common`)

Ces outils ne sont pas installes par le role `openclaw_server` par defaut.
Installez-les manuellement ou via un role personnalise lorsque vous activez
l'inspection reseau.
