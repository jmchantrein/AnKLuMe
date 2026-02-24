# Inter-Container Services via MCP

anklume provides controlled service exposure between containers using
MCP (Model Context Protocol) over Incus proxy devices. A container can
declare services that other containers are allowed to call, with access
controlled by an allow-list in `infra.yml`.

## Architecture

```
container-work                host              container-vault
  [MCP client]  <-- unix --> [proxy] <-- unix --> [MCP server]
  tools/call: sign_file                           gpg --sign
```

The MCP server runs inside the provider container, listening on stdio.
An Incus proxy device bridges a Unix socket from the consumer container
to the provider. The MCP client connects to the server through this
socket, sending JSON-RPC messages.

Only `initialize`, `tools/list`, and `tools/call` from the MCP spec
are supported. No prompts, resources, or sampling.

## Available tools

| Tool | Description |
|------|-------------|
| `gpg_sign` | Sign file content with GPG (detached signature) |
| `clipboard_get` | Get current clipboard content |
| `clipboard_set` | Set clipboard content |
| `file_accept` | Accept an incoming file (base64) and write to path |
| `file_provide` | Read a file and return content as base64 |

## Quick start

### 1. Declare services in infra.yml

```yaml
domains:
  vault:
    trust_level: admin
    machines:
      vault-signer:
        type: lxc
        services:
          - name: file_sign
            tool: gpg_sign
            consumers: [work-dev, pro-dev]
          - name: clipboard
            tool: clipboard_get
            consumers: [work-dev]
  work:
    trust_level: trusted
    machines:
      work-dev:
        type: lxc
```

### 2. Generate and apply

```bash
make sync    # Validates service declarations, generates host_vars
make apply   # Creates infrastructure
```

### 3. Use the client

```bash
# List tools on an instance
make mcp-list I=vault-signer

# Call a tool
make mcp-call I=vault-signer TOOL=clipboard_get
make mcp-call I=vault-signer TOOL=clipboard_set ARGS='{"content": "hello"}'
```

## Policy engine

The policy engine validates that a caller is authorized before allowing
a service call. It reads the `services:` declarations from `infra.yml`.

```bash
# Check if work-dev can access file_sign on vault-signer
python3 scripts/mcp-policy.py check \
  --caller work-dev --service file_sign --infra infra.yml

# List all declared services
python3 scripts/mcp-policy.py list --infra infra.yml
```

Exit codes:
- `0` = access allowed
- `1` = access denied or error

## Validation rules

The PSOT generator validates service declarations:

| Condition | Result |
|-----------|--------|
| `consumers` references unknown machine | Error |
| `tool` is not a known MCP tool | Error |
| `name` duplicated within same machine | Error |
| `name` or `tool` missing | Error |
| Service entry not a dict | Error |

## Implementation details

### Why the official `mcp` Python SDK

anklume uses the official MCP Python SDK (`pip install mcp`) with the
FastMCP server framework and ClientSession client. This provides correct
protocol implementation, automatic capability negotiation, type-safe
tool definitions via decorators, and future-proofing as the MCP protocol
evolves. The dependency is acceptable — anklume already requires pip
packages (pyyaml, pytest, libtmux).

### Transport

MCP messages are JSON-RPC 2.0 over stdin/stdout, one message per line.
This maps naturally to:
- `incus exec <container> -- python3 /opt/anklume/mcp-server.py` for
  direct access
- Incus proxy devices for persistent Unix socket bridging

### Security model

- Services are opt-in: no services declared = no access
- Consumer allow-list per service per machine
- Policy checked before tool execution
- Incus proxy devices provide transport isolation
- No network traffic crosses domain bridges

## Makefile targets

| Target | Description |
|--------|-------------|
| `make mcp-list I=<instance>` | List MCP tools on an instance |
| `make mcp-call I=<instance> TOOL=<name>` | Call an MCP tool |

## Server deployment

To deploy the MCP server inside a container:

```bash
# Push the server script
incus file push scripts/mcp-server.py <instance>/opt/anklume/mcp-server.py --project <project>

# Test it
echo '{"jsonrpc":"2.0","method":"tools/list","id":1,"params":{}}' | \
  incus exec <instance> --project <project> -- python3 /opt/anklume/mcp-server.py
```

## Proxy device setup

To create a persistent Unix socket bridge between containers:

```bash
# On the provider container, run the server on a socket
# (requires socat or systemd socket activation)

# Add proxy device bridging the socket
incus config device add <consumer> mcp-<service> proxy \
  connect=unix:/run/mcp-<service>.sock \
  listen=unix:/run/mcp-<service>.sock \
  bind=instance
```

## Troubleshooting

### "Cannot reach MCP server"

Verify the target instance is running:

```bash
incus list --all-projects | grep <instance>
```

Verify the server script is deployed:

```bash
incus exec <instance> --project <project> -- ls /opt/anklume/mcp-server.py
```

### "Unknown tool"

Check available tools:

```bash
make mcp-list I=<instance>
```

### Policy denies access

Check the service declaration in `infra.yml` — the caller must be
listed in `consumers`:

```bash
python3 scripts/mcp-policy.py list --infra infra.yml
```
