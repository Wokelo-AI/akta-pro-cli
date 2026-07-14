"""`akta update` — check for a newer release and update the CLI in place."""

from __future__ import annotations

import shutil
import subprocess
from typing import Annotated

import typer

from akta_cli import __version__
from akta_cli import update as _u
from akta_cli.console import err, out
from akta_cli.runtime import EXIT_API


def update(
    check: Annotated[bool, typer.Option("--check", help="Only report whether an update exists; don't install.")] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip the confirmation prompt and update.")] = False,
) -> None:
    """Check for a newer release and, if found, reinstall it via pipx.

    Discovers the latest version from the repo's git tags (using your existing
    git credentials), so it works for the private repo without a token.
    """
    current = __version__
    latest = _u.cached_latest(timeout=8.0, force=True)
    if latest is None:
        err.print(
            f"[yellow]Couldn't reach {_u.REPO} to check for updates[/] (network or git auth?). "
            f"You're on v{current}."
        )
        err.print(f"See {_u.REPO_URL}/releases, or reinstall a specific tag manually.")
        raise typer.Exit(code=EXIT_API)

    if not _u.is_newer(latest, current):
        out.print(f"[green]✓ up to date[/] — v{current} is the latest.")
        return

    cmd = ["pipx", "install", "--force", f"git+{_u.REPO_URL}@v{latest}"]
    out.print(f"Update available: [bold]v{current}[/] → [bold green]v{latest}[/]")

    if check:
        out.print("Run to update:  " + " ".join(cmd))
        return

    if shutil.which("pipx") is None:
        err.print("[yellow]pipx not found on PATH.[/] Update manually:  " + " ".join(cmd))
        raise typer.Exit(code=EXIT_API)

    if not yes and not typer.confirm(f"Update to v{latest} now?", default=True):
        out.print("Skipped. Run when ready:  " + " ".join(cmd))
        return

    err.print(f"Updating to v{latest} via pipx…")
    rc = subprocess.run(cmd).returncode
    if rc == 0:
        out.print(f"[green]✓ updated to v{latest}[/]")
    else:
        err.print(f"[red]pipx exited {rc}.[/] Try manually:  " + " ".join(cmd))
        raise typer.Exit(code=EXIT_API)


def register(app: typer.Typer) -> None:
    app.command("update")(update)
