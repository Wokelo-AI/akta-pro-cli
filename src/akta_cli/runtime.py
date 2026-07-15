"""Shared request/render plumbing for the Akta CLI.

- `AppContext` holds the resolved global options (set on `ctx.obj` by the root
  callback).
- `fetch()` resolves the API key, performs the GET, and maps failures to exit
  codes (0 ok / 2 bad-input / 3 auth / 4 API / 5 timeout).
- `emit()` renders a result: a file (`-o`), clean JSON (`--json` or a pipe), or
  a human-friendly table/Markdown in a TTY. Credits go to stderr.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.markdown import Markdown

from akta_cli.client import DEFAULT_BASE_URL, AktaAPIError, AktaClient
from akta_cli.config import stored_api_key, stored_base_url
from akta_cli.console import err, out

# Exit codes (common CLI convention).
EXIT_BAD_INPUT = 2
EXIT_AUTH = 3
EXIT_API = 4
EXIT_TIMEOUT = 5


@dataclass
class AppContext:
    api_key: str | None
    base_url: str | None  # from --base-url / AKTA_API_BASE_URL; None if unset
    quiet: bool
    timeout: float = 30.0


def resolve_base_url(ctx: AppContext) -> str:
    """Effective base URL: explicit flag/env → stored (from `akta login`) → default.

    Lets local testing target a dev backend either per-command
    (`--base-url http://localhost:8000/api/v1` or the AKTA_API_BASE_URL env) or
    persistently (`akta login --base-url …`, then every command follows).
    """
    return ctx.base_url or stored_base_url() or DEFAULT_BASE_URL


def resolve_api_key(ctx: AppContext) -> str:
    key = ctx.api_key or stored_api_key()
    if not key:
        err.print(
            "[red]No Akta API key found.[/]\n"
            "Provide one with [bold]--api-key[/], the [bold]AKTA_API_KEY[/] env var, "
            "or run [bold]akta login[/].\n"
            "Get a key at https://playground.akta.pro (API Keys)."
        )
        raise typer.Exit(code=EXIT_AUTH)
    return key


def probe_is_enterprise(ctx: AppContext) -> bool:
    """Best-effort Enterprise-tier check via /mcp/account (free, 0 credits).

    Returns False on any failure (no key, network error, endpoint not deployed)
    so a probe never blocks or crashes the actual command.
    """
    key = ctx.api_key or stored_api_key()
    if not key:
        return False
    client = AktaClient(resolve_base_url(ctx), key, timeout=ctx.timeout)
    try:
        account = client.get("/mcp/account")
        return bool(account.get("is_enterprise")) if isinstance(account, dict) else False
    except Exception:
        return False
    finally:
        client.close()


def _exit_code_for_status(status: int) -> int:
    if status in (400, 422):
        return EXIT_BAD_INPUT
    if status in (401, 403):
        return EXIT_AUTH
    return EXIT_API


def fetch(ctx: AppContext, path: str, params: dict | None = None) -> Any:
    """Resolve the key, GET `path`, and translate errors into `typer.Exit`."""
    key = resolve_api_key(ctx)
    client = AktaClient(resolve_base_url(ctx), key, timeout=ctx.timeout)
    try:
        return client.get(path, params=params)
    except AktaAPIError as exc:
        err.print(f"[red]Error {exc.status_code}:[/] {exc}")
        raise typer.Exit(code=_exit_code_for_status(exc.status_code)) from exc
    except httpx.TimeoutException as exc:
        err.print("[red]Request timed out.[/]")
        raise typer.Exit(code=EXIT_TIMEOUT) from exc
    except httpx.HTTPError as exc:
        err.print(f"[red]Network error:[/] {exc}")
        raise typer.Exit(code=EXIT_API) from exc
    finally:
        client.close()


def _json_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False)


def emit(
    ctx: AppContext,
    result: Any,
    *,
    json_out: bool = False,
    output: Path | None = None,
    renderer: Callable[[Any], Any] | None = None,
    markdown: bool = False,
) -> None:
    # 1. credits → stderr (for dict/JSON results). `company data` returns a
    # Markdown string with credits already appended as an in-body footer, so it
    # deliberately doesn't hit this branch — see commands/company.py.
    if isinstance(result, dict) and not ctx.quiet:
        credits = result.get("credits_consumed")
        if credits is not None:
            err.print(f"[dim]credits consumed: {credits}[/]")

    # 2. file output → raw machine payload
    if output is not None:
        output.write_text(_json_text(result))
        err.print(f"[green]✓[/] wrote {output}")
        return

    # 3. --json or a non-TTY pipe → clean, un-styled payload on stdout
    if json_out or not out.is_terminal:
        print(_json_text(result))
        return

    # 4. human/default rendering in a TTY
    if markdown and isinstance(result, str):
        out.print(Markdown(result))
        return
    if renderer is not None:
        renderable = renderer(result)
        if renderable is not None:
            out.print(renderable)
            return
    if isinstance(result, str):
        out.print(result)
    else:
        out.print_json(_json_text(result))
