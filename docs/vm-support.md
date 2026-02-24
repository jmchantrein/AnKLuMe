# VM Support (KVM Instances)

anklume supports both LXC containers and KVM virtual machines. This guide
covers how to declare, create, and provision VMs alongside containers.

## When to use VMs vs containers

| Criteria | LXC Container | KVM VM |
|----------|--------------|--------|
| Startup time | ~1-2 seconds | ~10-30 seconds |
| Resource overhead | Minimal (shared kernel) | Higher (full kernel + UEFI) |
| Isolation level | Namespace isolation | Hardware-level isolation |
| GPU passthrough | Direct (nvidia.runtime) | vfio-pci (IOMMU required) |
| Non-Linux guests | No | Yes |
| Custom kernel | No (shared with host) | Yes |

**Use VMs when you need**:
- Stronger isolation for untrusted workloads
- A different kernel version or non-Linux OS
- GPU passthrough via vfio-pci with hardware isolation
- Testing kernel modules or system-level software

**Use LXC containers for everything else** — they are faster, lighter,
and sufficient for most compartmentalization use cases.

## Declaring a VM in infra.yml

Set `type: vm` on any machine:

```yaml
domains:
  secure:
    description: "High-isolation domain"
    trust_level: untrusted
    machines:
      secure-sandbox:
        description: "Untrusted workload sandbox"
        type: vm
        roles: [base_system]
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
```

VMs and LXC containers can coexist in the same domain:

```yaml
domains:
  work:
    trust_level: trusted
    machines:
      work-dev:
        type: lxc
      work-sandbox:
        type: vm
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
```

## How it works

### Instance creation

The `incus_instances` role branches on `instance_type`:

- `type: lxc` → `incus launch <image> <name> --project <domain>`
- `type: vm` → `incus launch <image> <name> --vm --project <domain>`

The same OS image alias works for both. Incus automatically fetches the
correct image variant (container rootfs vs. VM disk image).

### Boot wait

VMs take longer to boot than containers (UEFI firmware + kernel boot).
The role uses different timeouts:

| Type | Retries | Delay | Total timeout |
|------|---------|-------|---------------|
| LXC | 30 | 2s | 60s |
| VM | 60 | 2s | 120s |

These are configurable via role defaults:

```yaml
incus_instances_lxc_retries: 30
incus_instances_lxc_delay: 2
incus_instances_vm_retries: 60
incus_instances_vm_delay: 2
```

### incus-agent wait

After a VM reaches Running status, the `incus-agent` inside the VM
still needs a few seconds to initialize. The role polls `incus exec
<vm> -- true` until the agent responds before continuing.

This is critical: without a running agent, `incus exec` (and therefore
the `community.general.incus` connection plugin) cannot connect to the
VM, and the provisioning phase would fail.

Agent wait configuration:

```yaml
incus_instances_vm_agent_retries: 30
incus_instances_vm_agent_delay: 2
```

### Provisioning

The `community.general.incus` connection plugin works identically for
containers and VMs. It uses `incus exec` under the hood, which
communicates with the `incus-agent` via virtio-vsock for VMs.

No SSH is needed. No change to `site.yml` provisioning phase.

## VM-specific configuration

### Resource limits

Incus defaults for VMs are 1 vCPU and 1 GiB memory. Override via
`config:` in infra.yml:

```yaml
config:
  limits.cpu: "2"
  limits.memory: "4GiB"
```

### Secure boot

Secure boot is enabled by default for VMs. To disable it (e.g., for
testing or non-UEFI images):

```yaml
config:
  security.secureboot: "false"
```

### VM-specific profiles

Create a domain-level profile for VMs with appropriate defaults:

```yaml
domains:
  secure:
    subnet_id: 4
    profiles:
      vm-resources:
        config:
          limits.cpu: "2"
          limits.memory: "2GiB"
    machines:
      secure-vm:
        type: vm
        profiles: [default, vm-resources]
```

## OS image compatibility

Most Linux distributions from the `images:` remote have both container
and VM variants:

| Distribution | VM support |
|-------------|-----------|
| Debian 13 (trixie) | Yes |
| Ubuntu 24.04+ | Yes |
| Alpine 3.20+ | Yes |
| Fedora 41+ | Yes |
| Arch Linux | Yes (amd64) |

Use the same image reference for both types:

```yaml
# Both use images:debian/13 — Incus picks the right variant
container:
  type: lxc
  os_image: "images:debian/13"

vm:
  type: vm
  os_image: "images:debian/13"
```

## Validation

The PSOT generator validates:

- `type` must be `lxc` or `vm` (error on invalid values)
- All existing validations (unique names, IPs, subnets) apply equally

## Troubleshooting

### VM stuck at "Starting"

VMs take 10-30 seconds to boot. The role waits up to 120 seconds.
If the timeout is exceeded:

```bash
# Check VM console for boot issues
incus console <vm-name> --project <domain>

# Check VM status
incus info <vm-name> --project <domain>
```

### incus-agent not responding

If provisioning fails with connection errors after the VM is Running:

```bash
# Test agent manually
incus exec <vm-name> --project <domain> -- true

# Check agent status inside VM (via console)
incus console <vm-name> --project <domain>
# Then: systemctl status incus-agent
```

Standard `images:` images come with `incus-agent` pre-configured.
Custom images may need manual agent installation.

### VM requires more memory

If the VM fails to boot or runs out of memory during provisioning:

```bash
incus config set <vm-name> limits.memory=2GiB --project <domain>
incus restart <vm-name> --project <domain>
```
