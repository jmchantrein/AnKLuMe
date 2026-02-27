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
        "opt_persist": "Configurer la persistance (recommande)",
        "opt_explore": "Explorer sans persistance (donnees perdues au redemarrage)",
        "opt_skip": "Passer (expert)",
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
        ],
        "next_title": "PROCHAINES ETAPES",
        "next_keys_label": "Raccourcis essentiels",
        "next_guide": "'anklume guide' pour revenir ici",
        "next_help": "'anklume --help' pour toutes les commandes",
        "next_console": "'anklume console' pour la console par domaine",
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
        "opt_persist": "Configure persistence (recommended)",
        "opt_explore": "Explore without persistence (data lost on reboot)",
        "opt_skip": "Skip (expert)",
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
        ],
        "next_title": "NEXT STEPS",
        "next_keys_label": "Essential shortcuts",
        "next_guide": "'anklume guide' to return here",
        "next_help": "'anklume --help' for all commands",
        "next_console": "'anklume console' for the domain console",
        "finish": "Finish",
        "choice": "Choice",
        "continue": "Press Enter to continue...",
        "yes": "y",
        "disks": "Available disks:",
    },
}
