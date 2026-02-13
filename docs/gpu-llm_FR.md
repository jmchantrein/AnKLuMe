# Guide du Passthrough GPU et des LLM

> Traduction francaise de [`gpu-llm.md`](gpu-llm.md). En cas de divergence, la version anglaise fait foi.

Ce guide explique comment configurer le passthrough GPU dans AnKLuMe pour
executer de l'inference LLM locale avec Ollama et Open WebUI.

## Prerequis

### Exigences de l'hote

- GPU NVIDIA (grand public ou datacenter)
- Pilote NVIDIA installe sur l'hote (>= 535 recommande)
- `nvidia-smi` fonctionnel sur l'hote
- Incus >= 6.0 LTS

### Verifier le GPU sur l'hote

```bash
nvidia-smi
```

Vous devriez voir le modele de votre GPU, la version du pilote et la version
CUDA. Si cette commande echoue, installez le pilote NVIDIA pour votre
distribution avant de continuer.

### Support GPU d'Incus

Incus peut passer le GPU de l'hote dans les containers LXC en utilisant
un type de peripherique `gpu`. Cela partage le pilote GPU de l'hote avec
le container -- aucune installation de pilote n'est necessaire dans le container.

## Profil GPU dans infra.yml

Consultez [examples/pro-workstation/](../examples/pro-workstation/) pour un
exemple complet fonctionnel. Points cles de configuration :

1. Definir un profil `nvidia-compute` au niveau du domaine avec un
   peripherique `gpu` (`type: gpu`, `gputype: physical`)
2. Referencer le profil dans la liste `profiles:` de la machine (garder
   `default` comme premiere entree)
3. Definir `gpu: true` sur la machine pour signaler l'utilisation GPU
4. Open WebUI fonctionne dans un container separe sans acces GPU

## Politique GPU (ADR-018)

Par defaut, AnKLuMe applique une politique GPU **exclusive** : une seule
instance dans tous les domaines peut avoir acces au GPU. Cela previent
les conflits lies a plusieurs containers partageant le meme GPU sans
isolation.

Si vous avez besoin de partager le GPU entre plusieurs containers (par exemple,
Ollama et un futur service STT), definissez la politique sur `shared` dans
la section globale :

```yaml
global:
  base_subnet: "10.100"
  default_os_image: "images:debian/13"
  gpu_policy: shared
```

En mode `shared`, le generateur emet un avertissement mais autorise plusieurs
instances GPU. Sachez que les GPUs NVIDIA grand public n'ont pas d'isolation
VRAM materielle (pas de SR-IOV), donc les charges de travail GPU concurrentes
se disputent la memoire.

## Configuration d'Ollama

Le role `ollama_server` installe Ollama et le demarre comme service systemd.
Variables par defaut (surchageables dans `host_vars/`) :

| Variable | Defaut | Description |
|----------|--------|-------------|
| `ollama_host` | `0.0.0.0:11434` | Adresse d'ecoute |
| `ollama_default_model` | `""` (aucun) | Modele a telecharger automatiquement |
| `ollama_service_enabled` | `true` | Activer le service systemd |

Pour telecharger automatiquement un modele pendant le provisionnement, definissez
`ollama_default_model` dans les host_vars de votre container LLM (hors section geree) :

```yaml
# host_vars/homelab-llm.yml (ajouter sous la section geree)
ollama_default_model: "llama3.2:3b"
```

## Configuration d'Open WebUI

Le role `open_webui` installe Open WebUI via pip et le configure comme
service systemd. Variables par defaut :

| Variable | Defaut | Description |
|----------|--------|-------------|
| `open_webui_port` | `3000` | Port d'ecoute |
| `open_webui_ollama_url` | `http://localhost:11434` | URL de l'API Ollama |

Puisqu'Open WebUI et Ollama fonctionnent dans des containers separes, configurez
l'URL d'Ollama pour pointer vers l'IP du container LLM :

```yaml
# host_vars/homelab-webui.yml (ajouter sous la section geree)
open_webui_ollama_url: "http://10.100.3.10:11434"
```

## Deploiement

```bash
# Generer les fichiers Ansible
make sync

# Tout appliquer (ou juste les roles LLM)
make apply

# Ou appliquer uniquement les roles lies au LLM
make apply-llm
```

## Verification

### Verifier le GPU dans le container

```bash
incus exec homelab-llm --project homelab -- nvidia-smi
```

Vous devriez voir le meme GPU que sur l'hote.

### Verifier Ollama

```bash
incus exec homelab-llm --project homelab -- curl -s http://localhost:11434/api/tags
```

Cela devrait retourner une reponse JSON avec les modeles disponibles.

### Verifier Open WebUI

```bash
incus exec homelab-webui --project homelab -- curl -s http://localhost:3000
```

Open WebUI devrait repondre avec du HTML. Accedez-y depuis un navigateur a
`http://<ip-hote>:3000` (apres avoir configure la redirection de port ou un proxy).

### Tester l'inference

```bash
incus exec homelab-llm --project homelab -- ollama run llama3.2:3b "Hello, world!"
```

## Volumes de stockage pour les modeles

Les modeles LLM peuvent etre volumineux (3-70 Go). Utilisez une entree
`storage_volumes` pour monter un volume dedie a `/root/.ollama`. Consultez
l'exemple [pro-workstation](../examples/pro-workstation/).

## Depannage

- **nvidia-smi introuvable** : Verifiez que le profil GPU est applique et que
  l'hote a les pilotes NVIDIA. Verifiez avec
  `incus profile show nvidia-compute --project homelab`
- **Ollama revient au CPU** : Verifiez que `nvidia-smi` fonctionne, puis
  consultez les journaux Ollama avec `journalctl -u ollama` dans le container
- **Open WebUI ne peut pas se connecter a Ollama** : Testez la connectivite avec
  `curl -s http://<ip-llm>:11434/api/tags` depuis le container webui.
  Assurez-vous qu'Ollama ecoute sur `0.0.0.0` (pas `127.0.0.1`)
- **Memoire VRAM insuffisante** : Utilisez un modele plus petit (ex. `llama3.2:3b`
  necessite ~2 Go de VRAM) ou une variante quantifiee

## Etapes suivantes

- [Specification complete](SPEC.md) pour la reference complete du format infra.yml
- [Decisions d'architecture](ARCHITECTURE.md) pour les details de la politique GPU
  (ADR-018)
- [Exemples de configurations](../examples/) incluant
  [llm-supervisor](../examples/llm-supervisor/) pour les configurations multi-LLM
