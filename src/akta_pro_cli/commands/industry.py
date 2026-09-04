"""`akta-pro industry` — resolve free-text industries to akta.pro codes."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer
from rich.table import Table

from akta_pro_cli.options import JsonOpt, OutOpt
from akta_pro_cli.runtime import csv, emit, fetch

app = typer.Typer(no_args_is_help=True, help="Industry search.")


class Level(str, Enum):
    l1 = "l1"
    l2 = "l2"
    l3 = "l3"
    l4 = "l4"
    all = "all"


def _industry_table(result: object) -> Table | None:
    rows = result.get("data") if isinstance(result, dict) else None
    if not rows:
        return None
    table = Table(title="Industry matches")
    table.add_column("Code")
    table.add_column("Industry", overflow="fold")
    table.add_column("Similarity", justify="right")
    for row in rows:
        sim = row.get("similarity")
        table.add_row(
            str(row.get("code", "")),
            str(row.get("industry_name", "")),
            f"{sim:.3f}" if isinstance(sim, (int, float)) else str(sim or ""),
        )
    return table


@app.command("search")
def search(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Free-text industry or topic, e.g. 'warehouse automation'.")],
    level: Annotated[
        list[Level] | None,
        typer.Option("--level", help="Taxonomy depth(s) to search: l1 (broadest) to l4 (most granular), or 'all' (repeatable). Default l4."),
    ] = None,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Resolve a free-text industry to akta.pro industry codes (free).

    Use the returned `code` values as `--industry` in `akta-pro news`.
    """
    params = {"query": query, "level": csv([lv.value for lv in level] if level else None)}
    result = fetch(ctx.obj, "/industry/search", params)
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_industry_table)
