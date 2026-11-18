"""`akta-pro connect codex` — the akta-pro skill + MCP server in OpenAI Codex.

Everything goes to Codex's *user* scope: the skill to `~/.agents/skills/akta-pro/`
(Codex's user skills folder), the MCP server as an `[mcp_servers.akta-pro]` table
in `~/.codex/config.toml` (or `$CODEX_HOME/config.toml`), which the Codex CLI,
IDE extension, and desktop app share. `codex mcp add` can't set the `x-api-key`
header, so the table is written directly: the rest of the file is left as it
was, and every edit is re-parsed and checked before it replaces the file, so a
config we can't edit safely is reported, never rewritten.
"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import tomllib
from pathlib import Path

from akta_pro_cli.config import mask_key
from akta_pro_cli.connectors.base import (
    ERROR,
    MCP_SERVER_NAME,
    MCP_URL,
    OK,
    SKIPPED,
    ConnectOptions,
    Connector,
    Report,
    StepResult,
    display_path,
)
from akta_pro_cli.connectors.skill import SKILL_NAME
from akta_pro_cli.runtime import EXIT_API

SCOPE = "user"
CODEX_INSTALL_URL = "https://developers.openai.com/codex/cli"

# `[mcp_servers.akta-pro]` and its subtables (`[mcp_servers.akta-pro.tools.x]`),
# with the name bare or quoted. Any other `[` line starts a different table.
_OUR_HEADER = re.compile(
    r"""^\s*\[\s*mcp_servers\s*\.\s*(?:akta-pro|"akta-pro"|'akta-pro')\s*(?:\.[^\]]*)?\]\s*(?:\#.*)?$"""
)
_ANY_HEADER = re.compile(r"^\s*\[")


class CodexConfigError(RuntimeError):
    pass


def codex_home() -> Path:
    override = os.environ.get("CODEX_HOME")
    return Path(override).expanduser() if override else Path.home() / ".codex"


def config_path() -> Path:
    return codex_home() / "config.toml"


def _entry_block(key: str | None) -> str:
    lines = [f"[mcp_servers.{MCP_SERVER_NAME}]", f"url = {json.dumps(MCP_URL)}"]
    if key is not None:
        lines.append(f'http_headers = {{ "x-api-key" = {json.dumps(key)} }}')
    return "\n".join(lines) + "\n"


def _entry(data: dict) -> dict | None:
    servers = data.get("mcp_servers")
    entry = servers.get(MCP_SERVER_NAME) if isinstance(servers, dict) else None
    return entry if isinstance(entry, dict) else None


def _without_entry(data: dict) -> dict:
    """`data` minus our server, with an emptied `mcp_servers` dropped."""
    data = copy.deepcopy(data)
    servers = data.get("mcp_servers")
    if isinstance(servers, dict):
        servers.pop(MCP_SERVER_NAME, None)
        if not servers:
            del data["mcp_servers"]
    return data


def _strip_entry(text: str) -> str:
    """`text` with our `[mcp_servers.akta-pro…]` tables cut out."""
    kept: list[str] = []
    skipping = False
    for line in text.splitlines(keepends=True):
        if _OUR_HEADER.match(line):
            skipping = True
            continue
        if skipping and _ANY_HEADER.match(line):
            skipping = False
        if not skipping:
            kept.append(line)
    return "".join(kept)


class CodexConfig:
    """Reads and edits `config.toml` for the akta-pro entry only."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> tuple[str, dict]:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return "", {}
        except (OSError, UnicodeDecodeError) as exc:
            raise CodexConfigError(f"Couldn't read {display_path(self.path)}: {exc}") from exc
        try:
            return text, tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise CodexConfigError(f"{display_path(self.path)} isn't valid TOML ({exc}); fix it, then rerun.") from exc

    def entry(self) -> dict | None:
        return _entry(self.read()[1])

    def remove(self) -> bool:
        """Drop our server. False if it wasn't there."""
        text, data = self.read()
        if _entry(data) is None:
            return False
        new = _strip_entry(text)
        self._check(new, _without_entry(data), None)
        self._write(new)
        return True

    def add(self, key: str | None) -> None:
        """Write our server, replacing any existing entry."""
        text, data = self.read()
        base = _strip_entry(text) if _entry(data) is not None else text
        body = base.rstrip("\n")
        new = (body + "\n\n" if body.strip() else "") + _entry_block(key)
        expected = {"url": MCP_URL}
        if key is not None:
            expected["http_headers"] = {"x-api-key": key}
        self._check(new, _without_entry(data), expected)
        self._write(new)

    def _check(self, new: str, rest: dict, entry: dict | None) -> None:
        """Refuse an edit that changes anything besides our entry."""
        try:
            parsed = tomllib.loads(new)
        except tomllib.TOMLDecodeError:
            parsed = None
        if parsed is None or _without_entry(parsed) != rest or _entry(parsed) != entry:
            raise CodexConfigError(
                f"Couldn't update the '{MCP_SERVER_NAME}' entry in {display_path(self.path)} automatically "
                "(it's written in a form akta-pro doesn't edit). Remove that entry by hand, then rerun."
            )

    def _write(self, text: str) -> None:
        """Atomic replace, private to the user: the file can hold the API key."""
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".toml", dir=parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.chmod(tmp, 0o600)
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError as exc:
            raise CodexConfigError(f"Couldn't write {display_path(self.path)}: {exc}") from exc


