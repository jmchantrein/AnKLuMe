# Examples

Ready-to-use `infra.yml` configurations for common use cases. Each
example is a complete, valid file that passes the PSOT generator's
validation.

## Overview

| Example | Domains | Machines | GPU | Description |
|---------|---------|----------|-----|-------------|
| [student-sysadmin](student-sysadmin/) | 2 | 3 | No | Simple anklume + lab for sysadmin students |
| [teacher-lab](teacher-lab/) | 4 | 7 | No | Admin + 3 student domains for classroom labs |
| [pro-workstation](pro-workstation/) | 4 | 5 | Yes | Compartmentalized workstation with AI homelab (LLM + STT) |
| [sandbox-isolation](sandbox-isolation/) | 2 | 3 | No | Maximum isolation for untrusted software |
| [llm-supervisor](llm-supervisor/) | 4 | 5 | Yes | 2 LLMs + supervisor for multi-model orchestration |
| [developer](developer/) | 2 | 3 | No | AnKLuMe dev setup with Incus-in-Incus testing |

## Usage

Copy the example `infra.yml` to the project root and deploy:

```bash
cp examples/<name>/infra.yml infra.yml
make sync
make check
make apply
```

Each example directory contains a `README.md` with details about the
use case, hardware requirements, and configuration.

## Customizing examples

After copying, you can:

1. Change `project_name` to your own
2. Add or remove domains and machines
3. Adjust IPs and subnet_ids
4. Add custom roles to machines

Run `make sync` after any change to regenerate the Ansible files.

## Documentation

- [Quick start guide](../docs/quickstart.md)
- [Lab deployment guide](../docs/lab-tp.md)
- [GPU + LLM guide](../docs/gpu-llm.md)
- [Full specification](../docs/SPEC.md)
