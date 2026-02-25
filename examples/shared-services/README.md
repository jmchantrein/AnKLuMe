# Shared Services (print)

Dedicated CUPS print server container with USB printer passthrough
and network printer access via macvlan. Other domains print via IPP
(port 631) controlled by network policies.

## Use case

You want centralized print management in a dedicated container.
USB printers are passed through directly, and network printers
(WiFi/Ethernet) are accessed via a macvlan NIC that gives the
container direct LAN access. Other domains send print jobs via
IPP without direct LAN access.

## Domains

| Domain | trust_level | Description |
|--------|-------------|-------------|
| anklume | admin | Ansible controller (protected) |
| shared | semi-trusted | User-facing shared services |
| pro | trusted | Professional workstation |
| perso | semi-trusted | Personal domain |

## Machines

| Machine | Domain | Type | Role |
|---------|--------|------|------|
| anklume-instance | anklume | lxc | Ansible controller |
| shared-print | shared | lxc | CUPS print server |
| pro-dev | pro | lxc | Development workstation |
| perso-desktop | perso | lxc | Personal desktop |

## Network policies

- `pro` can access `shared` on port 631 (IPP)
- `perso` can access `shared` on port 631 (IPP)

## Hardware requirements

- 2 CPU cores
- 4 GB RAM
- 10 GB disk

## Getting started

```bash
cp examples/shared-services/infra.yml infra.yml
make sync
make apply

# Setup CUPS in the print container
make apply-print I=shared-print

# Add a USB printer
scripts/cups-setup.sh add-usb shared-print --vendor 04b8 --product 0005

# Add network printer access
scripts/cups-setup.sh add-network shared-print --nic-parent enp3s0

# Check status
scripts/cups-setup.sh status shared-print
```

## Printing from other domains

```bash
# Install CUPS client
incus exec pro-dev --project pro -- apt install -y cups-client

# Add remote printer (use the container's IP from `make sync` output)
incus exec pro-dev --project pro -- \
    lpadmin -p remote-printer -v ipp://shared-print:631/printers/MyPrinter -E

# Print a test page
incus exec pro-dev --project pro -- lp -d remote-printer /etc/hostname
```
