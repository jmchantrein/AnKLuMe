# Service de Reconnaissance Vocale (STT)

> Traduction francaise de [`stt-service.md`](stt-service.md). En cas de divergence, la version anglaise fait foi.

anklume fournit un service local de reconnaissance vocale (speech-to-text)
accelere par GPU en utilisant faster-whisper et le serveur API Speaches.
Ce service s'integre avec Open WebUI pour la saisie vocale et avec tout
client supportant l'API STT d'OpenAI.

## Architecture

L'architecture recommandee co-localise Ollama et Speaches dans un seul
container (`homelab-ai`), partageant le GPU dans un meme espace de
processus. Cela evite le besoin de `gpu_policy: shared` et conserve la
politique GPU exclusive par defaut.

```
+-----------------------------------------------------+
| domaine homelab (net-homelab, 10.100.3.0/24)         |
|                                                      |
|  +------------------------------------+             |
|  | homelab-ai                         |             |
|  | GPU (exclusif)                     |             |
|  |                                    |             |
|  |  +-------------+ +--------------+ |             |
|  |  | Ollama      | | Speaches     | |             |
|  |  | :11434      | | :8000        | |             |
|  |  | (systemd)   | | (systemd)    | |             |
|  |  +-------------+ +--------------+ |             |
|  |       VRAM partagee dans le container |          |
|  +----------+----------------+---------+             |
|             |                |                        |
|  /api/generate    /v1/audio/transcriptions            |
|             |                |                        |
|             v                v                        |
|  +----------------------------------+                |
|  | homelab-webui                    |                |
|  | Open WebUI :3000                 |                |
|  | LLM -> homelab-ai:11434         |                |
|  | STT -> homelab-ai:8000          |                |
|  +----------------------------------+                |
+-----------------------------------------------------+
```

## Demarrage rapide

### 1. Declarer l'instance IA dans infra.yml

```yaml
global:
  addressing:
    base_octet: 10
    zone_base: 100
    zone_step: 10
  # gpu_policy: exclusive  # Defaut -- un seul container possede le GPU

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
      homelab-ai:
        description: "Serveur IA -- Ollama + Speaches STT"
        type: lxc
        ip: "10.100.3.10"
        gpu: true
        profiles: [default, nvidia-compute]
        roles: [base_system, ollama_server, stt_server]
      homelab-webui:
        type: lxc
        ip: "10.100.3.30"
        roles: [base_system, open_webui]
```

### 2. Deployer

```bash
make sync          # Generer les fichiers Ansible
make apply         # Infrastructure complete + provisionnement
# ou :
make apply-stt     # Role STT uniquement
```

### 3. Configurer Open WebUI

Definissez le point d'acces STT dans `host_vars/homelab-webui.yml` :

```yaml
open_webui_ollama_url: "http://10.100.3.10:11434"
open_webui_stt_url: "http://10.100.3.10:8000/v1"
```

La variable `open_webui_stt_url` configure automatiquement Open WebUI
avec `AUDIO_STT_ENGINE=openai` et l'URL de base correcte de l'API. Laissez-la
vide (la valeur par defaut) pour desactiver l'integration STT.

## Moteur et modele

**Moteur** : faster-whisper (backend CTranslate2)
- Jusqu'a 4x plus rapide que le Whisper natif sur les GPUs NVIDIA
- Utilisation memoire reduite grace a la quantification
- Meme precision qu'OpenAI Whisper

**Modele par defaut** : Whisper Large V3 Turbo
- Meilleur compromis precision/vitesse
- Multilingue (francais + anglais et 90+ langues)
- ~6 Go de VRAM avec la quantification float16

**Serveur API** : Speaches (anciennement faster-whisper-server)
- Point d'acces `/v1/audio/transcriptions` compatible OpenAI
- Remplacement direct de l'API Whisper d'OpenAI
- Processus unique, pas d'orchestration necessaire

## Configuration

### Variables du role

| Variable | Defaut | Description |
|----------|--------|-------------|
| `stt_server_host` | `0.0.0.0` | Adresse d'ecoute |
| `stt_server_port` | `8000` | Port d'ecoute |
| `stt_server_model` | `large-v3-turbo` | Modele Whisper |
| `stt_server_quantization` | `float16` | Type de calcul |
| `stt_server_language` | `""` | Langue (vide=auto) |
| `stt_server_enabled` | `true` | Activer le service |

### Options de quantification

