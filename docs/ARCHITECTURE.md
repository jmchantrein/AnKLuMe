# Décisions d'architecture

Chaque décision est numérotée et définitive sauf indication contraire.

## ADR-001 : anklume est un outil installé, pas un dépôt cloné

L'utilisateur installe anklume (`pip install anklume`) et lance
`anklume init` pour créer un répertoire projet. Le framework et
l'infrastructure utilisateur sont entièrement séparés.

**Pourquoi** : Le POC mélangeait les fichiers du framework avec
l'infrastructure utilisateur. Cela causait de la confusion
(quel `infra.yml` ?), des conflits lecture seule (squashfs sur
Live ISO), et du couplage entre mises à jour et configuration.

**Conséquence** : `anklume init` scaffolde un projet autonome.
Les rôles sont résolus depuis le package installé. `roles_custom/`
pour les rôles utilisateur. Mises à jour via `pip install --upgrade`.

## ADR-002 : PSOT — les domaines sont la source de vérité

Les fichiers `domains/*.yml` décrivent l'infrastructure de manière
déclarative. `anklume apply` lit ces fichiers et pilote Incus
directement via Python + `incus` CLI.

**Changement vs POC** : Plus d'étape `sync`, plus de fichiers
Ansible intermédiaires (inventory, group_vars, host_vars). Python
crée les ressources Incus directement. Ansible est utilisé
uniquement pour le provisioning (installation de logiciels dans
les instances).

## ADR-003 : La CLI est la seule interface

Pas de Makefile. Toute opération est une commande Typer.

**Pourquoi** : Le POC avait trois couches (CLI Python → Makefile →
scripts bash). Chaque bug nécessitait un débogage sur trois niveaux.

**Conséquence** : `anklume <nom> <verbe>` pour tout. Le développement
sous `anklume dev`. Les scripts sont appelés par la CLI, jamais
directement par l'utilisateur.

## ADR-004 : Délégation transparente à anklume-instance

La CLI détecte si elle tourne sur l'hôte ou dans un conteneur.
Les commandes hôte nécessitant Incus/Ansible sont déléguées de
manière transparente à `anklume-instance` via `incus exec`.

**Pourquoi** : Le POC exigeait de l'utilisateur qu'il entre
manuellement dans anklume-instance. C'était déroutant.

## ADR-005 : Incus via CLI, pas de modules Ansible natifs

`subprocess` + `incus` CLI + `--format json` + vérifications
d'idempotence manuelles.

**Raison** : Aucun module Ansible `incus_*` stable n'existe.

## ADR-006 : Adressage IP par niveau de confiance

Les adresses IP encodent les zones de confiance dans le deuxième
octet : `10.<zone_base + zone_offset>.<domain_seq>.<host>/24`

**Conservé du POC** : IPs lisibles par un humain. Depuis `10.140.0.5`,
on sait : zone 140 = 100+40 = untrusted.

## ADR-007 : Isolation réseau par défaut

Tout le trafic inter-domaines est bloqué par nftables. Les exceptions
sont déclarées dans `policies.yml`.

**Conservé du POC** : Sécurisé par défaut, autorisation sélective.

## ADR-008 : La Live ISO est un concern séparé

La Live ISO (`live/`) est un produit éducatif construit au-dessus
d'anklume. Elle n'est pas requise pour l'utilisation normale.

**Pourquoi** : Le POC mélangeait scripts de boot, configs desktop,
plateforme web et code du framework dans les mêmes répertoires.

## ADR-009 : KDE Plasma uniquement

Pas de sway, pas de labwc. L'intégration desktop cible KDE Plasma
sur Wayland.

**Pourquoi** : Le POC maintenait des configs pour sway, labwc et KDE.
Seul KDE était réellement testé et utilisé.

## ADR-010 : Noms de machines globalement uniques

Les noms de machines (après auto-préfixage par le domaine) sont
globalement uniques. Le moteur valide cette contrainte.

## ADR-011 : Protection ephemeral

`ephemeral: false` (défaut) met `security.protection.delete=true`
sur les instances Incus. `anklume destroy` ignore les instances
protégées sauf avec `--force`.

## ADR-012 : Serveur web sur l'hôte pour la plateforme d'apprentissage

La plateforme d'apprentissage tourne sur l'hôte, pas dans un
conteneur. Elle sert du contenu en lecture seule avec un terminal
(ttyd) qui se connecte au shell hôte.

## ADR-013 : Domaines docker-compose-like

Chaque domaine est un fichier YAML autonome dans `domains/`. Le nom
du fichier est le nom du domaine. Les noms courts des machines sont
auto-préfixés avec le nom du domaine.

**Pourquoi** : Le `infra.yml` monolithique du POC devenait difficile
à lire au-delà de 3-4 domaines. Le format par fichier est plus
familier aux utilisateurs de docker-compose et facilite le travail
collaboratif (un fichier par personne, moins de conflits git).

## ADR-014 : Python pour le core, Bash pour le système

Python (Typer, PyYAML, FastAPI) pour toute la logique métier.
Bash uniquement pour les scripts de boot et l'intégration système
(Live ISO, systemd, hooks).

**Pourquoi** : Python offre la meilleure qualité de génération par
LLM, l'écosystème le plus riche pour CLI/web/YAML, et l'itération
la plus rapide. Go serait l'alternative (binaire unique), mais
anklume tourne sur des machines Linux avec Python déjà installé.

## ADR-015 : Pas d'étape sync intermédiaire

`anklume apply` lit les fichiers domaine et pilote Incus directement.
Pas de génération de fichiers Ansible intermédiaires.

**Pourquoi** : L'étape `sync` du POC ajoutait une couche sans valeur.
L'utilisateur devait comprendre les fichiers générés, les sections
gérées, et quand relancer sync. La suppression simplifie le modèle
mental : éditer les domaines → apply → c'est déployé.

**Ansible reste** pour le provisioning (installation de paquets,
configuration de services à l'intérieur des instances). Mais
l'utilisateur n'interagit pas avec les fichiers Ansible — le moteur
les génère en mémoire et les exécute.
