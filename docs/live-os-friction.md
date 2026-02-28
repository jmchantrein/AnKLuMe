# Live OS — Friction Point Analysis (Student Perspective)

A computer science student boots anklume from a USB stick on their
laptop. This document traces every friction point from boot to first
useful work, proposes solutions, and maps dependencies.

## Conventions

- **Severity**: `BLOQUANT` (cannot continue), `MAJEUR` (painful, workaround exists), `MINEUR` (annoying)
- **Dependencies**:
  - `-> eliminates: F-XX` — fixing this point makes F-XX disappear
  - `requires: F-XX unfixed` — this point only exists if F-XX is NOT fixed

---

## Phase 1 — Obtaining the ISO

### F-01 | BLOQUANT | No pre-built ISO available

The student must clone the repo, install build deps, and run
`sudo scripts/build-image.sh` (~30-60min, root, 5GB+ disk). A student
who just wants to try anklume cannot.

**Solution**: Publish pre-built ISOs on GitHub Releases (Debian+KDE,
Debian+sway). Automate via CI.

-> eliminates: F-02, F-03

### F-02 | MAJEUR | Build dependencies undiscoverable

`build-image.sh` fails at random points if host is missing
`debootstrap`, `grub-mkstandalone`, `xorriso`, `mksquashfs`, etc.
No single command installs everything.

**Solution**: Add `scripts/build-image.sh --install-deps` that installs
all required host packages.

requires: F-01 unfixed

### F-03 | MAJEUR | `dd` is the only documented USB write method

`sudo dd if=... of=/dev/sdX bs=4M` can destroy the wrong disk. No
mention of safer alternatives.

**Solution**: Document Ventoy (copy ISO, done), balenaEtcher,
GNOME Disks. Add a warning about `dd` target verification.

---

## Phase 2 — GRUB Boot Menu

### F-04 | MAJEUR | 16 menu entries, no guidance

4 top-level + 4 "More Desktops" + 8 "Advanced". Student must choose
between KDE/sway/labwc, GPU/no-GPU, toram/direct without knowing
what any of these mean.

**Solution**: Single default entry: `anklume Live` (KDE, toram,
auto-detect GPU at initramfs level). Move everything else to
`Advanced options` submenu. Add 3-second help text under each entry.

-> eliminates: F-05, F-06

### F-05 | MAJEUR | GPU vs no-GPU requires hardware knowledge

