# Decisions de traduction -- Synchronisation FR

Ce document recense les decisions prises lors de la synchronisation
des traductions francaises avec les documents anglais de reference.

## Fichiers mis a jour

| Fichier | Nature des modifications |
|---------|------------------------|
| `docs/SPEC_FR.md` | Reecriture complete. Mise a jour des sections 1-5 (vision etendue, convention d'adressage ADR-038, directives enabled/ephemeral, boot_autostart, snapshots automatiques, nesting prefix, niveaux de confiance, politiques reseau, allocation de ressources, volumes partages, infra.yml en repertoire, politique de securite, auto-creation sys-firewall, contraintes de validation etendues). Suppression des sections 6-12 (deplacees vers SPEC-operations.md en anglais). |
| `docs/ARCHITECTURE_FR.md` | Mise a jour de ADR-004 (titre et contenu modifies), ADR-009 (matrice comportementale, tests BDD, Hypothesis), ADR-010 (dependances de qualite autorisees), ADR-012 (reference a SPEC-operations.md), ADR-013 (ajout role Ansible + historique), ADR-017/018/019 (references mises a jour). Suppression de ADR-007 (retire de la version EN). Ajout de ADR-020 a ADR-040 (16 nouvelles ADR). |
| `README_FR.md` | Mise a jour de la plage ADR dans le tableau de documentation (ADR-036 -> ADR-040). |
| `docs/desktop-integration_FR.md` | Reecriture complete. Ajout des sections manquantes : fonctionnement du presse-papier, variables d'environnement, mode terminal, configuration Sway/i3 detaillee, profils foot, entrees .desktop, endpoints API du dashboard, securite du dashboard, schema de couleurs complet. |
| `docs/sys-print_FR.md` | Mise a jour importante. Ajout des details de la commande setup (4 etapes), section interface web CUPS, passthrough USB (points cles, recherche IDs, retrait), acces imprimante reseau via macvlan (avantages/limitations), sections depannage manquantes. Mise a jour de l'exemple infra.yml (suppression de base_subnet/subnet_id/ip obsoletes au profit du mode addressing). |
| `docs/scenario-testing_FR.md` | Mise a jour. Ajout de la section complete des steps disponibles (Given/When/Then), reference a `scripts/matrix-coverage.py`, mention de pyproject.toml pour les dependances, details Phase 18e pour le pre-cache d'images. |

## Termes techniques gardes en anglais

Ces termes sont gardes en anglais car ils sont soit des noms propres
de logiciels, soit des termes techniques standard sans equivalent
francais etabli :

| Terme | Justification |
|-------|--------------|
| Ansible, Incus, Molecule, pytest | Noms de logiciels |
| PSOT, YAML, JSON, CLI | Acronymes techniques standard |
| bridge, socket, daemon | Termes reseau/systeme universels |
| container, snapshot, profile | Terminologie Incus officielle |
| playbook, role, tag, host_vars, group_vars | Terminologie Ansible |
| nftables, NAT, DHCP, IOMMU, SR-IOV | Protocoles/technologies reseau |
| GPU, VRAM, LXC, KVM, VM | Acronymes materiels/virtualisation |
| trust_level, ephemeral, weight | Champs infra.yml (code) |
| Given/When/Then, Gherkin, BDD | Terminologie de test BDD |
| tmux, foot, Sway, i3, htmx | Noms de logiciels |
| bind mount, passthrough, macvlan | Termes techniques Linux |
| overcommit, ballooning, CFS scheduler | Termes de gestion de ressources |
| CUPS, IPP, mDNS/Bonjour | Protocoles d'impression |
| upstream, framework, bootstrap | Termes de developpement logiciel |

## Termes techniques traduits

| Anglais | Francais | Note |
|---------|----------|------|
| host | hote | Terme standard en francais |
| instance | instance | Identique en francais |
| domain | domaine | Terme standard |
| subnet | sous-reseau | Terme reseau standard |
| gateway | passerelle | Terme reseau standard |
| forwarding | transfert / forwarding | Selon contexte |
| addressing | adressage | Terme reseau standard |
| nesting | imbrication | Terme technique francais |
| provisioning | provisionnement | Usage informatique courant |
| device | peripherique | Terme materiel standard |
| orphan | orphelin | Terme technique |
| reconciliation | reconciliation | Identique |
| idempotency | idempotence | Terme mathematique francais |
| consumer | consommateur | Terme technique |
| shift (idmap) | shifting | Garde en anglais (terme Incus) |

## Sections posant des questions de traduction

### 1. SPEC.md -- Titres des sous-sections infra.yml

Les titres comme "Addressing convention", "Enabled directive",
"Ephemeral directive" sont des references directes aux champs YAML.
Decision : traduire le titre descriptif mais garder le nom du champ
en anglais (ex. "Convention d'adressage (ADR-038)", "Directive enabled",
"Directive ephemere").

### 2. ARCHITECTURE.md -- Titres des ADR

Les titres des ADR contiennent souvent des termes techniques mixtes.
Decision : traduire la partie descriptive, garder les termes techniques
(ex. "ADR-022 : Priorite nftables -1 -- coexistence avec les chaines
Incus").

### 3. Exemples de code et configuration

Decision conforme a CLAUDE.md : les exemples YAML, les blocs de code
shell, et les extraits de configuration ne sont PAS traduits. Les
commentaires dans les exemples sont gardes en anglais pour correspondre
au code reel.

### 4. Sections 6-12 de SPEC_FR.md

L'ancienne SPEC_FR.md contenait des sections 6 a 12 (generateur, roles,
snapshots, validateurs, workflow de developpement, pile technique, hors
perimetre) qui n'existent plus dans la SPEC.md anglaise -- elles ont
ete deplacees vers SPEC-operations.md. Decision : supprimer ces sections
de SPEC_FR.md et ajouter la reference vers SPEC-operations.md, comme
dans la version anglaise. Une traduction de SPEC-operations.md
(SPEC-operations_FR.md) pourra etre ajoutee ulterieurement.

### 5. Fichiers EN sans equivalent FR

Les fichiers suivants n'ont pas de traduction francaise :
- `docs/SPEC-operations.md`
- `docs/addressing-convention.md`
- `docs/live-os.md`
- `docs/parallel-prompts.md`
- `docs/tor-gateway.md`
- `docs/vm-support.md`

Ces traductions pourront etre ajoutees dans un prochain cycle de
synchronisation.
