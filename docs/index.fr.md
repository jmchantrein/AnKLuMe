---
title: Accueil
---

# anklume

Isolation de type QubesOS utilisant les fonctionnalites natives du noyau
Linux (KVM/LXC), orchestree sereinement par Ansible, Incus et Molecule.

## Qu'est-ce qu'anklume ?

anklume est un framework declaratif de cloisonnement d'infrastructure.
Decrivez votre infrastructure dans un seul fichier YAML (`infra.yml`),
lancez `anklume sync && anklume domain apply`, et obtenez des
environnements isoles, reproductibles et jetables.

## Liens rapides

- [Demarrage rapide](quickstart.md) - Premiers pas
- [Specification](SPEC.md) - Specification technique complete
- [Decisions d'architecture](ARCHITECTURE.md) - Registre des ADR
- [Feuille de route](ROADMAP.md) - Phases d'implementation

## Principes de conception

- **Declaratif** : un seul fichier YAML decrit tout
- **Natif** : utilise les fonctionnalites du noyau Linux (namespaces, cgroups, nftables)
- **Minimal** : assemble des outils standard (Ansible, Incus, nftables)
- **Sur par defaut** : adressage IP par zone de confiance, isolation nftables
- **Pret pour l'IA** : IA integree optionnelle respectant les frontieres de domaine

## Licence

AGPL-3.0
