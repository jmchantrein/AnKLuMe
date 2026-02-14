# Guide Interactif de Demarrage

> Traduction francaise de [`guide.md`](guide.md). En cas de divergence, la version anglaise fait foi.

AnKLuMe inclut un guide interactif etape par etape qui vous accompagne
dans la mise en place de votre infrastructure depuis zero.

## Utilisation

```bash
make guide              # Demarrer a l'etape 1
make guide STEP=5       # Reprendre a l'etape 5
make guide AUTO=1       # Mode non-interactif CI
```

Ou executer le script directement :

```bash
scripts/guide.sh
scripts/guide.sh --step 5
scripts/guide.sh --auto
```

## Etapes

| Etape | Nom | Description |
|-------|-----|-------------|
| 1 | Prerequis | Verifie les outils requis (incus, ansible, python3, git, make) |
| 2 | Cas d'usage | Selectionner un exemple pre-construit (etudiant, enseignant, pro, personnalise) |
| 3 | infra.yml | Copier l'exemple et optionnellement l'editer |
| 4 | Generation | Executer `make sync` pour creer les fichiers Ansible |
| 5 | Validation | Executer les linters et les verifications syntaxiques |
| 6 | Application | Creer l'infrastructure Incus (`make apply`) |
| 7 | Verification | Lister les instances et reseaux en cours d'execution |
| 8 | Snapshot | Creer un snapshot initial pour le rollback |
| 9 | Prochaines etapes | Liens vers les fonctionnalites avancees et la documentation |

## Mode automatique

Le flag `--auto` execute toutes les etapes de maniere non-interactive :

- Selectionne l'option 1 pour toutes les questions
- Saute les etapes necessitant un daemon Incus actif (etapes 6-8)
- Quitte immediatement en cas d'echec
- Utile pour les tests CI de fumee

## Reprise

Chaque etape est independante. Si le guide se termine ou si vous
appuyez sur Ctrl+C, reprenez la ou vous en etiez :

```bash
make guide STEP=4    # Reprendre a l'etape 4
```

## Depannage

### "incus not found"

Installez Incus en suivant la documentation officielle :
https://linuxcontainers.org/incus/docs/main/installing/

### "make sync failed"

Verifiez `infra.yml` pour les erreurs de syntaxe. Problemes courants :
- Noms de machines dupliques
- Identifiants de sous-reseau (subnet_id) dupliques
- IPs en dehors du sous-reseau declare

Executez `make sync-dry` pour previsualiser sans ecrire.

### "Cannot connect to Incus"

Les etapes 6-8 necessitent un daemon Incus actif. Soit :
- Executez depuis une machine avec Incus installe et initialise
- Executez depuis le conteneur admin avec le socket Incus monte
- Sautez ces etapes et executez `make apply` manuellement plus tard

### L'editeur ne s'ouvre pas

Le guide utilise `$EDITOR` ou `$VISUAL` (par defaut `vi`).
Definissez votre editeur prefere :

```bash
export EDITOR=nano
make guide STEP=3
```
