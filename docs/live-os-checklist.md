# Live ISO Pre-Release Checklist

Run after every ISO build, before declaring "done".
Test in QEMU with UEFI firmware (OVMF).

## Package verification

- [ ] `konsole` in Debian KDE package list (`build-image.sh`)
- [ ] `konsole` in Arch KDE package list (`build-image.sh`)
- [ ] `foot` still present (for sway/labwc desktops)
- [ ] `python3-typer` / `python-typer` in package list (for Python CLI)

## Configuration files

- [ ] `/etc/hosts` contains `127.0.1.1 anklume` (both Debian and Arch)
- [ ] `plasma-welcomerc` suppresses KDE welcome wizard
- [ ] `kwalletrc` disables KWallet
- [ ] `anklume.desktop` installed to `/usr/share/applications/`
- [ ] `anklume.desktop` installed to user Desktop

## CLI verification

- [ ] `/usr/local/bin/anklume` invokes Python CLI (not make wrapper)
- [ ] `anklume --help` shows Typer CLI output with subcommands
- [ ] `anklume guide` launches the welcome TUI (welcome.py)

## Boot flow

- [ ] Splash banner displays with ASCII art and quote
- [ ] 5-second console interrupt window shows after splash
- [ ] Pressing 'c' during countdown drops to console mode
- [ ] Desktop launches automatically if no interrupt
- [ ] Desktop logout returns to console (no auto-re-login loop)
- [ ] `~/.anklume-console` sentinel prevents desktop launch
- [ ] Removing sentinel restores desktop on next login

## First-boot operations

- [ ] `sudo` works without "unable to resolve host" warning
- [ ] Incus daemon starts and responds to `incus info`
- [ ] Incus initialization succeeds (bridge modules loaded)
- [ ] Welcome guide has default selections (Enter to accept)
- [ ] Screen clears between guide pages
- [ ] Explore mode provisions infrastructure without errors

## Desktop environment

- [ ] No plasma-welcome wizard on first KDE login
- [ ] No KWallet popup during operations
- [ ] `anklume` appears in KDE application menu (search)
- [ ] `anklume` shortcut on desktop
- [ ] Konsole available in KDE app menu
