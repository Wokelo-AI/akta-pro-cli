"""`akta config` — view and change stored settings without re-entering the key."""

from __future__ import annotations

from typing import Annotated

import typer

from akta_cli.client import DEFAULT_BASE_URL
from akta_cli.config import credentials_path, load_credentials, save_credentials
from akta_cli.console import err, out
from akta_cli.runtime import EXIT_BAD_INPUT

config_app = typer.Typer(no_args_is_help=True, help="View or change stored settings (offline).")


def _mask(key: str | None) -> str:
    if not key:
        return "(not set)"
    return f"{key[:5]}…{key[-4:]}" if len(key) > 12 else "…"


@config_app.command("show")
def show() -> None:
    """Show the stored credentials/config (offline; API key masked)."""
    creds = load_credentials()
    base = creds.get("base_url")
    out.print(f"config file : {credentials_path()}")
    out.print(f"api key     : {_mask(creds.get('api_key'))}")
    out.print(f"base url    : {base or f'(not set → default {DEFAULT_BASE_URL})'}")


@config_app.command("base-url")
def base_url(
    url: Annotated[str | None, typer.Argument(help="New base URL. Omit and pass --reset to restore the default.")] = None,
    reset: Annotated[bool, typer.Option("--reset", help="Reset to the default (api.akta.pro).")] = False,
) -> None:
    """Change or reset the stored base URL, keeping the stored API key."""
    creds = load_credentials()
    if reset:
        creds.pop("base_url", None)
        save_credentials(creds)
        out.print(f"[green]✓[/] base url reset → default ({DEFAULT_BASE_URL})")
        return
    if not url:
        err.print("[red]Provide a URL, or pass --reset.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    creds["base_url"] = url
    save_credentials(creds)
    out.print(f"[green]✓[/] base url set → {url}")


def register(app: typer.Typer) -> None:
    app.add_typer(config_app, name="config")
