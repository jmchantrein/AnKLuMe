"""anklume live — live OS / USB boot image management."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_cmd, run_make

app = typer.Typer(name="live", help="Live OS / USB boot image management.")


@app.command()
def build(
    base: Annotated[
        str | None,
        typer.Option("--base", "-b", help="Base distro: debian, arch (both if omitted)"),
    ] = None,
    desktop: Annotated[
        str, typer.Option(help="Desktop environment")
    ] = "kde",
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Output ISO path"),
    ] = None,
) -> None:
    """Build live ISO images (both Debian+Arch by default)."""
    if base and base not in ("debian", "arch"):
        from scripts.cli._helpers import console
        console.print(f"[red]Invalid base: {base}. Choose debian or arch.[/red]")
        raise typer.Exit(1)

    if base:
        out = output or f"images/anklume-{base}-{desktop}.iso"
        run_make("build-image", f"BASE={base} DESKTOP={desktop} OUT={out}")
    else:
        run_make("build-images", f"DESKTOP={desktop}")


@app.command()
def update() -> None:
    """Update an existing live image."""
    run_make("live-update")


@app.command()
def status() -> None:
    """Show live image build status."""
    run_make("live-status")


@app.command()
def test(
    clean: Annotated[
        bool, typer.Option("--clean", help="Clean test artifacts first")
    ] = False,
) -> None:
    """Test live image in a VM."""
    if clean:
        run_make("live-os-test-vm", "CLEAN=1")
    else:
        run_make("live-os-test-vm")


@app.command()
def mount() -> None:
    """Mount LUKS-encrypted persistent storage."""
    run_cmd(["sudo", "bash", "/opt/anklume/host/boot/scripts/mount-data.sh"])


@app.command()
def umount() -> None:
    """Unmount persistent storage."""
    run_cmd(["sudo", "bash", "/opt/anklume/host/boot/scripts/umount-data.sh"])
