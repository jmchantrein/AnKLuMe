> La version anglaise fait foi en cas de divergence.

# Live OS -- Analyse des points de friction (perspective etudiant)

Un etudiant en informatique demarre anklume depuis une cle USB sur son
portable. Ce document retrace chaque point de friction du demarrage
jusqu'au premier travail utile, propose des solutions et cartographie
les dependances.

## Conventions

- **Severite** : `BLOQUANT` (impossible de continuer), `MAJEUR` (penible, contournement possible), `MINEUR` (agacant)
- **Dependances** :
  - `-> eliminates: F-XX` -- corriger ce point fait disparaitre F-XX
  - `requires: F-XX unfixed` -- ce point n'existe que si F-XX n'est PAS corrige

---

## Phase 1 -- Obtention de l'ISO

### F-01 | BLOQUANT | Aucune ISO pre-construite disponible

L'etudiant doit cloner le depot, installer les dependances de build et
executer `sudo scripts/build-image.sh` (~30-60 min, root, 5 Go+ de
disque). Un etudiant qui veut simplement essayer anklume ne peut pas.

**Solution** : Publier des ISO pre-construites sur GitHub Releases
(Debian+KDE, Debian+sway). Automatiser via CI.

-> eliminates: F-02, F-03

### F-02 | MAJEUR | Dependances de build introuvables

`build-image.sh` echoue a des endroits aleatoires si l'hote n'a pas
`debootstrap`, `grub-mkstandalone`, `xorriso`, `mksquashfs`, etc.
Aucune commande unique n'installe tout.

**Solution** : Ajouter `scripts/build-image.sh --install-deps` pour
installer tous les paquets requis sur l'hote.

requires: F-01 unfixed

### F-03 | MAJEUR | `dd` est la seule methode documentee pour ecrire sur USB

`sudo dd if=... of=/dev/sdX bs=4M` peut detruire le mauvais disque.
Aucune mention d'alternatives plus sures.

**Solution** : Documenter Ventoy (copier l'ISO, c'est fait),
balenaEtcher, GNOME Disks. Ajouter un avertissement sur la
verification de la cible `dd`.

---

## Phase 2 -- Menu de demarrage GRUB

### F-04 | MAJEUR | 16 entrees de menu, aucune indication

4 entrees principales + 4 "More Desktops" + 8 "Advanced". L'etudiant
doit choisir entre KDE/sway/labwc, GPU/no-GPU, toram/direct sans savoir
ce que signifie chacune de ces options.

**Solution** : Une seule entree par defaut : `anklume Live` (KDE, toram,
auto-detection GPU au niveau initramfs). Deplacer tout le reste dans un
sous-menu `Advanced options`. Ajouter un texte d'aide de 3 secondes sous
chaque entree.

-> eliminates: F-05, F-06

### F-05 | MAJEUR | GPU vs no-GPU necessite une connaissance du materiel

Mauvais choix : "GPU" sur du materiel non-NVIDIA = inoffensif (le module
ne se charge simplement pas). "No GPU" sur du materiel NVIDIA = pas
d'acceleration materielle. Mais l'etudiant ne sait pas quoi choisir.

**Solution** : Auto-detection dans initramfs ou au demarrage precoce.
Tenter le chargement du module `nvidia` ; en cas d'echec, blacklister
automatiquement. Supprimer le choix.

requires: F-04 unfixed

### F-06 | MINEUR | "toram" est du jargon inexplique

Aucune description de ce que fait toram. L'etudiant ne sait pas que cela
copie l'OS en RAM pour la vitesse et la possibilite d'ejecter la cle USB.

**Solution** : Renommer en "anklume Live (rapide -- charge en RAM)" si
l'option reste visible. Sinon, simplement mettre toram par defaut.

requires: F-04 unfixed

---

## Phase 3 -- Premiere connexion / Bureau

### F-07 | MINEUR | Nom d'utilisateur de developpeur code en dur

Le script de build utilisait un nom d'utilisateur specifique au
developpeur au lieu d'un compte etudiant generique.

**Solution** : Utiliser `anklume` comme nom d'utilisateur par defaut.
Configurable au build via la variable `LIVE_USER`.