| Type | Utilisation VRAM | Vitesse | Precision |
|------|-----------------|---------|-----------|
| `float16` | ~6 Go | Rapide | Meilleure |
| `int8_float16` | ~4 Go | Plus rapide | Bonne |
| `int8` | ~3 Go | La plus rapide | Acceptable |

Pour les GPUs avec une VRAM limitee (< 8 Go), utilisez `int8_float16` ou un
modele plus petit (`medium`, `small`).

### Modeles plus petits

Si la VRAM ou la latence est une preoccupation :

```yaml
# Dans host_vars/homelab-ai.yml (hors section geree)
stt_server_model: "medium"
stt_server_quantization: "int8_float16"
```

| Modele | Parametres | VRAM (float16) | Precision |
|--------|-----------|----------------|-----------|
| tiny | 39M | ~1 Go | Faible |
| base | 74M | ~1 Go | Correcte |
| small | 244M | ~2 Go | Bonne |
| medium | 769M | ~4 Go | Tres bonne |
| large-v3-turbo | 809M | ~6 Go | Excellente |
| large-v3 | 1.55B | ~10 Go | Meilleure |

## Partage de VRAM dans un seul container

Lorsqu'Ollama et Speaches s'executent dans le meme container, ils partagent
le GPU en tant que deux processus independants. Le pilote NVIDIA gere
l'allocation de VRAM au niveau des processus :

- Ollama charge les poids du LLM dans la VRAM a la demande (et peut dechargez)
- Speaches charge le modele Whisper dans la VRAM a la premiere transcription
- Les deux processus se disputent la VRAM au niveau du pilote
- Pas d'overhead d'isolation au niveau container (pas besoin de `gpu_policy: shared`)

**Recommandations** :
- Utiliser la quantification `int8_float16` pour le STT afin de reduire la pression VRAM
- Eviter d'executer simultanement une inference LLM lourde et une transcription
  sur des GPUs avec moins de 16 Go de VRAM
- Surveiller l'utilisation de la VRAM : `nvidia-smi` dans le container ou sur l'hote
- Ollama decharge automatiquement les couches du modele vers le CPU quand la VRAM est pleine

C'est plus simple et plus efficace que l'ancienne approche a deux containers,
qui necessitait `gpu_policy: shared` et engendrait un overhead du peripherique
GPU Incus pour chaque container.

## Verification

```bash
# Verifier le statut du service
incus exec homelab-ai --project homelab -- systemctl status speaches

# Tester le point d'acces API
incus exec homelab-ai --project homelab -- \
  curl -s http://localhost:8000/health

# Verifier que les deux services fonctionnent
incus exec homelab-ai --project homelab -- systemctl status ollama
incus exec homelab-ai --project homelab -- systemctl status speaches

# Tester la transcription (depuis n'importe quel container avec acces reseau)
curl -X POST http://homelab-ai:8000/v1/audio/transcriptions \
  -H "Content-Type: multipart/form-data" \
  -F "file=@audio.wav" \
  -F "model=large-v3-turbo"
```

## Moteurs alternatifs

Le role `stt_server` utilise Speaches (backend faster-whisper) par defaut.
Pour d'autres cas d'usage :

| Moteur | Points forts | Limitations |
|--------|-------------|-------------|
| **Speaches** (defaut) | Compatible OpenAI, GPU, multilingue | Python/pip |
| **OWhisper** | CLI unifie, backends multiples | Plus recent, moins mature |
| **NVIDIA Parakeet** | Extremement rapide (RTFx 3386) | Anglais uniquement |
| **Vosk** | Leger, CPU uniquement | Precision inferieure |

Pour utiliser un moteur alternatif, creez un role personnalise ou surchargez
le template du service systemd.

## Depannage

### Telechargement du modele lent a la premiere requete

Le modele Whisper est telecharge a la premiere requete de transcription.
Les gros modeles (1-6 Go) prennent du temps a telecharger. Le service reste
reactif pendant le telechargement.

### Memoire VRAM insuffisante

Si Ollama et le STT manquent de VRAM :

```bash
# Verifier l'utilisation de la VRAM
nvidia-smi

# Passer a un modele plus petit ou une quantification plus legere
# Editer host_vars/homelab-ai.yml :
stt_server_model: "small"
stt_server_quantization: "int8"

# Re-provisionner
make apply-stt
```

### Le service ne demarre pas

```bash
# Verifier les journaux
incus exec homelab-ai --project homelab -- journalctl -u speaches -f

# Verifier que ffmpeg est installe (dependance requise)
incus exec homelab-ai --project homelab -- ffmpeg -version
```
