# Print Service (sys-print)

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

| Domain | subnet_id | Description |
|--------|-----------|-------------|
| anklume | 0 | Ansible controller (protected) |
| print-service | 7 | Dedicated print service |
| pro | 2 | Professional workstation |
| perso | 1 | Personal domain |

## Machines

| Machine | Domain | Type | IP | Role |
|---------|--------|------|-----|------|
| anklume-instance | anklume | lxc | 10.100.0.10 | Ansible controller |
| sys-print | print-service | lxc | 10.100.7.10 | CUPS print server |
| pro-dev | pro | lxc | 10.100.2.10 | Development workstation |
| perso-desktop | perso | lxc | 10.100.1.10 | Personal desktop |

## Network policies

- `pro` can access `print-service` on port 631 (IPP)
- `perso` can access `print-service` on port 631 (IPP)

## Hardware requirements

- 2 CPU cores
- 4 GB RAM
- 10 GB disk

## Getting started

```bash
cp examples/sys-print/infra.yml infra.yml
make sync
make apply

# Setup CUPS in the print container
make apply-print I=sys-print

# Add a USB printer
scripts/sys-print.sh add-usb sys-print --vendor 04b8 --product 0005

# Add network printer access
scripts/sys-print.sh add-network sys-print --nic-parent enp3s0

# Check status
scripts/sys-print.sh status sys-print
```

## Printing from other domains

```bash
# Install CUPS client
incus exec pro-dev --project pro -- apt install -y cups-client

# Add remote printer
incus exec pro-dev --project pro -- \
    lpadmin -p remote-printer -v ipp://10.100.7.10:631/printers/MyPrinter -E

# Print a test page
incus exec pro-dev --project pro -- lp -d remote-printer /etc/hostname
```
