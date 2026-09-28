"""The `Connector` interface every `akta-pro connect <target>` implements.

A connector wires akta.pro into one agent (Claude Code, Codex; Cursor, …
later): it installs the akta-pro skill where that agent looks for skills and
registers the akta.pro MCP server in the agent's own config. The skill steps are
shared here; only the paths and the MCP registration differ per agent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

from akta_pro_cli.connectors import skill as _skill
from akta_pro_cli.runtime import EXIT_API, EXIT_TIMEOUT

MCP_SERVER_NAME = "akta-pro"
MCP_URL = "https://mcp.akta.pro/mcp"

OK, SKIPPED, WARNING, ERROR = "ok", "skipped", "warning", "error"


@dataclass
class StepResult:
    status: str  # OK | SKIPPED | WARNING | ERROR
    message: str
    data: dict = field(default_factory=dict)
    exit_code: int = 0  # non-zero only for ERROR

    def to_dict(self) -> dict:
        return {"status": self.status, "message": self.message, **self.data}


@dataclass
class ConnectOptions:
    api_key: str | None  # None when registering for OAuth
    oauth: bool = False
    skill: bool = True
    mcp: bool = True
    force: bool = False


@dataclass
class Report:
    target: str
    display_name: str
    action: str  # "connect" | "disconnect"
    steps: dict[str, StepResult] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.status != ERROR for s in self.steps.values())

    @property
    def exit_code(self) -> int:
        return next((s.exit_code for s in self.steps.values() if s.status == ERROR), 0)

    def to_dict(self) -> dict:
        return {
            "target": self.target,
            "action": self.action,
            "ok": self.ok,
            "steps": {name: step.to_dict() for name, step in self.steps.items()},
            "notes": self.notes,
        }


def display_path(path: Path) -> str:
    """`~/…` for paths under the home directory, for friendlier output."""
    try:
        return f"~/{path.relative_to(Path.home()).as_posix()}"
    except ValueError:
        return str(path)


class Connector(ABC):
    name: ClassVar[str]  # CLI target, e.g. "claude-code"
    display_name: ClassVar[str]  # e.g. "Claude Code"

    @abstractmethod
    def skill_dir(self) -> Path:
        """Where this agent loads the akta-pro skill from."""

    @abstractmethod
    def connect(self, opts: ConnectOptions) -> Report: ...

    @abstractmethod
    def disconnect(self) -> Report: ...

    @abstractmethod
    def status(self) -> dict: ...

    def launch_command(self) -> list[str] | None:
        """Command that starts the agent (for `--launch`), or None if unavailable."""
        return None

    def install_skill_step(self, force: bool, notes: list[str]) -> StepResult:
        dest = self.skill_dir()
        shown = f"{display_path(dest)}/"
        try:
            pkg = _skill.load_skill()
        except _skill.SkillNetworkError as exc:
            # Storage unreachable (offline, firewalled, outage): keep a working
            # install rather than failing the whole command over it.
            marker = _skill.read_marker(dest)
            if marker is not None and (dest / _skill.SKILL_FILE).is_file():
                label = _skill.describe(marker.get("version"), marker.get("sha256"))
                return StepResult(
                    WARNING,
                    f"{exc} Kept the installed skill {label} → {shown}",
                    {"version": marker.get("version"), "sha256": marker.get("sha256"),
                     "path": str(dest), "source": marker.get("source")},
                )
            return StepResult(ERROR, f"{exc} Nothing was installed; try again when online.",
                              exit_code=EXIT_TIMEOUT if exc.timeout else EXIT_API)
        except _skill.SkillError as exc:
            return StepResult(ERROR, str(exc), exit_code=EXIT_API)

        data = {"version": pkg.version, "sha256": pkg.sha256, "path": str(dest), "source": pkg.source}
        if not force and _skill.is_current(dest, pkg):
            return StepResult(SKIPPED, f"Skill {pkg.label} already installed → {shown}", data)
        if not force and dest.exists() and _skill.read_marker(dest) is None:
            return StepResult(
                ERROR,
                f"{shown} exists but wasn't installed by akta-pro. Rerun with --force to replace it.",
                data,
                exit_code=EXIT_API,
            )

        skills_root_existed = dest.parent.is_dir()
        try:
            _skill.install_skill(pkg, dest)
        except _skill.SkillError as exc:
            return StepResult(ERROR, str(exc), data, exit_code=EXIT_API)
        if not skills_root_existed:
            notes.append(
                f"Created {display_path(dest.parent)} — restart any open {self.display_name} "
                "session so it picks up the new skills folder."
            )
        return StepResult(OK, f"Skill {pkg.label} installed → {shown}", data)

    def remove_skill_step(self) -> StepResult:
        dest = self.skill_dir()
        shown = f"{display_path(dest)}/"
        if not dest.exists():
            return StepResult(SKIPPED, f"Skill not installed ({shown})", {"path": str(dest)})
        if _skill.read_marker(dest) is None:
            return StepResult(
                WARNING,
                f"Left {shown} in place: it wasn't installed by akta-pro. Remove it by hand if you want it gone.",
                {"path": str(dest)},
            )
        try:
            _skill.remove_skill(dest)
        except _skill.SkillError as exc:
            return StepResult(ERROR, str(exc), {"path": str(dest)}, exit_code=EXIT_API)
        return StepResult(OK, f"Skill removed ({shown})", {"path": str(dest)})

    def skill_status(self) -> dict:
        dest = self.skill_dir()
        marker = _skill.read_marker(dest)
        installed = (dest / _skill.SKILL_FILE).is_file()
        return {
            "installed": installed,
            "managed": marker is not None,
            "path": str(dest),
            "version": marker.get("version") if marker else None,
            "sha256": marker.get("sha256") if marker else None,
            "label": _skill.describe(marker.get("version"), marker.get("sha256")) if marker else None,
            "installed_at": marker.get("installed_at") if marker else None,
            "source": marker.get("source") if marker else None,
        }
