"""`akta-pro connect claude-code` — the akta-pro skill + MCP server in Claude Code.

Everything goes to Claude Code's *user* scope: the skill to
`~/.claude/skills/akta-pro/` (or `$CLAUDE_CONFIG_DIR/skills/akta-pro/`), the
MCP server via `claude mcp add --scope user`, which keeps it in `~/.claude.json`
— private to this machine, never in a repo. The `claude` CLI is always driven
with an argument list (no shell), and the API key is redacted from anything we
echo back from it.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

from akta_pro_cli.config import mask_key
from akta_pro_cli.connectors.base import (
    ERROR,
    MCP_SERVER_NAME,
    MCP_URL,
    OK,
    SKIPPED,
    WARNING,
    ConnectOptions,
    Connector,
    Report,
    StepResult,
)
from akta_pro_cli.connectors.skill import SKILL_NAME
from akta_pro_cli.runtime import EXIT_API

SCOPE = "user"
CLAUDE_TIMEOUT = 30.0
CLAUDE_INSTALL_URL = "https://docs.claude.com/en/docs/claude-code/setup"


class ClaudeCLIError(RuntimeError):
    pass


def claude_config_dir() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(override).expanduser() if override else Path.home() / ".claude"


def _add_args(api_key_header: str | None) -> list[str]:
    args = ["mcp", "add", "--transport", "http", "--scope", SCOPE, MCP_SERVER_NAME, MCP_URL]
    if api_key_header is not None:
        args += ["--header", api_key_header]
    return args


class ClaudeCodeConnector(Connector):
    name = "claude-code"
    display_name = "Claude Code"

    def skill_dir(self) -> Path:
        return claude_config_dir() / "skills" / SKILL_NAME

    def launch_command(self) -> list[str] | None:
        exe = shutil.which("claude")
        return [exe] if exe else None


    def connect(self, opts: ConnectOptions) -> Report:
        report = Report(self.name, self.display_name, "connect")
        if opts.skill:
            report.steps["skill"] = self.install_skill_step(opts.force, report.notes)
        if opts.mcp:
            report.steps["mcp"] = self._register(opts, report.notes, required=not opts.skill)
        return report

    def _register(self, opts: ConnectOptions, notes: list[str], *, required: bool) -> StepResult:
        key = None if opts.oauth else opts.api_key
        data: dict = {"name": MCP_SERVER_NAME, "url": MCP_URL, "scope": SCOPE,
                      "auth": "oauth" if key is None else "api_key"}
        if key is not None:
            data["key"] = mask_key(key)
        redact = [key] if key else []

        exe = shutil.which("claude")
        if exe is None:
            manual = shlex.join(["claude", *_add_args(None if key is None else "x-api-key: <your wk_ key>")])
            return StepResult(
                ERROR if required else WARNING,
                "Claude Code CLI (`claude`) not found on PATH, so the MCP server wasn't registered.\n"
                f"Install Claude Code ({CLAUDE_INSTALL_URL}), then run "
                "`akta-pro connect claude-code --mcp-only`, or register it by hand:\n"
                f"    {manual}",
                {**data, "manual_command": manual},
                exit_code=EXIT_API if required else 0,
            )

        try:
            existing = self._lookup(exe)
            if existing and existing["user_scope"] and not opts.force:
                return StepResult(
                    SKIPPED,
                    f"MCP server '{MCP_SERVER_NAME}' already registered — use --force to replace it",
                    data,
                )
            if opts.force:
                removed = self._run(exe, ["mcp", "remove", MCP_SERVER_NAME, "--scope", SCOPE])
                if removed.returncode != 0 and not _not_found(removed):
                    return self._failure("Couldn't remove the existing MCP server", removed, redact, data)
            if existing and not existing["user_scope"]:
                notes.append(
                    f"An '{MCP_SERVER_NAME}' server is also configured in {existing['scope']} for this "
                    "directory; Claude Code uses that one here instead of the user-level entry."
                )
            header = None if key is None else f"x-api-key: {key}"
            added = self._run(exe, _add_args(header))
        except ClaudeCLIError as exc:
            return StepResult(ERROR, str(exc), data, exit_code=EXIT_API)
        if added.returncode != 0:
            return self._failure("`claude mcp add` failed", added, redact, data)

        how = f"key {data['key']}" if key is not None else "OAuth — sign in when Claude Code first uses it"
        return StepResult(OK, f"MCP server '{MCP_SERVER_NAME}' registered ({how})", data)

    def disconnect(self) -> Report:
        report = Report(self.name, self.display_name, "disconnect")
        report.steps["skill"] = self.remove_skill_step()
        report.steps["mcp"] = self._unregister()
        return report

    def _unregister(self) -> StepResult:
        data = {"name": MCP_SERVER_NAME, "scope": SCOPE}
        manual = shlex.join(["claude", "mcp", "remove", MCP_SERVER_NAME, "--scope", SCOPE])
        exe = shutil.which("claude")
        if exe is None:
            return StepResult(
                WARNING,
                f"Claude Code CLI (`claude`) not found on PATH. If the MCP server is registered, remove it with:\n    {manual}",
                {**data, "manual_command": manual},
            )
        try:
            removed = self._run(exe, ["mcp", "remove", MCP_SERVER_NAME, "--scope", SCOPE])
        except ClaudeCLIError as exc:
            return StepResult(ERROR, str(exc), data, exit_code=EXIT_API)
        if removed.returncode == 0:
            return StepResult(OK, f"MCP server '{MCP_SERVER_NAME}' removed", data)
        if _not_found(removed):
            return StepResult(SKIPPED, f"MCP server '{MCP_SERVER_NAME}' not registered", data)
        return self._failure("`claude mcp remove` failed", removed, [], data)

    def status(self) -> dict:
        mcp: dict = {"name": MCP_SERVER_NAME, "claude_found": False, "registered": None,
                     "scope": None, "url": None}
        exe = shutil.which("claude")
        if exe is not None:
            mcp["claude_found"] = True
            try:
                existing = self._lookup(exe)
            except ClaudeCLIError as exc:
                mcp["error"] = str(exc)
            else:
                mcp["registered"] = existing is not None
                if existing:
                    mcp["scope"], mcp["url"] = existing["scope"], existing["url"]
        return {"target": self.name, "name": self.display_name, "skill": self.skill_status(), "mcp": mcp}

    def _run(self, exe: str, args: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                [exe, *args],
                capture_output=True,
                text=True,
                stdin=subprocess.DEVNULL,
                timeout=CLAUDE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as exc:
            raise ClaudeCLIError(f"`claude {args[0]} {args[1]}` timed out after {CLAUDE_TIMEOUT:.0f}s.") from exc
        except OSError as exc:
            raise ClaudeCLIError(f"Couldn't run `claude`: {exc}") from exc

    def _lookup(self, exe: str) -> dict | None:
        """The `akta-pro` entry visible from here (`claude mcp get`), or None."""
        got = self._run(exe, ["mcp", "get", MCP_SERVER_NAME])
        if got.returncode != 0:
            return None
        fields: dict[str, str] = {}
        for line in got.stdout.splitlines():
            label, sep, value = line.strip().partition(":")
            if sep and label in ("Scope", "URL"):
                fields[label] = value.strip()
        scope = fields.get("Scope", "")
        return {"scope": scope or None, "url": fields.get("URL"),
                "user_scope": scope.lower().startswith("user")}

    @staticmethod
    def _failure(what: str, proc: subprocess.CompletedProcess, redact: list[str], data: dict) -> StepResult:
        detail = (proc.stderr or proc.stdout or "").strip()
        for secret in redact:
            detail = detail.replace(secret, mask_key(secret))
        message = f"{what} (exit {proc.returncode})" + (f": {detail}" if detail else ".")
        return StepResult(ERROR, message, data, exit_code=EXIT_API)


def _not_found(proc: subprocess.CompletedProcess) -> bool:
    return "no mcp server" in f"{proc.stdout}\n{proc.stderr}".lower()
