"""anklume live — live OS / USB boot image management."""

from typing import Annotated

import typer

from scripts.cli._helpers import run_make

app = typer.Typer(name="live", help="Live OS / USB boot image management.")


@app.command()
def build(
    debian: Annotated[
        bool, typer.Option("--debian", help="Build Debian-based image only")
    ] = False,
    arch: Annotated[
        bool, typer.Option("--arch", help="Build Arch-based image only")
    ] = False,
    desktop: Annotated[
        str, typer.Option(help="Desktop environment")
    ] = "kde",
) -> None:
    """Build live ISO images (both Debian+Arch by default)."""
    if debian and arch:
        # Both flags = build both (same as no flag)
        run_make("build-images", f"DESKTOP={desktop}")
    elif debian:
        run_make(
            "build-image",
            f"BASE=debian DESKTOP={desktop} OUT=images/anklume-debian-{desktop}.iso",
        )
    elif arch:
        run_make(
            "build-image",
            f"BASE=arch DESKTOP={desktop} OUT=images/anklume-arch-{desktop}.iso",
        )
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
