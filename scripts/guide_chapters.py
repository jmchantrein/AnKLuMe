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
        "key": "isolation",
        "title": {"en": "Domain Isolation", "fr": "Isolation par domaines"},
        "description": {
            "en": "See how anklume isolates domains in separate networks",
            "fr": "Découvrez l'isolation des domaines en réseaux séparés",
        },
        "requires": ["incus", "deployed_domains"],
        "demo_commands": [
            "incus list --all-projects --format compact",
            "incus network list --format compact",
        ],
        "safe_for_web": True,
    },
    {
        "id": 2,
        "key": "console",
        "title": {"en": "Tmux Console", "fr": "Console tmux"},
        "description": {
            "en": "Color-coded tmux console with domain windows",
            "fr": "Console tmux colorée avec fenêtres par domaine",
        },
        "requires": ["incus", "deployed_domains", "tmux"],
        "demo_commands": [
            "python3 scripts/console.py --dry-run",
        ],
        "safe_for_web": True,
    },
    {
        "id": 3,
        "key": "gui-apps",
        "title": {"en": "GUI App Forwarding", "fr": "Déport graphique"},
        "description": {
            "en": "Forward graphical applications from containers to host",
            "fr": "Affichez les applications graphiques des conteneurs",
        },
        "requires": ["incus", "deployed_domains", "wayland"],
        "demo_commands": [],
        "safe_for_web": False,
    },
    {
        "id": 4,
        "key": "clipboard",
        "title": {"en": "Clipboard Transfer", "fr": "Presse-papiers"},
        "description": {
            "en": "Copy and paste between host and containers",
            "fr": "Copiez-collez entre l'hôte et les conteneurs",
        },
        "requires": ["incus", "deployed_domains"],
        "demo_commands": [],
        "safe_for_web": False,
    },
    {
        "id": 5,
        "key": "network",
        "title": {"en": "Network Isolation", "fr": "Isolation réseau"},
        "description": {
            "en": "Inter-domain traffic is blocked by nftables",
            "fr": "Le trafic inter-domaines est bloqué par nftables",
        },
        "requires": ["incus", "deployed_domains"],
        "demo_commands": [
            "nft list table inet anklume 2>/dev/null || echo 'No anklume nftables table'",
        ],
        "safe_for_web": True,
    },
    {
        "id": 6,
        "key": "snapshots",
        "title": {"en": "Snapshots & Restore", "fr": "Snapshots & restauration"},
        "description": {
            "en": "Save and restore instance state instantly",
            "fr": "Sauvegardez et restaurez l'état des instances",
        },
        "requires": ["incus", "deployed_domains"],
        "demo_commands": [
            "incus list --all-projects --format compact -c nsS",
        ],
        "safe_for_web": True,
    },
    {
        "id": 7,
        "key": "dashboard",
        "title": {"en": "Web Dashboard", "fr": "Dashboard web"},
        "description": {
            "en": "Live infrastructure status in your browser",
            "fr": "État de l'infrastructure en temps réel dans le navigateur",
        },
        "requires": ["incus", "python3"],
        "demo_commands": [],
        "safe_for_web": False,
    },
    {
        "id": 8,
        "key": "ai",
        "title": {"en": "GPU & AI Services", "fr": "GPU & services IA"},
        "description": {
            "en": "Local LLM inference with GPU passthrough",
            "fr": "Inférence LLM locale avec accès GPU",
        },
        "requires": ["incus", "gpu"],
        "demo_commands": [
            "incus info --resources 2>/dev/null | grep -A5 'GPU:'",
        ],
        "safe_for_web": True,
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
