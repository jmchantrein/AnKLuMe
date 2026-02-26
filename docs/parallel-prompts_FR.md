# Prompts pour implementations paralleles — Claude Code Web

> Traduction francaise de [`parallel-prompts.md`](parallel-prompts.md). En cas de divergence, la version anglaise fait foi.

Chaque prompt est a copier-coller dans une instance Claude Code web separee.
Chaque instance travaille sur sa propre branche.
Les branches sont independantes (pas de conflit de merge).

Workflow :
1. Ouvrir le repo dans Claude Code web
2. Copier-coller le prompt
3. Laisser l'IA travailler de facon autonome
4. Quand c'est fini, review le DECISIONS.md a la racine
5. Merger la branche dans main

---

## Branche 1 : `feat/matrix-boot-snapshots`

**Fichiers touches** : `tests/test_spec_features.py`, `tests/behavior_matrix.yml` (lecture seule)
**Conflit avec** : aucune autre branche

```
Tu travailles sur le projet AnKLuMe. Lis CLAUDE.md, docs/SPEC.md et docs/ARCHITECTURE.md pour comprendre le contexte.

Ta mission : combler les trous de la behavior matrix pour les capabilities boot_autostart et snapshots_config.

Etapes :
1. `git checkout -b feat/matrix-boot-snapshots`
2. Lis tests/behavior_matrix.yml pour comprendre les cellules manquantes :
   - boot_autostart : BA-004, BA-005, BA-006 (depth 1), BA-2-001, BA-2-002 (depth 2), BA-3-001 (depth 3)
   - snapshots_config : SN-004, SN-005, SN-006 (depth 1), SN-2-001 (depth 2), SN-3-001 (depth 3)
3. Lis tests/test_spec_features.py pour comprendre les patterns existants (classes TestBootAutostart et TestSnapshotsConfig)
4. Ecris les tests manquants en suivant EXACTEMENT les patterns existants :
   - Chaque test a un commentaire `# Matrix: XX-NNN`
   - Les tests depth 1 manquants sont des tests de VALIDATION (valeurs invalides, erreurs attendues)
   - Les tests depth 2 testent les INTERACTIONS entre features (boot + snapshots, boot + ephemeral, etc.)
   - Les tests depth 3 testent les interactions COMPLEXES (3+ features combinees)
5. Lance les tests : `pip install pytest pyyaml hypothesis && python -m pytest tests/test_spec_features.py -v`
6. Lance le linter : `pip install ruff && ruff check tests/test_spec_features.py`
7. Verifie la couverture : `python3 scripts/matrix-coverage.py`

Contraintes :
- NE MODIFIE PAS generate.py, les roles, ou les docs
- NE MODIFIE PAS les tests existants, AJOUTE seulement
- Chaque test doit avoir le commentaire # Matrix: correspondant
- Utilise _base_infra() et les helpers existants du fichier

A la fin, cree un fichier DECISIONS.md a la racine avec :
- Liste de chaque test ajoute et ce qu'il verifie
- Decisions prises (ex: "J'ai choisi de tester boot_priority=-1 comme valeur invalide car SPEC dit 0-100")
- Questions ou incertitudes pour review humaine

Commit final : `feat(tests): add depth 2-3 matrix tests for boot_autostart and snapshots_config`
```

---

## Branche 2 : `feat/matrix-nesting-resource`

**Fichiers touches** : `tests/test_spec_features.py` (sections differentes de branche 1)
**Conflit avec** : potentiellement branche 1 si les deux ajoutent a la fin du fichier

```
Tu travailles sur le projet AnKLuMe. Lis CLAUDE.md, docs/SPEC.md et docs/ARCHITECTURE.md pour comprendre le contexte.

Ta mission : combler les trous de la behavior matrix pour les capabilities nesting_prefix et resource_policy.

Etapes :
1. `git checkout -b feat/matrix-nesting-resource`
2. Lis tests/behavior_matrix.yml pour comprendre les cellules manquantes :
   - nesting_prefix : NX-004, NX-005 (depth 1), NX-2-001, NX-2-002 (depth 2), NX-3-001 (depth 3)
   - resource_policy : RP-2-001, RP-2-002 (depth 2), RP-3-001 (depth 3)
