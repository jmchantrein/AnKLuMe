# language: fr
Fonctionnalité: Initialisation de projet
  En tant qu'utilisateur anklume
  Je veux créer un nouveau projet avec `anklume init`
  Afin d'avoir une structure prête à configurer

  Scénario: Créer un projet dans un nouveau répertoire
    Soit un répertoire vide "mon-infra"
    Quand je lance "init mon-infra"
    Alors le fichier "mon-infra/anklume.yml" existe
    Et le répertoire "mon-infra/domains" existe
    Et le fichier "mon-infra/policies.yml" existe

  Scénario: Créer un projet en français par défaut
    Soit un répertoire vide "mon-infra"
    Quand je lance "init mon-infra"
    Alors le fichier "mon-infra/domains/pro.yml" existe

  Scénario: Créer un projet en anglais
    Soit un répertoire vide "my-infra"
    Quand je lance "init my-infra --lang en"
    Alors le fichier "my-infra/domains/work.yml" existe

  Scénario: Refuser un répertoire non vide
    Soit un répertoire non vide "deja-la"
    Quand je lance "init deja-la"
    Alors la commande échoue

  Scénario: Le projet généré est parsable
    Soit un répertoire vide "test-proj"
    Quand je lance "init test-proj"
    Alors le projet "test-proj" peut être parsé par le moteur
