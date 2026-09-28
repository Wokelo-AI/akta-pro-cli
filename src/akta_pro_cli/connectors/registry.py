"""Maps `akta-pro connect <target>` names to their connectors.

Adding an agent (e.g. Codex) is one entry here plus its `Connector` subclass;
the `connect` / `disconnect` / `connect status` commands pick it up automatically.
"""

from __future__ import annotations

from akta_pro_cli.connectors.base import Connector
from akta_pro_cli.connectors.claude_code import ClaudeCodeConnector

CONNECTORS: dict[str, type[Connector]] = {
    ClaudeCodeConnector.name: ClaudeCodeConnector,
}


def names() -> list[str]:
    return list(CONNECTORS)


def get(name: str) -> Connector:
    try:
        return CONNECTORS[name]()
    except KeyError:
        raise KeyError(f"Unknown target '{name}'. Supported: {', '.join(names())}") from None
