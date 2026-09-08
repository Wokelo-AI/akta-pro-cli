"""Assembles the `akta-pro` Typer application: root callback + command tree."""

from __future__ import annotations

from typing import Annotated

import typer

from akta_pro_cli import __version__
from akta_pro_cli.client import DEFAULT_BASE_URL, DEFAULT_TIMEOUT
from akta_pro_cli.commands import (
    account,
    alternative,
    auth,
    company,
    config,
    industry,
    list_gen,
    news,
    region,
    status,
    update,
)
from akta_pro_cli.console import err, out
from akta_pro_cli.runtime import AppContext

app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
    help="akta.pro CLI — company & market intelligence from api.akta.pro.",
    epilog="Auth: set AKTA_PRO_API_KEY, pass --api-key, or run `akta-pro login`. Docs: https://docs.akta.pro",
)


def _version_callback(value: bool) -> None:
    if value:
        out.print(f"akta-pro {__version__}")
        # Best-effort, cached (~daily) hint — interactive only, to stderr so it
        # never pollutes a scripted `akta-pro --version`. Never blocks or errors.
        if out.is_terminal:
            try:
                from akta_pro_cli.update import cached_latest, is_newer

                latest = cached_latest(timeout=2.0)
                if latest and is_newer(latest, __version__):
                    err.print(f"[dim]A newer version v{latest} is available — run `akta-pro update`.[/]")
            except Exception:
                pass
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", envvar="AKTA_PRO_API_KEY", show_default=False, help="akta.pro API key (wk_...)."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            envvar="AKTA_PRO_API_BASE_URL",
            show_default=False,
            help=f"Override the API base URL (default {DEFAULT_BASE_URL}; or persist it via `akta-pro login --base-url …`).",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress the credits line on stderr."),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="HTTP request timeout in seconds."),
    ] = DEFAULT_TIMEOUT,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """Global options. Pass these before the command, e.g. `akta-pro --api-key wk_… company search Canva`."""
    ctx.obj = AppContext(api_key=api_key, base_url=base_url, quiet=quiet, timeout=timeout)


PANEL_SETUP = "Setup & account"
PANEL_DATA = "Company & news data"
PANEL_ALT = "Alternative signals (Subscription/Enterprise)"
PANEL_LISTS = "List generation"

auth.register(app, PANEL_SETUP)     # login, logout, whoami
account.register(app, PANEL_SETUP)  # account
update.register(app, PANEL_SETUP)   # update (self-update / check)
config.register(app, PANEL_SETUP)   # config show / base-url

status.register(app, PANEL_DATA)    # status <request_id> — polls `company add`
app.add_typer(company.app, name="company", rich_help_panel=PANEL_DATA)    # search, data, concise, add
app.add_typer(industry.app, name="industry", rich_help_panel=PANEL_DATA)
app.add_typer(region.app, name="region", rich_help_panel=PANEL_DATA)
app.add_typer(news.app, name="news", rich_help_panel=PANEL_DATA)          # signals, detail, types

alternative.register(app, PANEL_ALT)  # headcount, traffic, jobs, posts
app.add_typer(alternative.reviews_app, name="reviews", rich_help_panel=PANEL_ALT)

app.add_typer(list_gen.app, name="list", rich_help_panel=PANEL_LISTS)     # generate, filters, filter-options, filter-builder
