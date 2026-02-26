# Telemetry locale

> Note : La version anglaise (`telemetry.md`) fait foi en cas de divergence.

anklume inclut une telemetry optionnelle et purement locale pour vous
aider a comprendre vos habitudes d'utilisation. Les donnees ne quittent
jamais votre machine.

## Garanties de confidentialite

- **Par defaut : DESACTIVEE** (modele opt-in)
- **Locale uniquement** : donnees dans `~/.anklume/telemetry/`, aucun appel reseau
- **Inspectable** : vous pouvez `cat ~/.anklume/telemetry/usage.jsonl` a tout moment
- **Supprimable** : `anklume telemetry clear` efface tout
- **Minimale** : seuls le nom de la cible, le domaine, la duree et le code de sortie sont enregistres
- **Pas de donnees personnelles** : aucun nom d'utilisateur, nom d'hote, IP, secret ou contenu de fichier

## Demarrage rapide

```bash
anklume telemetry on       # Activer la telemetry
anklume sync               # Utilisation normale — les evenements sont enregistres
anklume domain apply
anklume telemetry report   # Afficher les graphiques d'utilisation
```

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `anklume telemetry on` | Activer la collecte de telemetry |
| `anklume telemetry off` | Desactiver la telemetry (donnees conservees) |
| `anklume telemetry status` | Afficher l'etat, le nombre d'evenements, la taille du fichier |
| `anklume telemetry clear` | Supprimer toutes les donnees de telemetry |
| `anklume telemetry report` | Graphiques en terminal des habitudes d'utilisation |

## Ce qui est enregistre

Chaque evenement est une ligne JSON dans `~/.anklume/telemetry/usage.jsonl` :

```json
{
  "timestamp": "2026-02-14T10:30:00+00:00",
  "target": "apply",
  "domain": null,
  "duration_seconds": 45.0,
  "exit_code": 0
}
```

| Champ | Description |
|-------|-------------|
| `timestamp` | Horodatage UTC au format ISO 8601 |
| `target` | Nom de la cible Make (ex : `sync`, `apply`, `lint`) |
| `domain` | Argument domaine si `G=<groupe>` a ete passe, sinon `null` |
| `duration_seconds` | Duree en secondes |
| `exit_code` | Code de sortie (0 = succes) |

## Cibles suivies

Les cibles Make suivantes sont instrumentees avec la telemetry lorsqu'elle
est activee :

- `sync` — Generation PSOT
- `apply` — Deploiement complet de l'infrastructure
- `apply-infra` — Infrastructure uniquement
- `apply-provision` — Provisionnement uniquement
- `apply-limit` — Deploiement d'un seul domaine (inclut le domaine dans le log)
- `test-generator` — Tests pytest

Les autres cibles s'executent sans surcharge de telemetry.

## Rapport

`anklume telemetry report` produit des graphiques en terminal montrant :

1. **Invocations par cible** — quelles cibles vous utilisez le plus
2. **Succes vs echec** — taux de succes global
3. **Duree moyenne** — temps moyen par cible

Necessite `plotext` pour l'affichage graphique :

```bash
pip install plotext
```

Sans `plotext`, un affichage textuel de secours est utilise.

## Emplacement des donnees

```
~/.anklume/
└── telemetry/
    ├── enabled        # Fichier marqueur (presence = active)
    └── usage.jsonl    # Journal d'evenements (format JSON Lines)
```

## Utilisation du script

Le script de telemetry peut aussi etre utilise directement :

```bash
python3 scripts/telemetry.py on
python3 scripts/telemetry.py off
python3 scripts/telemetry.py status
python3 scripts/telemetry.py clear
python3 scripts/telemetry.py report
python3 scripts/telemetry.py log --target sync --duration 1.5 --exit-code 0
```
