"""i18n strings for the anklume capability guide.

Bilingual (fr/en) text for chapter explanations, recaps, and UI labels.
Pattern follows welcome_strings.py.
"""

STRINGS = {
    "fr": {
        "guide_title": "Prise en main d'anklume",
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
            "Tout le travail avec anklume se fait depuis anklume-instance, "
            "un conteneur dédié qui a accès au socket Incus et au "
            "framework.\n\n"
            "Entrez dans anklume-instance :\n\n"
            "  incus exec anklume-instance -- bash -l\n\n"
            "Vérifiez que la CLI fonctionne :\n\n"
            "  anklume --help\n\n"
            "anklume décrit votre infrastructure dans un seul fichier : "
            "infra.yml. Ce fichier déclare vos domaines (zones isolées), "
            "les machines dans chaque domaine, et les niveaux de confiance.\n\n"
            "Créez votre premier infra.yml :\n\n"
            "  anklume init\n\n"
            "Le fichier créé contient deux domaines isolés :\n\n"
            "- 'pro' (semi-trusted, IP 10.120.x.x) — espace professionnel\n"
            "- 'perso' (trusted, IP 10.110.x.x) — espace personnel\n\n"
            "Consultez le contenu :\n\n"
            "  cat infra.yml"
        ),
        "ch1_recap": "infra.yml est la source de vérité — tout passe par anklume-instance",
        "ch2_explain": (
            "Maintenant, générez les fichiers Ansible à partir de infra.yml, "
            "puis déployez l'infrastructure sur Incus.\n\n"
            "Étape 1 — Prévisualisez ce que anklume va générer :\n\n"
            "  anklume sync --dry-run\n\n"
            "Étape 2 — Générez les fichiers :\n\n"
            "  anklume sync\n\n"
            "Ceci crée inventory/, group_vars/ et host_vars/ — les fichiers "
            "Ansible qui décrivent votre infra. Vous pouvez les personnaliser "
            "en dehors des sections '=== MANAGED ==='.\n\n"
            "Étape 3 — Déployez sur Incus :\n\n"
            "  anklume domain apply\n\n"
            "anklume crée les projets Incus, les réseaux (bridges), "
            "et lance vos conteneurs."
        ),
        "ch2_recap": "anklume sync génère, anklume domain apply déploie",
        "ch3_explain": (
            "Voyons ce que anklume a créé. Chaque domaine a son propre "
            "projet Incus et son bridge réseau :\n\n"
            "  anklume instance list\n\n"
            "Vous devriez voir vos conteneurs pro-dev et perso-desktop "
            "dans leurs projets respectifs.\n\n"
            "  anklume network list\n\n"
            "Les bridges net-pro et net-perso isolent le trafic de chaque "
            "domaine. Les machines d'un domaine ne peuvent pas atteindre "
            "celles d'un autre — c'est le principe de compartimentalisation."
        ),
        "ch3_recap": "Chaque domaine est isolé dans son propre réseau et projet",
        "ch4_explain": (
            "Par défaut, tout trafic entre domaines est bloqué par nftables. "
            "pro-dev ne peut pas pinger perso-desktop, et vice-versa.\n\n"
            "Pour vérifier :\n\n"
            "  anklume network rules\n\n"
            "Ceci génère les règles nftables. Pour les appliquer :\n\n"
            "  anklume network deploy\n\n"
            "Si vous avez besoin qu'un domaine accède à un service dans "
            "un autre, ajoutez une network_policy dans infra.yml :\n\n"
            "  network_policies:\n"
            "    - description: \"Pro accède au DNS partagé\"\n"
            "      from: pro\n"
            "      to: shared-dns\n"
            "      ports: [53]\n"
            "      protocol: udp\n"
        ),
        "ch4_recap": "L'isolation réseau est active par défaut entre domaines",
        "ch5_explain": (
            "Les snapshots sauvegardent l'état complet d'une instance. "
            "Vous pouvez restaurer en un instant après une erreur.\n\n"
            "Créez un snapshot de pro-dev :\n\n"
            "  anklume snapshot create --instance pro-dev --name avant-test\n\n"
            "Faites des modifications dans le conteneur, puis restaurez :\n\n"
            "  anklume snapshot restore --instance pro-dev --name avant-test\n\n"
            "Listez les snapshots :\n\n"
            "  anklume snapshot list"
        ),
        "ch5_recap": "Les snapshots permettent un retour arrière instantané",
        "ch6_explain": (
            "Votre infra.yml minimal fonctionne. Voici comment l'enrichir :\n\n"
            "Ajouter un domaine sandbox jetable :\n\n"
            "  sandbox:\n"
            "    description: \"Bac à sable jetable\"\n"
            "    trust_level: disposable\n"
            "    ephemeral: true\n"
            "    machines:\n"
            "      sandbox-test:\n"
            "        type: lxc\n\n"
            "Ajouter un profil avec limites de ressources :\n\n"
            "  pro:\n"
            "    profiles:\n"
            "      limited:\n"
            "        config:\n"
            "          limits.cpu: \"2\"\n"
            "          limits.memory: \"4GiB\"\n"
            "    machines:\n"
            "      pro-dev:\n"
            "        profiles: [default, limited]\n\n"
            "Après modification :\n\n"
            "  anklume sync && anklume domain apply"
        ),
        "ch6_recap": "Modifiez infra.yml puis sync + apply pour déployer",
        "ch7_explain": (
            "Le dashboard web affiche l'état de votre infrastructure "
            "en temps réel : instances, réseaux, politiques réseau.\n\n"
            "Lancez-le :\n\n"
            "  anklume dashboard\n\n"
            "Ouvrez votre navigateur sur l'URL affichée pour voir "
            "vos domaines, leurs instances et leur état."
        ),
        "ch7_recap": "Le dashboard donne une vue d'ensemble en temps réel",
        "ch8_explain": (
            "Vous avez déployé votre première infrastructure anklume !\n\n"
            "Pour aller plus loin :\n\n"
            "• GPU & IA locale — passez le GPU aux conteneurs pour "
            "Ollama (LLM local)\n"
            "• Labs — exercices guidés pour approfondir\n"
            "• Passerelle Tor — routez le trafic via Tor\n"
            "• Console tmux — fenêtres colorées par domaine\n"
            "• Applications graphiques — affichez les GUI des "
            "conteneurs sur votre bureau\n\n"
            "Documentation complète :\n\n"
            "  anklume --help\n"
            "  cat docs/SPEC.md\n"
            "  cat docs/quickstart.md"
        ),
        "ch8_recap": "Bonne compartimentation !",
        "deep_dive_title": "Pour aller plus loin",
        "deep_dive_network": "Isolation réseau avancée (nftables, firewall VM)",
        "deep_dive_gpu": "GPU & services IA (Ollama, VRAM flush)",
        "deep_dive_labs": "Labs éducatifs (exercices guidés)",
        "deep_dive_tor": "Gateway Tor",
        "tour_complete": "Tour terminé ! Bonne compartimentation.",
    },
    "en": {
        "guide_title": "Getting Started with anklume",
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
            "All work with anklume happens inside anklume-instance, "
            "a dedicated container with access to the Incus socket and "
            "the framework.\n\n"
            "Enter anklume-instance:\n\n"
            "  incus exec anklume-instance -- bash -l\n\n"
            "Verify the CLI works:\n\n"
            "  anklume --help\n\n"
            "anklume describes your infrastructure in a single file: "
            "infra.yml. This file declares your domains (isolated zones), "
            "the machines in each domain, and trust levels.\n\n"
            "Create your first infra.yml:\n\n"
            "  anklume init\n\n"
            "The generated file contains two isolated domains:\n\n"
            "- 'work' (semi-trusted, IP 10.120.x.x) — professional workspace\n"
            "- 'personal' (trusted, IP 10.110.x.x) — personal space\n\n"
            "Check the content:\n\n"
            "  cat infra.yml"
        ),
        "ch1_recap": "infra.yml is the source of truth — everything goes through anklume-instance",
        "ch2_explain": (
            "Now generate Ansible files from infra.yml, then deploy "
            "the infrastructure to Incus.\n\n"
            "Step 1 — Preview what anklume will generate:\n\n"
            "  anklume sync --dry-run\n\n"
            "Step 2 — Generate the files:\n\n"
            "  anklume sync\n\n"
            "This creates inventory/, group_vars/, and host_vars/ — the "
            "Ansible files describing your infra. You can customize them "
            "outside the '=== MANAGED ===' sections.\n\n"
            "Step 3 — Deploy to Incus:\n\n"
            "  anklume domain apply\n\n"
            "anklume creates Incus projects, networks (bridges), "
            "and launches your containers."
        ),
        "ch2_recap": "anklume sync generates, anklume domain apply deploys",
        "ch3_explain": (
            "Let's see what anklume created. Each domain gets its own "
            "Incus project and network bridge:\n\n"
            "  anklume instance list\n\n"
            "You should see your containers work-dev and personal-desktop "
            "in their respective projects.\n\n"
            "  anklume network list\n\n"
            "Bridges net-work and net-personal isolate each domain's "
            "traffic. Machines in one domain cannot reach machines in "
            "another — that's compartmentalization."
        ),
        "ch3_recap": "Each domain is isolated in its own network and project",
        "ch4_explain": (
            "By default, all inter-domain traffic is blocked by nftables. "
            "work-dev cannot ping personal-desktop, and vice versa.\n\n"
            "To verify:\n\n"
            "  anklume network rules\n\n"
            "This generates the nftables rules. To apply them:\n\n"
            "  anklume network deploy\n\n"
            "If you need one domain to access a service in another, "
            "add a network_policy to infra.yml:\n\n"
            "  network_policies:\n"
            "    - description: \"Work accesses shared DNS\"\n"
            "      from: work\n"
            "      to: shared-dns\n"
            "      ports: [53]\n"
            "      protocol: udp\n"
        ),
        "ch4_recap": "Network isolation is active by default between domains",
        "ch5_explain": (
            "Snapshots save the complete state of an instance. "
            "Restore instantly after a mistake.\n\n"
            "Create a snapshot of work-dev:\n\n"
            "  anklume snapshot create --instance work-dev --name before-test\n\n"
            "Make changes in the container, then restore:\n\n"
            "  anklume snapshot restore --instance work-dev --name before-test\n\n"
            "List all snapshots:\n\n"
            "  anklume snapshot list"
        ),
        "ch5_recap": "Snapshots provide instant rollback",
        "ch6_explain": (
            "Your minimal infra.yml works. Here's how to extend it:\n\n"
            "Add a disposable sandbox domain:\n\n"
            "  sandbox:\n"
            "    description: \"Disposable sandbox\"\n"
            "    trust_level: disposable\n"
            "    ephemeral: true\n"
            "    machines:\n"
            "      sandbox-test:\n"
            "        type: lxc\n\n"
            "Add a profile with resource limits:\n\n"
            "  work:\n"
            "    profiles:\n"
            "      limited:\n"
            "        config:\n"
            "          limits.cpu: \"2\"\n"
            "          limits.memory: \"4GiB\"\n"
            "    machines:\n"
            "      work-dev:\n"
            "        profiles: [default, limited]\n\n"
            "After changes:\n\n"
            "  anklume sync && anklume domain apply"
        ),
        "ch6_recap": "Edit infra.yml then sync + apply to deploy changes",
        "ch7_explain": (
            "The web dashboard shows live infrastructure status: "
            "instances, networks, network policies.\n\n"
            "Launch it:\n\n"
            "  anklume dashboard\n\n"
            "Open the displayed URL in your browser to see your "
            "domains, instances, and their status."
        ),
        "ch7_recap": "The dashboard gives a real-time overview",
        "ch8_explain": (
            "You've deployed your first anklume infrastructure!\n\n"
            "Next steps:\n\n"
            "- GPU & local AI — pass the GPU to containers for "
            "Ollama (local LLM)\n"
            "- Labs — guided exercises to deepen your skills\n"
            "- Tor gateway — route traffic through Tor\n"
            "- Tmux console — color-coded domain windows\n"
            "- GUI app forwarding — display container GUIs on "
            "your desktop\n\n"
            "Full documentation:\n\n"
            "  anklume --help\n"
            "  cat docs/SPEC.md\n"
            "  cat docs/quickstart.md"
        ),
        "ch8_recap": "Happy compartmentalizing!",
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
