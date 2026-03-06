# Plan: Premier boot tout-en-web

## Context

Le premier démarrage de l'ISO anklume a deux parcours parallèles
qui font doublon : un wizard TUI (`welcome.py`) et un autostart
KDE vers la plateforme learn web. L'utilisateur veut unifier le
tout : KDE se lance directement (zéro interaction TTY), puis un
wizard web guide la persistance ET la prise en main — dans le
navigateur, avec xterm.js pour les commandes interactives.

## Architecture cible

```
ISO boot → autologin tty1 → bash_profile
  → KDE Plasma démarre directement (clavier fr par défaut)
  → Autostart: ouvre le navigateur sur http://localhost:8890
  → Wizard web: Persistance → Prise en main anklume
  → Coche ~/.anklume/welcome-done → ne se relance plus
```

## Changements

### 1. `bash_profile` — lancer KDE directement, sans wizard TUI

Supprimer l'appel à `start.sh` et le bloc wizard. Le flow
devient :

```
if tty1 && no WAYLAND_DISPLAY:
    # Clavier fr par défaut (déjà géré par vconsole.conf)
    # Lancer KDE directement (toujours, pas seulement si anklume.desktop=kde)
    exec start-desktop.sh
```

**Fichier**: `host/boot/desktop/bash_profile`

### 2. `anklume-start.service` — ne plus lancer le wizard TTY

Deux options :
- **A.** Désactiver le service (ne plus enable dans build-image.sh)
- **B.** Le garder mais lui faire lancer le serveur web en background
  au lieu du wizard TTY

→ Option **B** : le service démarre `platform_server.py` en
background, pour que le navigateur KDE le trouve prêt. Renommer
en `anklume-learn.service`.

**Fichier**: `host/boot/systemd/anklume-learn.service` (nouveau)
**Fichier**: `host/boot/systemd/anklume-start.service` (supprimé)
**Fichier**: `scripts/build-image.sh` (remplacer enable)

### 3. `platform_server.py` — ajouter le wizard onboarding

Nouvelles routes :

| Route | Contenu |
|-------|---------|
| `/onboard` | Landing wizard (détecte si persistance déjà faite) |
| `/onboard/{step}` | Étape du wizard (split-pane: instructions + xterm.js) |
| `/onboard/done` | Marque welcome-done, redirige vers `/` (learn) |

Le wizard détecte automatiquement l'état :
- Pas de pool → étape persistance en premier
- Pool existant → passer directement à la prise en main
- Pas de disque supplémentaire → proposer mode exploration

**Fichier**: `scripts/platform_server.py` — ajouter routes

### 4. Contenu du wizard onboarding

Nouveau fichier `scripts/onboarding.py` — définit les étapes
comme des `ContentSection` / `ContentPage` (même modèle que
`guide_chapters.py` + `web/content.py`).

**Étapes** :

1. **Bienvenue** — Qu'est-ce qu'anklume, choix clavier (si live OS)
2. **Stockage** — Détection des disques, choix backend (ZFS/BTRFS/dir),
   LUKS optionnel. Commandes cliquables dans xterm.js.
   Validation : `pool.conf` existe ou Incus storage configuré.
3. **Premiers pas** — `anklume sync`, `anklume domain apply`,
   vérification que l'infra tourne. Commandes cliquables.
4. **Et après** — Liens vers labs, console, dashboard. Bouton "Terminer".

Bilingual (fr/en) — réutilise les strings de `welcome_strings.py`.

**Fichier**: `scripts/onboarding.py` (nouveau)

### 5. Landing page `/` — rediriger si premier boot

Modifier la route `/` de `platform_server.py` :
- Si `~/.anklume/welcome-done` n'existe pas → redirect vers `/onboard`
- Sinon → afficher la landing actuelle (learn)

### 6. `open-learn.sh` — simplifier

Ne fait plus qu'ouvrir le navigateur (le serveur est déjà
lancé par le service systemd). Retire le démarrage du serveur.

**Fichier**: `host/boot/desktop/open-learn.sh`

### 7. `anklume-welcome.desktop` — pointer vers learn, pas open-learn

Simplifié : ouvre `xdg-open http://localhost:8890` si
`~/.anklume/welcome-done` n'existe pas. Le redirect `/` → `/onboard`
se charge du reste.

**Fichier**: `host/boot/desktop/anklume-welcome.desktop`

### 8. Nettoyage

- `scripts/welcome.py` → supprimé (remplacé par le wizard web)
- `scripts/welcome_strings.py` → conservé (les strings sont
  réutilisées par `onboarding.py`)
- `scripts/guide.sh` et `scripts/guide/*.sh` → déjà supprimés
  dans la branche `simplify`
- `scripts/guide_chapters.py` + `scripts/guide_strings.py` →
  conservés (alimentent le Capability Tour dans learn)

### 9. Tests

- Modifier `tests/test_web_content.py` pour couvrir l'onboarding
- Modifier `tests/test_live_os.py` si des tests référencent
  `welcome.py`
- Ajouter test : redirect `/` → `/onboard` quand pas welcome-done
- BDD : mettre à jour `scenarios/live/live_execution.feature`

### 10. Build image

**Fichier**: `scripts/build-image.sh`
- Remplacer `anklume-start.service` par `anklume-learn.service`
- S'assurer que `open-learn.sh` est copié
- Supprimer toute référence à `welcome.py` en tant que wizard

## Fichiers modifiés (résumé)

| Fichier | Action |
|---------|--------|
| `host/boot/desktop/bash_profile` | Simplifier : KDE direct |
| `host/boot/systemd/anklume-learn.service` | Nouveau (lance platform_server) |
| `host/boot/systemd/anklume-start.service` | Supprimer |
| `scripts/platform_server.py` | Ajouter routes /onboard, redirect / |
| `scripts/onboarding.py` | Nouveau (étapes wizard) |
| `host/boot/desktop/open-learn.sh` | Simplifier |
| `host/boot/desktop/anklume-welcome.desktop` | Simplifier |
| `scripts/welcome.py` | Supprimer |
| `scripts/build-image.sh` | Adapter service + refs |
| Tests | Adapter |

## Vérification

1. `anklume dev test --fast` → tous les tests passent
2. `anklume dev lint` → 0 violations
3. L4 : boot ISO QEMU → KDE se lance → navigateur s'ouvre sur
   `/onboard` → wizard fonctionne → persistance OK → prise en
   main OK → relance → navigateur s'ouvre sur `/` (learn, pas onboard)
