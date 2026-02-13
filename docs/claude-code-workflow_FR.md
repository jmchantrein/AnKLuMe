# Flux de Travail Claude Code

> Traduction francaise de [`claude-code-workflow.md`](claude-code-workflow.md). En cas de divergence, la version anglaise fait foi.

Comment travailler efficacement sur AnKLuMe avec Claude Code.

## Demarrer une session

Claude Code lit automatiquement `CLAUDE.md` au demarrage de la session. Pour
un contexte plus approfondi sur une tache specifique, chargez le document pertinent :

```
@docs/SPEC.md           # Specification complete -- formats, roles, architecture
@docs/ARCHITECTURE.md   # ADRs -- decisions que vous ne devez pas contourner
@docs/ROADMAP.md        # Sur quoi travailler ensuite
```

## Cycle de developpement (pilote par la specification et les tests)

1. **Verifier la specification** : Avant d'implementer quoi que ce soit, lisez la
   section pertinente de SPEC.md. Si la specification est manquante ou floue,
   mettez-la a jour d'abord.

2. **Ecrire les tests** : Avant d'ecrire du code, ecrivez les tests :
   - Roles -> test Molecule (`roles/<n>/molecule/default/`)
   - Generateur -> pytest (`tests/test_generate.py`)

3. **Implementer** : Ecrivez le code jusqu'a ce que les tests passent.

4. **Valider** : Executez `make lint` (chaine tous les validateurs).

5. **Revue** : Invoquez l'agent de revue :
   ```
   @.claude/agents/reviewer.md Review the changes in roles/incus_networks/
   ```

6. **Commiter** : Seulement quand `make lint && make test` passent.

## Utiliser les agents

### Architecte
Pour les decisions structurelles, questions de conception, nouveaux ADRs :
```
@.claude/agents/architect.md Should we split incus_instances into
separate roles for LXC and VM, or keep them together?
```

### Reviewer
Avant de commiter, pour les verifications de qualite :
```
@.claude/agents/reviewer.md Review all changes since last commit
```

## Utiliser les skills

Le skill `incus-ansible` est charge automatiquement quand vous travaillez sur
des fichiers dans `roles/`. Il fournit le template du patron de reconciliation
et les commandes Incus courantes.

## Conseils

- **Gardez le contexte concentre** : Chargez uniquement ce qui est pertinent pour la tache en cours.
- **Utilisez des sous-agents pour des taches distinctes** : Evitez la pollution de contexte.
- **Executez `make lint` frequemment** : Detectez les problemes tot.
- **Consultez ROADMAP.md** : Sachez dans quelle phase vous etes.
