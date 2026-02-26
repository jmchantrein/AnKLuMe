# Analyse statique du code

> **Note** : La version anglaise (`code-analysis.md`) fait foi en cas
> de divergence.

anklume fournit des outils d'analyse statique pour la detection de
code mort, la generation de graphes d'appels et la visualisation des
dependances entre modules.

## Demarrage rapide

```bash
anklume dev graph --type dead    # Detection de code mort (Python + Shell)
anklume dev graph --type call   # Graphe d'appels Python (DOT + SVG)
anklume dev graph --type dep    # Graphe de dependances entre modules (SVG)
anklume dev graph --type code   # Executer tous les outils d'analyse
```

## Outils

### Detection de code mort (`anklume dev graph --type dead`)

Detecte le code inutilise dans les fichiers Python et Shell :

- **Python** : [vulture](https://github.com/jendrikseipp/vulture)
  analyse `scripts/` et `tests/` pour trouver les fonctions,
  variables, imports et classes inutilises. Utilise
  `--min-confidence 80` pour reduire les faux positifs.
- **Shell** : [ShellCheck](https://www.shellcheck.net/) regle SC2034
  detecte les variables inutilisees dans `scripts/*.sh`.

Les resultats sont **informatifs** — vulture peut signaler des faux
positifs pour les fixtures pytest, les fonctions appelees
dynamiquement et les parametres de methodes abstraites. Verifiez
manuellement avant de supprimer du code.

### Graphe d'appels (`anklume dev graph --type call`)

Genere un graphe d'appels des fonctions Python dans `scripts/`.
Le resultat est sauvegarde dans `reports/call-graph.dot` (format
GraphViz DOT) et `reports/call-graph.svg` (si graphviz est installe).

Utilise [pyan3](https://github.com/Technologicat/pyan) quand
disponible, avec un repli base sur l'AST pour la compatibilite avec
les versions recentes de Python.

### Graphe de dependances (`anklume dev graph --type dep`)

Genere un graphe de dependances entre modules avec
[pydeps](https://github.com/thebjorn/pydeps). Le resultat est
sauvegarde dans `reports/dep-graph.svg`. Necessite graphviz.

## Dependances

| Outil | Installation | Requis pour |
|-------|-------------|-------------|
| vulture | `pip install vulture` | `anklume dev graph --type dead` |
| shellcheck | `apt install shellcheck` | `anklume dev graph --type dead` (section shell) |
| pyan3 | `pip install pyan3` | `anklume dev graph --type call` (optionnel, repli AST disponible) |
| pydeps | `pip install pydeps` | `anklume dev graph --type dep` |
| graphviz | `apt install graphviz` | Sortie SVG pour `anklume dev graph --type call` et `anklume dev graph --type dep` |

Le script verifie la presence de chaque outil avant utilisation et
fournit des instructions d'installation claires si absent.

## Sortie

Les rapports sont generes dans le repertoire `reports/` (gitignore) :

```
reports/
├── call-graph.dot   # Source GraphViz DOT
├── call-graph.svg   # Visualisation du graphe d'appels (si graphviz installe)
└── dep-graph.svg    # Graphe de dependances entre modules (si graphviz installe)
```

Utilisez `--output-dir` pour changer le repertoire de sortie :

```bash
scripts/code-analysis.sh call-graph --output-dir /tmp/mes-rapports
```

## Integration CI

Le job `dead-code` s'execute en CI comme verification
**informative et non bloquante** (`continue-on-error: true`). Il
signale les decouvertes sans faire echouer le pipeline, car la
detection de code mort comporte des faux positifs inherents.

## Utilisation du script

```bash
scripts/code-analysis.sh <sous-commande> [options]

Sous-commandes :
  dead-code   Detection de code mort
  call-graph  Generation du graphe d'appels Python
  dep-graph   Generation du graphe de dependances entre modules
  all         Executer tous les outils d'analyse

Options :
  --output-dir DIR   Repertoire de sortie pour les rapports (defaut : reports/)
  --help             Afficher l'aide
```

## Limitations

- **Faux positifs de vulture** : les fixtures pytest, les methodes
  `__init__` et les fonctions appelees dynamiquement sont souvent
  signalees comme inutilisees. Verifiez soigneusement avant de
  supprimer.
- **Compatibilite pyan3** : pyan3 peut ne pas fonctionner avec
  Python 3.13+. Le script bascule automatiquement sur l'analyse AST.
- **pydeps** : necessite que le projet soit structure comme un
  package Python. Peut echouer sur des scripts autonomes.
- **graphviz** : necessaire pour la sortie SVG. Sans lui, seuls les
  fichiers DOT sont generes pour les graphes d'appels.