3. Lis tests/test_spec_features.py pour comprendre les patterns :
   - TestNestingPrefix (autour de la ligne 305)
   - TestResourcePolicyEnrichment (autour de la ligne 425)
4. Ecris les tests manquants :
   - NX depth 1 : tests de validation (nesting_prefix non-booleen, etc.)
   - NX depth 2 : interactions nesting + shared_volumes, nesting + addressing
   - RP depth 2 : resource_policy + explicit config override, multi-domain weights
   - RP depth 3 : resource_policy + nesting + GPU
   IMPORTANT : pour les tests resource_policy qui ont besoin de _mock_host(),
   regarde le pattern existant avec unittest.mock.patch pour mocker _detect_host_resources()
5. Lance les tests : `pip install pytest pyyaml hypothesis && python -m pytest tests/test_spec_features.py -v`
6. Lance le linter : `pip install ruff && ruff check tests/test_spec_features.py`
7. Verifie la couverture : `python3 scripts/matrix-coverage.py`

Contraintes :
- NE MODIFIE PAS generate.py, les roles, ou les docs
- Ajoute les tests NX dans la section Nesting existante, les RP dans la section Resource existante
- Ne rajoute PAS de code a la toute fin du fichier (pour eviter les conflits avec la branche 1)

A la fin, cree un fichier DECISIONS.md a la racine avec :
- Liste de chaque test ajoute et ce qu'il verifie
- Decisions prises sur les combinaisons de features testees
- Questions ou incertitudes pour review humaine

Commit final : `feat(tests): add depth 2-3 matrix tests for nesting_prefix and resource_policy`
```

---

## Branche 3 : `feat/make-help-categories`

**Fichiers touches** : `Makefile`, `tests/test_makefile.py`, `scripts/llm-bench.sh`
**Conflit avec** : aucune autre branche

```
Tu travailles sur le projet AnKLuMe. Lis CLAUDE.md et docs/ROADMAP.md (section Phase 32) pour comprendre le contexte.

Ta mission : restructurer `anklume --help` pour afficher les targets groupees par categorie, et corriger le bug warn() dans llm-bench.sh.

Etapes :
1. `git checkout -b feat/make-help-categories`
2. Lis le Makefile complet pour comprendre toutes les targets existantes
3. Lis docs/ROADMAP.md section Phase 32 pour les categories attendues
4. Restructure le target `help` :
   - Affiche les targets groupees par categorie (Getting Started, Core Workflow, Snapshots, AI/LLM, Console, Instance Management, Lifecycle, Development)
   - Chaque categorie a un header en couleur (utilise les variables de couleur existantes du Makefile)
   - Seules les ~28 targets user-facing sont affichees (pas les targets internes)
   - Ajoute un target `help-all` qui affiche TOUT (comportement actuel)
5. Corrige scripts/llm-bench.sh :
   - Le script utilise warn() mais ne la definit pas
   - Ajoute la fonction warn() comme dans les autres scripts (pattern: `warn() { printf "\033[0;33m%s\033[0m\n" "$1"; }`)
6. Mets a jour tests/test_makefile.py :
   - Le test test_help_groups_targets doit verifier que les categories apparaissent dans la sortie
   - Ajoute un test pour help-all
7. Lance les validations :
   - `pip install pytest pyyaml && python -m pytest tests/test_makefile.py -v`
   - `shellcheck scripts/llm-bench.sh`

Contraintes :
- Garde la retrocompatibilite : `anklume --help` doit toujours fonctionner
- Ne change PAS le comportement des targets existantes
- Les noms de categories doivent correspondre au ROADMAP

A la fin, cree un fichier DECISIONS.md a la racine avec :
- Mapping complet target -> categorie
- Decisions sur quelles targets sont "user-facing" vs "internes"
- Screenshots ou copie de la sortie de `anklume --help`

Commit final : `feat(ux): categorized anklume --help with color-coded groups`
```

---

## Branche 4 : `feat/sys-firewall-rename`

**Fichiers touches** : `scripts/generate.py`, `tests/test_generate.py`, `docs/SPEC.md`, `docs/ARCHITECTURE.md`, `examples/`
**Conflit avec** : aucune des branches 1-3

```
Tu travailles sur le projet AnKLuMe. Lis CLAUDE.md, docs/SPEC.md et docs/ROADMAP.md (section Phase 36) pour comprendre le contexte.

