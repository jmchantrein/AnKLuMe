# ROADMAP.md -- Phases d'Implementation

> Traduction francaise de [`ROADMAP.md`](ROADMAP.md). En cas de divergence, la version anglaise fait foi.

Chaque phase produit un livrable testable. Ne pas commencer la phase N+1
avant que la phase N ne soit complete et validee.

---

## Phase 1 : Generateur PSOT -- COMPLETE

**Objectif** : `infra.yml` -> arborescence complete de fichiers Ansible

**Livrables** :
- `scripts/generate.py` -- le generateur PSOT
- `infra.yml` -- fichier PSOT avec 4 domaines (anklume, pro, perso, homelab)
- Inventaire genere dans `inventory/`
- group_vars et host_vars generes avec sections gerees
- Validation des contraintes (noms uniques, sous-reseaux uniques, IPs valides)
- Detection d'orphelins
- `make sync` et `make sync-dry`

**Criteres de validation** :
- [x] `make sync` idempotent (re-executer ne change rien)
- [x] Ajouter un domaine dans infra.yml + `make sync` -> fichiers crees
- [x] Supprimer un domaine -> orphelins detectes et listes
- [x] Sections gerees preservees, contenu utilisateur conserve
- [x] Contraintes de validation : erreur claire en cas de doublon nom/sous-reseau/IP

---

## Phase 2 : Roles d'Infrastructure (Reconciliation Incus) -- COMPLETE

**Objectif** : `make apply --tags infra` cree toute l'infrastructure Incus

**Livrables** :
- `roles/incus_networks/` -- bridges
- `roles/incus_projects/` -- projets + profil par defaut (root + eth0)
- `roles/incus_profiles/` -- profils supplementaires (GPU, imbrication)
- `roles/incus_instances/` -- containers LXC (surcharge de peripherique, IP statique)
- `site.yml` -- playbook principal a la racine du projet (ADR-016)

**Criteres de validation** :
- [x] `ansible-lint` 0 violation, profil production
- [x] Idempotent (0 changement a la seconde execution)
- [x] Les 4 domaines crees avec les IPs statiques correctes
- [x] `--tags networks` fonctionne seul
- [x] `--limit homelab` fonctionne seul

**Lecons apprises (ADR-015, ADR-016)** :
- `run_once: true` incompatible avec le patron hosts:all + connection:local
- Les variables de connexion dans group_vars surchargent `connection:` du playbook
- Le playbook doit etre a la racine du projet pour la resolution group_vars/host_vars
- `device set` d'Incus echoue sur un peripherique herite du profil -> utiliser `device override`
- Ansible 2.19 exige que les conditionnels `when:` evaluent en booleen strict

---

## Phase 2b : Durcissement Post-Deploiement -- COMPLETE

**Objectif** : Corriger les problemes decouverts pendant le deploiement Phase 2

**Livrables** :
- Commiter les corrections manuelles (failed_when images remote)
- Service systemd pour le socket proxy anklume-instance (ADR-019)
- ADR-017, ADR-018, ADR-019 documentes dans ARCHITECTURE.md
- Tests Molecule mis a jour pour les corrections

**Criteres de validation** :
- [x] anklume-instance redemarre sans intervention manuelle
- [x] `ansible-playbook site.yml` idempotent apres corrections
- [x] `make lint` passe
- [x] ADR-017 a ADR-019 presents dans ARCHITECTURE.md

---

## Phase 3 : Provisionnement des Instances -- COMPLETE

**Objectif** : `make apply --tags provision` installe les paquets et services

**Livrables** :
- `roles/base_system/` -- paquets de base, locale, fuseau horaire
- `roles/admin_bootstrap/` -- provisionnement specifique a l'admin (ansible, git)
- `site.yml` -- phase de provisionnement ajoutee
- Plugin de connexion `community.general.incus` configure

**Criteres de validation** :
- [x] Instance creee + provisionnee en un seul `make apply`
- [x] Re-provisionnement idempotent
- [x] Paquets installes verifiables

---

## Phase 4 : Snapshots -- COMPLETE

**Objectif** : `make snapshot` / `make restore`

**Livrables** :
- `roles/incus_snapshots/` -- role Ansible pour la gestion des snapshots
- `snapshot.yml` -- playbook autonome
- Support de snapshot individuel, par domaine et global
- Restauration + suppression avec idempotence

**Criteres de validation** :
- [x] Aller-retour snapshot + restauration fonctionnel
- [x] Snapshot par domaine ne touche que ce domaine

---

## Phase 5 : GPU + LLM -- COMPLETE

**Objectif** : Container Ollama avec GPU + Open WebUI

**Livrables** :
- `roles/ollama_server/` -- installation d'Ollama avec detection GPU
- `roles/open_webui/` -- frontend Open WebUI via pip
- Support `instance_devices` dans le generateur PSOT et le role incus_instances
- Provisionnement conditionnel dans site.yml (base sur instance_roles)
- Cible `make apply-llm`

**Criteres de validation** :
- [x] Peripherique GPU correctement ajoute a l'instance cible
- [x] `nvidia-smi` fonctionne dans le container GPU
- [x] Service Ollama en fonctionnement et repondant sur le port 11434
- [x] Idempotent a la seconde execution

---

## Phase 6 : Tests Molecule -- COMPLETE

**Objectif** : Tests automatises pour chaque role

**Livrables** :
- Repertoire `molecule/` dans chaque role
- Compatible CI/CD (GitHub Actions ou script local)

**Note** : Les tests s'executent actuellement sur le meme hote Incus (temporaire).
La Phase 12 fournira une isolation appropriee via Incus-in-Incus.

---

## Phase 7 : Documentation + Publication -- COMPLETE

**Objectif** : Projet utilisable par d'autres

