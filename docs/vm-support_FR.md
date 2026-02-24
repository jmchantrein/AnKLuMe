# Support des VMs (Instances KVM)

> Traduction francaise de [`vm-support.md`](vm-support.md). En cas de divergence, la version anglaise fait foi.

anklume supporte a la fois les containers LXC et les machines virtuelles KVM.
Ce guide couvre comment declarer, creer et provisionner des VMs aux cotes
des containers.

## Quand utiliser des VMs ou des containers

| Critere | Container LXC | VM KVM |
|---------|--------------|--------|
| Temps de demarrage | ~1-2 secondes | ~10-30 secondes |
| Overhead de ressources | Minimal (noyau partage) | Plus eleve (noyau complet + UEFI) |
| Niveau d'isolation | Isolation par espaces de noms | Isolation au niveau materiel |
| Passthrough GPU | Direct (nvidia.runtime) | vfio-pci (IOMMU requis) |
| Systemes non-Linux | Non | Oui |
| Noyau personnalise | Non (partage avec l'hote) | Oui |

**Utilisez des VMs quand vous avez besoin** :
- D'une isolation plus forte pour des charges de travail non fiables
- D'une version de noyau differente ou d'un OS non-Linux
- D'un passthrough GPU via vfio-pci avec isolation materielle
- De tester des modules noyau ou des logiciels au niveau systeme

**Utilisez des containers LXC pour tout le reste** -- ils sont plus rapides,
plus legers, et suffisants pour la plupart des cas d'usage de cloisonnement.

## Declarer une VM dans infra.yml

Definissez `type: vm` sur n'importe quelle machine :

```yaml
domains:
  secure:
    description: "Domaine a haute isolation"
    subnet_id: 4
    machines:
      secure-sandbox:
        description: "Bac a sable pour charges non fiables"
        type: vm
        ip: "10.100.4.10"
        roles: [base_system]
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
```

Les VMs et les containers LXC peuvent coexister dans le meme domaine :

```yaml
domains:
  work:
    subnet_id: 2
    machines:
      work-dev:
        type: lxc
        ip: "10.100.2.10"
      work-sandbox:
        type: vm
        ip: "10.100.2.20"
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
```

## Fonctionnement

### Creation d'instance

Le role `incus_instances` branche sur `instance_type` :

- `type: lxc` -> `incus launch <image> <nom> --project <domaine>`
- `type: vm` -> `incus launch <image> <nom> --vm --project <domaine>`

Le meme alias d'image OS fonctionne pour les deux. Incus recupere
automatiquement la bonne variante d'image (rootfs container vs image disque VM).

### Attente de demarrage

Les VMs mettent plus de temps a demarrer que les containers (firmware UEFI + demarrage noyau).
Le role utilise des timeouts differents :

| Type | Tentatives | Delai | Timeout total |
|------|-----------|-------|---------------|
| LXC | 30 | 2s | 60s |
| VM | 60 | 2s | 120s |

Ces valeurs sont configurables via les defauts du role :

```yaml
incus_instances_lxc_retries: 30
incus_instances_lxc_delay: 2
incus_instances_vm_retries: 60
incus_instances_vm_delay: 2
```

### Attente de l'incus-agent

Apres qu'une VM atteint le statut Running, l'`incus-agent` dans la VM
a encore besoin de quelques secondes pour s'initialiser. Le role interroge
`incus exec <vm> -- true` jusqu'a ce que l'agent reponde avant de continuer.

C'est critique : sans un agent en fonctionnement, `incus exec` (et donc
le plugin de connexion `community.general.incus`) ne peut pas se connecter
a la VM, et la phase de provisionnement echouerait.

Configuration de l'attente de l'agent :

```yaml
incus_instances_vm_agent_retries: 30
incus_instances_vm_agent_delay: 2
```

### Provisionnement

Le plugin de connexion `community.general.incus` fonctionne de maniere
identique pour les containers et les VMs. Il utilise `incus exec` en
interne, qui communique avec l'`incus-agent` via virtio-vsock pour les VMs.

Pas de SSH necessaire. Pas de changement dans la phase de provisionnement de `site.yml`.

## Configuration specifique aux VMs

### Limites de ressources

Les valeurs par defaut d'Incus pour les VMs sont 1 vCPU et 1 Gio de memoire.
Surchargez via `config:` dans infra.yml :

```yaml
config:
  limits.cpu: "2"
  limits.memory: "4GiB"
```

### Secure boot

Le secure boot est active par defaut pour les VMs. Pour le desactiver
(ex. pour des tests ou des images non-UEFI) :

```yaml
config:
  security.secureboot: "false"
```

### Profils specifiques aux VMs

Creez un profil au niveau du domaine pour les VMs avec des valeurs par defaut appropriees :

```yaml
domains:
  secure:
    subnet_id: 4
    profiles:
      vm-resources:
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
    machines:
      secure-vm:
        type: vm
        profiles: [default, vm-resources]
```

## Compatibilite des images OS

La plupart des distributions Linux du remote `images:` ont des variantes
container et VM :

| Distribution | Support VM |
|-------------|-----------|
| Debian 13 (trixie) | Oui |
| Ubuntu 24.04+ | Oui |
| Alpine 3.20+ | Oui |
| Fedora 41+ | Oui |
| Arch Linux | Oui (amd64) |

Utilisez la meme reference d'image pour les deux types :

```yaml
# Les deux utilisent images:debian/13 -- Incus choisit la bonne variante
container:
  type: lxc
  os_image: "images:debian/13"

vm:
  type: vm
  os_image: "images:debian/13"
```

## Validation

Le generateur PSOT valide :

- `type` doit etre `lxc` ou `vm` (erreur sur les valeurs invalides)
- Toutes les validations existantes (noms uniques, IPs, sous-reseaux) s'appliquent egalement

## Depannage

### VM bloquee a "Starting"

Les VMs mettent 10 a 30 secondes a demarrer. Le role attend jusqu'a 120 secondes.
Si le timeout est depasse :

```bash
# Verifier la console VM pour les problemes de demarrage
incus console <nom-vm> --project <domaine>

# Verifier le statut de la VM
incus info <nom-vm> --project <domaine>
```

### L'incus-agent ne repond pas

Si le provisionnement echoue avec des erreurs de connexion apres que la VM est Running :

```bash
# Tester l'agent manuellement
incus exec <nom-vm> --project <domaine> -- true

# Verifier le statut de l'agent dans la VM (via la console)
incus console <nom-vm> --project <domaine>
# Puis : systemctl status incus-agent
```

Les images standard `images:` sont livrees avec `incus-agent` pre-configure.
Les images personnalisees peuvent necessiter une installation manuelle de l'agent.

### La VM necessite plus de memoire

Si la VM ne demarre pas ou manque de memoire pendant le provisionnement :

```bash
incus config set <nom-vm> limits.memory=2GiB --project <domaine>
incus restart <nom-vm> --project <domaine>
```
