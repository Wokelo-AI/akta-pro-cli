"""Update checking for the CLI.

Discovers the latest released version from PyPI (the `akta-pro-cli` project's
JSON API). Results are cached in the config dir so `akta-pro --version` can show
a hint without hitting the network on every call.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from akta_pro_cli.config import config_dir

PACKAGE = "akta-pro-cli"
PYPI_URL = f"https://pypi.org/pypi/{PACKAGE}/json"
PROJECT_URL = f"https://pypi.org/project/{PACKAGE}/"
_CACHE_TTL = 24 * 3600  # re-check at most once a day for the --version hint


def _cache_path() -> Path:
    return config_dir() / "update-check.json"


def install_method(prefix: str | None = None, package_dir: str | None = None) -> str:
    """How this copy of the CLI was installed: 'uv', 'pipx', 'pip', or 'source'.

    Read off the filesystem, since nothing records the installer: uv keeps its
    tools in `<uv data dir>/tools/<pkg>`, pipx in `<pipx home>/venvs/<pkg>`, and
    both env overrides (`UV_TOOL_DIR`, `PIPX_HOME`) win over the default layout.
    A package that isn't under a `site-packages` at all is an editable/source
    checkout, which no installer should be pointed at. Everything else is pip.
    """
    pkg = Path(package_dir) if package_dir is not None else Path(__file__).resolve().parent
    if "site-packages" not in pkg.parts:
        return "source"

    root = Path(prefix if prefix is not None else sys.prefix)
    try:
        root = root.resolve()
    except OSError:
        pass
    parts = root.parts

    for env_var, method in (("UV_TOOL_DIR", "uv"), ("PIPX_HOME", "pipx")):
        home = os.environ.get(env_var)
        if not home:
            continue
        try:
            if root.is_relative_to(Path(home).resolve()):
                return method
        except (OSError, ValueError):
            pass

    if "tools" in parts and "uv" in parts[: parts.index("tools")]:
        return "uv"
    if "pipx" in parts:
        return "pipx"
    return "pip"


def upgrade_command(prefix: str | None = None, package_dir: str | None = None) -> list[str] | None:
    """The argv that upgrades this installation, or None if we shouldn't run one.

    pip goes through this interpreter (`sys.executable -m pip`) so it upgrades
    the environment the CLI actually runs in, not whichever pip is on PATH.
    """
    method = install_method(prefix, package_dir)
    if method == "uv":
        return ["uv", "tool", "upgrade", PACKAGE]
    if method == "pipx":
        return ["pipx", "upgrade", PACKAGE]
    if method == "pip":
        return [sys.executable, "-m", "pip", "install", "--upgrade", PACKAGE]
    return None  # source checkout — see install_method


def parse_version(v: str) -> tuple[int, ...]:
    """Lenient version tuple: '1.2.3' -> (1, 2, 3); non-numeric parts -> 0."""
    parts: list[int] = []
    for chunk in v.split("."):
        digits = ""
        for ch in chunk:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def latest_version(timeout: float = 5.0) -> str | None:
    """Latest version of the package on PyPI, or None on any failure."""
    try:
        with urllib.request.urlopen(PYPI_URL, timeout=timeout) as resp:  # noqa: S310 (https only)
            data = json.load(resp)
        version = data.get("info", {}).get("version")
        return version or None
    except (OSError, ValueError):
        return None


def cached_latest(*, timeout: float = 2.0, ttl: int = _CACHE_TTL, force: bool = False) -> str | None:
    """Latest version string, using a time-boxed cache. Best-effort; None on failure.

    With `force`, always re-checks (used by `akta-pro update`). Otherwise reads
    the cache and only re-checks once `ttl` has elapsed (used by the `--version`
    hint, so it stays fast and offline most of the time).
    """
    path = _cache_path()
    now = int(time.time())
    if not force:
        try:
            data = json.loads(path.read_text())
            if now - int(data.get("checked_at", 0)) < ttl:
                return data.get("latest")
        except (OSError, ValueError):
            pass
    latest = latest_version(timeout=timeout)
    if latest is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"checked_at": now, "latest": latest}))
        except OSError:
            pass
    return latest
