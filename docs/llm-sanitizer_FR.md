# Proxy de Sanitisation LLM

> Traduction francaise de [`llm-sanitizer.md`](llm-sanitizer.md). En cas de divergence, la version anglaise fait foi.

Phase 39 — Anonymisation transparente des requetes LLM a destination du cloud.

## Vue d'ensemble

Lorsqu'un domaine envoie des prompts a des fournisseurs LLM cloud, ces
prompts peuvent contenir des donnees specifiques a l'infrastructure :
adresses IP internes, noms de ressources Incus, noms d'hotes Ansible,
identifiants ou FQDNs internes. Le proxy de sanitisation LLM intercepte
ces requetes et remplace les identifiants sensibles par des marqueurs
generiques avant que les donnees ne quittent le perimetre local.

## Architecture

```
Instance du domaine      Proxy sanitiseur         API LLM cloud
  (client LLM)    --->   (patterns regex)   --->  (OpenAI, etc.)
                          |                |
                          | audit.log      |
                          | (redactions)   |
```

Le proxy s'execute dans le perimetre reseau du domaine. Il est
transparent pour le client LLM : le client envoie ses requetes au
point d'acces du proxy, qui sanitise le contenu et le transmet a
l'API en amont. Les reponses de l'API sont transmises sans
modification.

## Configuration

### infra.yml

Parametres par domaine dans `infra.yml` :

```yaml
domains:
  pro:
    trust_level: trusted
    ai_provider: cloud          # local | cloud | local-first
    ai_sanitize: true           # true | false | "always"
    machines:
      pro-dev:
        type: lxc
        roles: [base_system, llm_sanitizer]
```

### Valeurs par defaut

| Champ | Defaut | Effet |
|-------|--------|-------|
| `ai_provider` | `local` | Toute l'inference sur le reseau local |
| `ai_sanitize` | auto | `false` pour local, `true` pour cloud/local-first |

### Propagation

Le generateur ecrit dans `group_vars/<domain>.yml` :
- `domain_ai_provider` : la valeur de fournisseur resolue
- `domain_ai_sanitize` : la valeur de sanitisation resolue

## Patterns de detection

Le proxy est fourni avec des patterns regex organises par categorie :

### Adresses IP
- IPs de zone anklume (`10.100-159.x.x`, convention ADR-038)
- RFC 1918 Classe A (`10.0.0.0/8`)
- RFC 1918 Classe B (`172.16.0.0/12`)
- RFC 1918 Classe C (`192.168.0.0/16`)
- Sous-reseaux en notation CIDR

### Ressources Incus
- Noms de projets (avec prefixe d'imbrication optionnel)
- Noms de ponts (`net-<domain>`)
- Noms d'instances (`<domain>-<machine>`)
- Commandes CLI Incus avec arguments de ressource

### FQDNs internes
- Domaines `*.internal`, `*.corp`, `*.local`, `*.lan`

### Identifiants de service
- Chemins de socket Unix Incus
- Points d'acces API Ollama
- URLs de services locaux sur IPs privees

### Noms Ansible
- `ansible_host` avec valeurs IP
- Chemins de fichiers `group_vars/`, `host_vars/`, `inventory/`

### Identifiants et secrets
- Tokens Bearer
- En-tetes de cles API
- Patterns courants de variables secretes (`password=`, `token=`)
- En-tetes de cles privees SSH
- Chaines base64 longues (probablement des secrets)

## Variables du role

Toutes les variables utilisent le prefixe `llm_sanitizer_` :

| Variable | Defaut | Description |
|----------|--------|-------------|
| `llm_sanitizer_listen_port` | `8089` | Port d'ecoute du proxy |
| `llm_sanitizer_upstream_endpoint` | `http://localhost:11434` | API LLM en amont |
| `llm_sanitizer_replacement_mode` | `mask` | `mask` ou `pseudonymize` |
| `llm_sanitizer_audit_enabled` | `true` | Activer la journalisation d'audit |
| `llm_sanitizer_audit_log_path` | `/var/log/llm-sanitizer/audit.log` | Emplacement du journal d'audit |
| `llm_sanitizer_enable_ip_patterns` | `true` | Activer la detection des IPs |
| `llm_sanitizer_enable_incus_patterns` | `true` | Activer la detection des noms Incus |
| `llm_sanitizer_enable_fqdn_patterns` | `true` | Activer la detection des FQDNs |
| `llm_sanitizer_enable_credential_patterns` | `true` | Activer la detection des identifiants |
| `llm_sanitizer_enable_ansible_patterns` | `true` | Activer la detection des noms Ansible |
| `llm_sanitizer_enable_service_patterns` | `true` | Activer la detection des IDs de service |

## Modes de remplacement

### Masquage (defaut)
Remplace les correspondances par des marqueurs generiques :
- `10.120.0.5` -> `10.ZONE.SEQ.HOST`
- `net-pro` -> `net-DOMAIN`
- `Bearer eyJhbG...` -> `Bearer [REDACTED]`

### Pseudonymisation
Remplace les correspondances par des pseudonymes coherents (la meme
entree produit toujours la meme sortie au sein d'une session). Utile
lorsque le LLM doit raisonner sur les relations entre entites sans
connaitre leurs vrais noms.

## Journal d'audit

Lorsque `llm_sanitizer_audit_enabled` est `true`, chaque redaction est
journalisee avec :
- Horodatage
- Categorie et nom du pattern ayant matche
- Valeurs originale et de remplacement
- Metadonnees de la requete (modele, point d'acces)

Le flag `llm_sanitizer_audit_log_redacted_only` (defaut `true`) limite
la journalisation aux requetes ayant subi au moins une redaction.

## Liens

- ADR-044 : Registre de decision du proxy de sanitisation LLM
- ADR-038 : Adressage IP par niveau de confiance (patterns ciblant 10.1xx)
- ADR-032 : Acces exclusif au reseau ai-tools
- SPEC.md : Contraintes de validation `ai_provider` et `ai_sanitize`
