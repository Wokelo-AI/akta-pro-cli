"""`akta login` / `logout` / `whoami` — API-key credential management (v1).

Browser OAuth (`akta login` without a key) is planned for a later version and
depends on the Akta backend exposing a public/native OAuth client; today the
CLI authenticates with an `x-api-key` minted at https://playground.akta.pro.
"""

from __future__ import annotations

from typing import Annotated

import httpx
import typer

from akta_cli.client import AktaAPIError, AktaClient
from akta_cli.config import clear_credentials, credentials_path, save_credentials, stored_api_key
from akta_cli.console import err, out
from akta_cli.runtime import EXIT_AUTH, EXIT_BAD_INPUT, AppContext, resolve_base_url


def _validate_key(base_url: str, key: str) -> tuple[bool, str]:
    """Probe a free endpoint to check the key. Returns (ok, message)."""
    client = AktaClient(base_url, key)
    try:
        client.get("/company/search", params={"query": "akta"})
        return True, "key is valid"
    except AktaAPIError as exc:
        if exc.status_code in (401, 403):
            return False, f"key rejected ({exc.status_code})"
        return True, f"could not fully verify (error {exc.status_code}), key stored anyway"
    except httpx.HTTPError as exc:
        return True, f"could not reach Akta to verify ({exc})"
    finally:
        client.close()


def login(
    ctx: typer.Context,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", help="Akta API key (wk_...). Omit to be prompted.", show_default=False),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option("--base-url", help="API base URL to log into (persisted). Defaults to --base-url/env or api.akta.pro.", show_default=False),
    ] = None,
) -> None:
    """Store an Akta API key for future commands.

    Get a key at https://playground.akta.pro (sign up → API Keys). Passing only
    `--base-url` (no `--api-key`) keeps your already-stored key and just changes
    the endpoint — no re-prompt. To change only the base URL later you can also
    use `akta config base-url <url>`.
    """
    cfg: AppContext = ctx.obj
    key = (api_key or cfg.api_key or "").strip()
    if not key:
        stored = stored_api_key()
        if base_url is not None and stored:
            # Only changing the base URL — keep the stored key, don't re-prompt.
            key = stored
        else:
            key = typer.prompt("Paste your Akta API key (wk_...)", hide_input=True).strip()
    if not key:
        err.print("[red]No key provided.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)

    # Local --base-url wins; else fall back to global flag/env → stored → default.
    base_url = base_url or resolve_base_url(cfg)
    ok, message = _validate_key(base_url, key)
    if not ok:
        err.print(f"[red]{message}.[/]")
        raise typer.Exit(code=EXIT_AUTH)

    path = save_credentials({"api_key": key, "base_url": base_url})
    err.print(f"[green]✓[/] Logged in ({message}) against {base_url}. Stored at {path}")


def logout(ctx: typer.Context) -> None:
    """Remove the stored Akta API key."""
    if clear_credentials():
        err.print(f"[green]✓[/] Removed stored credentials ({credentials_path()}).")
    else:
        err.print("No stored credentials to remove.")


def whoami(ctx: typer.Context) -> None:
    """Show the active API key (masked), its source, and validate it."""
    cfg: AppContext = ctx.obj
    if cfg.api_key:
        source, key = "flag / AKTA_API_KEY", cfg.api_key
    else:
        key = stored_api_key()
        source = f"stored ({credentials_path()})" if key else None

    if not key:
        err.print("[yellow]Not logged in.[/] Run [bold]akta login[/] or set AKTA_API_KEY.")
        raise typer.Exit(code=EXIT_AUTH)

    base_url = resolve_base_url(cfg)
    masked = f"{key[:5]}…{key[-4:]}" if len(key) > 12 else "…"
    out.print(f"API key : [bold]{masked}[/]  (source: {source})")
    out.print(f"Base URL: {base_url}")

    ok, message = _validate_key(base_url, key)
    if ok and message == "key is valid":
        out.print(f"[green]✓ {message}[/]")
    elif ok:
        out.print(f"[yellow]{message}[/]")
    else:
        out.print(f"[red]✗ {message}[/]")
        raise typer.Exit(code=EXIT_AUTH)


def register(app: typer.Typer) -> None:
    app.command("login")(login)
    app.command("logout")(logout)
    app.command("whoami")(whoami)
