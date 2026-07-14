"""Reusable Typer option/argument annotations shared across command modules."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

CompanyArg = Annotated[str, typer.Argument(help="Company website (e.g. 'canva.com') or Akta UUID.")]

JsonOpt = Annotated[bool, typer.Option("--json", help="Emit raw JSON to stdout (clean for pipes).")]

OutOpt = Annotated[
    Path | None,
    typer.Option("-o", "--output", help="Write the raw JSON/text payload to a file.", show_default=False),
]

LimitOpt = Annotated[int, typer.Option("-n", "--limit", help="Max items to return.")]

OffsetOpt = Annotated[int, typer.Option("--offset", help="Pagination offset.")]
