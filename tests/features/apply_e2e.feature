# language: fr
@e2e
Fonctionnalité: Pipeline apply E2E — déploiement réel sur Incus
  En tant qu'utilisateur anklume
  Je veux déployer mon infrastructure sur Incus
  Afin de valider le pipeline complet contre le vrai moteur

  Contexte:
    Soit un projet anklume valide avec la config par défaut

  Scénario: Déployer un domaine avec une machine
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Alors le projet Incus "bdd-alpha" existe dans Incus
    Et le réseau "net-bdd-alpha" existe dans le projet Incus "bdd-alpha"
    Et l'instance "bdd-alpha-dev" existe dans le projet Incus "bdd-alpha"
    Et l'instance "bdd-alpha-dev" a le statut "Running" dans le projet Incus "bdd-alpha"

  Scénario: Déployer plusieurs domaines
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Et un domaine "bdd-beta" avec la machine "web" de type "lxc"
    Quand je lance "apply all"
    Alors le projet Incus "bdd-alpha" existe dans Incus
    Et le projet Incus "bdd-beta" existe dans Incus
    Et l'instance "bdd-alpha-dev" existe dans le projet Incus "bdd-alpha"
    Et l'instance "bdd-beta-web" existe dans le projet Incus "bdd-beta"

  Scénario: Déployer un seul domaine spécifique
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Et un domaine "bdd-beta" avec la machine "web" de type "lxc"
    Quand je lance "apply domain bdd-alpha"
    Alors le projet Incus "bdd-alpha" existe dans Incus
    Et le projet Incus "bdd-beta" n'existe pas dans Incus

  Scénario: Dry-run ne crée rien dans Incus
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Quand je lance "apply all --dry-run"
    Alors le projet Incus "bdd-alpha" n'existe pas dans Incus

  Scénario: Idempotence — deuxième apply ne change rien
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Et je lance "apply all"
    Alors le résultat de réconciliation est vide

  Scénario: Instance arrêtée est redémarrée
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Et j'arrête l'instance "bdd-alpha-dev" dans le projet "bdd-alpha"
    Et je lance "apply all"
    Alors l'instance "bdd-alpha-dev" a le statut "Running" dans le projet Incus "bdd-alpha"

  Scénario: Protection delete sur machine non-éphémère
    Soit un domaine "bdd-alpha" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Alors la config Incus "security.protection.delete" de "bdd-alpha-dev" dans "bdd-alpha" vaut "true"

  Scénario: Pas de protection delete sur machine éphémère
    Soit un domaine éphémère "bdd-alpha" avec la machine "dev" de type "lxc"
    Quand je lance "apply all"
    Alors la config Incus "security.protection.delete" de "bdd-alpha-dev" dans "bdd-alpha" ne vaut pas "true"
