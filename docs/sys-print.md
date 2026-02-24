# Print Service (sys-print)

anklume supports a dedicated CUPS print server container. USB printers
are passed through via Incus device passthrough, and network printers
are accessed via a macvlan NIC that gives the container direct LAN access.
Other domains print via IPP (port 631) through `network_policies`.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         Host                             │
│                                                          │
│  net-pro ────────────┐                                  │
│    pro-dev           │  IPP :631     ┌───────────────┐  │
│                      ├──────────────▶│ net-print      │  │
│  net-perso ──────────┤               │  sys-print     │  │
│    perso-desktop     │               │  CUPS :631     │  │
│                      │               │                │  │
│                      │               │  USB: printer  │  │
│                      │               │  NIC: macvlan  │  │
│                      │               └────────┬───────┘  │
│                      │                        │          │
│                      │                   Physical LAN    │
│                      │                   (WiFi printers)  │
└──────────────────────┴───────────────────────────────────┘
```

## Quick start

### 1. Declare the print service in infra.yml

```yaml
domains:
  print-service:
    description: "Dedicated print service domain"
    trust_level: trusted
    machines:
      sys-print:
        description: "CUPS print server"
        type: lxc
        roles:
          - base_system

network_policies:
  - description: "Pro domain prints via CUPS"
    from: pro
    to: print-service
    ports: [631]
    protocol: tcp

  - description: "Perso domain prints via CUPS"
    from: perso
    to: print-service
    ports: [631]
    protocol: tcp
```

### 2. Deploy infrastructure

```bash
make sync
make apply
```

### 3. Setup CUPS in the container

```bash
make apply-print I=sys-print
```

### 4. Add printers

```bash
# USB printer (requires vendor and product IDs)
scripts/sys-print.sh add-usb sys-print --vendor 04b8 --product 0005

# Network printer (macvlan NIC for physical LAN access)
scripts/sys-print.sh add-network sys-print --nic-parent enp3s0
```

### 5. Check status

```bash
scripts/sys-print.sh status sys-print
```

## Commands

### setup

Install and configure CUPS for remote access:

```bash
scripts/sys-print.sh setup <instance> [--project PROJECT]
```

The setup command:
1. Installs `cups` and `cups-filters` packages
2. Configures CUPS for remote access (`Listen *:631`, `Allow @LOCAL`)
3. Enables web interface
4. Enables and starts the CUPS service

### add-usb

Add a USB printer via Incus device passthrough:

```bash
scripts/sys-print.sh add-usb <instance> --vendor VID --product PID [--project PROJECT]
```

Find your printer's vendor and product IDs with `lsusb` on the host:

```bash
lsusb
# Bus 001 Device 005: ID 04b8:0005 Seiko Epson Corp. Printer
#                         ^^^^:^^^^
#                         vendor:product
```

The command uses `incus config device add` to attach the USB device
directly to the container.

### add-network

Add a macvlan NIC for network printer discovery:

```bash
scripts/sys-print.sh add-network <instance> --nic-parent IFACE [--project PROJECT]
```

This gives the container direct access to the physical LAN, allowing
it to discover WiFi and Ethernet network printers. The `--nic-parent`
must be the host's physical network interface (e.g., `eth0`, `enp3s0`,
`wlan0`).

After adding the NIC, restart the instance for it to take effect.

### status

Show CUPS service status and configured printers:

```bash
scripts/sys-print.sh status <instance> [--project PROJECT]
```

## Makefile targets

| Target | Description |
|--------|-------------|
| `make apply-print I=<instance>` | Setup CUPS print service in container |

Accepts optional `PROJECT=<project>` parameter.

## CUPS web interface

After setup, the CUPS web interface is available at:

```
http://<instance-ip>:631
```

From the web interface you can:
- Add and configure printers
- Manage print queues
- View print job history

## Printing from other domains

Containers in other domains can print if allowed by `network_policies`:

```bash
# Install CUPS client in the client container
incus exec pro-dev --project pro -- apt install -y cups-client

# Add the remote printer
incus exec pro-dev --project pro -- \
    lpadmin -p remote-printer -v ipp://sys-print:631/printers/MyPrinter -E

# Print a test page
incus exec pro-dev --project pro -- \
    lp -d remote-printer /etc/hostname
```

## USB printer passthrough

Incus USB device passthrough gives the container direct access to the
USB device. Key points:

- The device must be plugged in when the container starts (or
  hot-plugged after adding the device config)
- Only one container can own a USB device at a time
- The host does not need printer drivers installed

### Finding USB IDs

```bash
# On the host
lsusb
# Bus 001 Device 005: ID 04b8:0005 Seiko Epson Corp. Printer

# Vendor ID: 04b8
# Product ID: 0005
```

### Removing a USB device

```bash
incus config device remove sys-print printer-04b8-0005 --project print-service
```

## Network printer access via macvlan

The macvlan NIC gives the container a virtual interface on the physical
LAN, with its own MAC and IP address. This allows the container to
discover and communicate with network printers directly.

Advantages:
- Direct access to WiFi and Ethernet printers
- mDNS/Bonjour printer discovery works natively
- No port forwarding needed

Limitations:
- The host cannot communicate with the container via the macvlan
  interface (use the bridge interface instead)
- Requires the physical interface name (varies by host)

## Troubleshooting

### CUPS not starting

Check the service logs:

```bash
incus exec sys-print --project print-service -- journalctl -u cups -f
```

### USB printer not detected

Verify the device is attached:

```bash
incus config device show sys-print --project print-service
```

Check that the USB device is plugged in on the host:

```bash
lsusb | grep <vendor-id>
```

### Network printer not found

After adding a macvlan NIC, restart the instance:

```bash
incus restart sys-print --project print-service
```

Verify the NIC is up:

```bash
incus exec sys-print --project print-service -- ip addr show
```

### Permission denied on printing

CUPS is configured with `Allow @LOCAL` which allows access from the
local network. If access is denied from another domain, verify the
`network_policies` in `infra.yml` allow port 631 from the client domain.
