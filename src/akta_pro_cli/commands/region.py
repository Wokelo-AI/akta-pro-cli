"""`akta-pro region` — resolve free-text geographic regions to UN M49 codes."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer
from rich.table import Table

from akta_pro_cli.options import JsonOpt, OutOpt
from akta_pro_cli.runtime import emit, fetch

app = typer.Typer(no_args_is_help=True, help="Region search.")


class Level(str, Enum):
    region = "region"
    sub_region = "sub-region"
    intermediate_region = "intermediate-region"


def _region_table(result: object) -> Table | None:
    rows = result.get("data") if isinstance(result, dict) else None
    if not rows:
        return None
    table = Table(title="Region matches")
    table.add_column("Code")
    table.add_column("Name", overflow="fold")
    table.add_column("Level")
    table.add_column("Parent", overflow="fold")
    for row in rows:
        table.add_row(
            str(row.get("code", "")),
            str(row.get("name", "")),
            str(row.get("level", "")),
            str(row.get("parent_name", "") or ""),
        )
    return table


@app.command("search")
def search(
    ctx: typer.Context,
    query: Annotated[str | None, typer.Argument(help="Free-text region name, e.g. 'europe', or a region code. Omit to list all 29.")] = None,
    level: Annotated[
        Level | None,
        typer.Option("--level", help="Scope to one depth: region (5 continents), sub-region (17), or intermediate-region (7). Omit for all."),
    ] = None,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Resolve a free-text region to akta.pro UN M49 region codes (free).

    Use the returned `code` values as an `hq_region_codes` filter in `akta-pro list generate companies`.
    """
    params = {"query": query, "level": level.value if level else None}
    result = fetch(ctx.obj, "/region/search", params)
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_region_table)
