"""Entry point for `akta-pro` and `python -m akta_pro_cli`.

Lazily imports the Typer app so a broken/partial install prints a helpful hint
instead of an ImportError traceback.
"""

from __future__ import annotations

import io
import sys


def main() -> None:
    # On Windows, piped output (e.g. when an agent runs the CLI) is cp1252, which can't
    # encode symbols like ✓/✗, so force both output and error streams to UTF-8.
    if isinstance(sys.stdout, io.TextIOWrapper) and isinstance(sys.stderr, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    try:
        from akta_pro_cli.app import app
    except ModuleNotFoundError as exc:  # e.g. a broken install missing typer/rich
        sys.stderr.write(
            f"The akta.pro CLI is missing a dependency ({exc.name}).\n"
            "Reinstall with:  pipx install akta-pro-cli\n"
        )
        raise SystemExit(1) from exc
    app()


if __name__ == "__main__":
    main()
