> **Note** : La version anglaise (`incus-coverage.md`) fait reference en cas
> de divergence.

# Couverture des fonctionnalites natives Incus

AnKLuMe est une interface declarative haut niveau pour Incus. Il gere les
ressources Incus (projets, reseaux, profils, instances) via le CLI, en
exploitant les fonctionnalites natives autant que possible et en ajoutant
une logique specifique uniquement la ou Incus ne couvre pas le besoin.

## Positionnement

AnKLuMe ne remplace pas Incus. Il fournit :
- Un fichier YAML unique (`infra.yml`) decrivant toute l'infrastructure
- La generation automatique de l'inventaire et des variables Ansible
- Une gestion idempotente par reconciliation des ressources Incus
- L'isolation reseau inter-domaines via nftables
- Des outils de cycle de vie (snapshots, flush, import, upgrade)

Toutes les fonctionnalites Incus restent accessibles via le CLI
en parallele d'AnKLuMe.

## Matrice de couverture

| Fonctionnalite Incus | Couverture | Comment |
|----------------------|------------|---------|
| **Projets** | Complete | Role `incus_projects` cree un projet par domaine |
| **Bridges (geres)** | Complete | Role `incus_networks` cree les bridges `net-*` |
| **Profils** | Complete | Role `incus_profiles` + `profiles:` dans infra.yml |
| **Instances LXC** | Complete | Role `incus_instances`, `type: lxc` |
| **VMs KVM** | Complete | Role `incus_instances`, `type: vm` avec `--vm` |
| **IPs statiques** | Complete | Override de device sur `eth0` du profil par defaut |
| **GPU passthrough (LXC)** | Complete | Profil `nvidia-compute` |
| **GPU passthrough (VM)** | Documente | Profil avec adresse PCI |
| **Config d'instance** | Complete | `config:` dans infra.yml propage a `incus config set` |
| **Volumes de stockage** | Complete | `storage_volumes:` dans infra.yml |
| **Instances ephemeres** | Complete | Flag `--ephemeral` sur `incus launch` |
| **boot.autostart** | Complete | `boot_autostart:` dans infra.yml |
| **boot.autostart.priority** | Complete | `boot_priority:` dans infra.yml (0-100) |
| **security.protection.delete** | Complete | Derive de `ephemeral: false` |
| **snapshots.schedule** | Complete | Expression cron `snapshots_schedule:` |
| **snapshots.expiry** | Complete | Duree de retention `snapshots_expiry:` |
| **Snapshots manuels** | Complete | `scripts/snap.sh` encapsule `incus snapshot` |
| **Cache d'images** | Complete | Role `incus_images` pre-telecharge les images |
| **Export/import d'images** | Complete | Depot partage entre niveaux d'imbrication |
| **Imbrication** | Complete | Profil `security.nesting` + role `incus_nesting` |
| **Devices proxy** | Complete | Socket Incus redirige vers le conteneur anklume |
| **Cloud-init** | Partiel | Supporte via `config:`, pas d'abstraction dediee |
| **Limites (CPU/memoire)** | Complete | Cles `config:` + `resource_policy` auto |
| **Network ACLs** | Non utilise | Voir explication ci-dessous |
| **Network Zones** | Non utilise | Voir explication ci-dessous |
| **Reseau OVN** | Non utilise | Voir explication ci-dessous |
| **Clustering** | Hors perimetre | AnKLuMe cible les deploiements mono-hote |
| **Conteneurs OCI** | Hors perimetre | AnKLuMe gere LXC et KVM uniquement |
| **SR-IOV** | Hors perimetre | Necessite du materiel entreprise |
| **VMs confidentielles (SEV/TDX)** | Hors perimetre | Fonctionnalites CPU specifiques |
| **Authentification OIDC** | Hors perimetre | AnKLuMe utilise le socket Unix local |
| **Serveurs distants** | Hors perimetre | Toutes les operations sont locales |
| **Migration d'instances** | Non couvert | Potentiel pour le multi-hote |
| **pause/resume** | Non couvert | Commande operationnelle, pas de besoin declaratif |

## Fonctionnalites utilisees nativement

AnKLuMe utilise les fonctionnalites natives Incus pour :

- **Isolation par projet** : Chaque domaine est un projet Incus avec un
  namespace separe (`features.networks=false` pour les bridges partages).
- **Heritage de profils** : Les profils (GPU, imbrication, ressources)
  sont appliques via `incus profile assign`.
- **Gestion du demarrage** : `boot.autostart` et `boot.autostart.priority`
  controlent l'ordre de demarrage nativement.
- **Protection contre la suppression** : `security.protection.delete`
  empeche la suppression accidentelle des instances non-ephemeres.
- **Snapshots automatiques** : `snapshots.schedule` et `snapshots.expiry`
  deleguent le cycle de vie des snapshots a Incus.
- **Volumes de stockage** : Crees via `incus storage volume create` et
  attaches comme devices disque.
- **Gestion des images** : `incus image copy` pour le pre-cache,
  export/import pour l'imbrication.

## Logique specifique (pourquoi nftables, pas les Network ACLs)

### Network ACLs

Les Network ACLs Incus operent **au sein d'un seul bridge** (filtrage
intra-reseau). Elles controlent le trafic entre instances sur le meme
bridge.

Le besoin d'isolation d'AnKLuMe est **cross-bridge** : bloquer le
forwarding entre `net-pro` et `net-perso`. Les ACLs ne peuvent pas
appliquer cela car elles ne voient pas le trafic traversant les
limites des bridges au niveau du noyau hote.

Le role `incus_nftables` genere des regles nftables au niveau hote dans
une table separee (`inet anklume`) a la priorite -1, qui s'execute
avant les chaines gerees par Incus et rejette le trafic inter-bridges.

Les Network ACLs pourraient completer nftables en defense en profondeur
(filtrage intra-bridge en plus de l'isolation cross-bridge), mais cela
n'est pas actuellement implemente.

### Network Zones

Les Network Zones Incus fournissent des enregistrements DNS auto-generes
pour les instances. C'est complementaire a la gestion d'IP d'AnKLuMe
mais ne la remplace pas. AnKLuMe utilise des IPs statiques attribuees
via des overrides de devices, pas de resolution DNS. Les Network Zones
pourraient etre integrees dans une phase future pour la decouverte de
services basee sur DNS.

### Reseau OVN

OVN (Open Virtual Network) fournit un reseau defini par logiciel avec
des routeurs distribues et des ACLs. Il est concu pour les clusters
multi-hotes et ajoute une complexite significative. AnKLuMe cible les
deploiements mono-hote ou les bridges Linux + nftables fournissent
une isolation suffisante avec moins de surcharge.

## Feuille de route pour integration future

| Fonctionnalite | Benefice | Priorite |
|----------------|----------|----------|
| Network Zones (DNS) | DNS auto-genere pour les instances | Moyenne |
| Network ACLs (defense en profondeur) | Filtrage intra-bridge | Basse |
| Migration d'instances | Deploiements multi-hotes | Basse |
| Limites de ressources par projet | Plafonds par domaine | Moyenne |
| pause/resume | Suspendre/reprendre a la demande | Basse |
