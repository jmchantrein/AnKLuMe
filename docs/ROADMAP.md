# ROADMAP.md — Phases d'implémentation

Chaque phase produit un livrable testable. Ne pas commencer la phase N+1
avant que la phase N soit complète et validée.

---

## Phase 1 : Générateur SSOT ✅ COMPLÈTE

**Objectif** : `infra.yml` → arborescence Ansible complète

**Livrables** :
- `scripts/generate.py` — le générateur (PSOT)
- `infra.yml` — fichier SSOT avec les 4 domaines (admin, pro, perso, homelab)
- Inventaire généré dans `inventory/`
- group_vars et host_vars générés avec sections managées
- Validation des contraintes (noms uniques, subnets uniques, IPs valides)
- Détection d'orphelins
- `make sync` et `make sync-dry`

**Critères de validation** :
- [x] `make sync` idempotent (relancer ne change rien)
- [x] Ajouter un domaine dans infra.yml + `make sync` → fichiers créés
- [x] Supprimer un domaine → orphelins détectés et listés
- [x] Sections managées préservées, contenu libre conservé
- [x] Contraintes de validation : erreur claire si nom/subnet/IP dupliqué

---

## Phase 2 : Rôles infrastructure (réconciliation Incus) ✅ COMPLÈTE

**Objectif** : `make apply --tags infra` crée toute l'infrastructure Incus

**Livrables** :
- `roles/incus_networks/` — bridges
- `roles/incus_projects/` — projets + profil default (root + eth0)
- `roles/incus_profiles/` — profils extra (GPU, nesting)
- `roles/incus_instances/` — containers LXC (device override, IP statique)
- `site.yml` — playbook maître au root du projet (ADR-016)

**Critères de validation** :
- [x] `ansible-lint` 0 violation, profil production
- [x] Idempotent (0 changed sur la 2e exécution)
- [x] Les 4 domaines créés avec IPs statiques correctes
- [x] `--tags networks` fonctionne seul
- [x] `--limit homelab` fonctionne seul

**Leçons apprises (ADR-015, ADR-016)** :
- `run_once: true` incompatible avec le pattern hosts:all + connection:local
  (seul le premier host exécute le rôle → un seul domaine créé)
- Les variables de connexion dans group_vars (`ansible_connection`) ont
  priorité sur `connection:` du playbook → ne pas les mettre dans le PSOT
- Le playbook doit être à la racine du projet pour que la résolution
  des group_vars/host_vars fonctionne
- Incus `device set` échoue sur un device hérité de profil → utiliser
  `device override` d'abord
- Ansible 2.19 exige que les conditionals `when:` évaluent à un bool
  strict → utiliser `| length > 0` pour tester un dict/string

---

## Phase 2b : Durcissement post-déploiement ✦ PRIORITÉ

**Objectif** : Corriger les problèmes découverts pendant le déploiement Phase 2

**Livrables** :
- Commit des hotfixes manuels (failed_when images remote)
- Systemd service pour le proxy socket admin-ansible (ADR-019)
- ADR-017, ADR-018, ADR-019 documentés dans ARCHITECTURE.md
- Tests Molecule mis à jour pour les fixes

**Critères de validation** :
- [ ] admin-ansible redémarre sans intervention manuelle
- [ ] `ansible-playbook site.yml` idempotent après les fixes
- [ ] `make lint` passe
- [ ] ADR-017 à ADR-019 présentes dans ARCHITECTURE.md

---

## Phase 3 : Provisioning des instances

**Objectif** : `make apply --tags provision` installe les paquets et services

**Livrables** :
- `roles/base_system/` — paquets de base, locale, user
- `roles/incus_provision/` — méthodes d'installation (apt, pip, script, git)
- `site.yml` — phase provisioning ajoutée
- Connection plugin `community.general.incus` configuré

**Critères de validation** :
- [ ] Instance créée + provisionnée en un seul `make apply`
- [ ] Re-provisioning idempotent
- [ ] Paquets installés vérifiables