### F-08 | MAJEUR | Mot de passe non communique nulle part

Le mot de passe est `anklume` mais rien a l'ecran ne l'indique a
l'etudiant. S'il a besoin de `sudo`, il est bloque.

**Solution** : Afficher dans le texte d'aide GRUB, dans l'invite de
connexion TTY (motd) et comme notification bureau au premier demarrage.

### F-09 | MAJEUR | sway/labwc : aucune affordance UI

Les gestionnaires de fenetres en mosaique n'ont pas de decorations de
fenetre, pas de menu d'applications, pas de zone de notification.
Un etudiant habitue a GNOME/KDE/Windows voit un ecran vide avec une
barre de statut.

**Solution** : KDE Plasma est deja le defaut GRUB -- le conserver.
Pour sway/labwc, ajouter un calque translucide de raccourcis clavier au
premier demarrage (fermeture avec n'importe quelle touche).

### F-10 | BLOQUANT | Aucune decouverte possible sur sway/labwc

L'etudiant sur sway voit un ecran sombre. Super+Entree pour le
terminal, Super+d pour le lanceur -- zero decouvrabilite. Il ne peut
meme pas ouvrir un terminal.

**Solution** : Ouvrir automatiquement un terminal `foot` au premier
lancement de sway (en plus de l'assistant d'accueil). Ajouter un widget
permanent waybar "? Raccourcis" pointant vers le fichier de raccourcis.

requires: F-09 (sway/labwc uniquement)

### F-11 | BLOQUANT | Clavier AZERTY suppose, pas d'alternative

`KEYMAP=fr` et `XKB_DEFAULT_LAYOUT=fr` sont codes en dur. Un etudiant
non francophone ne peut pas taper `[`, `{`, `|`, `\` ni meme la
ponctuation de base correctement.

**Solution** : Ajouter le support du parametre noyau `anklume.keymap=XX`.
Proposer le choix de la disposition clavier dans l'assistant d'accueil.
Defaut a `fr` mais modifiable.

### F-12 | MINEUR | Raccourcis d'espace de travail sway casses en AZERTY

`bindsym $mod+1` necessite Shift en AZERTY (la touche physique "1"
produit "&"). Changer d'espace de travail necessite $mod+Shift+&, ce
qui n'est pas intuitif.

**Solution** : Ajouter le drapeau `--to-code` a tous les raccourcis dans
sway-config : `bindsym --to-code $mod+1 workspace number 1`. Cela lie a
la position physique de la touche quelle que soit la disposition.

---

## Phase 4 -- Assistant d'accueil

### F-13 | MINEUR | L'assistant d'accueil peut ne pas etre visible

Sur sway, `exec_always { foot -e python3 welcome.py }` lance un
terminal qui peut ne pas avoir le focus ou apparaitre derriere d'autres
fenetres.

**Solution** : Ajouter une regle sway `for_window` pour rendre le
terminal de l'assistant flottant, centre et avec le focus. Definir
l'app_id sur foot (`foot --app-id anklume-welcome`).

### F-14 | MAJEUR | Trois choix sans contexte

- "Configure persistence" -- qu'est-ce que cela signifie ?
- "Explore without persistence" -- a quel point "donnees perdues" est-il grave ?
- "Skip (expert)" -- suis-je un expert ? Probablement pas.

**Solution** : Reecrire :
1. "Sauvegarder mon travail (necessite un second disque ou partition)"
2. "Juste essayer (tout disparait a l'extinction)"
3. "Je sais ce que je fais -- passer"

Ajouter une explication d'une ligne sous chaque option.

### F-15 | BLOQUANT | "Explorer" laisse le systeme non fonctionnel

L'etudiant choisit l'option 2 ("explorer"). L'assistant se termine. Et
maintenant ?
- Incus n'est pas initialise (pas de `incus admin init`)
- Pas de pool de stockage, pas de reseau
- `anklume sync` echoue (garde `require_container`)
- L'etudiant est bloque avec un bureau et zero infrastructure

**Solution** : Le mode "Explorer" doit auto-provisionner :
1. `incus admin init --minimal` (backend dir sur tmpfs)
2. Copier le `infra.yml` de demarrage dans le repertoire de travail
3. Executer `anklume sync && anklume domain apply`
4. Afficher "Votre lab est pret. Ouvrez un terminal et essayez : `anklume console`"

-> eliminates: F-19, F-24, F-25, F-26, F-30

### F-16 | BLOQUANT | "Persister" necessite un second disque >= 100 Go

La plupart des etudiants ont UN disque (SSD interne avec leur OS
principal) + la cle USB executant le live OS. `first-boot.sh` refuse si
aucun disque >= 100 Go n'est trouve (excluant le peripherique racine).

**Solution** : Proposer des modes de stockage alternatifs :
- Partition sur un disque existant (reduire une partition existante)
- Fichier loop sur tout systeme de fichiers en ecriture
- Backend `dir` (pas de ZFS/BTRFS, juste un repertoire)
- Abaisser le seuil de taille ou le supprimer entierement

### F-17 | MINEUR | Le choix ZFS vs BTRFS n'a aucun sens pour les etudiants

L'etudiant n'a aucune idee de ce que sont ZFS ou BTRFS.

**Solution** : Selectionner automatiquement BTRFS (natif au noyau, pas
de module supplementaire). Proposer ZFS uniquement en "Avance : ZFS
(recommande pour les serveurs)".

requires: F-16 unfixed

### F-18 | MINEUR | L'invite de chiffrement LUKS est prematuree

"Chiffrer le disque de stockage avec LUKS ? (o/n)" -- l'etudiant ne
connait pas les compromis (mot de passe a chaque demarrage vs protection
des donnees).

**Solution** : Pas de chiffrement par defaut en mode etudiant. Afficher
le chiffrement comme option avancee avec une explication d'une ligne.

requires: F-16 unfixed

---

## Phase 5 -- Initialisation d'Incus

### F-19 | BLOQUANT | `first-boot.sh` n'initialise pas Incus

Cree un pool de stockage mais n'execute jamais `incus admin init`.
Resultat : pas de reseau par defaut, pas de profil par defaut,
`incus launch` echoue.

**Solution** : Apres la creation du pool, executer
`incus admin init --preseed` avec le pool cree comme stockage par
defaut. Ou fusionner les parties pertinentes de `bootstrap.sh` dans
`first-boot.sh`.

-> eliminates: F-26

### F-20 | BLOQUANT | `pool.conf` ecrit au mauvais chemin

`first-boot.sh` ecrit `pool.conf` dans le repertoire courant
(`./pool.conf`). La garde systemd verifie
`/mnt/anklume-persist/pool.conf`. Ils ne correspondent jamais.
Resultat : `anklume-first-boot.service` se relance a chaque demarrage.

**Solution** : Ecrire dans `/mnt/anklume-persist/pool.conf`. Creer
`/mnt/anklume-persist/` si la partition persistante est disponible, ou
se rabattre sur `/var/lib/anklume/pool.conf` avec le
ConditionPathExists systemd mis a jour en consequence.

### F-21 | MAJEUR | `anklume-first-boot.service` entre en competition avec `getty` sur tty1

Le service a `TTYPath=/dev/tty1` et `StandardInput=tty`, mais
`getty@tty1.service` demarre aussi pour l'autologin. Ils se disputent
le meme TTY : first-boot.sh se bloque en attente d'entree pendant que
getty tente d'afficher l'invite de connexion.

**Solution** : Supprimer entierement le service systemd. Executer
first-boot uniquement depuis l'assistant d'accueil (qui s'execute apres
la connexion, dans un terminal adequat). Ou utiliser un TTY dedie (tty2).

---

## Phase 6 -- Execution des commandes anklume

### F-22 | BLOQUANT | `require_container` bloque TOUTES les commandes sur l'hote

Sur le live OS, l'etudiant EST sur l'hote (`systemd-detect-virt` ->
`none`). Chaque commande utile echoue :
- `anklume sync` -> "must run inside anklume-instance"
- `anklume domain apply` -> idem
- `anklume init` -> idem

Mais `anklume-instance` n'existe pas (seul `bootstrap.sh` le cree).

**Solution** : Detecter le contexte live OS (`boot=anklume` dans
`/proc/cmdline` ou fichier marqueur `/etc/anklume/live`) et contourner
`require_container`. Sur le live OS, l'hote EST l'environnement
d'administration.

-> eliminates: F-23

### F-23 | BLOQUANT | Pas d'`anklume-instance` et aucun moyen d'en creer un

Le workflow standard necessite `incus exec anklume-instance -- bash`.
Sur le live OS, ce conteneur n'existe pas. `bootstrap.sh --prod` le
cree mais l'etudiant ne connait pas ce script et il duplique le travail
deja fait (ou pas fait) par `first-boot.sh`.

**Solution** : Sur le live OS, ne pas utiliser `anklume-instance` du
tout. Tout executer directement depuis l'hote (voir F-22).
Alternativement, faire executer `bootstrap.sh` par l'assistant d'accueil
au lieu de `first-boot.sh`.

requires: F-22 unfixed

---

## Phase 7 -- Premiere infrastructure

### F-24 | MAJEUR | Aucune infrastructure pre-deployee

Apres toute la configuration, l'etudiant a un Incus vide sans domaines,
sans conteneurs, sans reseaux. Il doit manuellement editer `infra.yml`,
executer sync, executer apply. Pour une experience "demo live", c'est
trop.

**Solution** : Auto-deployer une infrastructure de demarrage en mode
"explorer". Le `infra.yml` livre (student-sysadmin : 1 domaine admin +
1 domaine lab avec 2 conteneurs) est un bon point de depart. Le deployer
automatiquement.

requires: F-15 unfixed

### F-25 | MINEUR | Le `infra.yml` livre est specifique au projet

L'ISO live embarque le `infra.yml` du depot actuel (qui peut changer).
L'etudiant ne sait pas qu'il existe a `/opt/anklume/infra.yml` ou que
c'est un point de depart valide.

**Solution** : Etape de l'assistant d'accueil : "Votre infrastructure de
demarrage est a /opt/anklume/infra.yml -- editez-le pour ajouter vos
propres domaines."

### F-26 | MAJEUR | Les conteneurs n'ont pas d'internet

Si Incus n'a pas ete correctement initialise (pas de `incus admin init`),
il n'y a pas de reseau gere par defaut avec NAT. Les conteneurs ne
peuvent pas atteindre internet. `apt install` dans les conteneurs echoue.

**Solution** : S'assurer que `incus admin init` fait partie du flux de
configuration du live OS (voir F-19). Verifier que le NAT fonctionne
dans l'assistant d'accueil ou `anklume doctor`.

requires: F-19 unfixed

### F-27 | MINEUR | L'isolation nftables n'est pas auto-deployee

`anklume network deploy` doit etre execute manuellement depuis l'hote.
L'etudiant ne le sait pas. Le trafic inter-domaine fonctionne
silencieusement (pas d'isolation) ou echoue silencieusement (regles
obsoletes).

**Solution** : Ajouter un hook post-apply qui auto-genere et applique
les regles nftables. Ou faire en sorte que `anklume domain apply`
inclue le deploiement nftables par defaut sur le live OS.

---

## Phase 8 -- Travail avec les conteneurs

### F-28 | MINEUR | L'acces aux conteneurs n'est pas evident

Le moyen principal d'acceder aux conteneurs est
`incus exec <nom> -- bash`. `anklume console` existe (base sur tmux)
mais l'assistant d'accueil ne le mentionne qu'en passant.

**Solution** : Apres l'auto-deploiement, afficher :
```
Vos conteneurs sont prets :
  anklume console          -> console de domaine coloree
  incus exec sa-web -- bash -> shell direct dans sa-web
```

### F-29 | MAJEUR | La sortie Ansible est illisible

Quand `apply` echoue (infra.yml mal configure, probleme reseau),
Ansible deverse un mur de YAML jaune/rouge. L'etudiant ne peut pas
analyser l'erreur.

**Solution** : Envelopper la sortie de `ansible-playbook` dans un
filtre qui extrait uniquement les resumes de taches `fatal` et `failed`.
Afficher le chemin complet du log pour le debogage. Utiliser `--forks=1`
sur le live OS pour une sortie sequentielle (plus lisible).

### F-30 | MINEUR | Pas de reinitialisation pour les sessions d'exploration

L'etudiant casse quelque chose, aucune idee de comment recommencer.
`anklume flush` existe mais fait peur ("destroy all infrastructure").

**Solution** : Ajouter `anklume reset` (mode exploration uniquement) qui
purge et re-deploie la configuration de demarrage. Equivalent a
"recommencer a zero".

requires: F-15 unfixed

---

## Phase 9 -- Fonctionnalites pedagogiques

### F-31 | MAJEUR | Les labs ne sont jamais mentionnes pendant l'integration

Le repertoire `labs/` et `anklume lab list` sont une fonctionnalite
pedagogique cle mais l'assistant d'accueil ne les mentionne jamais.
L'etudiant ne les decouvre qu'en lisant attentivement `--help`.

**Solution** : Ajouter une etape de visite guidee : "Apprenez en
pratiquant -> `anklume lab list` affiche les exercices guides. Commencez
avec `anklume lab start 01`." En faire l'appel a l'action principal
apres la visite.

### F-32 | MINEUR | `anklume --help` trop charge en mode etudiant

35+ commandes visibles meme en mode etudiant. L'etudiant n'en a besoin
que de 4 : `sync`, `domain apply`, `console`, `lab start`.

**Solution** : En mode etudiant, afficher une section "Demarrage rapide"
avec uniquement les commandes essentielles. Liste complete derriere
`--help-all`.

---

## Phase 10 -- Environnement volatile

### F-33 | MAJEUR | Toutes les modifications perdues au redemarrage (pas de persistance)

Sans persistance, toute la couche superieure overlayfs (tmpfs) est
effacee au redemarrage. Pas seulement les conteneurs -- les paquets
systeme, les fichiers de configuration, le repertoire personnel, tout.
L'assistant d'accueil dit "donnees perdues au redemarrage" mais ne
transmet pas l'ampleur reelle.

**Solution** : Rendre l'avertissement explicite : "TOUT ce que vous
faites dans cette session sera efface a l'extinction. Sauvegardez les
fichiers importants sur une cle USB." Ajouter un montage persistant de
`/home` si UNE partition en ecriture est disponible.

### F-34 | MINEUR | tmpfs limite a 50% de la RAM

La couche COW overlayfs est un tmpfs a 50% de la RAM. Sur un portable
de 8 Go, seulement ~4 Go sont disponibles pour TOUTES les ecritures
(installations apt, images de conteneurs, fichiers utilisateur).
Facilement sature.

**Solution** : En mode exploration, avertir des contraintes RAM.
Afficher l'espace libre dans waybar. Si une partition en ecriture est
disponible, l'utiliser comme couche superieure au lieu de tmpfs.

---

## Carte des dependances

```
F-01 (pas d'ISO pre-construite)
 |-- F-02 (deps de build)
 `-- F-03 (dd uniquement)

F-04 (confusion menu GRUB)
 |-- F-05 (choix GPU)
 `-- F-06 (jargon toram)

F-15 (explorer = impasse)          <- CHEMIN CRITIQUE
 |-- F-19 (pas d'init incus)
 |-- F-24 (pas d'infra deployee)
 |-- F-25 (infra.yml inconnu)
 |-- F-26 (pas d'internet dans les conteneurs)
 `-- F-30 (pas de reinitialisation)

F-16 (besoin d'un second disque)   <- CHEMIN CRITIQUE
 |-- F-17 (ZFS vs BTRFS)
 `-- F-18 (invite LUKS)

F-19 (first-boot.sh incomplet)
 `-- F-26 (pas de reseau/NAT)

F-22 (require_container bloque l'hote)  <- CHEMIN CRITIQUE
 `-- F-23 (pas d'anklume-instance)
```

## Resume du chemin critique

Trois bloqueurs doivent etre corriges pour qu'un etudiant ait une
experience utilisable sur le live OS :

1. **F-15** : Le mode "Explorer" doit auto-provisionner un environnement fonctionnel
2. **F-22** : `require_container` doit etre contourne sur le live OS
3. **F-19** : Incus doit etre entierement initialise (pas seulement le pool de stockage)

Corriger ces trois points elimine 8 points de friction en aval et
transforme le live OS de "ecran vide + messages d'erreur" en
"demarrage -> bureau -> conteneurs fonctionnels en 2 minutes."

---

## Etat d'implementation

| ID | Statut | Notes |
|----|--------|-------|
| F-04 | CORRIGE | Entree GRUB par defaut unique + sous-menu Advanced (16 -> 1+6) |
| F-05 | CORRIGE | GPU auto-detecte au demarrage (NVIDIA charge si present) |
| F-06 | CORRIGE | L'entree par defaut est toram, pas de jargon dans le libelle |
| F-07 | CORRIGE | `LIVE_USER=anklume`, configurable au build |
| F-08 | CORRIGE | `/etc/motd` avec utilisateur/mot de passe/commandes a chaque connexion |
| F-10 | CORRIGE | Ouverture automatique d'un terminal foot au premier lancement sway |
| F-11 | CORRIGE | Selection du clavier dans l'assistant d'accueil + parametre noyau `anklume.keymap` |
| F-12 | CORRIGE | Tous les raccourcis d'espace de travail sway utilisent `--to-code` |
| F-13 | CORRIGE | `for_window [app_id=anklume-welcome]` flottant/centre/focus |
| F-14 | CORRIGE | Libelles de choix reecrits avec descriptions |
| F-15 | CORRIGE | Le mode exploration auto-provisionne : init Incus + infra.yml + sync + apply |
| F-16 | CORRIGE | Option backend `dir` dans first-boot.sh (pas de disque supplementaire requis) |
| F-17 | N/A | Elimine par la correction F-16 (backend dir disponible) |
| F-18 | N/A | Elimine par la correction F-16 (backend dir disponible) |
| F-19 | CORRIGE | `initialize_incus()` avec preseed dans first-boot.sh |
| F-20 | CORRIGE | `pool.conf` ecrit dans `/mnt/anklume-persist/pool.conf` sur le live OS |
| F-21 | CORRIGE | Le service utilise tty2, ignore quand SDDM present (l'assistant gere) |
| F-22 | CORRIGE | Contournement `is_live_os()` dans le Makefile et `require_container()` du CLI |
| F-23 | N/A | Elimine par la correction F-22 |
| F-24 | N/A | Elimine par la correction F-15 (exploration auto-deploie) |
| F-25 | N/A | Elimine par la correction F-15 (exploration copie infra.yml) |
| F-26 | N/A | Elimine par la correction F-19 (Incus entierement initialise) |
| F-30 | N/A | Elimine par la correction F-15 |
| F-31 | CORRIGE | Etape de visite guidee des labs + `next_labs` dans les prochaines etapes |
| F-33 | CORRIGE | Avertissement explicite de perte de donnees en mode exploration et descriptions des choix |
| F-34 | CORRIGE | Espace disponible (Mo) affiche apres le provisionnement exploration |
| F-01 | CORRIGE | Workflow GitHub Actions : build ISO declenchee par tag + GitHub Releases |
| F-02 | CORRIGE | `build-image.sh --install-deps` installe toutes les dependances de build |
| F-03 | CORRIGE | Ventoy, GNOME Disks, balenaEtcher documentes comme alternatives plus sures |
| F-09 | CORRIGE | Calque de raccourcis clavier au premier demarrage sway |
| F-27 | CORRIGE | Auto-deploiement nftables apres `domain apply` sur le live OS (drapeau `--local`) |
| F-28 | N/A | Le mode exploration affiche que les conteneurs sont prets ; les labs guident l'acces |
| F-29 | CORRIGE | Mode etudiant/live-os : `--forks 1`, callback YAML, resume des echecs |
| F-32 | CORRIGE | Mode etudiant : Demarrage rapide (4 commandes) + groupes de commandes simplifies |

Tous les bloqueurs du chemin critique (F-15, F-19, F-22) sont resolus.
34/34 points de friction traites (CORRIGE ou N/A).
Validation L4 QEMU : demarrage -> graphical.target, aucun echec d'authentification.
