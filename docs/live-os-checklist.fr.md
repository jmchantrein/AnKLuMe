> La version anglaise fait foi en cas de divergence.

# Checklist de pre-release pour l'ISO Live

A executer apres chaque build d'ISO, avant de declarer la tache terminee.
Tester dans QEMU avec le firmware UEFI (OVMF).

## Verification des paquets

- [ ] `konsole` dans la liste des paquets KDE Debian (`build-image.sh`)
- [ ] `konsole` dans la liste des paquets KDE Arch (`build-image.sh`)
- [ ] `foot` toujours present (pour les bureaux sway/labwc)
- [ ] `python3-typer` / `python-typer` dans la liste des paquets (pour le CLI Python)

## Fichiers de configuration

- [ ] `/etc/hosts` contient `127.0.1.1 anklume` (Debian et Arch)
- [ ] `plasma-welcomerc` supprime l'assistant de bienvenue KDE
- [ ] `kwalletrc` desactive KWallet
- [ ] `anklume.desktop` installe dans `/usr/share/applications/`
- [ ] `anklume.desktop` installe sur le bureau utilisateur

## Verification du CLI

- [ ] `/usr/local/bin/anklume` invoque le CLI Python (pas le wrapper make)
- [ ] `anklume --help` affiche la sortie du CLI Typer avec les sous-commandes
- [ ] `anklume guide` lance le TUI de bienvenue (welcome.py)

## Flux de demarrage

- [ ] La banniere d'accueil s'affiche avec l'art ASCII et la citation
- [ ] Une fenetre d'interruption console de 5 secondes apparait apres la banniere
- [ ] Appuyer sur 'c' pendant le compte a rebours bascule en mode console
- [ ] Le bureau se lance automatiquement sans interruption
- [ ] La deconnexion du bureau revient a la console (pas de boucle de re-connexion automatique)
- [ ] La sentinelle `~/.anklume-console` empeche le lancement du bureau
- [ ] Supprimer la sentinelle restaure le bureau au prochain login

## Operations de premier demarrage

- [ ] `sudo` fonctionne sans avertissement "unable to resolve host"
- [ ] Le daemon Incus demarre et repond a `incus info`
- [ ] L'initialisation d'Incus reussit (modules bridge charges)
- [ ] Le guide de bienvenue propose des selections par defaut (Entree pour accepter)
- [ ] L'ecran s'efface entre les pages du guide
- [ ] Le mode exploration provisionne l'infrastructure sans erreur

## Environnement de bureau

- [ ] Pas d'assistant plasma-welcome au premier login KDE
- [ ] Pas de popup KWallet pendant les operations
- [ ] `anklume` apparait dans le menu d'applications KDE (recherche)
- [ ] Raccourci `anklume` sur le bureau
- [ ] Konsole disponible dans le menu d'applications KDE
