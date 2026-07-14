"""`akta company` — search, enrichment (Markdown), and concise overview."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer
from rich.table import Table

from akta_cli.console import err
from akta_cli.options import JsonOpt, OutOpt
from akta_cli.runtime import EXIT_BAD_INPUT, emit, fetch, probe_is_enterprise

app = typer.Typer(no_args_is_help=True, help="Company search, enrichment, and concise overview.")


class Section(str, Enum):
    """Enrichment sections. `funding_detail` / `mna_and_investment` are
    enterprise-only: selectable, but auto-skipped for non-enterprise callers
    (the backend 403s the whole request otherwise)."""

    firmographic = "firmographic"
    business_model = "business_model"
    company_assessment = "company_assessment"
    trust_signal = "trust_signal"
    company_hierarchy = "company_hierarchy"
    digital_presence = "digital_presence"
    financial_estimate = "financial_estimate"
    location = "location"
    management_profile = "management_profile"
    product_offering = "product_offering"
    strategic_signal = "strategic_signal"
    customer_profile = "customer_profile"
    industry = "industry"
    technology = "technology"
    funding_detail = "funding_detail"
    mna_and_investment = "mna_and_investment"


# Sections the Akta backend gates to Enterprise plans (mirrors the MCP tool).
ENTERPRISE_SECTIONS = {"funding_detail", "mna_and_investment"}


def _search_table(result: object) -> Table | None:
    rows = result.get("data") if isinstance(result, dict) else None
    if not rows:
        return None
    table = Table(title="Company search results")
    for col in ("Name", "Website", "Category", "Status", "UUID"):
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            str(row.get("name", "")),
            str(row.get("website", "")),
            str(row.get("product_category", "")),
            str(row.get("company_status", "")),
            str(row.get("uuid", "")),
        )
    return table


@app.command("search")
def search(
    ctx: typer.Context,
    query: Annotated[str, typer.Argument(help="Company name or website, e.g. 'Canva' or 'canva.com'.")],
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Resolve a company by name or website to its Akta identifiers (free).

    Run this first — every other company command needs the `uuid` (or website)
    returned here.
    """
    result = fetch(ctx.obj, "/company/search", {"query": query})
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_search_table)


@app.command("data")
def data(
    ctx: typer.Context,
    company: Annotated[str, typer.Argument(help="Company website or Akta UUID.")],
    sections: Annotated[
        list[Section] | None,
        typer.Option("-s", "--section", help="Section(s) to fetch (repeatable). Required — there is no 'all'."),
    ] = None,
    raw: Annotated[bool, typer.Option("--json", "--raw", help="Emit raw Markdown instead of rendering it.")] = False,
    output: OutOpt = None,
) -> None:
    """Enrich a company with the chosen sections, returned as Markdown.

    Credits per section: firmographic 2, business_model 2, company_assessment 2,
    trust_signal 0.5, company_hierarchy 0.5, digital_presence 0.5,
    financial_estimate 0.5, location 0.5, management_profile 1.5,
    product_offering 2, strategic_signal 1.5, customer_profile 1, industry 1,
    technology 2, funding_detail 3 (enterprise), mna_and_investment 5 (enterprise).

    The two enterprise-only sections are auto-skipped (not an error) for
    non-enterprise callers; a note lists any dropped.
    """
    if not sections:
        err.print(
            "[red]Choose at least one --section.[/] Options: "
            + ", ".join(s.value for s in Section)
        )
        raise typer.Exit(code=EXIT_BAD_INPUT)

    requested = list(dict.fromkeys(s.value for s in sections))  # de-dupe, keep order
    enterprise_req = [s for s in requested if s in ENTERPRISE_SECTIONS]
    skipped: list[str] = []
    if enterprise_req and not probe_is_enterprise(ctx.obj):
        requested = [s for s in requested if s not in ENTERPRISE_SECTIONS]
        skipped = enterprise_req
    if not requested:
        err.print(
            f"[yellow]Only enterprise-only section(s) requested ({', '.join(skipped)}); "
            "your plan doesn't include them.[/] Pick non-enterprise sections or upgrade."
        )
        raise typer.Exit(code=EXIT_BAD_INPUT)

    result = fetch(
        ctx.obj,
        "/company/enrichment/markdown",
        {"company": company, "sections": ",".join(requested)},
    )
    # The endpoint returns Markdown text, or a JSON envelope with `data` = markdown.
    if isinstance(result, dict):
        result = result.get("data", result)
    if skipped and isinstance(result, str):
        result = (
            f"> _Skipped enterprise-only section(s): {', '.join(skipped)} — "
            "not in your plan._\n\n" + result
        )
    emit(ctx.obj, result, json_out=raw, output=output, markdown=True)


@app.command("concise")
def concise(
    ctx: typer.Context,
    company: Annotated[str, typer.Argument(help="Company website or Akta UUID.")],
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Condensed company overview — slimmed JSON with the fluff redacted."""
    result = fetch(ctx.obj, "/company/enrichment/concise", {"company": company})
    emit(ctx.obj, result, json_out=json_out, output=output)
