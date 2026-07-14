"""`akta news` — signals (list), detail (full bodies), and the type taxonomy."""

from __future__ import annotations

from enum import Enum
from typing import Annotated

import typer
from rich.table import Table

from akta_cli.console import err
from akta_cli.news_tags import NEWS_CATEGORIES, NEWS_TAGS
from akta_cli.options import JsonOpt, OutOpt
from akta_cli.runtime import EXIT_BAD_INPUT, emit, fetch

app = typer.Typer(no_args_is_help=True, help="News signals, article detail, and the type taxonomy.")

# Compact list fields (mirrors the MCP's news_signals shaping); `id` feeds `detail`.
_STRIPPED_FIELDS = ("id", "title", "published_date", "publisher", "sentiment", "ai_summary", "url")


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


def _signals_table(result: object) -> Table | None:
    rows = result.get("data") if isinstance(result, dict) else None
    if not rows:
        return None
    table = Table(title=f"News ({result.get('count', '?')} of {result.get('total', '?')})")
    for col in ("Id", "Date", "Publisher", "Sentiment", "Title"):
        table.add_column(col, overflow="fold")
    for row in rows:
        table.add_row(
            str(row.get("id", "") or ""),
            str(row.get("published_date", "") or ""),
            str(row.get("publisher", "") or ""),
            str(row.get("sentiment", "") or ""),
            str(row.get("title", "") or ""),
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
    group_articles: Annotated[bool, typer.Option("--group-articles", help="Group near-duplicate articles from the same event.")] = False,
    limit: Annotated[int, typer.Option("-n", "--limit", min=1, max=1000, help="Max articles (max 1000).")] = 10,
    offset: Annotated[int, typer.Option("--offset", min=0, help="Pagination offset.")] = 0,
    full: Annotated[bool, typer.Option("--full", help="Return all per-article fields (industries, types, entities, mentions) except body text.")] = False,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """List news signals. Provide at least one of --company/--industry/--query/--title.

    The list is compact and never includes article bodies; each result carries an
    `id` — pass those to `akta news detail` for full text. Cost: 0.1/call +
    0.01/article. Filter by type with `-t` codes from `akta news types`.
    """
    if not any([company, industry, query, title]):
        err.print("[red]Provide at least one of[/] --company, --industry, --query, or --title.")
        raise typer.Exit(code=EXIT_BAD_INPUT)

    params = {
        "company": company,
        "industry": industry,
        "query": query,
        "title": title,
        "start_date": start_date,
        "end_date": end_date,
        "sentiment_list": None if sentiment == Sentiment.all else sentiment.value,
        "news_score_list": None if news_score == NewsScore.all else news_score.value,
        "type_list": ",".join(type_codes) if type_codes else None,
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


@app.command("detail")
def detail(
    ctx: typer.Context,
    news_ids: Annotated[list[int], typer.Argument(help="News id(s) from `akta news signals` (max 10).")],
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Fetch full article bodies for specific news id(s). Cost: 0.1/call + 0.01/article."""
    if not news_ids:
        err.print("[red]Provide at least one news id[/] (from `akta news signals`).")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    ids_csv = ",".join(str(i) for i in news_ids[:10])
    result = fetch(ctx.obj, "/news/by-id/", {"news_ids": ids_csv})
    emit(ctx.obj, result, json_out=json_out, output=output)


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
