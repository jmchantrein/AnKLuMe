# Gestion Avancee du GPU

> Traduction francaise de [`gpu-advanced.md`](gpu-advanced.md). En cas de divergence, la version anglaise fait foi.

anklume supporte le passthrough GPU pour les containers LXC et les VMs KVM,
avec une politique de securite qui controle combien d'instances peuvent
acceder au GPU simultanement.

## Politique d'acces GPU (ADR-018)

Par defaut, anklume applique un acces GPU **exclusif** : une seule instance
dans tous les domaines peut avoir acces au GPU. Cela previent les conflits
de VRAM et les risques de securite lies a la memoire GPU partagee sur les
GPUs grand public.

### Mode exclusif (defaut)

```yaml
# infra.yml -- une SEULE machine peut avoir gpu: true
global:
  addressing:
    base_octet: 10
    zone_base: 100
  # gpu_policy: exclusive  # C'est le defaut

domains:
  homelab:
    subnet_id: 3
    profiles:
      nvidia-compute:
        devices:
          gpu:
            type: gpu
            gputype: physical
    machines:
      homelab-llm:
        type: lxc
        gpu: true
        profiles: [default, nvidia-compute]
```

Si vous ajoutez une seconde machine GPU en mode exclusif, `anklume sync` echouera :

```
Validation errors:
  - GPU policy is 'exclusive' but 2 instances have GPU access:
    homelab-llm, work-gpu. Set global.gpu_policy: shared to allow this.
```

### Mode partage

Pour les charges de travail qui beneficient d'un acces GPU concurrent
(ex. plusieurs serveurs d'inference LLM), activez le mode partage :

```yaml
global:
  gpu_policy: shared  # Permettre a plusieurs instances de partager le GPU
```

`anklume sync` emettra un avertissement mais continuera :

```
WARNING: GPU policy is 'shared': 2 instances share GPU access
(homelab-llm, work-gpu). No VRAM isolation on consumer GPUs.
```

**Risques de l'acces GPU partage :**
- Pas d'isolation VRAM sur les GPUs grand public (pas de SR-IOV)
- L'etat partage du pilote pourrait causer des plantages sous charge
- Tout container avec acces GPU peut lire la memoire GPU

## GPU dans les containers LXC

Le passthrough GPU LXC expose le pilote GPU de l'hote directement au
container via le type de peripherique `gpu`.

### Configuration du profil

Definissez un profil `nvidia-compute` dans le domaine :

```yaml
profiles:
  nvidia-compute:
    devices:
      gpu:
        type: gpu
        gputype: physical
```

### Configuration de la machine

```yaml
machines:
  my-gpu-container:
    type: lxc
    gpu: true
    profiles: [default, nvidia-compute]
    roles: [base_system, ollama_server]
```

### Fonctionnement

1. Le profil ajoute un peripherique `gpu` avec `type: gpu` a l'instance
2. Incus monte les noeuds de peripherique GPU (`/dev/nvidia*`) dans le container
3. Le pilote NVIDIA de l'hote est accessible dans le container
4. `nvidia-smi` fonctionne dans le container sans configuration supplementaire

### Verification

```bash
incus exec homelab-llm --project homelab -- nvidia-smi
```

## GPU dans les VMs KVM

Le passthrough GPU des VMs utilise **vfio-pci**, qui fournit une isolation
au niveau materiel en liant le peripherique PCI directement a la VM.

### Prerequis

- IOMMU doit etre active dans le BIOS et le noyau (`intel_iommu=on` ou
  `amd_iommu=on`)
- Le GPU doit etre dans son propre groupe IOMMU (ou surcharge ACS appliquee)
- Le module noyau `vfio-pci` doit etre charge

### Configuration du profil pour les VMs

```yaml
profiles:
  gpu-passthrough:
    devices:
      gpu:
        type: gpu
        pci: "0000:01:00.0"  # Adresse PCI du GPU
    config:
      security.secureboot: "false"
```

### Configuration de la machine

```yaml
machines:
  my-gpu-vm:
    type: vm
    gpu: true
    profiles: [default, gpu-passthrough]
    config:
      limits.cpu: "4"
      limits.memory: "8GiB"
```

### Notes importantes

- Le passthrough vfio-pci donne a la VM un acces materiel **exclusif** au
  peripherique PCI -- l'hote et les autres instances ne peuvent pas l'utiliser
- La politique GPU `shared` n'est pas pertinente pour les VMs (les peripheriques
  PCI ne peuvent pas etre partages sans SR-IOV)
- La VM a besoin de son propre pilote NVIDIA installe dans le systeme invite

## Detection GPU

Le role `ollama_server` detecte automatiquement la disponibilite du GPU :

```yaml
# Dans le role :
- name: OllamaServer | Check GPU access
  ansible.builtin.command:
    cmd: nvidia-smi
  register: ollama_gpu_check
  changed_when: false
  failed_when: false
```

Si aucun GPU n'est detecte, Ollama fonctionne en mode CPU uniquement.

## Regles de validation PSOT

Le generateur applique ces regles :

| Condition | gpu_policy: exclusive | gpu_policy: shared |
|-----------|----------------------|-------------------|
| 0 instance GPU | OK | OK |
| 1 instance GPU | OK | OK |
| 2+ instances GPU | **Erreur** | Avertissement |
| gpu_policy invalide | **Erreur** | **Erreur** |

Methodes de detection GPU :
- Directe : flag `gpu: true` sur la machine
- Indirecte : la machine utilise un profil avec un type de peripherique `gpu`

## Depannage

### nvidia-smi introuvable dans le container

Le container a besoin des bibliotheques du pilote NVIDIA. Pour les images
basees sur Debian, la version du pilote de l'hote doit correspondre a ce
qui est disponible dans le container. Le role `ollama_server` gere cela
pour les charges de travail Ollama.

### Le peripherique GPU n'apparait pas dans le container

```bash
# Verifier que le peripherique est attache
incus config show my-container --project my-domain | grep -A5 devices

# Verifier que le profil inclut le peripherique GPU
incus profile show nvidia-compute --project my-domain
```

### Le redemarrage du container perd l'acces GPU

Apres un redemarrage du container, les peripheriques GPU devraient persister.
Si ce n'est pas le cas :

```bash
# Re-appliquer l'infrastructure
anklume domain apply --tags infra

# Ou redemarrer l'instance specifique
incus restart my-container --project my-domain
```
