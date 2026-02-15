> **Note** : La version anglaise (`desktop-integration.md`) fait foi en
> cas de divergence.

# Integration Bureau

AnKLuMe fournit une integration avec les environnements de bureau pour
les utilisateurs de stations de travail. Les codes couleur par domaine
dans les terminaux et gestionnaires de fenetres donnent un retour visuel
instantane sur le domaine de securite en cours — le meme modele que les
bordures colorees de QubesOS.

## Demarrage rapide

```bash
make console                    # Console tmux avec panneaux colores
make domain-exec I=pro-dev TERMINAL=1  # Terminal colore par domaine
make clipboard-to I=pro-dev     # Presse-papier hote -> conteneur
make clipboard-from I=pro-dev   # Presse-papier conteneur -> hote
make desktop-config             # Generer les configs Sway/foot/.desktop
make dashboard                  # Dashboard web sur http://localhost:8888
```

## Console tmux (Phase 19a)

La console tmux genere automatiquement une session depuis `infra.yml`
avec des panneaux colores par domaine. Les couleurs sont definies
**cote serveur** — les conteneurs ne peuvent pas usurper leur identite
visuelle (meme modele de securite que QubesOS).

| Niveau de confiance | Couleur | Code tmux |
|---------------------|---------|-----------|
| admin | Bleu fonce | colour17 |
| trusted | Vert fonce | colour22 |
| semi-trusted | Jaune fonce | colour58 |
| untrusted | Rouge fonce | colour52 |
| disposable | Magenta fonce | colour53 |

## Transfert de presse-papier

Partage controle du presse-papier entre l'hote et les conteneurs.
Chaque transfert est une **action explicite de l'utilisateur** — pas
de synchronisation automatique entre domaines.

```bash
# Presse-papier hote -> conteneur
make clipboard-to I=pro-dev

# Presse-papier conteneur -> hote
make clipboard-from I=pro-dev
```

### Modele de securite

- Chaque transfert est une decision consciente de l'utilisateur
- Pas de daemon, pas de synchronisation en arriere-plan
- Chaque direction est une commande separee
- Le conteneur ne peut pas declencher de lectures du presse-papier hote

## Wrapper domain-exec

Lance des commandes dans les conteneurs avec le contexte du domaine :

```bash
make domain-exec I=pro-dev              # Shell interactif
make domain-exec I=pro-dev TERMINAL=1   # Fenetre terminal coloree
scripts/domain-exec.sh pro-dev -- htop  # Commande specifique
```

Variables d'environnement definies dans le conteneur :
- `ANKLUME_DOMAIN` — nom du domaine
- `ANKLUME_TRUST_LEVEL` — niveau de confiance
- `ANKLUME_INSTANCE` — nom de l'instance

## Integration environnement de bureau

```bash
make desktop-config   # Genere toutes les configurations
```

Fichiers generes dans `desktop/` :
- `sway-anklume.conf` — regles Sway/i3 pour colorer les bordures
- `foot-anklume.ini` — profils foot terminal
- `anklume-*.desktop` — entrees pour les menus d'application

## Dashboard Web

Statut de l'infrastructure en direct dans un navigateur :

```bash
make dashboard              # http://localhost:8888
make dashboard PORT=9090    # Port personnalise
```

Fonctionnalites :
- Statut des instances en temps reel (actualisation toutes les 5s)
- Cartes d'instances colorees par domaine
- Liste des reseaux avec informations de sous-reseau
- Visualisation des politiques reseau
- Aucune dependance Python externe (stdlib + htmx CDN)
- **Lecture seule** — le dashboard ne modifie pas l'infrastructure
