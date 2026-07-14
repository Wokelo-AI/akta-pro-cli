"""`akta account` — the caller's plan tier and credit balance."""

from __future__ import annotations

import typer
from rich.table import Table

from akta_cli.options import JsonOpt, OutOpt
from akta_cli.runtime import emit, fetch


def _account_table(result: object) -> Table | None:
    if not isinstance(result, dict):
        return None
    table = Table(title="Akta account", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    for key in ("package_type", "is_enterprise", "credit_balance", "currency"):
        if key in result:
            table.add_row(key.replace("_", " ").title(), str(result[key]))
    return table


def account(ctx: typer.Context, json_out: JsonOpt = False, output: OutOpt = None) -> None:
    """Show your plan tier (is_enterprise, package_type) and credit balance (free).

    Check this before Subscription/Enterprise-only commands (headcount, traffic,
    jobs, posts, reviews) to know whether they'll be allowed.
    """
    result = fetch(ctx.obj, "/mcp/account")
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_account_table)


def register(app: typer.Typer) -> None:
    app.command("account")(account)
