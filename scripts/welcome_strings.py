"""i18n strings for the anklume welcome guide."""

STRINGS = {
    "fr": {
        "welcome_title": "BIENVENUE",
        "welcome_what": (
            "anklume isole vos activités dans des compartiments étanches\n"
            "(conteneurs, VM) — comme QubesOS, mais sur n'importe quel Linux.\n"
            "Chaque domaine a son réseau, son stockage, ses règles."
        ),
        "start": "Commencer",
        "situation_title": "SITUATION",
        "returning": "Disque de données trouvé — bienvenue !",
        "opt_persist": "Sauvegarder mon travail (nécessite un disque ou une partition)",
        "opt_persist_desc": "Vos conteneurs et fichiers survivront aux redémarrages.",
        "opt_explore": "Juste essayer (tout disparaît à l'extinction)",
        "opt_explore_desc": (
            "ATTENTION : TOUT sera effacé à l'arrêt — fichiers, conteneurs, config.\n"
            "Sauvegardez vos fichiers importants sur une clé USB."
        ),
        "opt_skip": "Je sais ce que je fais — passer",
        "persist_title": "PERSISTANCE",
        "persist_explain": (
            "La persistance chiffre un disque avec LUKS.\n"
            "Vos conteneurs, données et configuration survivront aux redémarrages."
        ),
        "persist_no_disk": "Aucun disque supplémentaire détecté.",
        "persist_no_disk_explain": (
            "La persistance nécessite un disque ou une partition dédiée.\n"
            "Aucun disque supplémentaire n'a été trouvé sur cette machine.\n"
            "Vous pouvez brancher un disque USB ou utiliser le mode Exploration."
        ),
        "persist_fallback_explore": "Passer en mode Exploration à la place ?",
        "persist_no_script": "start.sh introuvable.",
        "persist_confirm": "Lancer la configuration maintenant ?",
        "persist_running": "Lancement de la configuration...",
        "persist_skip": "Passé. Lancez manuellement : sudo /opt/anklume/scripts/start.sh",
        "persist_success": "Configuration de la persistance terminée avec succès.",
        "persist_error": "Erreur lors de la configuration de la persistance.",
        "explore_title": "MODE EXPLORATION",
        "explore_init": "Préparation de l'environnement d'exploration...",
        "explore_incus": "Initialisation d'Incus...",
        "explore_infra": "Configuration de l'infrastructure par défaut...",
        "explore_sync": "Génération des fichiers Ansible...",
        "explore_apply": "Déploiement de l'infrastructure (cela peut prendre quelques minutes)...",
        "explore_done": "Environnement prêt ! Les données seront perdues au redémarrage.",
        "explore_space": "Espace disponible : {free_mb} Mo (limité par la RAM)",
        "explore_warn": (
            "Rappel : TOUT sera effacé à l'arrêt.\n"
            "Sauvegardez vos fichiers importants sur une clé USB."
        ),
        "keyboard_title": "CLAVIER",
        "keyboard_choice": "Disposition",
        "keyboard_set": "Clavier configuré :",
        "tour_title": "DÉCOUVERTE",
        "tour_steps": [
            (
                "Domaines = environnements isolés",
                "Chaque domaine est un réseau séparé avec ses propres machines.\n"
                "Exemple : 'pro' pour le travail, 'perso' pour la vie privée.",
            ),
            (
                "anklume sync → génère l'infrastructure",
                "Éditez infra.yml puis lancez 'anklume sync'.\n"
                "Les fichiers Ansible sont générés automatiquement.",
            ),
            (
                "anklume domain apply → crée tout",
                "Réseaux, projets Incus, conteneurs : tout est créé\n"
                "d'après votre description dans infra.yml.",
            ),
            (
                "Apprendre en pratiquant",
                "'anklume lab list' affiche les exercices guidés.\n"
                "Commencez avec 'anklume lab start 01'.",
            ),
        ],
        "next_title": "PROCHAINES ÉTAPES",
        "next_keys_label": "Raccourcis essentiels",
        "next_guide": "'anklume guide' pour revenir ici",
        "next_help": "'anklume --help' pour toutes les commandes",
        "next_console": "'anklume console' pour la console par domaine",
        "next_labs": "'anklume lab list' pour les exercices guidés",
        "finish": "Terminer",
        "choice": "Choix",
        "continue": "Appuyez sur Entrée pour continuer...",
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
        "persist_no_disk_explain": (
            "Persistence requires a dedicated disk or partition.\n"
            "No additional disk was found on this machine.\n"
            "You can plug in a USB disk or use Explore mode instead."
        ),
        "persist_fallback_explore": "Switch to Explore mode instead?",
        "persist_no_script": "start.sh not found.",
        "persist_confirm": "Run setup now?",
        "persist_running": "Running start.sh...",
        "persist_skip": "Skipped. Run manually: sudo /opt/anklume/scripts/start.sh",
        "persist_success": "Persistence setup completed successfully.",
        "persist_error": "Error during persistence setup.",
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
