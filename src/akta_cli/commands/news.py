"""`akta news` — signals (list), detail (full bodies), and the type taxonomy."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from akta_cli.console import err
from akta_cli.news_tags import NEWS_CATEGORIES, NEWS_TAGS
from akta_cli.options import JsonOpt, OutOpt
from akta_cli.runtime import EXIT_BAD_INPUT, emit, fetch

app = typer.Typer(no_args_is_help=True, help="News signals, article detail, and the type taxonomy.")

# Compact list fields (mirrors the MCP's news_signals shaping); `id` feeds `detail`.
_STRIPPED_FIELDS = ("id", "title", "ai_summary", "url", "published_date", "publisher")


class Sentiment(str, Enum):
    positive = "positive"
    negative = "negative"
    neutral = "neutral"
    all = "all"


class NewsScore(str, Enum):
    high = "High"
    medium = "Medium"
    low = "Low"
    all = "all"


def _shape(article: dict, *, full: bool) -> dict:
    if full:
        return {k: v for k, v in article.items() if k != "full_text"}
    return {k: article.get(k) for k in _STRIPPED_FIELDS}


def _csv(values: list[str] | None) -> str | None:
    """Join repeatable-option values into the comma-separated string the API
    expects (or None when nothing was passed)."""
    if not values:
        return None
    return ",".join(v.strip() for v in values if v.strip()) or None


def _signals_table(result: object) -> Table | None:
    rows = result.get("data") if isinstance(result, dict) else None
    if not rows:
        return None
    table = Table(title=f"News ({result.get('count', '?')} of {result.get('total', '?')})")
    for col in ("Id", "Date", "Publisher", "Title", "AI summary", "URL"):
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            str(row.get("id", "") or ""),
            str(row.get("published_date", "") or ""),
            str(row.get("publisher", "") or ""),
            str(row.get("title", "") or ""),
            str(row.get("ai_summary", "") or ""),
            str(row.get("url", "") or ""),
        )
    return table


@app.command("signals")
def signals(
    ctx: typer.Context,
    company: Annotated[str | None, typer.Option("--company", help="Company website or Akta UUID.")] = None,
    industry: Annotated[str | None, typer.Option("--industry", help="Comma-separated industry codes (from `akta industry search`) — preferred for sector/market topics.")] = None,
    query: Annotated[str | None, typer.Option("--query", help="Open-ended topic, e.g. 'crude oil prices' (last resort; prefer --company/--industry).")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Search by text in the article title.")] = None,
    start_date: Annotated[str | None, typer.Option("--start-date", help="Start of range, YYYY-MM-DD. Non-enterprise limited to ~6 months back.")] = None,
    end_date: Annotated[str | None, typer.Option("--end-date", help="End of range, YYYY-MM-DD. Default today.")] = None,
    type_codes: Annotated[list[str] | None, typer.Option("--type-code", "-t", help="News-type tag code(s) from `akta news types`, e.g. SD01, CM03 (repeatable).")] = None,
    sentiment: Annotated[Sentiment, typer.Option("--sentiment", help="Filter by article sentiment.")] = Sentiment.all,
    news_score: Annotated[NewsScore, typer.Option("--news-score", help="Filter by relevance/quality tier.")] = NewsScore.all,
    countries: Annotated[list[str] | None, typer.Option("--country", help="Filter by the event's country — ISO codes, e.g. USA, GBR (repeatable).")] = None,
    blacklisted: Annotated[list[str] | None, typer.Option("--blacklist", help="Publisher domain(s) to exclude, e.g. example.com (repeatable).")] = None,
    entity_person: Annotated[list[str] | None, typer.Option("--entity-person", help="Only articles mentioning these people, by name (repeatable).")] = None,
    entity_location: Annotated[list[str] | None, typer.Option("--entity-location", help="Only articles mentioning these locations (repeatable).")] = None,
    entity_product: Annotated[list[str] | None, typer.Option("--entity-product", help="Only articles mentioning these product names (repeatable).")] = None,
    entity_event: Annotated[list[str] | None, typer.Option("--entity-event", help="Only articles mentioning these event names (repeatable).")] = None,
    naics_codes: Annotated[list[str] | None, typer.Option("--naics", help="Filter by NAICS industry classification code(s) (repeatable).")] = None,
    sic_codes: Annotated[list[str] | None, typer.Option("--sic", help="Filter by SIC industry classification code(s) (repeatable).")] = None,
    iptc_codes: Annotated[list[str] | None, typer.Option("--iptc", help="Filter by IPTC media topic code(s) (repeatable).")] = None,
    iab_codes: Annotated[list[str] | None, typer.Option("--iab", help="Filter by IAB content taxonomy code(s) (repeatable).")] = None,
    group_articles: Annotated[bool, typer.Option("--group-articles", help="Group near-duplicate articles from the same event.")] = False,
    limit: Annotated[int, typer.Option("-n", "--limit", min=1, max=1000, help="Max articles (max 1000).")] = 10,
    offset: Annotated[int, typer.Option("--offset", min=0, help="Pagination offset.")] = 0,
    full: Annotated[bool, typer.Option("--full", help="Return all per-article fields (industries, types, entities, mentions) except body text.")] = False,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """List news signals. Typically anchor the search with one of
    --company/--industry/--query/--title (all optional).

    The list is compact and never includes article bodies; each result carries an
    `id` — pass those to `akta news detail` for full text. Cost: 0.1/call +
    0.01/article. Filter by type with `-t` codes from `akta news types`.
    """
    params = {
        "company": company,
        "industry": industry,
        "query": query,
        "title": title,
        "start_date": start_date,
        "end_date": end_date,
        "sentiment_list": None if sentiment == Sentiment.all else sentiment.value,
        "news_score_list": None if news_score == NewsScore.all else news_score.value,
        "type_list": _csv(type_codes),
        "countries": _csv(countries),
        "blacklisted": _csv(blacklisted),
        "entity_person_list": _csv(entity_person),
        "entity_location_list": _csv(entity_location),
        "entity_product_list": _csv(entity_product),
        "entity_event_list": _csv(entity_event),
        "naics_code_list": _csv(naics_codes),
        "sic_code_list": _csv(sic_codes),
        "iptc_code_list": _csv(iptc_codes),
        "iab_code_list": _csv(iab_codes),
        "group_articles": True if group_articles else None,
        "limit": limit,
        "offset": offset,
        "full_text": False,  # list stays compact; bodies via `news detail`
    }
    resp = fetch(ctx.obj, "/news", params)
    articles = (resp.get("data") if isinstance(resp, dict) else None) or []
    shaped = [_shape(a, full=full) for a in articles]
    result = {
        "total": resp.get("total") if isinstance(resp, dict) else None,
        "count": len(shaped),
        "credits_consumed": resp.get("credits_consumed") if isinstance(resp, dict) else None,
        "data": shaped,
    }
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_signals_table)


def _detail_view(result: object) -> Group | None:
    """Readable reader view for `news detail`: title + meta + article body.

    Puts `full_text` front and centre (the whole point of `detail`); when the
    body is empty, falls back to the AI summary and points at the source URL so
    the output is still useful. Use --json for the full enrichment payload.
    """
    rows = result.get("data") if isinstance(result, dict) else None
    if not rows:
        return None
    panels = []
    for a in rows:
        meta_bits = [str(a.get(k)) for k in ("publisher", "published_date") if a.get(k)]
        meta = "  ·  ".join(meta_bits)
        url = a.get("url") or ""
        body = (a.get("full_text") or "").strip()
        if body:
            content = Text(body)
        else:
            summary = (a.get("ai_summary") or "").strip()
            content = Text()
            content.append("Full article text is unavailable for this article.\n", style="yellow")
            if summary:
                content.append("\nAI summary:\n", style="bold")
                content.append(summary + "\n")
            if url:
                content.append("\nRead the source: ", style="dim")
                content.append(url, style="cyan underline")
        header = Text(str(a.get("title") or f"#{a.get('id')}"), style="bold")
        if meta:
            header.append(f"\n{meta}", style="dim")
        if body and url:
            header.append(f"\n{url}", style="cyan")
        panels.append(Panel(content, title=header, title_align="left",
                            subtitle=f"id {a.get('id')}", subtitle_align="right"))
    return Group(*panels)


@app.command("detail")
def detail(
    ctx: typer.Context,
    news_ids: Annotated[list[int], typer.Argument(help="News id(s) from `akta news signals` (max 10).")],
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Fetch full article bodies for specific news id(s). Cost: 0.1/call + 0.01/article.

    In a terminal this renders a readable reader view — the article `full_text`
    up top, falling back to the AI summary + source URL when a body isn't
    available. Pass --json for the complete enrichment payload.
    """
    if not news_ids:
        err.print("[red]Provide at least one news id[/] (from `akta news signals`).")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    ids_csv = ",".join(str(i) for i in news_ids[:10])
    result = fetch(ctx.obj, "/news/by-id/", {"news_ids": ids_csv})
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_detail_view)


def _types_table(_: object) -> Table:
    table = Table(title=f"News types ({len(NEWS_TAGS)} tags)")
    table.add_column("Code", style="bold cyan")
    table.add_column("Category")
    table.add_column("Type", overflow="fold")
    for code, name in NEWS_TAGS:
        table.add_row(code, NEWS_CATEGORIES.get(code[:2], ""), name)
    return table


@app.command("types")
def types(
    ctx: typer.Context,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """List the news-type tag codes for `--type-code` filtering (free, offline)."""
    categories = []
    for prefix, cat_name in NEWS_CATEGORIES.items():
        tags = [{"code": c, "name": n} for c, n in NEWS_TAGS if c.startswith(prefix)]
        if tags:
            categories.append({"category": cat_name, "codes": tags})
    result = {
        "count": len(NEWS_TAGS),
        "usage": "Pass matching code(s) to `akta news signals --type-code CODE`.",
        "categories": categories,
    }
    # No network/credits — flat table in a TTY, structured JSON otherwise.
    emit(ctx.obj, result, json_out=json_out, output=output, renderer=_types_table)
