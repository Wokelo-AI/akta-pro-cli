"""`akta-pro list` — structured/NL company list generation (List Generation API)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from akta_pro_cli.console import err
from akta_pro_cli.options import JsonOpt, OutOpt
from akta_pro_cli.runtime import EXIT_BAD_INPUT, emit, post

app = typer.Typer(no_args_is_help=True, help="Generate company lists from structured filters or free text.")


def _load_filters(raw: str) -> dict:
    """A JSON object, given inline or as `@path/to/file.json`."""
    text = Path(raw[1:]).read_text() if raw.startswith("@") else raw
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        err.print(f"[red]Invalid --filters JSON:[/] {exc}")
        raise typer.Exit(code=EXIT_BAD_INPUT) from exc
    if not isinstance(parsed, dict):
        err.print("[red]--filters must be a JSON object.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    return parsed


@app.command("generate")
def generate(
    ctx: typer.Context,
    query: Annotated[str | None, typer.Option("--query", help="Free-text description of the target companies, translated to filters server-side. Mutually exclusive with --filters.")] = None,
    filters: Annotated[str | None, typer.Option("--filters", help="Structured filters as a JSON string or @file.json, keyed by enrichment field path — see `akta-pro list filter-builder`.")] = None,
    sections: Annotated[list[str] | None, typer.Option("-s", "--section", help="Enrichment section(s) to include per company (repeatable, same names as `company data`). Omit for identity fields only.")] = None,
    sort_by: Annotated[str | None, typer.Option("--sort-by", help="relevance (default), revenue_estimate, total_funding, valuation_estimate, founded_year, or employee_range.")] = None,
    sort_order: Annotated[str | None, typer.Option("--sort-order", help="asc or desc (default desc).")] = None,
    limit: Annotated[int, typer.Option("-n", "--limit", min=1, max=500, help="Max companies to return. offset+limit is capped at 500 (20 on pay-as-you-go).")] = 20,
    offset: Annotated[int, typer.Option("--offset", min=0, help="Pagination offset.")] = 0,
    skip_unavailable: Annotated[bool, typer.Option("--skip-unavailable", help="Drop sections your plan doesn't cover instead of failing the whole request.")] = False,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Generate a list of companies from --query or --filters (exactly one required).

    Cost: 1.5/call (once any company matches) + 0.2/company + each section's
    `company data` cost, per company. --query additionally costs 2.5 for the
    NL-to-filters translation — run `akta-pro list filter-builder` once to
    inspect/edit the filters and reuse them via --filters for free afterwards.
    """
    if bool(query) == bool(filters):
        err.print("[red]Pass exactly one of --query or --filters.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    body = {
        "query": query,
        "filters": _load_filters(filters) if filters else None,
        "sections": sections,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "limit": limit,
        "offset": offset,
        "skip_unavailable_sections": skip_unavailable,
    }
    result = post(ctx.obj, "/list/generate/companies", body)
    emit(ctx.obj, result, json_out=json_out, output=output)


@app.command("filter-builder")
def filter_builder(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Free-text description of the target companies, e.g. 'US fintechs founded after 2015'.")],
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Translate a free-text query into structured filters. 2.5 credits.

    Inspect or edit the returned `filters`, then pass them to
    `akta-pro list generate --filters '<json>'` to skip the translation fee.
    """
    result = post(ctx.obj, "/list/filter-builder", {"query": query})
    emit(ctx.obj, result, json_out=json_out, output=output)