class CodexConnector(Connector):
    name = "codex"
    display_name = "Codex"

    def skill_dir(self) -> Path:
        return Path.home() / ".agents" / "skills" / SKILL_NAME

    def launch_command(self) -> list[str] | None:
        exe = shutil.which("codex")
        return [exe] if exe else None

    def connect(self, opts: ConnectOptions) -> Report:
        report = Report(self.name, self.display_name, "connect")
        if opts.skill:
            report.steps["skill"] = self.install_skill_step(opts, report.notes)
        if opts.mcp:
            report.steps["mcp"] = self._register(opts, report.notes)
        if shutil.which("codex") is None:
            report.notes.append(
                f"Codex CLI (`codex`) not found on PATH. Install it ({CODEX_INSTALL_URL}); "
                "it picks this setup up on first run."
            )
        return report

    def _register(self, opts: ConnectOptions, notes: list[str]) -> StepResult:
        key = None if opts.oauth else opts.api_key
        cfg = CodexConfig(config_path())
        data: dict = {"name": MCP_SERVER_NAME, "url": MCP_URL, "scope": SCOPE, "config": str(cfg.path),
                      "auth": "oauth" if key is None else "api_key"}
        if key is not None:
            data["key"] = mask_key(key)
        shown = display_path(cfg.path)
        try:
            if cfg.entry() is not None and not opts.force:
                return StepResult(
                    SKIPPED,
                    f"MCP server '{MCP_SERVER_NAME}' already in {shown} — use --force to replace it",
                    data,
                )
            cfg.add(key)
        except CodexConfigError as exc:
            return StepResult(ERROR, str(exc), data, exit_code=EXIT_API)

        if key is None:
            notes.append(f"Sign in once with: codex mcp login {MCP_SERVER_NAME}")
        how = f"key {data['key']}" if key is not None else "OAuth"
        return StepResult(OK, f"MCP server '{MCP_SERVER_NAME}' registered in {shown} ({how})", data)

    def disconnect(self) -> Report:
        report = Report(self.name, self.display_name, "disconnect")
        report.steps["skill"] = self.remove_skill_step()
        report.steps["mcp"] = self._unregister()
        return report

    def _unregister(self) -> StepResult:
        cfg = CodexConfig(config_path())
        data = {"name": MCP_SERVER_NAME, "scope": SCOPE, "config": str(cfg.path)}
        try:
            removed = cfg.remove()
        except CodexConfigError as exc:
            return StepResult(ERROR, str(exc), data, exit_code=EXIT_API)
        if not removed:
            return StepResult(SKIPPED, f"MCP server '{MCP_SERVER_NAME}' not registered", data)
        return StepResult(OK, f"MCP server '{MCP_SERVER_NAME}' removed from {display_path(cfg.path)}", data)

    def status(self) -> dict:
        cfg = CodexConfig(config_path())
        mcp: dict = {"name": MCP_SERVER_NAME, "cli_found": shutil.which("codex") is not None,
                     "registered": None, "scope": None, "url": None, "config": str(cfg.path)}
        try:
            entry = cfg.entry()
        except CodexConfigError as exc:
            mcp["error"] = str(exc)
        else:
            mcp["registered"] = entry is not None
            if entry:
                mcp["scope"], mcp["url"] = SCOPE, entry.get("url")
        return {"target": self.name, "name": self.display_name, "skill": self.skill_status(), "mcp": mcp}