---

## Phase 4 : Snapshots

**Objectif** : `make snapshot` / `make restore`

**Livrables** :
- `roles/incus_snapshots/`
- `snapshot.yml`
- Snapshot individuel, par domaine, global
- Restore + delete

**Critères de validation** :
- [ ] Snapshot + restore round-trip fonctionnel
- [ ] Snapshot par domaine ne touche que ce domaine

---

## Phase 5 : GPU + LLM

**Objectif** : Container Ollama avec GPU fonctionnel + Open WebUI

**Livrables** :
- `roles/ollama_server/`
- `roles/open_webui/`
- Guide `docs/gpu-llm.md`
- Profil `nvidia-compute` dans infra.yml

**Critères de validation** :
- [ ] `nvidia-smi` fonctionne dans le container Ollama
- [ ] Modèle LLM téléchargeable et interrogeable
- [ ] Open WebUI accessible depuis le navigateur de l'hôte
- [ ] GPU policy `exclusive` validée par le PSOT (ADR-018)

---

## Phase 6 : Tests Molecule

**Objectif** : Tests automatisés pour chaque rôle

**Livrables** :
- `molecule/` dans chaque rôle
- CI/CD compatible (GitHub Actions ou script local)

---

## Phase 7 : Documentation + publication

**Objectif** : Projet utilisable par d'autres

**Livrables** :
- `README.md` complet
- `docs/quickstart.md`
- `docs/lab-tp.md` — guide de déploiement de TPs
- `docs/gpu-llm.md` — guide GPU
- Exemples de domaines (demo, tp-reseaux)

---

## Phase 8 : Isolation nftables inter-bridges

**Objectif** : Bloquer le trafic entre domaines au niveau réseau

**Contexte** : Par défaut, Incus crée des chaînes nftables par bridge
mais n'interdit pas le forwarding entre bridges différents. Cela signifie
qu'un container dans un domaine peut communiquer avec les containers des
autres domaines, ce qui brise l'isolation réseau.

**Livrables** :
- `roles/incus_nftables/` — règles d'isolation inter-bridges
- Règles : DROP tout trafic entre net-X et net-Y par défaut
- Exception : admin → all (pour Ansible et monitoring)
- Intégration dans site.yml (tag `nftables`)
- Documentation `docs/network-isolation.md`

**Critères de validation** :
- [ ] Trafic entre domaines non-admin bloqué (ex: perso ↛ pro)
- [ ] Trafic depuis admin vers tous les domaines autorisé (Ansible, monitoring)
- [ ] NAT vers Internet fonctionnel depuis tous les bridges
- [ ] Idempotent (règles nftables appliquées une seule fois)

**Notes** :
- Les règles nftables sont sur l'HÔTE, pas dans les containers
- C'est une exception au principe "Ansible ne modifie pas l'hôte" (ADR-004)
- Alternative : gérer via Incus ACLs si la version le supporte

---

## Phase 9 : Support VM (instances KVM)

**Objectif** : Permettre de déclarer `type: vm` dans infra.yml

**Contexte** : Certaines charges de travail nécessitent une isolation plus
forte que LXC (workloads non fiables, GPU vfio-pci, kernel custom, OS
non-Linux). Le framework doit supporter les VMs KVM en plus des containers
LXC, de manière transparente.

**Livrables** :
- `incus_instances` : branchement sur `instance_type` pour passer `--vm`
- Profils VM-spécifiques (agent réseau, resources, secure boot)
- Support `incus-agent` pour la connexion Ansible aux VMs
- Validation PSOT : contraintes VM (mémoire minimum, CPU minimum)
- Guide `docs/vm-support.md`

**Critères de validation** :
- [ ] `type: vm` dans infra.yml → VM KVM créée et joignable
- [ ] Provisioning via `community.general.incus` fonctionne dans la VM
- [ ] VM et LXC coexistent dans le même domaine
- [ ] `make apply` idempotent avec un mix LXC + VM

