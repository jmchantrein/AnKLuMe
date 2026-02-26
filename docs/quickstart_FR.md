# Guide de Demarrage Rapide

> Traduction francaise de [`quickstart.md`](quickstart.md). En cas de divergence, la version anglaise fait foi.

Ce guide vous accompagne dans le deploiement de votre premiere infrastructure
anklume depuis zero.

## Prerequis

### Machine hote

- Un hote Linux (Debian, Arch, Ubuntu, Fedora)
- [Incus](https://linuxcontainers.org/incus/docs/main/installing/) >= 6.0
  LTS installe et initialise (`incus admin init`)
- Au moins 4 Go de RAM et 20 Go d'espace disque libre

### Instance d'administration

anklume fonctionne entierement depuis un container d'administration. Creez-le
manuellement sur votre hote :

```bash
# Creer le container d'administration
incus launch images:debian/13 anklume-instance

# Monter le socket Incus (necessaire pour gerer les autres instances)
incus config device add anklume-instance incus-socket proxy \
  connect=unix:/var/lib/incus/unix.socket \
  listen=unix:/var/run/incus/unix.socket \
  bind=container \
  security.uid=0 security.gid=0

# Activer l'imbrication (necessaire pour le CLI Incus dans le container)
incus config set anklume-instance security.nesting=true

# Entrer dans le container
incus exec anklume-instance -- bash
```

A l'interieur du container d'administration, installez les outils requis :

```bash
apt update && apt install -y ansible python3-pip python3-yaml git curl
pip install --break-system-packages pyyaml pytest molecule ruff
```

## Etape 1 : Cloner le depot

```bash
git clone https://github.com/<user>/anklume.git
cd anklume
```

## Etape 2 : Installer les dependances

```bash
anklume setup init
```

Cela installe les collections Ansible et les outils Python. Vous devriez
voir une sortie se terminant par des instructions pour les paquets systeme.

## Etape 3 : Creer votre descripteur d'infrastructure

```bash
cp infra.yml.example infra.yml
```

Editez `infra.yml` pour decrire votre infrastructure. Voici un exemple
minimal avec deux domaines :

Consultez `infra.yml.example` pour un modele complet, ou copiez-en un depuis
le repertoire [examples/](../examples/). Regles principales :

- **Noms de domaine** : minuscules alphanumeriques + tirets uniquement
- **Noms de machine** : doivent etre globalement uniques entre tous les domaines
- **subnet_id** : entier 0-254, unique par domaine
- **IPs** : auto-assignees depuis `10.<zone>.<seq>.<host>` (voir ADR-038)
- **Passerelle** : `.254` est attribuee automatiquement, ne l'utilisez pas pour les machines

Voir [SPEC.md section 5](SPEC.md) pour la reference complete du format.

## Etape 4 : Generer les fichiers Ansible

```bash
anklume sync
```

Sortie attendue :

```
Generating files for 2 domain(s)...
  Written: group_vars/all.yml
  Written: inventory/anklume.yml
  Written: group_vars/anklume.yml
  Written: host_vars/anklume-instance.yml
  Written: inventory/lab.yml
  Written: group_vars/lab.yml
  Written: host_vars/lab-server.yml

Done. Run `anklume dev lint` to validate.
```

Cela cree et met a jour des fichiers dans `inventory/`, `group_vars/` et
`host_vars/`. Chaque fichier contient une section `=== MANAGED ===` qui est
reecrite a chaque `anklume sync`. Vous pouvez ajouter des variables personnalisees
en dehors de cette section.

## Etape 5 : Previsualiser les changements

```bash
anklume domain check
```

Cela execute `ansible-playbook --check --diff` pour montrer ce qui changerait
sans modifier quoi que ce soit. Examinez la sortie pour verifier que votre
infrastructure est correcte.

## Etape 6 : Appliquer

```bash
anklume domain apply
```

Cela cree tous les reseaux, projets Incus, profils et instances definis
dans votre `infra.yml`. Lors d'une installation neuve, vous verrez toutes
les ressources creees. Lors des executions suivantes, seuls les changements
sont appliques (idempotent).

## Etape 7 : Verifier

Apres la fin de `anklume domain apply`, verifiez votre infrastructure :

```bash
# Lister toutes les instances Incus dans tous les projets
incus list --all-projects

# Verifier le reseau d'un domaine specifique
incus network show net-lab

# Entrer dans un container
incus exec lab-server --project lab -- bash
```

## Flux de travail courant

Apres votre installation initiale, le flux de travail quotidien est :

1. Editer `infra.yml` (ajouter des domaines, machines, profils)
2. `anklume sync` pour regenerer les fichiers Ansible
3. `anklume domain check` pour previsualiser les changements
4. `anklume domain apply` pour converger

## Commandes utiles

| Commande | Description |
|----------|-------------|
| `anklume sync` | Generer les fichiers Ansible depuis infra.yml |
| `anklume sync --dry-run` | Previsualiser la generation sans ecrire |
| `anklume domain check` | Execution a blanc (--check --diff) |
| `anklume domain apply` | Appliquer toute l'infrastructure |
| `anklume domain apply lab` | Appliquer un seul domaine |
| `anklume snapshot create` | Prendre un snapshot de toutes les instances |
| `anklume dev lint` | Executer tous les validateurs |
| `anklume --help` | Lister toutes les cibles disponibles |

## Depannage

- **Erreurs de validation sur anklume sync** : Le generateur verifie toutes
  les contraintes (noms uniques, sous-reseaux uniques, IPs valides) avant
  d'ecrire. Lisez le message d'erreur pour identifier la contrainte specifique
  qui a echoue.
- **Socket Incus introuvable** : Verifiez que le peripherique proxy est
  configure avec `incus config device show anklume-instance`
- **Le container ne demarre pas apres un redemarrage** : Le repertoire
  `/var/run/incus/` peut ne pas exister. Voir ADR-019 dans
  [ARCHITECTURE.md](ARCHITECTURE.md).
- **anklume domain apply bloque** : Verifiez qu'Incus fonctionne (`systemctl status incus`)
  et que le socket est accessible (`incus list` depuis anklume-instance).

## Etapes suivantes

- [Guide de deploiement de TP](lab-tp.md) pour les enseignants
- [Guide GPU + LLM](gpu-llm.md) pour le passthrough GPU et Ollama
- [Exemples de configurations](../examples/) pour des fichiers infra.yml prets a l'emploi
- [Specification complete](SPEC.md) pour la reference complete du format
