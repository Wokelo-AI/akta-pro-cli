"""Alternative-signal commands: headcount, traffic, jobs, posts, and reviews.

All require Subscription/Enterprise access; Pay-as-you-go returns 403.
`headcount`/`traffic`/`jobs`/`posts` register at the top level; employee and
product reviews live under the `akta reviews` group.
"""

from __future__ import annotations

from typing import Annotated

import typer

from akta_cli.options import CompanyArg, JsonOpt, LimitOpt, OffsetOpt, OutOpt
from akta_cli.runtime import emit, fetch

reviews_app = typer.Typer(
    no_args_is_help=True,
    help="Employee and product reviews (Subscription/Enterprise).",
)


def headcount(ctx: typer.Context, company: CompanyArg, json_out: JsonOpt = False, output: OutOpt = None) -> None:
    """Headcount trends: total employees, historical growth, function breakdown. 2.5 credits."""
    emit(ctx.obj, fetch(ctx.obj, "/company/headcount-trends", {"company": company}), json_out=json_out, output=output)


def traffic(ctx: typer.Context, company: CompanyArg, json_out: JsonOpt = False, output: OutOpt = None) -> None:
    """Website traffic: engagement, monthly visits, and channel breakdown. 1.5 credits."""
    emit(ctx.obj, fetch(ctx.obj, "/company/website-traffic", {"company": company}), json_out=json_out, output=output)


def jobs(
    ctx: typer.Context,
    company: CompanyArg,
    limit: LimitOpt = 10,
    offset: OffsetOpt = 0,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Live job posts: title, location, description, comp, level, skills. 3 credits."""
    emit(ctx.obj, fetch(ctx.obj, "/company/jobs", {"company": company, "limit": limit, "offset": offset}), json_out=json_out, output=output)


def posts(
    ctx: typer.Context,
    company: CompanyArg,
    limit: LimitOpt = 10,
    offset: OffsetOpt = 0,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Company social posts: content, date, paid/repost flags, engagement. 1.5 credits."""
    emit(ctx.obj, fetch(ctx.obj, "/company/posts", {"company": company, "limit": limit, "offset": offset}), json_out=json_out, output=output)


@reviews_app.command("employees")
def employee_reviews(
    ctx: typer.Context,
    company: CompanyArg,
    limit: LimitOpt = 10,
    offset: OffsetOpt = 0,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Employee reviews: overall + dimension ratings (Glassdoor et al.). 1.5 credits / 50."""
    emit(
        ctx.obj,
        fetch(ctx.obj, "/company/employee-reviews", {"company": company, "limit": limit, "offset": offset}),
        json_out=json_out,
        output=output,
    )


@reviews_app.command("products")
def product_reviews(
    ctx: typer.Context,
    company: CompanyArg,
    product_id: Annotated[
        list[str] | None,
        typer.Option("--product-id", help="Product ID(s) to fetch reviews for (repeatable). Omit to list the catalog."),
    ] = None,
    limit: Annotated[int, typer.Option("-n", "--limit", help="Max reviews per product (only with --product-id).")] = 0,
    offset: OffsetOpt = 0,
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Product catalog and per-product reviews (G2 et al.).

    Call once without --product-id to get the catalog + each product's `id`,
    then again with those ids. 1.5 credits / 50 reviews.
    """
    emit(
        ctx.obj,
        fetch(
            ctx.obj,
            "/company/product-reviews",
            {"company": company, "products": product_id or None, "limit": limit or None, "offset": offset or None},
        ),
        json_out=json_out,
        output=output,
    )


def register(app: typer.Typer) -> None:
    app.command("headcount")(headcount)
    app.command("traffic")(traffic)
    app.command("jobs")(jobs)
    app.command("posts")(posts)