Wrong choice: "GPU" on non-NVIDIA hardware = harmless (module just
doesn't load). "No GPU" on NVIDIA hardware = no hardware acceleration.
But student doesn't know which to pick.

**Solution**: Auto-detect in initramfs or early boot. Try loading
`nvidia` module; if fail, blacklist automatically. Remove the choice.

requires: F-04 unfixed

### F-06 | MINEUR | "toram" is unexplained jargon

No description of what toram does. Student doesn't know it copies the
OS to RAM for speed and USB ejectability.

**Solution**: Rename to "anklume Live (fast — loads into RAM)" if
keeping the option visible. Otherwise just default to toram.

requires: F-04 unfixed

---

## Phase 3 — First Login / Desktop

### F-07 | MINEUR | Hardcoded username `jmc`

Build script creates user `jmc`. This is clearly a developer name,
not a generic student account.

**Solution**: Use `anklume` or `student` as username. Or make it
configurable at build time (`--user`).

### F-08 | MAJEUR | Password not communicated anywhere

Password is `anklume` but nothing on screen tells the student. If
they need `sudo`, they're stuck.

**Solution**: Display in GRUB help text, in TTY login prompt (motd),
and as a desktop notification on first boot.

### F-09 | MAJEUR | sway/labwc: no UI affordances

Tiling WMs have no window decorations, no application menu, no
system tray. A student used to GNOME/KDE/Windows sees a blank
screen with a status bar.

**Solution**: KDE Plasma is already GRUB default — keep it. For
sway/labwc, add a translucent keybinding cheat sheet overlay on
first boot (dismiss with any key).

### F-10 | BLOQUANT | No discoverability on sway/labwc

Student on sway sees a dark screen. Super+Enter for terminal,
Super+d for launcher — zero discoverability. They cannot even
open a terminal.

**Solution**: Auto-open a `foot` terminal on first sway launch
(besides the welcome wizard). Add a permanent waybar widget
"? Raccourcis" linking to keybindings file.

requires: F-09 (sway/labwc only)

### F-11 | BLOQUANT | AZERTY keyboard assumed, no alternative

`KEYMAP=fr` and `XKB_DEFAULT_LAYOUT=fr` are hardcoded. A non-French
student cannot type `[`, `{`, `|`, `\` or even basic punctuation
correctly.

**Solution**: Add `anklume.keymap=XX` kernel parameter support.
Offer keyboard layout selection in the welcome wizard. Default to
`fr` but make it switchable.

### F-12 | MINEUR | sway workspace bindings broken on AZERTY

`bindsym $mod+1` requires Shift on AZERTY (physical "1" key
produces "&"). Switching workspaces needs $mod+Shift+&, which
is not intuitive.

**Solution**: Add `--to-code` flag to all keybindings in sway-config:
`bindsym --to-code $mod+1 workspace number 1`. This binds to the
physical key position regardless of layout.

---

## Phase 4 — Welcome Wizard

### F-13 | MINEUR | Welcome wizard may not be visible

On sway, `exec_always { foot -e python3 welcome.py }` spawns a
terminal that may lack focus or appear behind others.

**Solution**: Add sway `for_window` rule to make the welcome
terminal floating, centered, and focused. Set app_id on foot
(`foot --app-id anklume-welcome`).

### F-14 | MAJEUR | Three choices without context

- "Configure persistence" — what does this mean?
- "Explore without persistence" — how bad is "data lost"?
- "Skip (expert)" — am I an expert? Probably not.

**Solution**: Rewrite:
1. "Save my work (needs a second disk or partition)"
2. "Just try it (everything disappears on shutdown)"
3. "I know what I'm doing — skip"

Add 1-line explanation under each option.

### F-15 | BLOQUANT | "Explore" leaves the system non-functional

Student picks option 2 ("explore"). Wizard ends. Now what?
- Incus is not initialized (no `incus admin init`)
- No storage pool, no network
- `anklume sync` fails (`require_container` guard)
- Student is stuck with a desktop and zero infrastructure

**Solution**: "Explore" mode must auto-provision:
1. `incus admin init --minimal` (dir backend on tmpfs)
2. Copy starter `infra.yml` to working directory
3. Run `anklume sync && anklume domain apply`
4. Print "Your lab is ready. Open a terminal and try: `anklume console`"

-> eliminates: F-19, F-24, F-25, F-26, F-30

### F-16 | BLOQUANT | "Persist" requires a second disk >= 100GB

Most students have ONE disk (internal SSD with their main OS) +
the USB stick running the live OS. `first-boot.sh` refuses if no
disk >= 100GB is found (excluding the root device).

**Solution**: Offer alternative storage modes:
- Partition on existing disk (shrink existing partition)
- Loop file on any writable filesystem
- `dir` backend (no ZFS/BTRFS, just a directory)
- Lower the size threshold or remove it entirely

### F-17 | MINEUR | ZFS vs BTRFS choice is meaningless to students

Student has no idea what ZFS or BTRFS are.

**Solution**: Auto-select BTRFS (kernel-native, no extra module).
Offer ZFS only as "Advanced: ZFS (recommended for servers)".

requires: F-16 unfixed

### F-18 | MINEUR | LUKS encryption prompt is premature

"Encrypt the storage disk with LUKS? (y/n)" — student doesn't know
the trade-offs (password on every boot vs. data protection).

**Solution**: Default to no encryption in student mode. Show encryption
as an advanced option with a 1-line explanation.

requires: F-16 unfixed

---

## Phase 5 — Incus Initialization

### F-19 | BLOQUANT | `first-boot.sh` doesn't initialize Incus

Creates a storage pool but never runs `incus admin init`. Result:
no default network, no default profile, `incus launch` fails.

**Solution**: After pool creation, run `incus admin init --preseed`
with the created pool as default storage. Or merge the relevant
parts of `bootstrap.sh` into `first-boot.sh`.

-> eliminates: F-26

### F-20 | BLOQUANT | `pool.conf` written to wrong path

`first-boot.sh` writes `pool.conf` to CWD (`./pool.conf`).
The systemd guard checks `/mnt/anklume-persist/pool.conf`.
They never match. Result: `anklume-first-boot.service` re-runs
every boot.

**Solution**: Write to `/mnt/anklume-persist/pool.conf`. Create
`/mnt/anklume-persist/` if the persist partition is available,
or fall back to `/var/lib/anklume/pool.conf` with the systemd
ConditionPathExists updated to match.

### F-21 | MAJEUR | `anklume-first-boot.service` races with `getty` on tty1

The service has `TTYPath=/dev/tty1` and `StandardInput=tty`, but
`getty@tty1.service` also starts for autologin. They compete for
the same TTY: first-boot.sh blocks waiting for input while getty
tries to prompt login.

**Solution**: Remove the systemd service entirely. Run first-boot
only from the welcome wizard (which runs after login, inside a
proper terminal). Or use a dedicated tty (tty2).

---

## Phase 6 — Running anklume Commands

### F-22 | BLOQUANT | `require_container` blocks ALL commands on host

On live OS, the student IS on the host (`systemd-detect-virt` →
`none`). Every useful command fails:
- `anklume sync` → "must run inside anklume-instance"
- `anklume domain apply` → same
- `anklume init` → same

But `anklume-instance` doesn't exist (only `bootstrap.sh` creates it).

**Solution**: Detect live OS context (`boot=anklume` in
`/proc/cmdline` or `/etc/anklume/live` marker file) and bypass
`require_container`. On live OS, the host IS the admin environment.

-> eliminates: F-23

### F-23 | BLOQUANT | No `anklume-instance` and no way to create it

The standard workflow requires `incus exec anklume-instance -- bash`.
On live OS this container doesn't exist. `bootstrap.sh --prod`
creates it but the student doesn't know about this script and it
duplicates work already done (or not done) by `first-boot.sh`.

**Solution**: On live OS, don't use `anklume-instance` at all. Run
everything from the host directly (see F-22). Alternatively, make
the welcome wizard run `bootstrap.sh` instead of `first-boot.sh`.

requires: F-22 unfixed

---

## Phase 7 — First Infrastructure

### F-24 | MAJEUR | No pre-deployed infrastructure

After all setup, the student has an empty Incus with no domains,
no containers, no networks. They must manually edit `infra.yml`,
run sync, run apply. For a "live demo" experience, this is too much.

**Solution**: Auto-deploy a starter infrastructure in "explore" mode.
The shipped `infra.yml` (student-sysadmin: 1 admin + 1 lab domain
with 2 containers) is a good starting point. Deploy it automatically.

requires: F-15 unfixed

### F-25 | MINEUR | Shipped `infra.yml` is project-specific

The live ISO ships the current repo's `infra.yml` (which may change).
Student doesn't know it exists at `/opt/anklume/infra.yml` or that
it's a valid starting point.

**Solution**: Welcome wizard step: "Your starter infrastructure is
at /opt/anklume/infra.yml — edit it to add your own domains."

### F-26 | MAJEUR | Containers have no internet

If Incus wasn't properly initialized (no `incus admin init`), there's
no default managed network with NAT. Containers can't reach the
internet. `apt install` inside containers fails.

**Solution**: Ensure `incus admin init` is part of the live OS setup
flow (see F-19). Verify NAT is working in the welcome wizard or
`anklume doctor`.

requires: F-19 unfixed

### F-27 | MINEUR | nftables isolation not auto-deployed

`anklume network deploy` must be run manually from the host. Student
doesn't know this. Cross-domain traffic silently works (no isolation)
or silently fails (stale rules).

**Solution**: Add a post-apply hook that auto-generates and applies
nftables rules. Or make `anklume domain apply` include nftables
deployment by default on live OS.

---

## Phase 8 — Working with Containers

### F-28 | MINEUR | Container access not obvious

The main way to access containers is `incus exec <name> -- bash`.
`anklume console` exists (tmux-based) but the welcome wizard only
mentions it in passing.

**Solution**: After auto-deploy, show:
```
Your containers are ready:
  anklume console          → color-coded domain console
  incus exec sa-web -- bash → direct shell into sa-web
```

### F-29 | MAJEUR | Ansible output is unreadable

When `apply` fails (misconfigured infra.yml, network issue), Ansible
dumps a wall of yellow/red YAML. Student cannot parse the error.

**Solution**: Wrap `ansible-playbook` output in a filter that
extracts only `fatal` and `failed` task summaries. Show full log
path for debugging. Use `--forks=1` on live OS for sequential
(more readable) output.

### F-30 | MINEUR | No reset for explore sessions

Student breaks something, no idea how to start over. `anklume flush`
exists but is scary ("destroy all infrastructure").

**Solution**: Add `anklume reset` (explore mode only) that flushes
and re-deploys the starter config. Equivalent to "start over".

requires: F-15 unfixed

---

## Phase 9 — Educational Features

### F-31 | MAJEUR | Labs never mentioned during onboarding

The `labs/` directory and `anklume lab list` are a key educational
feature but the welcome wizard never mentions them. Student discovers
them only by reading `--help` carefully.

**Solution**: Add a tour step: "Learn by doing → `anklume lab list`
shows guided exercises. Start with `anklume lab start 01`." Make it
the primary call-to-action after the tour.

### F-32 | MINEUR | `anklume --help` overwhelming in student mode

35+ commands visible even in student mode. Student needs 4:
`sync`, `domain apply`, `console`, `lab start`.

**Solution**: In student mode, show a "Quick Start" section with
only essential commands. Full list behind `--help-all`.

---

## Phase 10 — Volatile Environment

### F-33 | MAJEUR | All changes lost on reboot (no persistence)

Without persistence, the entire overlayfs upper layer (tmpfs) is
wiped on reboot. Not just containers — system packages, config files,
home directory, everything. The welcome wizard says "data lost on
reboot" but doesn't convey the full scope.

**Solution**: Make the warning explicit: "EVERYTHING you do in this
session will be erased when you shut down. Save important files to
a USB drive." Add a persistent `/home` mount if ANY writable
partition is available.

### F-34 | MINEUR | tmpfs is limited to 50% RAM

The overlayfs COW layer is a 50% RAM tmpfs. On a 8GB laptop, only
~4GB is available for ALL writes (apt installs, container images,
user files). Easily exhausted.

**Solution**: In explore mode, warn about RAM constraints. Show free
space in waybar. If a writable partition is available, use it as
the upper layer instead of tmpfs.

---

## Dependency Map

```
F-01 (no pre-built ISO)
 ├── F-02 (build deps)
 └── F-03 (dd only)

F-04 (GRUB menu confusion)
 ├── F-05 (GPU choice)
 └── F-06 (toram jargon)

F-15 (explore = dead end)     ← CRITICAL PATH
 ├── F-19 (no incus init)
 ├── F-24 (no infra deployed)
 ├── F-25 (unknown infra.yml)
 ├── F-26 (no internet in containers)
 └── F-30 (no reset)

F-16 (need second disk)       ← CRITICAL PATH
 ├── F-17 (ZFS vs BTRFS)
 └── F-18 (LUKS prompt)

F-19 (first-boot.sh incomplete)
 └── F-26 (no network/NAT)

F-22 (require_container blocks host)  ← CRITICAL PATH
 └── F-23 (no anklume-instance)
```

## Critical Path Summary

Three blockers must be fixed for a student to have any usable
experience on live OS:

1. **F-15**: "Explore" mode must auto-provision a working environment
2. **F-22**: `require_container` must be bypassed on live OS
3. **F-19**: Incus must be fully initialized (not just storage pool)

Fixing these three eliminates 8 downstream friction points and
transforms the live OS from "blank screen + error messages" to
"boot → desktop → working containers in 2 minutes."
