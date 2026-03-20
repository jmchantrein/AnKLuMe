---
name: catchup
description: Rattraper le contexte après un /clear — lit ROADMAP, git diff, fichiers modifiés
disable-model-invocation: true
user-invocable: true
---

Protocole de rattrapage après /clear :

1. Lire `docs/ROADMAP.md` pour l'état courant et les priorités
2. Exécuter `git diff HEAD` et `git log --oneline -10`
3. Si des fichiers non commités existent, les lire et analyser
4. Si CLAUDE.md a changé depuis le dernier commit, relire les sections modifiées
5. Résumer à l'utilisateur :
   - Phase courante du ROADMAP
   - Modifications non commitées détectées
   - Prochaine action proposée
