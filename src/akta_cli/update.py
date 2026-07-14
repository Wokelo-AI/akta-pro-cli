"""Update checking for the CLI.

Discovers the latest released version via `git ls-remote --tags` on the repo —
which reuses the user's existing git credentials, so it works for the private
repo with no GitHub API token. Results are cached in the config dir so
`akta --version` can show a hint without hitting the network on every call.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from akta_cli.config import config_dir

REPO = "Wokelo-AI/Akta-CLI"
REPO_URL = f"https://github.com/{REPO}"
_CACHE_TTL = 24 * 3600  # re-check at most once a day for the --version hint


def _cache_path() -> Path:
    return config_dir() / "update-check.json"


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


def latest_tag(timeout: float = 5.0) -> str | None:
    """Highest `vX.Y.Z` tag on the remote, without the leading `v`. None on failure."""
    try:
        result = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", REPO_URL],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    versions = []
    for line in result.stdout.splitlines():
        if "refs/tags/" not in line:
            continue
        ref = line.rsplit("refs/tags/", 1)[-1].strip()
        if ref.startswith("v") and ref[1:2].isdigit():
            versions.append(ref[1:])
    if not versions:
        return None
    return max(versions, key=parse_version)


def cached_latest(*, timeout: float = 2.0, ttl: int = _CACHE_TTL, force: bool = False) -> str | None:
    """Latest version string, using a time-boxed cache. Best-effort; None on failure.

    With `force`, always re-checks (used by `akta update`). Otherwise reads the
    cache and only re-checks once `ttl` has elapsed (used by the `--version`
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
    latest = latest_tag(timeout=timeout)
    if latest is not None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"checked_at": now, "latest": latest}))
        except OSError:
            pass
    return latest
