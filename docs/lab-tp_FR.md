# Guide de Deploiement de TP pour Enseignants

> Traduction francaise de [`lab-tp.md`](lab-tp.md). En cas de divergence, la version anglaise fait foi.

Ce guide explique comment utiliser anklume pour deployer des TPs reseau
pour les etudiants. Chaque etudiant obtient un domaine isole avec son propre
sous-reseau, projet Incus et ensemble de containers.

## Concept : un domaine par etudiant

Le modele de domaine d'anklume s'adapte naturellement aux deploiements de TP :

```
domaine admin       = environnement de gestion de l'enseignant
domaine student-01  = TP isole de l'etudiant 1
domaine student-02  = TP isole de l'etudiant 2
...
domaine student-N   = TP isole de l'etudiant N
```

Chaque domaine etudiant :
- Possede son propre reseau isole (`net-student-XX`)
- Ne peut pas communiquer avec les autres domaines etudiants
- Peut etre snapshot, restaure ou detruit independamment
- Est marque `ephemeral: true` pour un nettoyage facile

## Etape 1 : Concevoir votre infra.yml

Utilisez l'exemple [teacher-lab](../examples/teacher-lab/) comme point
de depart :

```bash
cp examples/teacher-lab/infra.yml infra.yml
```

L'exemple comprend 1 domaine admin + 3 domaines etudiants, chacun avec un
serveur web et un container client. Conventions de nommage :

- Prefixe de nom de machine par etudiant : `s01-web`, `s02-web`, etc.
  (globalement uniques comme requis par l'ADR-008)
- Noms de domaine : patron `student-XX`
- subnet_id incremente par etudiant (1, 2, 3, ...)

## Etape 2 : Deployer

```bash
make sync    # Generer les fichiers Ansible
make check   # Previsualiser les changements
make apply   # Tout creer
```

Pour une classe de 30 etudiants avec 2 containers chacun, cela cree :
- 31 domaines (1 admin + 30 etudiants)
- 31 reseaux
- 61 containers (1 admin + 60 containers etudiants)

## Etape 3 : Snapshots pre-TP

Avant que les etudiants ne commencent a travailler, prenez un snapshot de l'etat propre :

```bash
make snapshot NAME=pre-lab
```

Cela prend un snapshot de chaque instance dans tous les domaines. Vous pouvez
aussi prendre un snapshot d'un seul domaine etudiant :

```bash
make snapshot-domain D=student-01 NAME=pre-lab
```

## Isolation reseau

Chaque domaine etudiant a son propre bridge reseau. Par defaut, les containers
au sein d'un domaine peuvent communiquer entre eux, mais le trafic inter-domaines
est bloque (lorsque les regles nftables sont configurees, voir Phase 8 dans
[ROADMAP.md](ROADMAP.md)).

Cela signifie :
- Le serveur web de l'etudiant 1 peut communiquer avec le client de l'etudiant 1
- L'etudiant 1 ne peut pas acceder aux containers de l'etudiant 2
- Le domaine admin peut atteindre tous les etudiants (pour la gestion)

## Reinitialisation entre les sessions

### Reinitialiser un seul etudiant

Restaurer le snapshot pre-TP pour un etudiant :

```bash
make restore-domain D=student-05 NAME=pre-lab
```

### Reinitialiser tous les etudiants

Restaurer le snapshot pre-TP globalement :

```bash
make restore NAME=pre-lab
```

### Destruction et reconstruction complete

Puisque les domaines etudiants sont `ephemeral: true`, vous pouvez les detruire
et les recreer. Retirez le domaine d'`infra.yml`, executez `make sync
--clean-orphans`, puis re-ajoutez-le et `make apply`.

## Mise a l'echelle

### Ajouter un etudiant

Ajoutez un nouveau bloc de domaine dans `infra.yml` avec le prochain `subnet_id`
et des noms de machine uniques, puis executez `make sync && make apply-limit
G=student-04`.

### Retirer un etudiant

Retirez le domaine d'`infra.yml` et executez `make sync-clean`. Les ressources
Incus doivent etre detruites separement via le CLI `incus`.

## Exigences materielles

A titre indicatif pour des containers LXC avec `base_system` :

| Etudiants | Containers | RAM (est.) | Disque (est.) |
|-----------|-----------|------------|---------------|
| 10 | 21 | 8 Go | 20 Go |
| 20 | 41 | 16 Go | 40 Go |
| 30 | 61 | 24 Go | 60 Go |

Vous pouvez limiter les ressources par etudiant en utilisant `config.limits.cpu` et
`config.limits.memory` dans la definition de la machine.

## Acces etudiant

Les etudiants accedent aux containers via `incus exec s01-web --project student-01
-- bash` (depuis l'hote ou le container d'administration).

## Conseils

- Utilisez `ephemeral: true` pour tous les domaines etudiants pour un nettoyage facile
- Prenez des snapshots avant chaque session de TP
- Utilisez `make apply-limit G=student-XX` pour reconstruire un seul etudiant

## Exemples de configurations

Consultez le repertoire [examples](../examples/) pour des configurations de TP
pretes a l'emploi :

- [teacher-lab](../examples/teacher-lab/) -- admin + 3 domaines etudiants
- [student-sysadmin](../examples/student-sysadmin/) -- configuration simple
  a 2 domaines pour etudiants administrateurs systeme
