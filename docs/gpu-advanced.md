# Advanced GPU Management

anklume supports GPU passthrough for both LXC containers and KVM VMs,
with a security policy that controls how many instances can access the
GPU simultaneously.

## GPU access policy (ADR-018)

By default, anklume enforces **exclusive** GPU access: only one instance
across all domains can have GPU access. This prevents VRAM conflicts and
security risks from shared GPU memory on consumer GPUs.

### Exclusive mode (default)

```yaml
# infra.yml — only ONE machine can have gpu: true
global:
  addressing:
    base_octet: 10
    zone_base: 100
  # gpu_policy: exclusive  # This is the default

domains:
  ai-tools:
    trust_level: semi-trusted
    profiles:
      nvidia-compute:
        devices:
          gpu:
            type: gpu
            gputype: physical
    machines:
      gpu-server:
        type: lxc
        gpu: true
        profiles: [default, nvidia-compute]
        roles: [base_system, ollama_server, stt_server]
```

If you add a second GPU machine in exclusive mode, `make sync` will fail:

```
Validation errors:
  - GPU policy is 'exclusive' but 2 instances have GPU access:
    gpu-server, work-gpu. Set global.gpu_policy: shared to allow this.
```

### Shared mode

For workloads that benefit from concurrent GPU access (e.g., multiple
LLM inference servers), enable shared mode:

```yaml
global:
  gpu_policy: shared  # Allow multiple instances to share the GPU
```

`make sync` will emit a warning but proceed:

```
WARNING: GPU policy is 'shared': 2 instances share GPU access
(llm-alpha-server, llm-beta-server). No VRAM isolation on consumer GPUs.
```

**Risks of shared GPU access:**
- No VRAM isolation on consumer GPUs (no SR-IOV)
- Shared driver state could cause crashes under load
- Any container with GPU access can read GPU memory

### Merging GPU workloads to avoid shared mode

If your GPU workloads can coexist in a single container (e.g., Ollama
and Speaches STT), merging them into one machine allows you to keep
the default `gpu_policy: exclusive`. Both services run as separate
systemd units and share VRAM within the same process namespace, without
the security and stability risks of cross-container GPU sharing.

See [stt-service.md](stt-service.md) for the recommended single-container
architecture for LLM + STT.

## GPU in LXC containers

LXC GPU passthrough exposes the host's GPU driver directly to the
container via the `gpu` device type.

### Profile setup

Define an `nvidia-compute` profile in the domain:

```yaml
profiles:
  nvidia-compute:
    devices:
      gpu:
        type: gpu
        gputype: physical
```

### Machine configuration

```yaml
machines:
  my-gpu-container:
    type: lxc
    gpu: true
    profiles: [default, nvidia-compute]
    roles: [base_system, ollama_server, stt_server]
```

### How it works

1. The profile adds a `gpu` device with `type: gpu` to the instance
2. Incus mounts the GPU device nodes (`/dev/nvidia*`) into the container
3. The NVIDIA driver from the host is accessible inside the container
4. `nvidia-smi` works inside the container without additional setup

### Verification

```bash
incus exec gpu-server --project ai-tools -- nvidia-smi
```

## GPU in KVM VMs

VM GPU passthrough uses **vfio-pci**, which provides hardware-level
isolation by binding the PCI device directly to the VM.

### Prerequisites

- IOMMU must be enabled in BIOS and kernel (`intel_iommu=on` or
  `amd_iommu=on`)
- The GPU must be in its own IOMMU group (or ACS override applied)
- The `vfio-pci` kernel module must be loaded

### Profile setup for VMs

```yaml
profiles:
  gpu-passthrough:
    devices:
      gpu:
        type: gpu
        pci: "0000:01:00.0"  # PCI address of the GPU
    config:
      security.secureboot: "false"
```

### Machine configuration

```yaml
machines:
  my-gpu-vm:
    type: vm
    gpu: true
    profiles: [default, gpu-passthrough]
    config:
      limits.cpu: "4"
      limits.memory: "8GiB"
```

### Important notes

- vfio-pci passthrough gives the VM **exclusive** hardware access to
  the PCI device — the host and other instances cannot use it
- The `shared` gpu_policy is irrelevant for VMs (PCI devices cannot
  be shared without SR-IOV)
- The VM needs its own NVIDIA driver installed inside the guest OS

## GPU detection

The `ollama_server` role automatically detects GPU availability:

```yaml
# Inside the role:
- name: OllamaServer | Check GPU access
  ansible.builtin.command:
    cmd: nvidia-smi
  register: ollama_gpu_check
  changed_when: false
  failed_when: false
```

If no GPU is detected, Ollama runs in CPU-only mode.

## PSOT validation rules

The generator enforces these rules:

| Condition | gpu_policy: exclusive | gpu_policy: shared |
|-----------|----------------------|-------------------|
| 0 GPU instances | OK | OK |
| 1 GPU instance | OK | OK |
| 2+ GPU instances | **Error** | Warning |
| Invalid gpu_policy | **Error** | **Error** |

GPU detection methods:
- Direct: `gpu: true` flag on the machine
- Indirect: machine uses a profile with a `gpu` device type

## Troubleshooting

### nvidia-smi not found in container

The container needs the NVIDIA driver libraries. For Debian-based
images, the host's driver version must match what's available inside
the container. The `ollama_server` role handles this for Ollama
workloads.

### GPU device not appearing in container

```bash
# Verify the device is attached
incus config show my-container --project my-domain | grep -A5 devices

# Verify the profile includes the GPU device
incus profile show nvidia-compute --project my-domain
```

### Container restart loses GPU access

After a container restart, GPU devices should persist. If they don't:

```bash
# Re-apply the infrastructure
make apply-infra

# Or restart the specific instance
incus restart my-container --project my-domain
```
