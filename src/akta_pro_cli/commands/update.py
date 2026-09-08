"""`akta-pro update` — check for a newer release and update the CLI in place."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Annotated

import typer

from akta_pro_cli import __version__
from akta_pro_cli import update as _u
from akta_pro_cli.console import err, out
from akta_pro_cli.runtime import EXIT_API


def update(
    check: Annotated[bool, typer.Option("--check", help="Only report whether an update exists; don't install.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt and update.")] = False,
) -> None:
    """Check for a newer release and, if found, reinstall it in place.

    Discovers the latest version from PyPI, then upgrades with whichever
    installer owns this copy — `uv tool upgrade`, `pipx upgrade`, or
    `pip install --upgrade` — detected from where the package sits on disk.
    `--check` prints that command instead of running it. A source/editable
    checkout is left alone: update it with git.
    """
    current = __version__
    latest = _u.cached_latest(timeout=8.0, force=True)
    if latest is None:
        err.print(
            f"[yellow]Couldn't reach PyPI to check for updates[/] (network?). "
            f"You're on v{current}."
        )
        err.print(f"See {_u.PROJECT_URL}, or upgrade manually.")
        raise typer.Exit(code=EXIT_API)

    if not _u.is_newer(latest, current):
        out.print(f"[green]✓ up to date[/] — v{current} is the latest.")
        return

    method = _u.install_method()
    cmd = _u.upgrade_command()
    out.print(f"Update available: [bold]v{current}[/] → [bold green]v{latest}[/]")

    if cmd is None:
        # Editable/source checkout: `pip install --upgrade` here would silently
        # swap the working tree for a PyPI build.
        err.print("[yellow]Running from a source checkout[/] — update it with git, not an installer.")
        raise typer.Exit(code=0 if check else EXIT_API)

    shown = " ".join(cmd)
    if check:
        out.print(f"Run to update ({method} install):  {shown}", soft_wrap=True)
        return

    # pip runs through this interpreter, so only the external tools can be missing.
    if cmd[0] != sys.executable and shutil.which(cmd[0]) is None:
        err.print(f"[yellow]{cmd[0]} not found on PATH.[/] Update manually:  {shown}")
        raise typer.Exit(code=EXIT_API)

    if not yes and not typer.confirm(f"Update to v{latest} now?", default=True):
        out.print(f"Skipped. Run when ready:  {shown}", soft_wrap=True)
        return

    err.print(f"Updating to v{latest} via {method}…")
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        out.print(f"[green]✓ updated to v{latest}[/]")
    else:
        err.print(f"[red]{method} exited {rc}.[/] Try manually:  {shown}")
        raise typer.Exit(code=EXIT_API)


def register(app: typer.Typer, panel: str | None = None) -> None:
    app.command("update", rich_help_panel=panel)(update)
