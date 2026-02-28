"""i18n strings for the anklume welcome guide."""

STRINGS = {
    "fr": {
        "welcome_title": "BIENVENUE",
        "welcome_what": (
            "anklume isole vos activites dans des compartiments etanches\n"
            "(conteneurs, VM) — comme QubesOS, mais sur n'importe quel Linux.\n"
            "Chaque domaine a son reseau, son stockage, ses regles."
        ),
        "start": "Commencer",
        "situation_title": "SITUATION",
        "returning": "Disque de donnees trouve — bienvenue !",
        "opt_persist": "Sauvegarder mon travail (necessite un disque ou une partition)",
        "opt_persist_desc": "Vos conteneurs et fichiers survivront aux redemarrages.",
        "opt_explore": "Juste essayer (tout disparait a l'extinction)",
        "opt_explore_desc": (
            "ATTENTION : TOUT sera efface a l'arret — fichiers, conteneurs, config.\n"
            "Sauvegardez vos fichiers importants sur une cle USB."
        ),
        "opt_skip": "Je sais ce que je fais — passer",
        "persist_title": "PERSISTANCE",
        "persist_explain": (
            "La persistance chiffre un disque avec LUKS.\n"
            "Vos conteneurs, donnees et configuration survivront aux redemarrages."
        ),
        "persist_no_disk": "Aucun disque supplementaire detecte.",
        "persist_no_script": "first-boot.sh introuvable.",
        "persist_confirm": "Lancer la configuration maintenant ?",
        "persist_running": "Lancement de first-boot.sh...",
        "persist_skip": "Passe. Lancez manuellement : sudo /opt/anklume/scripts/first-boot.sh",
        "explore_title": "MODE EXPLORATION",
        "explore_init": "Preparation de l'environnement d'exploration...",
        "explore_incus": "Initialisation d'Incus...",
        "explore_infra": "Configuration de l'infrastructure par defaut...",
        "explore_sync": "Generation des fichiers Ansible...",
        "explore_apply": "Deploiement de l'infrastructure (cela peut prendre quelques minutes)...",
        "explore_done": "Environnement pret ! Les donnees seront perdues au redemarrage.",
        "explore_space": "Espace disponible : {free_mb} Mo (limite par la RAM)",
        "explore_warn": (
            "Rappel : TOUT sera efface a l'arret.\n"
            "Sauvegardez vos fichiers importants sur une cle USB."
        ),
        "keyboard_title": "CLAVIER",
        "keyboard_choice": "Disposition",
        "keyboard_set": "Clavier configure :",
        "tour_title": "DECOUVERTE",
        "tour_steps": [
            (
                "Domaines = environnements isoles",
                "Chaque domaine est un reseau separe avec ses propres machines.\n"
                "Exemple : 'pro' pour le travail, 'perso' pour la vie privee.",
            ),
            (
                "anklume sync → genere l'infrastructure",
                "Editez infra.yml puis lancez 'anklume sync'.\n"
                "Les fichiers Ansible sont generes automatiquement.",
            ),
            (
                "anklume domain apply → cree tout",
                "Reseaux, projets Incus, conteneurs : tout est cree\n"
                "d'apres votre description dans infra.yml.",
            ),
            (
                "Apprendre en pratiquant",
                "'anklume lab list' affiche les exercices guides.\n"
                "Commencez avec 'anklume lab start 01'.",
            ),
        ],
        "next_title": "PROCHAINES ETAPES",
        "next_keys_label": "Raccourcis essentiels",
        "next_guide": "'anklume guide' pour revenir ici",
        "next_help": "'anklume --help' pour toutes les commandes",
        "next_console": "'anklume console' pour la console par domaine",
        "next_labs": "'anklume lab list' pour les exercices guides",
        "finish": "Terminer",
        "choice": "Choix",
        "continue": "Appuyez sur Entree pour continuer...",
        "yes": "o",
        "disks": "Disques disponibles :",
    },
    "en": {
        "welcome_title": "WELCOME",
        "welcome_what": (
            "anklume isolates your activities in sealed compartments\n"
            "(containers, VMs) — like QubesOS, but on any Linux.\n"
            "Each domain has its own network, storage, and rules."
        ),
        "start": "Get Started",
        "situation_title": "SITUATION",
        "returning": "Data disk found — welcome back!",
        "opt_persist": "Save my work (needs a disk or partition)",
        "opt_persist_desc": "Your containers and files will survive reboots.",
        "opt_explore": "Just try it (everything disappears on shutdown)",
        "opt_explore_desc": (
            "WARNING: EVERYTHING will be erased on shutdown — files, containers, config.\n"
            "Save important files to a USB drive."
        ),
        "opt_skip": "I know what I'm doing — skip",
        "persist_title": "PERSISTENCE",
        "persist_explain": (
            "Persistence encrypts a disk with LUKS.\n"
            "Your containers, data and config will survive reboots."
        ),
        "persist_no_disk": "No additional disk detected.",
        "persist_no_script": "first-boot.sh not found.",
        "persist_confirm": "Run setup now?",
        "persist_running": "Running first-boot.sh...",
        "persist_skip": "Skipped. Run manually: sudo /opt/anklume/scripts/first-boot.sh",
        "explore_title": "EXPLORE MODE",
        "explore_init": "Preparing explore environment...",
        "explore_incus": "Initializing Incus...",
        "explore_infra": "Setting up default infrastructure...",
        "explore_sync": "Generating Ansible files...",
        "explore_apply": "Deploying infrastructure (this may take a few minutes)...",
        "explore_done": "Environment ready! Data will be lost on reboot.",
        "explore_space": "Available space: {free_mb} MB (limited by RAM)",
        "explore_warn": (
            "Reminder: EVERYTHING will be erased on shutdown.\n"
            "Save important files to a USB drive."
        ),
        "keyboard_title": "KEYBOARD",
        "keyboard_choice": "Layout",
        "keyboard_set": "Keyboard configured:",
        "tour_title": "TOUR",
        "tour_steps": [
            (
                "Domains = isolated environments",
                "Each domain is a separate network with its own machines.\n"
                "Example: 'pro' for work, 'perso' for personal use.",
            ),
            (
                "anklume sync → generates infrastructure",
                "Edit infra.yml then run 'anklume sync'.\n"
                "Ansible files are generated automatically.",
            ),
            (
                "anklume domain apply → creates everything",
                "Networks, Incus projects, containers: all created\n"
                "from your description in infra.yml.",
            ),
            (
                "Learn by doing",
                "'anklume lab list' shows guided exercises.\n"
                "Start with 'anklume lab start 01'.",
            ),
        ],
        "next_title": "NEXT STEPS",
        "next_keys_label": "Essential shortcuts",
        "next_guide": "'anklume guide' to return here",
        "next_help": "'anklume --help' for all commands",
        "next_console": "'anklume console' for the domain console",
        "next_labs": "'anklume lab list' for guided exercises",
        "finish": "Finish",
        "choice": "Choice",
        "continue": "Press Enter to continue...",
        "yes": "y",
        "disks": "Available disks:",
    },
}
