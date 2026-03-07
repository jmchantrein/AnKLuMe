# Décisions d'architecture

Chaque décision est numérotée et définitive sauf indication contraire.

## ADR-002 : PSOT stateless — réconciliation sans state file

Les fichiers `domains/*.yml` décrivent l'infrastructure de manière
déclarative. `anklume apply` lit ces fichiers et pilote Incus
directement via Python + `incus` CLI.

**Source de vérité primaire** : `domains/*.yml` (état désiré)
**Source de vérité secondaire** : Incus (état réel)

`anklume apply` réconcilie les deux : interroge Incus via
`incus list/network list --format json`, compare avec le YAML,
applique les différences. Pas de state file.

Python gère la création d'infrastructure (projets, réseaux, instances).
Ansible gère le provisioning (installation de logiciels dans les instances).

## ADR-003 : La CLI est la seule interface

Pas de Makefile. Toute opération est une commande Typer.
`anklume <nom> <verbe>` pour tout, avec autocomplétion à tous
les niveaux de profondeur.

## ADR-004 : Exécution directe sur l'hôte

La CLI tourne directement sur l'hôte. Dépendances gérées par `uv`.
Incus et Ansible sont appelés via `subprocess`.
Sur la Live ISO, tout est pré-installé dans le squashfs.

## ADR-005 : Incus via subprocess + CLI

`subprocess` + `incus` CLI + `--format json` + vérifications
d'idempotence manuelles.

Pas de bibliothèque Python pour Incus : `pylxd` cible LXD et
ne garantit pas la compatibilité Incus. La communauté Incus
recommande l'usage de la CLI ou de l'API REST directement.

Le code subprocess est encapsulé dans `engine/incus_driver.py`
avec un contrat typé (dataclasses/TypedDict), pour isoler le code
métier du parsing CLI. Le reste du moteur utilise ce driver,
jamais `subprocess` directement.

## ADR-006 : Adressage IP par niveau de confiance

Les adresses IP encodent les zones de confiance dans le deuxième
octet : `10.<zone_base + zone_offset>.<domain_seq>.<host>/24`

IPs lisibles par un humain. Depuis `10.140.0.5`, on sait :
zone 140 = 100+40 = untrusted.

## ADR-007 : Isolation réseau par défaut

Tout le trafic inter-domaines est bloqué par nftables. Les exceptions
sont déclarées dans `policies.yml`.

Sécurisé par défaut, autorisation sélective.

`bidirectional` contrôle l'initiation de connexion : `false` = seul
`from` peut initier, `true` = initiation dans les deux sens.

## ADR-009 : KDE Plasma uniquement

L'intégration desktop cible exclusivement KDE Plasma sur Wayland.

## ADR-010 : Noms de machines globalement uniques

Les noms de machines (après auto-préfixage par le domaine) sont
globalement uniques. Le moteur valide cette contrainte.

## ADR-011 : Protection ephemeral

`ephemeral: false` (défaut) met `security.protection.delete=true`
sur les instances Incus. `anklume destroy` ignore les instances
protégées sauf avec `--force`.

## ADR-013 : Domaines docker-compose-like

Chaque domaine est un fichier YAML autonome dans `domains/`. Le nom
du fichier est le nom du domaine. Les noms courts des machines sont
auto-préfixés avec le nom du domaine.

## ADR-014 : Python pour le core, Bash pour le système

Python (Typer, PyYAML, FastAPI) pour toute la logique métier.
Bash uniquement pour les scripts de boot et l'intégration système
(Live ISO, systemd, hooks).

## ADR-015 : Pas d'étape sync intermédiaire

`anklume apply` lit les fichiers domaine et pilote Incus directement.
Pas de génération de fichiers Ansible intermédiaires visibles.

Ansible reste pour le provisioning (installation de paquets,
configuration de services à l'intérieur des instances). Le moteur
génère les fichiers Ansible en mémoire et les exécute.

## ADR-016 : Installation par git clone

anklume s'installe par `git clone` + `uv sync`. Le `.gitignore`
protège les fichiers utilisateur (projets créés par `anklume init`).

## ADR-017 : Environnement de développement intégré

`anklume dev setup` prépare un environnement complet pour développer
anklume lui-même : vérification du nesting Incus, installation des
dépendances dev, hooks git, conteneur de test éphémère.

Le développement du framework et son utilisation partagent le même
dépôt. Le `.gitignore` sépare les concerns.

## ADR-018 : Live ISO = OS immuable avec persistance chiffrée

La Live ISO est le mode de déploiement principal d'anklume :
un OS immuable (squashfs en RAM) avec persistance des données
sur volume chiffré (ZFS/BTRFS).

**Conséquences sur le core** :
- Chemins de données configurables
- Storage Incus sur le volume chiffré
- `anklume apply all` idempotent (survit aux redémarrages)
- Compatible avec tout mode de boot (installé ou live)

## ADR-019 : Nesting Incus avec préfixes

En environnement nesté (conteneur dans conteneur), les ressources
Incus sont préfixées par le niveau de profondeur (`{level:03d}-`)
pour éviter les collisions de noms.

4 fichiers de contexte dans `/etc/anklume/` propagent l'information
de nesting entre les niveaux : `absolute_level`, `relative_level`,
`vm_nested`, `yolo`.

Sécurité : L1 unprivileged avec `security.nesting=true`, L2+
privilegié dans unprivileged (safe, recommandation stgraber).

## ADR-020 : Resource policy — allocation par poids

Les ressources CPU/mémoire sont distribuées automatiquement aux
instances selon leur `weight`, après réserve pour l'hôte.

Modes : `proportional` (par poids) ou `equal` (parts égales).
Les machines avec des limites explicites sont exclues de
l'auto-allocation. Overcommit optionnel (warning vs erreur).

## ADR-021 : Snapshots automatiques

`anklume apply` crée des snapshots avant et après chaque modification
d'instance (pré-apply / post-apply). Les snapshots manuels sont
aussi disponibles via `anklume snapshot`.

Permet le rollback en cas de problème sans state file :
l'état précédent est dans les snapshots Incus.

## ADR-022 : Dry-run sur les commandes existantes

`--dry-run` est un flag sur `anklume apply`, pas une commande
séparée. Affiche le plan de réconciliation (créations,
modifications, suppressions) sans appliquer.

## ADR-023 : Schema versioning

`schema_version` (entier) dans `anklume.yml` versionne le format
des fichiers. Chaque version a une fonction de migration.
`anklume apply` vérifie et propose la migration automatique.
Approche minimaliste : un entier incrémental, pas de semver.
