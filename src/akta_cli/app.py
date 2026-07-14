"""Assembles the `akta` Typer application: root callback + command tree."""

from __future__ import annotations

from typing import Annotated

import typer

from akta_cli import __version__
from akta_cli.client import DEFAULT_BASE_URL
from akta_cli.commands import account, alternative, auth, company, config, industry, news, update
from akta_cli.console import err, out
from akta_cli.runtime import AppContext

app = typer.Typer(
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
    help="Akta CLI — company & market intelligence from api.akta.pro.",
    epilog="Auth: set AKTA_API_KEY, pass --api-key, or run `akta login`. Docs: https://docs.akta.pro",
)


def _version_callback(value: bool) -> None:
    if value:
        out.print(f"akta {__version__}")
        # Best-effort, cached (~daily) hint — interactive only, to stderr so it
        # never pollutes a scripted `akta --version`. Never blocks or errors.
        if out.is_terminal:
            try:
                from akta_cli.update import cached_latest, is_newer

                latest = cached_latest(timeout=2.0)
                if latest and is_newer(latest, __version__):
                    err.print(f"[dim]A newer version v{latest} is available — run `akta update`.[/]")
            except Exception:
                pass
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    api_key: Annotated[
        str | None,
        typer.Option("--api-key", envvar="AKTA_API_KEY", show_default=False, help="Akta API key (wk_...)."),
    ] = None,
    base_url: Annotated[
        str | None,
        typer.Option(
            "--base-url",
            envvar="AKTA_API_BASE_URL",
            show_default=False,
            help=f"Override the API base URL (default {DEFAULT_BASE_URL}; or persist it via `akta login --base-url …`).",
        ),
    ] = None,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress the credits line on stderr."),
    ] = False,
    timeout: Annotated[
        float,
        typer.Option("--timeout", help="HTTP request timeout in seconds."),
    ] = 30.0,
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """Global options. Pass these before the command, e.g. `akta --api-key wk_… company search Canva`."""
    ctx.obj = AppContext(api_key=api_key, base_url=base_url, quiet=quiet, timeout=timeout)


# Command groups
app.add_typer(company.app, name="company")
app.add_typer(industry.app, name="industry")
app.add_typer(news.app, name="news")          # signals, detail, types
app.add_typer(alternative.reviews_app, name="reviews")

# Top-level commands
auth.register(app)          # login, logout, whoami
account.register(app)       # account
config.register(app)        # config show / base-url
update.register(app)        # update (self-update / check)
alternative.register(app)   # headcount, traffic, jobs, posts