**Livrables** :
- `README.md` complet
- `docs/quickstart.md`
- `docs/lab-tp.md` -- guide de deploiement de TP
- `docs/gpu-llm.md` -- guide GPU
- Repertoire `examples/` avec des fichiers infra.yml documentes :
  - `examples/student-sysadmin.infra.yml` -- Etudiant sysadmin : 2 domaines
    simples (anklume + lab), pas de GPU, reseau isole pour exercices de TP
  - `examples/teacher-lab.infra.yml` -- Enseignant : 1 domaine anklume + N
    domaines etudiants generes dynamiquement, snapshots pre-TP
  - `examples/pro-workstation.infra.yml` -- Poste de travail pro :
    anklume/perso/pro/homelab, GPU sur homelab, isolation reseau stricte
  - `examples/sandbox-isolation.infra.yml` -- Test de logiciels non fiables
    (ex. OpenClaw) : isolation maximale, pas de reseau externe, snapshot
    avant chaque execution
  - `examples/llm-supervisor.infra.yml` -- 2 LLMs isoles dans des domaines
    separes + 1 container superviseur communiquant avec les deux via API,
    pour tester la supervision/gestion de LLM par un autre LLM
  - `examples/developer.infra.yml` -- Developpeur AnKLuMe : inclut un
    domaine dev-test avec Incus-in-Incus (Phase 12)
  - Chaque exemple accompagne d'un README expliquant le cas d'usage,
    les exigences materielles et comment demarrer

---

## Phase 8 : Isolation nftables Inter-Bridges -- COMPLETE

**Objectif** : Bloquer le trafic entre domaines au niveau reseau

**Contexte** : Par defaut, Incus cree des chaines nftables par bridge mais
n'interdit pas le forwarding entre differents bridges. Un container dans un
domaine peut communiquer avec les containers d'autres domaines, cassant
l'isolation reseau.

**Livrables** :
- `roles/incus_nftables/` -- regles d'isolation inter-bridges
- Regles : DROP tout trafic inter-bridges (anklume inclus -- D-034)
- Anklume communique via le socket Incus, pas le reseau
- Integration dans site.yml (tag `nftables`)
- `scripts/deploy-nftables.sh` -- script de deploiement cote hote
- Documentation `docs/network-isolation.md`

**Criteres de validation** :
- [x] Tout trafic inter-bridges bloque (ex. perso -> pro, anklume -> pro)
- [x] Anklume gere les instances via le socket Incus (pas le reseau -- D-034)
- [x] NAT vers Internet fonctionnel depuis tous les bridges
- [x] Idempotent (regles nftables appliquees une seule fois)

**Decisions de conception** :
- nftables priorite -1 (avant les chaines Incus a priorite 0)
- Flux de travail en deux etapes : generer dans le container anklume, deployer sur l'hote
- Regles d'acceptation intra-bridge pour la compatibilite br_netfilter
- Remplacement atomique de la table (supprimer + recreer)
- Exception ADR-004 : le script de deploiement s'execute sur l'hote, pas via Ansible

**Notes** :
- Les regles nftables sont sur l'HOTE, pas dans les containers
- C'est une exception a "Ansible ne modifie pas l'hote" (ADR-004)
- Alternative : gerer via les ACLs Incus si la version le supporte

---

## Phase 9 : Support des VMs (Instances KVM) -- COMPLETE

**Objectif** : Permettre de declarer `type: vm` dans infra.yml

**Contexte** : Certaines charges de travail necessitent une isolation plus forte
que LXC (charges non fiables, GPU vfio-pci, noyau personnalise, systemes non-Linux).

**Livrables** :
- `incus_instances` : timeouts d'attente separes pour VM (120s) vs LXC (60s)
- Tache d'attente `incus-agent` : interroge `incus exec <vm> -- true` avant le provisionnement
- Validation PSOT : `type` doit etre `lxc` ou `vm` (erreur sur les valeurs invalides)
- Configuration des ressources VM via les cles `config:` (limits.cpu, limits.memory, etc.)
- Exemple : sandbox-isolation mis a jour avec coexistence VM + LXC
- Guide `docs/vm-support.md`

**Criteres de validation** :
- [x] `type: vm` dans infra.yml -> VM KVM creee avec le flag `--vm`
- [x] Provisionnement via `community.general.incus` fonctionne (attente agent garantit la disponibilite)
- [x] VM et LXC coexistent dans le meme domaine (valide par tests + exemple)
- [x] `make apply` idempotent avec un mix LXC + VM

**Decisions de conception** :
- Timeouts d'attente separes : LXC 30x2s=60s, VM 60x2s=120s (configurables)
- Attente incus-agent : `incus exec <vm> -- true` avec failed_when: false
- Pas d'application de ressources minimales (KISS -- les valeurs Incus par defaut fonctionnent, la doc recommande)
- Profils VM geres via `config:` et profils de domaine, pas de logique interne au role

---

## Phase 10 : Gestion Avancee du GPU -- COMPLETE

**Objectif** : Passthrough GPU pour LXC et VM avec politique de securite

**Livrables** :
- Validation `gpu_policy: exclusive|shared` dans le generateur PSOT (ADR-018)
- Detection d'instance GPU via le flag `gpu: true` ET le scan de peripheriques de profil
- Fonction `get_warnings()` pour les avertissements non fatals de GPU partage
- Patron de profil `nvidia-compute` pour LXC (documente)
- Patron de profil `gpu-passthrough` pour VM/vfio-pci (documente)
- Guide `docs/gpu-advanced.md`

**Criteres de validation** :
- [x] LXC avec GPU : patron de profil nvidia-compute documente + role existant
- [x] VM avec GPU : patron de profil vfio-pci documente
- [x] Mode exclusif : erreur PSOT si 2 instances declarent GPU
- [x] Mode partage : avertissement PSOT, 2 LXC partagent le GPU
- [x] Redemarrage du container GPU : persistance du peripherique via les profils Incus