**Notes** :
- Les VMs sont plus lentes à démarrer (~30s vs ~2s pour LXC)
- Le `wait_for_running` devra avoir un timeout plus long pour les VMs
- Les VMs utilisent `incus-agent` au lieu de `incus exec` direct

---

## Phase 10 : Gestion GPU avancée

**Objectif** : GPU passthrough pour LXC et VM avec politique de sécurité

**Livrables** :
- Implémentation de `gpu_policy: exclusive|shared` dans le PSOT (ADR-018)
- Profil `nvidia-compute` pour LXC (device gpu + nvidia.runtime)
- Profil `gpu-passthrough` pour VM (vfio-pci + IOMMU)
- Validation PSOT : un seul GPU par instance en mode exclusive
- Gestion du device GPU au démarrage (vérification disponibilité)
- Guide `docs/gpu-advanced.md`

**Critères de validation** :
- [ ] LXC avec GPU : `nvidia-smi` fonctionne
- [ ] VM avec GPU : `nvidia-smi` fonctionne (vfio-pci)
- [ ] Mode exclusive : erreur PSOT si 2 instances déclarent GPU
- [ ] Mode shared : warning PSOT, 2 LXC partagent le GPU
- [ ] Restart du container GPU sans perte d'accès

---

## Phase 11 : VM firewall dédiée (sys-firewall style)

**Objectif** : Optionnel — routage de tout le trafic inter-domaine via une
VM firewall dédiée, à la manière de QubesOS sys-firewall

**Contexte** : En Phase 8, l'isolation se fait via nftables sur l'hôte.
Cette phase ajoute une option pour router tout le trafic via une VM
firewall dédiée, offrant une isolation plus forte (la firewall a son
propre kernel, contrairement aux containers LXC qui partagent le kernel
hôte).

**Livrables** :
- `infra.yml` : option `global.firewall_mode: host|vm`
- VM `sys-firewall` dans le domaine admin
- Configuration routage : tous les bridges passent par sys-firewall
- nftables/iptables dans la VM firewall
- Monitoring et logging centralisé

**Critères de validation** :
- [ ] Mode `host` : comportement Phase 8 (nftables sur l'hôte)
- [ ] Mode `vm` : tout le trafic inter-bridge transite par sys-firewall
- [ ] Pas de single point of failure excessif (health check + restart auto)
- [ ] Performance : latence ajoutée < 1ms pour le trafic inter-bridge

**Notes** :
- Complexité élevée — ne pas implémenter avant que Phase 8 soit stable
- Le gain de sécurité en LXC est marginal (même kernel que l'hôte)
- Le gain est significatif si les workloads sont dans des VMs
- Impact performance : double hop réseau (container → VM FW → container)

---

## État actuel

**Complétées** :
- Phase 1 : Générateur PSOT fonctionnel (make sync idempotent)
- Phase 2 : Infrastructure Incus déployée et idempotente

**Infrastructure déployée** :

| Domaine | Container       | IP          | Réseau      | Statut  |
|---------|-----------------|-------------|-------------|---------|
| admin   | admin-ansible   | 10.100.0.10 | net-admin   | Running |
| perso   | perso-desktop   | 10.100.1.10 | net-perso   | Running |
| pro     | pro-dev         | 10.100.2.10 | net-pro     | Running |
| homelab | homelab-llm     | 10.100.3.10 | net-homelab | Running |

**ADRs actives** : ADR-001 à ADR-016 + ADR-017 à ADR-019 (cette tâche)

**Problèmes connus** :
- Trafic inter-bridges ouvert (Phase 8)
- admin-ansible nécessite intervention manuelle au restart (Phase 2b)
- Hotfix `'exists'` dans failed_when non commité (Phase 2b)
- Pas de support VM effectif malgré `type:` dans infra.yml (Phase 9)
