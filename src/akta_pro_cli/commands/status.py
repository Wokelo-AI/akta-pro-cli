"""`akta-pro status` — poll an async request (e.g. a company addition) by id."""

from __future__ import annotations

from typing import Annotated

import typer

from akta_pro_cli.options import JsonOpt, OutOpt
from akta_pro_cli.runtime import emit, fetch


def status(
    ctx: typer.Context,
    request_id: Annotated[str, typer.Argument(help="Request id from an async command, e.g. `company add`.")],
    json_out: JsonOpt = False,
    output: OutOpt = None,
) -> None:
    """Check the status of an async request by id (free)."""
    result = fetch(ctx.obj, f"/status/{request_id}")
    emit(ctx.obj, result, json_out=json_out, output=output)


def register(app: typer.Typer) -> None:
    app.command("status")(status)