**Decisions de conception** :
- Detection GPU : directe (`gpu: true`) + indirecte (scan de peripheriques de profil)
- `get_warnings()` separe de `validate()` pour la compatibilite descendante
- GPU VM documente mais verification IOMMU non appliquee (frontiere ADR-004)

---

## Phase 11 : VM Pare-feu Dediee (Style sys-firewall) -- COMPLETE

**Objectif** : Optionnel -- router tout le trafic inter-domaines a travers une
VM pare-feu dediee, style sys-firewall de QubesOS

**Contexte** : En Phase 8, l'isolation est faite via nftables sur l'hote.
Cette phase ajoute une option pour router tout le trafic a travers une VM
pare-feu dediee, offrant une isolation plus forte (le pare-feu a son propre
noyau, contrairement aux containers LXC qui partagent le noyau de l'hote).

**Livrables** :
- Validation `global.firewall_mode: host|vm` dans le generateur PSOT
- `roles/incus_firewall_vm/` : role d'infrastructure -- creation du profil multi-NIC
- `roles/firewall_router/` : role de provisionnement -- forwarding IP + nftables dans la VM
- Template nftables (`firewall-router.nft.j2`) avec politique anklume/non-anklume + journalisation
- `site.yml` mis a jour avec les deux roles (phases infra + provisionnement)
- `docs/firewall-vm.md` -- guide architecture, configuration, depannage
- 4 tests de mode pare-feu dans test_generate.py

**Criteres de validation** :
- [x] Mode `host` : comportement Phase 8 (nftables sur l'hote)
- [x] Mode `vm` : VM pare-feu avec profil multi-NIC + routage nftables
- [x] Le generateur PSOT valide les valeurs de firewall_mode
- [x] Defense en profondeur : les modes hote + VM peuvent coexister

**Decisions de conception** :
- Architecture a deux roles : infra (profil multi-NIC) + provisionnement (nftables dans la VM)
- Bridge anklume toujours eth0, autres bridges tries alphabetiquement
- Le generateur valide firewall_mode mais pas la topologie de deploiement (KISS)
- Les modes hote + VM peuvent coexister pour une securite en couches

---

## Phase 12 : Environnement de Test Incus-in-Incus -- COMPLETE

**Objectif** : Tester AnKLuMe dans un bac a sable isole (AnKLuMe se testant lui-meme)
sans impacter l'infrastructure de production.

**Principe** : Un container test-runner avec `security.nesting: "true"` execute
son propre Incus et deploie une instance complete d'AnKLuMe a l'interieur.
Les tests Molecule s'executent dans cet environnement imbrique.

**Livrables** :
- Profil Incus `nesting` avec `security.nesting`,
  `security.syscalls.intercept.mknod`,
  `security.syscalls.intercept.setxattr`
- Role `dev_test_runner` qui provisionne le container de test :
  - Installe Incus dans le container (`apt install incus`)
  - Initialise Incus (`incus admin init --minimal`)
  - Clone le depot AnKLuMe
  - Installe Molecule + ansible-lint + dependances
- Script `scripts/run-tests.sh` qui :
  1. Cree le container test-runner (ou le reutilise)
  2. Execute `molecule test` pour chaque role dans le container
  3. Collecte les resultats
  4. Detruit optionnellement le container test-runner
- `examples/developer.infra.yml` incluant le domaine dev-test
- Cibles Makefile : `make test-sandboxed`, `make test-runner-create`,
  `make test-runner-destroy`

**References** :
- [Documentation d'imbrication Incus](https://linuxcontainers.org/incus/docs/main/faq/)
- [Container Incus dans Incus](https://discuss.linuxcontainers.org/t/incus-container-inside-incus/23146)
- [Worker Debusine Incus-in-Incus](https://freexian-team.pages.debian.net/debusine/howtos/set-up-incus.html)

**Criteres de validation** :
- [x] Le container test-runner demarre avec un Incus fonctionnel a l'interieur
- [x] `molecule test` pour base_system passe dans le bac a sable
- [x] Pas d'impact sur les projets/reseaux de production
- [x] Nettoyage automatique des ressources de test

---

## Phase 13 : Tests et Developpement Assistes par LLM -- COMPLETE

**Objectif** : Permettre a un LLM (local ou distant) d'analyser les resultats
de tests, proposer des corrections, et optionnellement soumettre des PRs de
maniere autonome.

**Modes** (configurables via la variable d'environnement `ANKLUME_AI_MODE`) :

| Mode | Valeur | Description |
|------|--------|-------------|
| Aucun | `none` | Tests Molecule standards, pas d'IA (defaut) |
| Local | `local` | LLM local via Ollama (ex. qwen2.5-coder:32b) |
| Distant | `remote` | API cloud (Claude API, OpenAI API via cle) |
| Claude Code | `claude-code` | CLI Claude Code en mode autonome |
| Aider | `aider` | CLI Aider connecte a Ollama ou API distante |

**Architecture** :

```
+--------------------------------------------------+
| test-runner (Incus-in-Incus, Phase 12)           |
|                                                   |
|  1. molecule test -> journaux                    |
|  2. si echec -> envoyer journaux au LLM          |
|  3. LLM analyse -> propose un patch              |
|  4. appliquer le patch dans branche fix/<issue>  |
|  5. molecule test a nouveau                      |
|  6. si succes -> git push + creer PR             |
|  7. si echec a nouveau -> rapport + stop (max)   |
|                                                   |
|  Backend LLM (configurable) :                    |
|  - Ollama (homelab-llm:11434 ou local)           |
|  - Claude API (ANTHROPIC_API_KEY)                |
|  - CLI Claude Code (claude -p "...")              |
|  - Aider (aider --model ollama_chat/...)          |
+--------------------------------------------------+
```

**Livrables** :

a) Script `scripts/ai-test-loop.sh` -- orchestrateur principal :
   - Execute `molecule test` et capture les journaux
   - En cas d'echec : envoie le contexte (journal + fichier en echec + CLAUDE.md) au LLM
   - Le LLM propose un diff/patch
   - Applique le patch, re-teste
   - Nombre de tentatives max configurable (defaut : 3)
   - En cas de succes : commit + push sur branche + creation de PR via le CLI `gh`
   - Mode a blanc : affiche le patch sans l'appliquer

b) Integrations de backends LLM (patron uniforme : envoyer contexte, recevoir patch) :
   - Ollama (local) : `curl http://homelab-llm:11434/api/generate`
   - CLI Claude Code : `claude -p "Analyser cet echec..."`
   - Aider : `aider --model ollama_chat/... --message "Corriger..."`
   - API directe (Claude, OpenAI) : appel REST avec prompt structure

c) Configuration (`anklume.conf.yml` ou variables d'environnement) :
   ```yaml
   ai:
     mode: none
     ollama_url: "http://homelab-llm:11434"
     ollama_model: "qwen2.5-coder:32b"
     anthropic_api_key: ""
     max_retries: 3
     auto_pr: false
     dry_run: true
   ```

d) Cibles Makefile :
   - `make ai-test` -- executer les tests avec correction assistee par IA
   - `make ai-develop` -- session de developpement autonome

e) Script `scripts/ai-develop.sh` -- developpement autonome :
   - Prend une description de tache en entree (TASK)
   - Cree une branche feature
   - Utilise le LLM choisi pour implementer la tache
   - Execute les tests, itere si echec (nombre de tentatives max)
   - Si les tests passent -> PR ; journal de session complet pour revue humaine

**Garde-fous de securite** :
- `dry_run: true` par defaut (le LLM propose, l'humain applique)
- `auto_pr: false` par defaut (l'humain cree la PR)
- Nombre de tentatives max pour prevenir les boucles infinies
- Chaque session est integralement journalisee
- Bac a sable Incus-in-Incus (Phase 12) isole toute l'execution
- Jamais d'acces direct a la production depuis le test-runner

**Principes de conception** :
- KISS : l'orchestrateur est un simple script shell, pas un framework complexe
- DRY : un seul script d'orchestration avec des backends enfichables
- Securite par defaut : dry_run + pas d'auto_pr + isolation par bac a sable

**References** :
- [CLI Claude Code](https://code.claude.com/docs/en/overview)
- [Aider + Ollama](https://aider.chat/docs/llms/ollama.html)
- [Patrons de CI auto-reparatrice](https://optimumpartners.com/insight/how-to-architect-self-healing-ci/cd-for-agentic-ai/)
- [claude-flow (orchestration multi-agents)](https://github.com/ruvnet/claude-flow)
- [Cookbook Self-Evolving Agents](https://developers.openai.com/cookbook/examples/partners/self_evolving_agents/autonomous_agent_retraining)

**Criteres de validation** :
- [x] `make ai-test AI_MODE=none` = tests Molecule standards (pas de regression)
- [x] `make ai-test AI_MODE=local` = tests + analyse d'echec par Ollama local
- [x] `make ai-test AI_MODE=claude-code` = tests + correction proposee par Claude Code
- [x] `make ai-test AI_MODE=aider` = tests + correction via Aider
- [x] dry_run empeche toute modification automatique par defaut
- [x] Les PRs creees automatiquement sont clairement etiquetees (ai-generated)
- [x] Journal de session complet pour chaque execution

---

## Phase 14 : Service de Reconnaissance Vocale (STT) -- COMPLETE

**Objectif** : Fournir un service local de reconnaissance vocale accelere par GPU
accessible par Open WebUI et les autres containers.

**Contexte** : L'interaction vocale avec les LLMs necessite de transcrire l'audio
en texte avant de l'envoyer a Ollama. Executer le STT localement preserve la
vie privee (pas d'audio envoye au cloud) et correspond a la philosophie de
cloisonnement. Open WebUI supporte deja nativement les points d'acces STT personnalises.

**Architecture** :

```
+-----------------------------------------------------+
| domaine homelab (net-homelab, 10.100.3.0/24)         |
|                                                       |
|  +--------------+    +----------------------+        |
|  | homelab-stt   |    | homelab-llm          |        |
|  | GPU (partage) |    | GPU (partage)        |        |
|  |               |    |                      |        |
|  | faster-whisper|    | Ollama               |        |
|  | + Speaches    |    | :11434               |        |
|  | :8000         |    |                      |        |
|  +------+-------+    +----------------------+        |
|         |                      ^                      |
|         |    /v1/audio/        |  /api/generate       |
|         |    transcriptions    |                      |
|         v                      |                      |
|  +------------------------------+                    |
|  | homelab-webui                |                    |
|  | Open WebUI :3000             |                    |
|  | STT -> homelab-stt:8000      |                    |
|  | LLM -> homelab-llm:11434     |                    |
|  +------------------------------+                    |
+-----------------------------------------------------+
```

**Choix du moteur** : **faster-whisper** avec le modele **Whisper Large V3 Turbo**.
faster-whisper utilise CTranslate2 pour une acceleration jusqu'a 4x par rapport
au Whisper natif sur les GPUs NVIDIA, avec une utilisation memoire inferieure.
Whisper Large V3 Turbo offre le meilleur compromis precision/vitesse pour les
charges de travail multilingues (francais + anglais).

**Serveur API** : **Speaches** (anciennement faster-whisper-server). Expose un
point d'acces `/v1/audio/transcriptions` compatible OpenAI qu'Open WebUI peut
consommer directement. Container unique, pas d'orchestration necessaire.

**Moteurs alternatifs** (pour consideration future) :
- **OWhisper** : "Ollama pour le STT" -- CLI/serveur unifie pour plusieurs
  backends STT (whisper.cpp, Moonshine). Projet plus recent (aout 2025),
  UX prometteuse mais moins mature.
- **NVIDIA Parakeet TDT 0.6B** : Extremement rapide (RTFx 3386) mais
  anglais uniquement. Ideal si le multilingue n'est pas requis.
- **Vosk** : Leger, CPU uniquement. Pour les instances sans acces GPU.

**Livrables** :
- `roles/stt_server/` -- Installer faster-whisper + serveur Speaches
  (service systemd, detection GPU, telechargement de modele)
- Support PSOT : instance `homelab-stt` avec peripherique GPU + config
- Integration Open WebUI : configurer le point d'acces STT dans les parametres admin
  (ou via la variable `open_webui_stt_url`)
- Cible Makefile `make apply-stt`
- `gpu_policy: shared` requis si le STT et Ollama partagent le meme GPU
  (ADR-018). Documenter le compromis : GPU partage signifie que l'inference
  concurrente se dispute la VRAM.

**Livrable optionnel TTS** (synthese vocale pour la boucle vocale complete) :
- **Piper TTS** comme moteur de synthese vocale local et leger
- Pourrait fonctionner dans le meme container `homelab-stt` ou un dedie
- Expose un point d'acces API pour la configuration TTS d'Open WebUI
- Reporte sauf si la sortie vocale est explicitement necessaire

**Variables (roles/stt_server/defaults/main.yml)** :
```yaml
stt_engine: "faster-whisper"
stt_model: "large-v3-turbo"
stt_host: "0.0.0.0:8000"
stt_quantization: "float16"    # float16, int8_float16, ou int8
stt_language: ""               # Vide = detection automatique
```

**References** :
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper)
- [Speaches (serveur compatible OpenAI)](https://github.com/speaches-ai/speaches)
- [OWhisper](https://hyprnote.com/product/owhisper)
- [NVIDIA Parakeet](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2)
- [Fonctionnalites STT Open WebUI](https://docs.openwebui.com/features/)
- [Meilleurs modeles STT open-source 2026](https://northflank.com/blog/best-open-source-speech-to-text-stt-model-in-2026-benchmarks)

**Criteres de validation** :
- [x] Le container `homelab-stt` demarre avec acces GPU
- [x] L'API Speaches repond sur `/v1/audio/transcriptions`
- [x] La saisie vocale Open WebUI transcrit correctement (FR + EN)
- [x] Idempotent a la seconde execution
- [x] Utilisation GPU concurrente avec Ollama stable (mode partage)
- [x] Latence de transcription < 2s pour un clip audio de 10s

---

## Phase 15 : Claude Code Agent Teams -- Developpement et Tests Autonomes -- COMPLETE

**Objectif** : Permettre des cycles de developpement et de tests entierement
autonomes en utilisant Claude Code Agent Teams (orchestration multi-agents)
dans le bac a sable Incus-in-Incus, avec une supervision humaine au niveau
de la fusion des PRs.

**Prerequis** : Phase 12 (Incus-in-Incus), Phase 13 (infrastructure de tests
assistes par IA), CLI Claude Code >= 1.0.34, cle API Anthropic ou forfait Max.

**Contexte** : La Phase 13 fournit des backends LLM enfichables (Ollama, Claude
API, Aider, CLI Claude Code) pour la correction de tests assistee par IA via
un orchestrateur en script shell. La Phase 15 va plus loin : elle utilise la
fonctionnalite native Agent Teams de Claude Code (livree avec Opus 4.6, fevrier
2026) pour orchestrer plusieurs instances Claude Code travaillant en parallele
dans le bac a sable. La Phase 13 reste l'option legere et agnostique du backend.
La Phase 15 est l'option a pleine puissance pour les utilisateurs ayant acces
a Claude Code.

**Architecture** :

```
+----------------------------------------------------------------+
| Container : test-runner (Incus-in-Incus, Phase 12)              |
| security.nesting: true                                          |
| CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1                          |
| --dangerously-skip-permissions (sur : bac a sable isole)       |
|                                                                 |
| Claude Code Agent Teams (Opus 4.6)                              |
|                                                                 |
|  Chef d'equipe : orchestrateur                                  |
|  +-- lit le ROADMAP / description de la tache                   |
|  +-- decompose le travail en liste de taches partagee           |
|  +-- assigne les taches aux coequipiers                         |
|  +-- synthetise les resultats, cree la PR                       |
|                                                                 |
|  Coequipier "Builder" : implementation de fonctionnalites       |
|  +-- implemente les roles Ansible, playbooks, configs           |
|  +-- suit les conventions de CLAUDE.md                          |
|  +-- commite sur la branche feature                             |
|                                                                 |
|  Coequipier "Tester" : tests continus                           |
|  +-- execute molecule test pour les roles affectes              |
|  +-- signale les echecs a l'equipe via la liste partagee        |
|  +-- valide l'idempotence                                       |
|                                                                 |
|  Coequipier "Reviewer" : qualite du code                        |
|  +-- execute ansible-lint, yamllint                              |
|  +-- verifie la conformite ADR                                  |
|  +-- verifie l'absence de regression sur les autres roles       |
|  +-- approuve ou rejette avec retour au Builder                 |
|                                                                 |
|  Incus imbrique (les cibles de test Molecule s'executent ici)   |
+----------------------------------------------------------------+
```

**Modes operationnels** :

a) **Mode correction** (`make agent-fix`) :
   - Le chef execute `molecule test` pour tous les roles
   - En cas d'echec : lance des coequipiers Fixer par role en echec
   - Les Fixers analysent les journaux + le code source, proposent et appliquent des patchs
   - Le Tester re-execute les tests affectes apres chaque correction
   - Boucle jusqu'a ce que tous les tests passent ou nombre max de tentatives atteint
   - En cas de succes : le chef cree une PR avec un resume de toutes les corrections

b) **Mode developpement** (`make agent-develop TASK="Implementer Phase N"`) :
   - Le chef lit ROADMAP.md, CLAUDE.md et la description de la tache
   - Decompose la phase en sous-taches paralleles
   - Lance Builder(s) pour l'implementation, Tester pour la validation,
     Reviewer pour la qualite
   - Les coequipiers se coordonnent via la liste de taches partagee et la messagerie inter-agents
   - Le Builder implemente, le Tester valide, le Reviewer verifie la qualite
   - Itere jusqu'a ce que Tester + Reviewer approuvent tous les deux
   - Le chef cree une PR avec l'implementation complete + tests passants

**Livrables** :

a) Role `dev_agent_runner` -- etend `dev_test_runner` (Phase 12) :
   - Installe le CLI Claude Code (`npm install -g @anthropic-ai/claude-code`)
   - Installe Node.js >= 18 (requis par Claude Code)
   - Installe tmux (pour le mode split-pane d'Agent Teams)
   - Configure les parametres de Claude Code :
     ```json
     {
       "env": {
         "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
       },
       "permissions": {
         "allow": [
           "Edit",
           "MultiEdit",
           "Bash(molecule *)",
           "Bash(ansible-lint *)",
           "Bash(yamllint *)",
           "Bash(git *)",
           "Bash(incus *)",
           "Bash(make *)"
         ],
         "deny": [
           "Bash(rm -rf /)",
           "Bash(curl * | bash)",
           "Bash(wget * | bash)"
         ]
       },
       "defaultMode": "bypassPermissions"
     }
     ```
   - Copie CLAUDE.md et le contexte du projet dans le container
   - Configure git (utilisateur, email, remote, identifiants)

b) Script `scripts/agent-fix.sh` -- orchestrateur du mode correction :
   - Cree/reutilise le container test-runner
   - Injecte la cle API Anthropic (depuis env ou `anklume.conf.yml`)
   - Lance Claude Code avec le prompt :
     ```
     Run molecule test for all roles. For each failure:
     1. Analyze the error log and the relevant source files
     2. Create a fix branch (fix/<role>-<issue>)
     3. Apply the fix
     4. Re-run the test
     5. If it passes, commit with a descriptive message
     If all tests pass, create a single PR summarizing all fixes.
     Use agent teams: spawn a Tester and a Fixer teammate.
     Max retries per role: 3.
     ```
   - Capture la transcription complete de session pour audit
   - Sort avec un resume : quels roles corriges, lesquels encore en echec

c) Script `scripts/agent-develop.sh` -- orchestrateur du mode developpement :
   - Prend une description de TASK (texte libre ou reference "Phase N")
   - Cree une branche feature (`feature/<slug-tache>`)
   - Lance Claude Code avec le prompt :
     ```
     Read ROADMAP.md and CLAUDE.md. Your task: {TASK}
     Use agent teams to parallelize the work:
     - Builder teammate(s) for implementation
     - Tester teammate to run molecule tests continuously
     - Reviewer teammate to check code quality and ADR compliance
     Iterate until all tests pass and Reviewer approves.
     Then create a PR with a comprehensive description.
     ```
   - Transcription complete de session sauvegardee
   - Sortie resumee : fichiers modifies, tests passes/echoues, URL de la PR

d) Cibles Makefile :
   ```makefile
   agent-fix:          ## Correction autonome de tests avec Claude Code Agent Teams
   agent-develop:      ## Developpement autonome de fonctionnalites (TASK requis)
   agent-runner-setup: ## Configurer le container agent-runner avec Claude Code
   ```

e) Ajouts a CLAUDE.md pour le contexte Agent Teams :
   - Section decrivant la structure du projet pour les agents
   - Conventions de nommage des roles, index ADR, patrons de test
   - Instructions pour l'execution des tests Molecule
   - Flux de travail git : branches feature, conventions PR, messages de commit

f) Hook PreToolUse (`scripts/agent-audit-hook.sh`) :
   - Journalise chaque invocation d'outil (nom, arguments, horodatage)
   - Stocke dans `logs/agent-session-<horodatage>.jsonl`
   - Permet un audit a posteriori de tout ce que les agents ont fait

**Modele de permissions et humain dans la boucle** :

| Couche | Controle |
|--------|----------|
| Bac a sable | Incus-in-Incus = isolation totale. Pas d'acces aux projets/reseaux de production |
| Permissions Claude Code | `bypassPermissions` (sur dans le bac a sable) + hook d'audit PreToolUse journalise tout |
| Flux git | Les agents travaillent sur des branches feature/fix. Jamais de commit sur main. PR creee automatiquement |
| Porte humaine | Fusion de la PR = decision humaine. Transcription complete de session disponible. `git diff` examinable avant fusion |

Le principe cle : autonomie complete dans le bac a sable, approbation humaine
a la frontiere de la production (fusion de la PR).

**Considerations de cout** :
- Les Agent Teams consomment significativement plus de tokens (3-5x une session unique)
- Chaque coequipier a sa propre fenetre de contexte
- Recommande : utiliser `agent-fix` pour les corrections ciblees (cout inferieur),
  `agent-develop` pour l'implementation de phases completes (cout superieur, valeur superieure)
- Couts estimes par mode (Opus 4.6 a 5$/25$ par MTok) :
  - `agent-fix` (un role) : ~3-8 $
  - `agent-fix` (tous les roles) : ~15-40 $
  - `agent-develop` (petite phase) : ~20-60 $
  - `agent-develop` (grande phase) : ~50-150 $

**Principes de conception** :

*Defense en profondeur* :
- Bac a sable Incus-in-Incus = isolation au niveau OS
- Permissions Claude Code = controle au niveau application
- Protection de branche git = porte au niveau flux de travail
- Fusion de PR = decision au niveau humain
- Journaux d'audit = responsabilite

*Autonome mais auditable* :
- Les agents ont une liberte totale dans le bac a sable
- Chaque action est journalisee (hook PreToolUse)
- Transcription complete de session sauvegardee
- Description de PR auto-generee avec resume
- L'humain examine avant que quoi que ce soit n'atteigne la production

*Confiance progressive* :
- Commencer avec `agent-fix` (risque inferieur, portee ciblee)
- Evoluer vers `agent-develop` a mesure que la confiance grandit
- Les backends Phase 13 restent disponibles pour un usage plus leger
- Possibilite de toujours revenir au developpement manuel

**References** :
- [Documentation Claude Code Agent Teams](https://code.claude.com/docs/en/agent-teams)
- [Permissions Claude Code](https://code.claude.com/docs/en/permissions)
- [Bac a sable Claude Code](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Fonctionnalites Opus 4.6](https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-6)
- [Guide de configuration Agent Teams](https://serenitiesai.com/articles/claude-code-agent-teams-documentation)
- [Addy Osmani sur les essaims Claude Code](https://addyosmani.com/blog/claude-code-agent-teams/)

**Criteres de validation** :
- [x] `make agent-runner-setup` cree le container avec Claude Code + Agent Teams
- [x] `make agent-fix` execute le cycle test-correction de maniere autonome, cree une PR
- [x] `make agent-develop TASK="..."` implemente une tache, la teste, cree une PR
- [x] Toutes les actions des agents journalisees dans la transcription de session
- [x] Les agents ne touchent jamais la production (isolation du bac a sable verifiee)
- [x] La PR contient une description claire des changements et resultats de tests
- [x] L'humain peut examiner le journal complet de session avant de fusionner

---

## Phase 16 : Politique de Securite, Communication Inter-Domaines et Bootstrap -- COMPLETE

**Objectif** : Appliquer la politique de securite d'imbrication, permettre
l'acces selectif entre domaines, fournir un outillage robuste de bootstrap/cycle de vie.

**Livrables** :

a) **Politique de securite (ADR-020)** :
   - Detection automatique du flag `vm_nested` via `systemd-detect-virt`
   - Fichiers de contexte d'imbrication (`/etc/anklume/{absolute_level,relative_level,vm_nested,yolo}`)
   - Validation du generateur : rejet de `security.privileged: true` sur LXC quand `vm_nested=false`
   - Mode YOLO de contournement

b) **Politiques reseau (ADR-021)** :
   - Section `network_policies:` dans infra.yml (syntaxe liste d'autorisations plate)
   - Validation du generateur des references from/to
   - Generation de regles nftables (regles accept avant drop)

c) **Support du repertoire infra/** :
   - Le generateur accepte le repertoire `infra/` (base.yml + domains/*.yml + policies.yml)
   - Auto-detection fichier unique vs repertoire
   - Retrocompatible avec infra.yml

d) **Domaine AI tools** :
   - Nouveaux roles : `lobechat` (interface web LobeChat), `opencode_server` (serveur OpenCode headless)
   - Exemple `examples/ai-tools/` avec configuration complete du stack IA
   - Cible `make apply-ai`

e) **Script de bootstrap** (`bootstrap.sh`) :
   - Modes `--prod` / `--dev` avec auto-configuration du preseed Incus
   - `--snapshot` pour les snapshots pre-modification du systeme de fichiers
   - Mode `--YOLO`

f) **Outillage de cycle de vie** :
   - `make flush` -- detruire toute l'infrastructure AnKLuMe
   - `make upgrade` -- mise a jour securisee du framework
   - `make import-infra` -- generer infra.yml depuis l'etat Incus existant

**Criteres de validation** :
- [x] `security.privileged: true` sur LXC rejete quand `vm_nested=false`
- [x] `network_policies` genere les regles nftables accept correctes
- [x] Le repertoire `infra/` produit une sortie identique a l'equivalent `infra.yml`
- [x] `bootstrap.sh --prod` configure Incus avec le backend FS detecte
- [x] `make flush` detruit l'infrastructure, preserve les fichiers utilisateur
- [x] Les roles `lobechat` et `opencode_server` crees et integres

---

## Phase 17 : Pipeline CI/CD et Couverture de Tests -- COMPLETE

**Objectif** : CI automatisee via GitHub Actions, couverture complete
des tests Molecule pour tous les roles.

**Livrables** :

a) **Workflow CI GitHub Actions** (`.github/workflows/ci.yml`) :
   - Declenche sur push et pull requests
   - 6 jobs paralleles : yamllint, ansible-lint, shellcheck, ruff,
     pytest (generateur), ansible syntax-check
   - Cache pip pour des executions plus rapides
   - Badge dans README.md et README_FR.md

b) **Tests Molecule pour les 7 roles restants** :
   - `roles/stt_server/molecule/` -- test template (speaches.service)
   - `roles/firewall_router/molecule/` -- test template (firewall-router.nft)
   - `roles/incus_firewall_vm/molecule/` -- test infra (profil multi-NIC)
   - `roles/incus_images/molecule/` -- test infra (listing d'images)
   - `roles/lobechat/molecule/` -- test template (lobechat.service)
   - `roles/opencode_server/molecule/` -- test template (service + config)
   - `roles/dev_agent_runner/molecule/` -- test template (settings.json)

c) **Nettoyage du ROADMAP** :
   - Marqueurs Phase 2b, 6, 7, 12 corriges en COMPLETE
   - ADRs actifs mis a jour jusqu'a ADR-031
   - Problemes connus effaces
   - ROADMAP francais synchronise (Phase 16 manquante ajoutee)

**Criteres de validation** :
- [x] La CI GitHub Actions passe sur push vers main
- [x] `make lint` + `make test-generator` s'executent en CI
- [x] Les 18 roles ont des repertoires `molecule/`
- [x] Badge CI actif dans README.md
- [x] Incoherences du ROADMAP resolues

---

## Phase 18 : Securite avancee, tests, onboarding et auto-amelioration -- COMPLETE

**Objectif** : Cinq sous-phases independantes couvrant la securite,
les tests, l'onboarding, l'auto-amelioration et le partage d'images.

### Phase 18a : Acces exclusif au reseau AI-Tools avec purge VRAM

**Objectif** : Un seul domaine a la fois peut acceder a ai-tools.
`make ai-switch DOMAIN=<nom>` bascule atomiquement l'acces avec purge VRAM.

**Livrables** :
- `ai_access_policy: exclusive|open` dans la section `global:` d'infra.yml
- Champs `ai_access_default` et `ai_vram_flush`
- Validation et auto-enrichissement des politiques reseau dans le generateur
- `scripts/ai-switch.sh` -- bascule atomique avec purge VRAM
- `roles/incus_nftables/` etendu avec `incus_nftables_ai_override`
- Cible Makefile `make ai-switch DOMAIN=<nom>`
- Documentation `docs/ai-switch.md`
- 11 nouveaux tests pytest

### Phase 18b : Tests exhaustifs par LLM (matrice de comportement)

**Objectif** : Matrice de comportement reliant chaque capacite aux reactions
attendues, avec couverture par tests generes par LLM et tests Hypothesis.

**Livrables** :
- `tests/behavior_matrix.yml` -- 120 cellules, 11 capacites, 3 niveaux
- `scripts/matrix-coverage.py` -- rapport de couverture par IDs de matrice
- `scripts/ai-matrix-test.sh` -- generateur de tests par LLM
- `tests/test_properties.py` -- 9 tests Hypothesis pour le generateur
- Annotations `# Matrix: XX-NNN` sur 54 tests existants
- Integration CI : job `matrix-coverage` informatif

### Phase 18c : Guide d'onboarding interactif

**Objectif** : `make guide` lance un tutoriel interactif etape par etape.

**Livrables** :
- `scripts/guide.sh` -- tutoriel en 9 etapes (Bash pur, couleurs ANSI)
- Cibles Makefile `make guide`, `make quickstart`
- `make help` restructure avec categorie "GETTING STARTED"
- Documentation `docs/guide.md`

### Phase 18d : Logiciel auto-ameliorant (bibliotheque d'experiences)

**Objectif** : Bibliotheque d'experiences persistante alimentee depuis
l'historique git, avec boucle d'amelioration pilotee par les specs.

**Livrables** :
- Repertoire `experiences/` (fixes/, patterns/, decisions/)
- `scripts/mine-experiences.py` -- extraction de patterns depuis git
- `scripts/ai-improve.sh` -- boucle d'amelioration pilotee par les specs
- `scripts/ai-test-loop.sh` etendu avec recherche d'experiences avant LLM
- Flag `--learn` pour capturer de nouveaux correctifs
- Cibles `make mine-experiences` et `make ai-improve`

### Phase 18e : Depot d'images partage entre niveaux d'imbrication

**Objectif** : Pre-exporter les images OS depuis l'hote, monter dans
les VMs Incus imbriquees pour eviter les telechargements redondants.

**Livrables** :
- `roles/incus_images/` etendu avec taches d'export + `incus_images_export_for_nesting`
- `roles/dev_test_runner/` etendu avec import depuis images montees
- Timeout intelligent (`incus_images_download_timeout: 600`)
- Cible Makefile `make export-images`

---

## Etat Actuel

**Complete** :
- Phase 1 : Generateur PSOT fonctionnel (make sync idempotent)
- Phase 2 : Infrastructure Incus deployee et idempotente
- Phase 2b : Durcissement post-deploiement (ADR-017 a ADR-019)
- Phase 3 : Provisionnement des instances (base_system + admin_bootstrap)
- Phase 4 : Gestion des snapshots (role + playbook)
- Phase 5 : Passthrough GPU + Ollama + roles Open WebUI
- Phase 6 : Tests Molecule pour chaque role
- Phase 7 : Documentation + publication
- Phase 8 : Isolation nftables inter-bridges
- Phase 9 : Support des VMs (instances KVM)
- Phase 10 : Gestion avancee du GPU (validation gpu_policy)
- Phase 11 : VM pare-feu dediee (modes hote + VM)
- Phase 12 : Environnement de test Incus-in-Incus
- Phase 13 : Tests assistes par LLM (ai-test-loop + ai-develop)
- Phase 14 : Service de reconnaissance vocale STT (role stt_server)
- Phase 15 : Claude Code Agent Teams (dev + tests autonomes)
- Phase 16 : Politique de securite, politiques reseau, bootstrap, domaine AI tools
- Phase 17 : Pipeline CI/CD + couverture complete des tests Molecule (18/18 roles)
- Phase 18 : Securite avancee, tests, onboarding et auto-amelioration (18a-18e)

**Suivant** :
- Phase 19+ (a definir)

**Infrastructure deployee** :

| Domaine | Container | IP | Reseau | Statut |
|---------|-----------|-----|--------|--------|
| anklume | anklume-instance | 10.100.0.10 | net-anklume | En fonctionnement |
| perso | perso-desktop | 10.100.1.10 | net-perso | En fonctionnement |
| pro | pro-dev | 10.100.2.10 | net-pro | En fonctionnement |
| homelab | homelab-llm | 10.100.3.10 | net-homelab | En fonctionnement |

**ADRs actifs** : ADR-001 a ADR-036

**Problemes connus** : Aucun
