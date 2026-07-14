"""Entry point for `akta` and `python -m akta_cli`.

Lazily imports the Typer app so a broken/partial install prints a helpful hint
instead of an ImportError traceback.
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from akta_cli.app import app
    except ModuleNotFoundError as exc:  # e.g. a broken install missing typer/rich
        sys.stderr.write(
            f"The Akta CLI is missing a dependency ({exc.name}).\n"
            "Reinstall with:  pipx install akta-cli\n"
        )
        raise SystemExit(1) from exc
    app()


if __name__ == "__main__":
    main()
