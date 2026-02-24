# Services inter-conteneurs via MCP

> **Note** : La version anglaise (`mcp-services.md`) fait foi en cas
> de divergence.

anklume fournit une exposition controllee de services entre conteneurs
via MCP (Model Context Protocol) et les proxy devices Incus. Un
conteneur peut declarer des services que d'autres conteneurs sont
autorises a appeler, avec un controle d'acces par liste blanche dans
`infra.yml`.

## Architecture

```
container-work                host              container-vault
  [client MCP]  <-- unix --> [proxy] <-- unix --> [serveur MCP]
  tools/call: sign_file                           gpg --sign
```

Le serveur MCP tourne dans le conteneur fournisseur, ecoutant sur
stdio. Un proxy device Incus relie un socket Unix du conteneur
consommateur au fournisseur. Le client MCP se connecte au serveur
via ce socket en envoyant des messages JSON-RPC.

Seuls `initialize`, `tools/list` et `tools/call` de la spec MCP
sont supportes. Pas de prompts, resources ou sampling.

## Outils disponibles

| Outil | Description |
|-------|-------------|
| `gpg_sign` | Signer le contenu d'un fichier avec GPG (signature detachee) |
| `clipboard_get` | Obtenir le contenu du presse-papier |
| `clipboard_set` | Definir le contenu du presse-papier |
| `file_accept` | Accepter un fichier entrant (base64) et l'ecrire |
| `file_provide` | Lire un fichier et retourner son contenu en base64 |

## Demarrage rapide

### 1. Declarer les services dans infra.yml

```yaml
domains:
  vault:
    subnet_id: 0
    machines:
      vault-signer:
        type: lxc
        ip: "10.100.0.10"
        services:
          - name: file_sign
            tool: gpg_sign
            consumers: [work-dev, pro-dev]
          - name: clipboard
            tool: clipboard_get
            consumers: [work-dev]
  work:
    subnet_id: 1
    machines:
      work-dev:
        type: lxc
        ip: "10.100.1.10"
```

### 2. Generer et appliquer

```bash
make sync    # Valide les declarations de services, genere host_vars
make apply   # Cree l'infrastructure
```

### 3. Utiliser le client

```bash
# Lister les outils sur une instance
make mcp-list I=vault-signer

# Appeler un outil
make mcp-call I=vault-signer TOOL=clipboard_get
make mcp-call I=vault-signer TOOL=clipboard_set ARGS='{"content": "bonjour"}'
```

## Moteur de politique

Le moteur de politique verifie qu'un appelant est autorise avant de
permettre un appel de service. Il lit les declarations `services:` de
`infra.yml`.

```bash
# Verifier si work-dev peut acceder a file_sign sur vault-signer
python3 scripts/mcp-policy.py check \
  --caller work-dev --service file_sign --infra infra.yml

# Lister tous les services declares
python3 scripts/mcp-policy.py list --infra infra.yml
```

Codes de sortie :
- `0` = acces autorise
- `1` = acces refuse ou erreur

## Regles de validation

Le generateur PSOT valide les declarations de services :

| Condition | Resultat |
|-----------|----------|
| `consumers` reference une machine inconnue | Erreur |
| `tool` n'est pas un outil MCP connu | Erreur |
| `name` duplique sur la meme machine | Erreur |
| `name` ou `tool` manquant | Erreur |
| Entree de service pas un dict | Erreur |

## Details d'implementation

### Pourquoi le SDK officiel `mcp`

anklume utilise le SDK Python MCP officiel (`pip install mcp`) avec le
framework serveur FastMCP et le client ClientSession. Cela fournit une
implementation correcte du protocole, la negociation automatique des
capacites, des definitions de tools type-safe via decorateurs, et une
compatibilite future avec l'evolution du protocole MCP. La dependance
est acceptable — anklume requiert deja des paquets pip (pyyaml, pytest,
libtmux).

### Transport

Les messages MCP sont du JSON-RPC 2.0 sur stdin/stdout, un message
par ligne. Cela correspond naturellement a :
- `incus exec <conteneur> -- python3 /opt/anklume/mcp-server.py`
- Les proxy devices Incus pour un socket Unix persistant

### Modele de securite

- Les services sont opt-in : pas de declaration = pas d'acces
- Liste blanche de consommateurs par service par machine
- Politique verifiee avant l'execution de l'outil
- Les proxy devices Incus isolent le transport
- Aucun trafic reseau ne traverse les bridges de domaine

## Cibles Makefile

| Cible | Description |
|-------|-------------|
| `make mcp-list I=<instance>` | Lister les outils MCP sur une instance |
| `make mcp-call I=<instance> TOOL=<nom>` | Appeler un outil MCP |

## Deploiement du serveur

Pour deployer le serveur MCP dans un conteneur :

```bash
# Pousser le script serveur
incus file push scripts/mcp-server.py <instance>/opt/anklume/mcp-server.py --project <projet>

# Tester
echo '{"jsonrpc":"2.0","method":"tools/list","id":1,"params":{}}' | \
  incus exec <instance> --project <projet> -- python3 /opt/anklume/mcp-server.py
```

## Depannage

### "Cannot reach MCP server"

Verifier que l'instance cible est en cours d'execution :

```bash
incus list --all-projects | grep <instance>
```

### "Unknown tool"

Verifier les outils disponibles :

```bash
make mcp-list I=<instance>
```

### La politique refuse l'acces

Verifier la declaration de service dans `infra.yml` — l'appelant
doit etre dans `consumers` :

```bash
python3 scripts/mcp-policy.py list --infra infra.yml
```
