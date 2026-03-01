"""i18n strings for the anklume capability guide.

Bilingual (fr/en) text for chapter explanations, recaps, and UI labels.
Pattern follows welcome_strings.py.
"""

STRINGS = {
    "fr": {
        "guide_title": "Découverte d'anklume",
        "chapter_prefix": "Chapitre",
        "progress": "Progression",
        "skip_no_wayland": "Pas de session Wayland détectée — chapitre passé",
        "skip_no_gpu": "Aucun GPU détecté — chapitre passé",
        "skip_no_tmux": "tmux non installé — chapitre passé",
        "menu_title": "Que souhaitez-vous explorer ?",
        "menu_all": "Tour complet (tous les chapitres)",
        "menu_setup": "Assistant de configuration initiale",
        "recap_label": "Récap",
        "try_it": "À vous de jouer",
        "how_it_works": "Comment ça marche",
        "live_demo": "Démo en direct",
        "continue": "Appuyez sur Entrée pour continuer...",
        "ch1_explain": (
            "anklume crée des domaines isolés, chacun avec son propre réseau\n"
            "  et projet Incus. Les machines d'un domaine ne peuvent pas\n"
            "  communiquer avec celles d'un autre par défaut."
        ),
        "ch1_recap": "Chaque domaine est isolé dans son propre réseau",
        "ch2_explain": (
            "La console tmux ouvre une fenêtre par domaine, chacune\n"
            "  colorée selon son niveau de confiance (comme QubesOS)."
        ),
        "ch2_recap": "La console tmux organise vos domaines visuellement",
        "ch3_explain": (
            "anklume peut afficher les applications graphiques des conteneurs\n"
            "  sur votre écran — via le partage du socket Wayland."
        ),
        "ch3_recap": "Les apps graphiques s'affichent comme des apps locales",
        "ch4_explain": (
            "Le presse-papiers peut être transféré entre l'hôte et un\n"
            "  conteneur, de manière contrôlée et explicite."
        ),
        "ch4_recap": "Le presse-papiers est transférable entre domaines",
        "ch5_explain": (
            "Par défaut, tout trafic entre domaines est bloqué par nftables.\n"
            "  Les network_policies autorisent des exceptions ciblées."
        ),
        "ch5_recap": "L'isolation réseau est active par défaut entre domaines",
        "ch6_explain": (
            "Les snapshots sauvegardent l'état complet d'une instance.\n"
            "  Restaurez en un instant après une erreur ou un test."
        ),
        "ch6_recap": "Les snapshots permettent un retour arrière instantané",
        "ch7_explain": (
            "Le dashboard web affiche l'état de l'infrastructure en temps\n"
            "  réel : instances, réseaux, politiques réseau."
        ),
        "ch7_recap": "Le dashboard donne une vue d'ensemble en temps réel",
        "ch8_explain": (
            "anklume peut passer le GPU aux conteneurs pour l'inférence\n"
            "  LLM locale (Ollama). Le VRAM est flushé entre domaines."
        ),
        "ch8_recap": "Le GPU est partageable pour l'IA locale",
        "deep_dive_title": "Pour aller plus loin",
        "deep_dive_network": "Isolation réseau avancée (nftables, firewall VM)",
        "deep_dive_gpu": "GPU & services IA (Ollama, VRAM flush)",
        "deep_dive_labs": "Labs éducatifs (exercices guidés)",
        "deep_dive_tor": "Gateway Tor",
        "tour_complete": "Tour terminé ! Bonne compartimentation.",
    },
    "en": {
        "guide_title": "anklume Capability Tour",
        "chapter_prefix": "Chapter",
        "progress": "Progress",
        "skip_no_wayland": "No Wayland session detected — chapter skipped",
        "skip_no_gpu": "No GPU detected — chapter skipped",
        "skip_no_tmux": "tmux not installed — chapter skipped",
        "menu_title": "What would you like to explore?",
        "menu_all": "Full tour (all chapters)",
        "menu_setup": "Initial setup wizard",
        "recap_label": "Recap",
        "try_it": "Your turn",
        "how_it_works": "How it works",
        "live_demo": "Live demo",
        "continue": "Press Enter to continue...",
        "ch1_explain": (
            "anklume creates isolated domains, each with its own network\n"
            "  and Incus project. Machines in one domain cannot reach\n"
            "  machines in another by default."
        ),
        "ch1_recap": "Each domain is isolated in its own network",
        "ch2_explain": (
            "The tmux console opens one window per domain, each colored\n"
            "  by trust level (QubesOS-style)."
        ),
        "ch2_recap": "The tmux console organizes your domains visually",
        "ch3_explain": (
            "anklume can forward graphical applications from containers\n"
            "  to your host display — via Wayland socket sharing."
        ),
        "ch3_recap": "GUI apps display as if they were local",
        "ch4_explain": (
            "The clipboard can be transferred between host and containers\n"
            "  in a controlled, explicit manner."
        ),
        "ch4_recap": "Clipboard is transferable between domains",
        "ch5_explain": (
            "By default, all inter-domain traffic is blocked by nftables.\n"
            "  Network policies allow targeted exceptions."
        ),
        "ch5_recap": "Network isolation is active by default between domains",
        "ch6_explain": (
            "Snapshots save the complete state of an instance.\n"
            "  Restore instantly after a mistake or experiment."
        ),
        "ch6_recap": "Snapshots provide instant rollback",
        "ch7_explain": (
            "The web dashboard shows live infrastructure status:\n"
            "  instances, networks, network policies."
        ),
        "ch7_recap": "The dashboard gives a real-time overview",
        "ch8_explain": (
            "anklume can pass the GPU to containers for local LLM\n"
            "  inference (Ollama). VRAM is flushed between domains."
        ),
        "ch8_recap": "GPU is shareable for local AI",
        "deep_dive_title": "Deep dives",
        "deep_dive_network": "Advanced network isolation (nftables, firewall VM)",
        "deep_dive_gpu": "GPU & AI services (Ollama, VRAM flush)",
        "deep_dive_labs": "Educational labs (guided exercises)",
        "deep_dive_tor": "Tor gateway",
        "tour_complete": "Tour complete! Happy compartmentalizing.",
    },
}


def t(key, lang="en"):
    """Get translated string by key and language."""
    return STRINGS.get(lang, STRINGS["en"]).get(key, key)
