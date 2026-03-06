"""Chapter metadata for the anklume interactive guide.

Source of truth for chapter definitions, shared between the terminal
guide (guide.sh) and learning platform (platform_server.py).

Each chapter describes: ID, key, titles (fr/en), prerequisites,
demo commands (whitelisted for web), and web-safety flag.
"""

TOTAL_CHAPTERS = 8

CHAPTERS = [
    {
        "id": 1,
        "key": "first-infra",
        "title": {
            "en": "Your First Infrastructure",
            "fr": "Votre premiere infrastructure",
        },
        "description": {
            "en": "Enter anklume-instance and create your first infra.yml",
            "fr": "Entrez dans anklume-instance et creez votre premier infra.yml",
        },
        "requires": [],
        "demo_commands": [
            "incus exec anklume-instance -- bash -l",
            "anklume --help",
            "anklume init",
            "cat infra.yml",
        ],
        "safe_for_web": True,
    },
    {
        "id": 2,
        "key": "sync-deploy",
        "title": {"en": "Sync & Deploy", "fr": "Synchroniser et déployer"},
        "description": {
            "en": "Generate Ansible files and apply your infrastructure",
            "fr": "Générez les fichiers Ansible et appliquez l'infrastructure",
        },
        "requires": ["incus"],
        "demo_commands": [
            "anklume sync --dry-run",
        ],
        "safe_for_web": True,
    },
    {
        "id": 3,
        "key": "explore",
        "title": {"en": "Explore Your Domains", "fr": "Explorez vos domaines"},
        "description": {
            "en": "See the isolated domains and instances anklume created",
            "fr": "Découvrez les domaines et instances créés par anklume",
        },
        "requires": ["incus"],
        "demo_commands": [
            "anklume instance list",
            "anklume network list",
        ],
        "safe_for_web": True,
    },
    {
        "id": 4,
        "key": "network",
        "title": {"en": "Network Isolation", "fr": "Isolation réseau"},
        "description": {
            "en": "Inter-domain traffic is blocked by default",
            "fr": "Le trafic inter-domaines est bloqué par défaut",
        },
        "requires": ["incus"],
        "demo_commands": [
            "anklume network rules",
            "anklume network deploy",
        ],
        "safe_for_web": True,
    },
    {
        "id": 5,
        "key": "snapshots",
        "title": {"en": "Snapshots & Restore", "fr": "Snapshots et restauration"},
        "description": {
            "en": "Save and restore instance state instantly",
            "fr": "Sauvegardez et restaurez l'état d'une instance",
        },
        "requires": ["incus"],
        "demo_commands": [
            "anklume snapshot list",
        ],
        "safe_for_web": True,
    },
    {
        "id": 6,
        "key": "customize",
        "title": {"en": "Customize Your Setup", "fr": "Personnalisez votre infra"},
        "description": {
            "en": "Add domains, machines, profiles, and network policies",
            "fr": "Ajoutez des domaines, machines, profils et politiques réseau",
        },
        "requires": [],
        "demo_commands": [],
        "safe_for_web": False,
    },
    {
        "id": 7,
        "key": "dashboard",
        "title": {"en": "Web Dashboard", "fr": "Dashboard web"},
        "description": {
            "en": "Live infrastructure status in your browser",
            "fr": "Etat de l'infrastructure en temps réel",
        },
        "requires": ["incus", "python3"],
        "demo_commands": [],
        "safe_for_web": False,
    },
    {
        "id": 8,
        "key": "next-steps",
        "title": {"en": "Next Steps", "fr": "Pour aller plus loin"},
        "description": {
            "en": "GPU passthrough, labs, Tor gateway, and more",
            "fr": "GPU, labs, passerelle Tor, et plus encore",
        },
        "requires": [],
        "demo_commands": [],
        "safe_for_web": False,
    },
]


def get_chapter(chapter_id):
    """Return chapter metadata by ID (1-indexed)."""
    for ch in CHAPTERS:
        if ch["id"] == chapter_id:
            return ch
    return None


def get_whitelisted_commands():
    """Return all demo commands that are safe for web execution."""
    cmds = []
    for ch in CHAPTERS:
        if ch["safe_for_web"]:
            cmds.extend(ch["demo_commands"])
    return cmds
