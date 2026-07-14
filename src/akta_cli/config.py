"""Local credential + config storage for the Akta CLI.

Credentials live in a JSON file under the user's config dir
(`$XDG_CONFIG_HOME/akta` or `~/.config/akta` on Unix, `%APPDATA%\\akta` on
Windows), written 0600. Only the API key path is used in v1.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

APP_NAME = "akta"


def config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / APP_NAME


def credentials_path() -> Path:
    return config_dir() / "credentials.json"


def load_credentials() -> dict:
    path = credentials_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def save_credentials(data: dict) -> Path:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass  # best-effort (e.g. Windows)
    path = credentials_path()
    path.write_text(json.dumps(data, indent=2))
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    return path


def clear_credentials() -> bool:
    """Delete the stored credentials file. Returns True if a file was removed."""
    path = credentials_path()
    if path.exists():
        path.unlink()
        return True
    return False


def stored_api_key() -> str | None:
    return load_credentials().get("api_key")


def stored_base_url() -> str | None:
    return load_credentials().get("base_url")