Ta mission : renommer sys-firewall en anklume-firewall dans tout le codebase (Phase 36 du ROADMAP).

Contexte : sys-firewall est auto-cree par le generator quand firewall_mode: vm. Le nom "sys-" est un heritage de QubesOS. La convention AnKLuMe est "anklume-" pour les machines d'infrastructure.

Etapes :
1. `git checkout -b feat/sys-firewall-rename`
2. Cherche TOUTES les occurrences de "sys-firewall" dans le codebase :
   `grep -r "sys-firewall" --include="*.py" --include="*.yml" --include="*.md" --include="*.sh"`
3. Dans scripts/generate.py :
   - Fonction enrich_infra() : remplace "sys-firewall" par "anklume-firewall"
   - Verifie que la validation et les tests de collision sont coherents
4. Dans docs/SPEC.md :
   - Section "Auto-creation of sys-firewall" : renomme en "Auto-creation of anklume-firewall"
   - Mets a jour tous les exemples
5. Dans docs/ARCHITECTURE.md :
   - Mets a jour les references si elles existent
6. Dans tests/test_generate.py :
   - Cherche tous les tests qui referencent "sys-firewall" et remplace
   - Lance les tests pour verifier : `python -m pytest tests/test_generate.py -v -k firewall`
7. Dans examples/ :
   - Mets a jour les infra.yml d'exemple si necessaire
8. Validation finale :
   - `python -m pytest tests/ -v --tb=short`
   - `ruff check scripts/generate.py`

Contraintes :
- C'est un renommage pur : AUCUN changement de comportement
- Si l'utilisateur a deja declare "sys-firewall" explicitement, ca doit toujours fonctionner (sa definition a priorite)
- Le changement ne concerne QUE le nom auto-genere, pas les noms declares par l'utilisateur

A la fin, cree un fichier DECISIONS.md a la racine avec :
- Liste exhaustive de tous les fichiers modifies avec le diff semantique
- Decision sur la retrocompatibilite (doit-on accepter "sys-firewall" comme alias ?)
- Impact sur les utilisateurs existants

Commit final : `refactor(naming): rename sys-firewall to anklume-firewall (Phase 36)`
```

---

## Branche 5 (optionnelle) : `docs/french-sync`

**Fichiers touches** : `docs/*_FR.md` uniquement
**Conflit avec** : aucune branche

```
Tu travailles sur le projet AnKLuMe. Lis CLAUDE.md (section ADR-011) pour comprendre la convention de traduction.

Ta mission : synchroniser les traductions francaises avec les docs anglaises.

Etapes :
1. `git checkout -b docs/french-sync`
2. Pour chaque fichier docs/*.md qui a un equivalent *_FR.md :
   - Compare les deux versions
   - Mets a jour la version FR pour refleter les changements recents de la version EN
3. Fichiers prioritaires (ceux qui ont le plus change recemment) :
   - docs/SPEC.md -> docs/SPEC_FR.md (addressing convention ADR-038)
   - docs/ARCHITECTURE.md -> docs/ARCHITECTURE_FR.md (nouveaux ADRs)
   - README.md -> README_FR.md
4. Chaque fichier FR doit avoir le header :
   > Note : la version anglaise fait reference en cas de divergence.

Contraintes :
- Traduction technique fidele, pas de reformulation creative
- Garder les termes techniques en anglais quand c'est l'usage (Ansible, Incus, PSOT, etc.)
- Ne PAS traduire les exemples de code/YAML
- Ne PAS modifier les fichiers anglais

A la fin, cree un fichier DECISIONS.md a la racine avec :
- Liste des fichiers mis a jour
- Termes techniques gardes en anglais vs traduits
- Sections qui posent des questions de traduction

Commit final : `docs(i18n): sync French translations with latest English docs`
```

---

## Notes pour le merge

Ordre de merge recommande :
1. Branches 1 et 2 (tests) — en premier car elles ne modifient que des tests
2. Branche 3 (anklume --help) — independante
3. Branche 4 (rename) — apres 1+2 car touche generate.py
4. Branche 5 (FR) — en dernier, independante

Apres chaque merge :
- `anklume dev lint && anklume dev test` pour verifier
- Review du DECISIONS.md de la branche
