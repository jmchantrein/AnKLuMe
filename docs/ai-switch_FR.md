# Acces Exclusif aux Outils IA (ai-switch)

> Traduction francaise de [`ai-switch.md`](ai-switch.md). En cas de divergence, la version anglaise fait foi.

anklume supporte un mode d'acces IA exclusif ou un seul domaine a la
fois peut atteindre le domaine `ai-tools`. Cela empeche les fuites de
donnees entre domaines via les services IA partages et permet le vidage
de la VRAM entre les changements d'acces pour effacer l'etat residuel
des modeles.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         Hote                             │
│                                                          │
│  net-pro ──────┐                                        │
│                │ ✓ (actuel)       ┌──────────────┐      │
│  net-perso ────┤ ✗ (bloque)  ──▶│ net-ai-tools │      │
│                │                  │  gpu-server   │      │
│  net-anklume ──┘ ✗ (bloque)     │  ai-webui    │      │
│                                   └──────────────┘      │
│  nftables: seul net-pro <-> net-ai-tools autorise       │
└─────────────────────────────────────────────────────────┘
```

A tout moment, exactement un bridge de domaine possede des regles
nftables d'acceptation vers `net-ai-tools`. Tous les autres domaines
sont bloques. Le changement de domaine vide optionnellement la VRAM
GPU pour prevenir les fuites de donnees inter-domaines via les poids
residuels des modeles ou le cache d'inference.

## Configuration

### Activer le mode exclusif dans infra.yml

```yaml
global:
  base_subnet: "10.100"
  ai_access_policy: exclusive    # Un seul domaine accede a ai-tools
  ai_access_default: pro         # Domaine par defaut avec acces IA

domains:
  ai-tools:
    subnet_id: 10
    machines:
      gpu-server:
        type: lxc
        ip: "10.100.10.10"
        gpu: true
        roles: [base_system, ollama_server]
  pro:
    subnet_id: 2
    machines:
      pro-dev:
        type: lxc
        ip: "10.100.2.10"
  perso:
    subnet_id: 1
    machines:
      perso-desktop:
        type: lxc
        ip: "10.100.1.10"
```

Executer `make sync` avec `ai_access_policy: exclusive` cree
automatiquement une politique reseau bidirectionnelle du domaine par
defaut vers `ai-tools`.

### Regles de validation

Le generateur PSOT verifie :

| Condition | Resultat |
|-----------|----------|
| `ai_access_policy` ni `exclusive` ni `open` | Erreur |
| `exclusive` sans `ai_access_default` | Erreur |
| `ai_access_default` est `ai-tools` | Erreur |
| `ai_access_default` n'est pas un domaine connu | Erreur |
| `exclusive` sans domaine `ai-tools` | Erreur |
| Plus d'une politique reseau ciblant `ai-tools` | Erreur |

## Utilisation

### Changer l'acces IA vers un autre domaine

```bash
make ai-switch DOMAIN=perso       # Changer l'acces + vider la VRAM
make ai-switch DOMAIN=pro NO_FLUSH=1  # Changer sans vidage VRAM
```

Ou utiliser le script directement :

```bash
scripts/ai-switch.sh --domain perso
scripts/ai-switch.sh --domain pro --no-flush
scripts/ai-switch.sh --domain pro --dry-run
```

### Ce qui se passe pendant un changement

1. Les services GPU (ollama, speaches) sont arretes dans le domaine ai-tools
2. La VRAM est videe : processus GPU tues, reset GPU tente
3. Les regles nftables sont mises a jour : ancien domaine bloque, nouveau autorise
4. Les services GPU sont redemares
5. L'etat actuel est enregistre dans `/opt/anklume/ai-access-current`
6. Le changement est journalise dans `/var/log/anklume/ai-switch.log`

### Verifier l'acces actuel

```bash
cat /opt/anklume/ai-access-current
```

### Voir l'historique des changements

```bash
cat /var/log/anklume/ai-switch.log
```

## Vidage VRAM

Quand `--no-flush` n'est PAS specifie (par defaut), le changement :

1. Arrete les services GPU (ollama, speaches)
2. Tue tous les processus GPU restants via `nvidia-smi`
3. Tente `nvidia-smi --gpu-reset` (pas supporte par tous les GPU)
4. Redemare les services GPU

Cela empeche le nouveau domaine de lire des donnees residuelles de
l'inference du domaine precedent via la memoire GPU.

Utilisez `--no-flush` uniquement quand la rapidite prime sur
l'isolation (ex. changement entre domaines de confiance).

## Depannage

### Le changement echoue avec "Domain not found"

Verifiez que le domaine existe dans `infra.yml` :

```bash
python3 scripts/generate.py infra.yml --dry-run 2>&1 | head
```

### La mise a jour nftables echoue

Le changement utilise `ansible-playbook` en interne. Verifiez que :
- `site.yml` est present a la racine du projet
- Le role `incus_nftables` fonctionne : `make nftables`
- Les bridges Incus existent : `incus network list | grep net-`

### Reset GPU non supporte

Certains GPU NVIDIA ne supportent pas `nvidia-smi --gpu-reset`. C'est
non bloquant -- le changement continue. Les processus GPU sont quand
meme tues, ce qui libere la plupart des allocations VRAM.

### Les services ne redemarrent pas

Verifiez l'etat des services dans le conteneur ai-tools :

```bash
incus exec gpu-server --project ai-tools -- systemctl status ollama
incus exec gpu-server --project ai-tools -- systemctl status speaches
```
