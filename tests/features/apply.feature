# language: fr
Fonctionnalité: Pipeline apply — déploiement de l'infrastructure
  En tant qu'utilisateur anklume
  Je veux déployer mon infrastructure avec `anklume apply`
  Afin que mes domaines soient créés dans Incus

  Contexte:
    Soit un projet anklume valide avec la config par défaut

  Scénario: Déployer un domaine avec une machine
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Alors le projet Incus "pro" est créé
    Et le réseau "net-pro" est créé dans le projet "pro"
    Et l'instance "pro-dev" est créée dans le projet "pro"
    Et l'instance "pro-dev" est démarrée

  Scénario: Déployer plusieurs domaines
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Et un domaine "perso" avec la machine "web" de type "lxc"
    Quand je lance "apply all"
    Alors le projet Incus "pro" est créé
    Et le projet Incus "perso" est créé
    Et l'instance "pro-dev" est créée dans le projet "pro"
    Et l'instance "perso-web" est créée dans le projet "perso"

  Scénario: Déployer un seul domaine spécifique
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Et un domaine "perso" avec la machine "web" de type "lxc"
    Quand je lance "apply domain pro"
    Alors le projet Incus "pro" est créé
    Et le projet Incus "perso" n'est pas créé

  Scénario: Dry-run n'exécute rien
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Quand je lance "apply all --dry-run"
    Alors aucune action n'est exécutée sur Incus
    Et le plan contient 4 actions

  Scénario: Domaine désactivé est ignoré
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Et un domaine désactivé "test" avec la machine "tmp" de type "lxc"
    Quand je lance "apply all"
    Alors le projet Incus "pro" est créé
    Et le projet Incus "test" n'est pas créé

  Scénario: Idempotence — tout existe déjà
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Et le projet Incus "pro" existe déjà
    Et le réseau "net-pro" existe déjà dans le projet "pro"
    Et l'instance "pro-dev" existe et tourne dans le projet "pro"
    Quand je lance "apply all"
    Alors aucune action n'est exécutée sur Incus

  Scénario: Instance arrêtée est redémarrée
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Et le projet Incus "pro" existe déjà
    Et le réseau "net-pro" existe déjà dans le projet "pro"
    Et l'instance "pro-dev" existe et est arrêtée dans le projet "pro"
    Quand je lance "apply all"
    Alors l'instance "pro-dev" est démarrée
    Et aucune création n'est effectuée

  Scénario: Machine VM utilise le type virtual-machine
    Soit un domaine "pro" avec la machine "desktop" de type "vm"
    Quand je lance "apply all"
    Alors l'instance "pro-desktop" est créée comme "virtual-machine"

  Scénario: Protection delete sur machine non-éphémère
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Alors l'instance "pro-dev" a la config "security.protection.delete" à "true"

  Scénario: Pas de protection delete sur machine éphémère
    Soit un domaine éphémère "tmp" avec la machine "sandbox" de type "lxc"
    Quand je lance "apply all"
    Alors l'instance "tmp-sandbox" n'a pas la config "security.protection.delete"

  Scénario: Erreur sur un domaine n'arrête pas les autres
    Soit un domaine "alpha" avec la machine "dev" de type "lxc"
    Et un domaine "beta" avec la machine "web" de type "lxc"
    Et la création du projet "alpha" échoue
    Quand je lance "apply all"
    Alors le projet Incus "beta" est créé
    Et des erreurs sont rapportées

  Scénario: Réseau configuré avec le gateway du domaine
    Soit un domaine "pro" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Alors le réseau "net-pro" est configuré avec le gateway du domaine "pro"
