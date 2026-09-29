"""The akta-pro agent skill: where it comes from and how it lands on disk.

The akta.pro API says where the skill is: `GET {base_url}/skills/akta-pro`
returns `{"name": "akta-pro", "url": "https://…"}`, and the file is downloaded
from that blob URL. The file can be replaced, or moved, without a CLI release.

Sources, one shape (`SkillPackage`):

- **Remote SKILL.md** — a bare file on blob storage, identified by its content
  hash: `connect` reinstalls only when the file changes.
- **Remote manifest** — a URL ending in `.json` is read as
  `{"version": "1.0.0", "url": "https://…/akta-pro-skill-1.0.0.zip", "sha256": "…"}`,
  for a versioned zip with extra reference files. The zip's SHA-256 must match,
  and every entry is checked for zip-slip.

Remote URLs must be HTTPS, on an allowlisted host and path prefix, and are never
redirected. That holds for the URL the API returns too, so the API alone can't
point the CLI anywhere else. `AKTA_SKILL_URL` skips the API lookup, for
internal testing.

`install_skill()` validates the files, stages them next to the destination, and
swaps them into place with renames, so a failure never leaves a partial skill.
A `.akta-install.json` marker records what was installed; `status` reads it and
`disconnect` only removes a folder that carries it.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

import httpx

from akta_pro_cli.client import CLIENT_SOURCE

SKILL_NAME = "akta-pro"
SKILL_FILE = "SKILL.md"
MARKER_FILE = ".akta-install.json"

SKILL_ENDPOINT = f"/skills/{SKILL_NAME}"  # on the akta.pro API; answers with the blob URL
SKILL_URL_ENV = "AKTA_SKILL_URL"

# The only places a remote skill (or manifest, or zip) may come from. The storage
# account holds other assets too, so the path is pinned as well as the host.
SKILL_HOSTS: frozenset[str] = frozenset({"wokelofiles.blob.core.windows.net", "files.akta.pro"})
SKILL_PATH_PREFIX = "/assets/"

HTTP_TIMEOUT = 15.0
MAX_MANIFEST_BYTES = 64 * 1024
MAX_SKILL_MD_BYTES = 1024 * 1024
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_FILES = 200


class SkillError(RuntimeError):
    """The skill couldn't be fetched, verified, or installed. Nothing was changed."""


class SkillNetworkError(SkillError):
    """Blob storage couldn't be reached (connection error, timeout, or 5xx)."""

    def __init__(self, message: str, *, timeout: bool = False):
        super().__init__(message)
        self.timeout = timeout


@dataclass(frozen=True)
class SkillPackage:
    version: str | None  # None for a bare SKILL.md, which is tracked by hash alone
    sha256: str
    source: str  # the URL it came from
    files: dict[str, bytes]  # POSIX relative path → content

    @property
    def label(self) -> str:
        return describe(self.version, self.sha256)


def describe(version: str | None, sha256: str | None) -> str:
    """How an install is shown: `v1.0.0`, or `@3f9a1c2` when unversioned."""
    if version:
        return f"v{version}"
    return f"@{(sha256 or '')[:7]}" if sha256 else "(unknown version)"


# --- sources ---------------------------------------------------------------

def skill_url(base_url: str, timeout: float = HTTP_TIMEOUT) -> str:
    """The skill's blob URL: `AKTA_SKILL_URL` if set, else asked of the API.

    The endpoint is public, so no API key is sent: `--skill-only` works without
    one, and the key never goes anywhere it isn't needed.
    """
    override = os.environ.get(SKILL_URL_ENV)
    if override:
        return override
    endpoint = base_url.rstrip("/") + SKILL_ENDPOINT
    try:
        with _client(timeout) as client:
            resp = client.get(endpoint, headers={"X-Client-Source": CLIENT_SOURCE})
    except httpx.HTTPError as exc:
        raise _network_error(exc) from exc
    if resp.status_code >= 500:
        raise SkillNetworkError(f"akta.pro API unavailable (HTTP {resp.status_code}).")
    if resp.status_code != 200:
        raise SkillError(f"Skill lookup failed: HTTP {resp.status_code} for {endpoint}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise SkillError("Skill lookup returned invalid JSON.") from exc
    url = data.get("url") if isinstance(data, dict) else None
    if not isinstance(url, str) or not url.strip():
        raise SkillError("Skill lookup response is missing 'url'.")
    return url.strip()


def load_skill(base_url: str, timeout: float = HTTP_TIMEOUT) -> SkillPackage:
    """Look up the skill's URL, then fetch it from blob storage. Raises
    `SkillNetworkError` if either can't be reached, `SkillError` if what came
    back is wrong."""
    url = skill_url(base_url, timeout=timeout)
    if urlsplit(url).path.endswith(".json"):
        return fetch_remote_skill(url, timeout=timeout)
    return fetch_skill_file(url, timeout=timeout)


def content_hash(files: dict[str, bytes]) -> str:
    """Identity of an unversioned skill: the plain SHA-256 of a lone SKILL.md
    (matching `shasum -a 256 SKILL.md`), else a digest over every file."""
    if set(files) == {SKILL_FILE}:
        return hashlib.sha256(files[SKILL_FILE]).hexdigest()
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(rel.encode() + b"\0" + files[rel] + b"\0")
    return digest.hexdigest()


def check_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise SkillError(f"Refusing non-HTTPS skill URL: {url}")
    if (parts.hostname or "").lower() not in SKILL_HOSTS or parts.port not in (None, 443):
        raise SkillError(f"Refusing skill URL on a host that isn't allowlisted: {parts.netloc}")
    path = PurePosixPath(parts.path)
    if not parts.path.startswith(SKILL_PATH_PREFIX) or ".." in path.parts:
        raise SkillError(f"Refusing skill URL outside {SKILL_PATH_PREFIX}: {url}")


def _client(timeout: float) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": CLIENT_SOURCE}, follow_redirects=False)


def _network_error(exc: httpx.HTTPError) -> SkillNetworkError:
    if isinstance(exc, httpx.TimeoutException):
        return SkillNetworkError("Timed out downloading the akta-pro skill.", timeout=True)
    return SkillNetworkError(f"Couldn't download the akta-pro skill ({exc}).")


def fetch_skill_file(url: str, timeout: float = HTTP_TIMEOUT) -> SkillPackage:
    """A bare SKILL.md, versioned by its SHA-256."""
    check_url(url)
    try:
        with _client(timeout) as client:
            content = _download(client, url, MAX_SKILL_MD_BYTES)
    except httpx.HTTPError as exc:
        raise _network_error(exc) from exc
    files = {SKILL_FILE: content}
    return SkillPackage(None, content_hash(files), url, files)


def fetch_remote_skill(url: str, timeout: float = HTTP_TIMEOUT) -> SkillPackage:
    """A manifest.json pointing at a versioned, checksummed zip."""
    check_url(url)
    try:
        with _client(timeout) as client:
            manifest = _parse_manifest(_download(client, url, MAX_MANIFEST_BYTES))
            check_url(manifest["url"])
            archive = _download(client, manifest["url"], MAX_ZIP_BYTES)
    except httpx.HTTPError as exc:
        raise _network_error(exc) from exc

    actual = hashlib.sha256(archive).hexdigest()
    if actual != manifest["sha256"]:
        raise SkillError(
            f"Skill checksum mismatch (expected {manifest['sha256']}, got {actual}). Aborted."
        )
    return SkillPackage(manifest["version"], actual, url, unpack_zip(archive))


def _download(client: httpx.Client, url: str, limit: int) -> bytes:
    with client.stream("GET", url) as resp:
        if resp.is_redirect:
            raise SkillError(f"Skill URL redirected ({resp.status_code}); redirects are not followed: {url}")
        if resp.status_code >= 500:
            raise SkillNetworkError(f"Skill storage unavailable (HTTP {resp.status_code}).")
        if resp.status_code != 200:
            raise SkillError(f"Skill download failed: HTTP {resp.status_code} for {url}")
        buf = bytearray()
        for chunk in resp.iter_bytes():
            buf += chunk
            if len(buf) > limit:
                raise SkillError(f"Skill download exceeds {limit} bytes: {url}")
    return bytes(buf)


def _parse_manifest(raw: bytes) -> dict:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise SkillError("Skill manifest is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise SkillError("Skill manifest must be a JSON object.")
    for key in ("version", "url", "sha256"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise SkillError(f"Skill manifest is missing '{key}'.")
    sha = data["sha256"].strip().lower()
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise SkillError("Skill manifest 'sha256' is not a SHA-256 hex digest.")
    return {"version": data["version"].strip(), "url": data["url"].strip(), "sha256": sha}


def unpack_zip(archive: bytes) -> dict[str, bytes]:
    """Read a skill zip into memory, rejecting anything that could escape the
    destination (absolute paths, `..`, drive letters, backslashes, symlinks) or
    blow up on extraction. A single wrapping top-level folder is stripped."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as exc:
        raise SkillError("Skill archive is not a valid zip file.") from exc

    files: dict[str, bytes] = {}
    total = 0
    with zf:
        entries = [i for i in zf.infolist() if not i.is_dir()]
        if len(entries) > MAX_FILES:
            raise SkillError(f"Skill archive has more than {MAX_FILES} files.")
        for info in entries:
            name = info.filename
            path = PurePosixPath(name)
            if (
                "\\" in name
                or path.is_absolute()
                or ".." in path.parts
                or (path.parts and ":" in path.parts[0])
            ):
                raise SkillError(f"Unsafe path in skill archive: {name!r}")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise SkillError(f"Symlink in skill archive: {name!r}")
            total += info.file_size
            if total > MAX_UNPACKED_BYTES:
                raise SkillError("Skill archive unpacks to more than the allowed size.")
            files[path.as_posix()] = zf.read(info)

    if SKILL_FILE not in files:
        tops = {PurePosixPath(p).parts[0] for p in files}
        if len(tops) == 1 and all(len(PurePosixPath(p).parts) > 1 for p in files):
            top = tops.pop()
            files = {PurePosixPath(p).relative_to(top).as_posix(): b for p, b in files.items()}
    return files


# --- validation ------------------------------------------------------------

def parse_frontmatter(text: str) -> dict[str, str]:
    """Top-level scalar keys of a SKILL.md YAML frontmatter block.

    Handles plain, quoted, and block (`>` / `|`) scalars, which covers what a
    skill header uses, without adding a YAML dependency.
    """
    lines = text.lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        raise SkillError(f"{SKILL_FILE} has no YAML frontmatter.")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise SkillError(f"{SKILL_FILE} frontmatter is not closed with '---'.") from exc

    meta: dict[str, str] = {}
    body = lines[1:end]
    i = 0
    while i < len(body):
        line = body[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#") or line[0].isspace():
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise SkillError(f"{SKILL_FILE} frontmatter line isn't 'key: value': {line!r}")
        value = value.strip()
        if value in ("", ">", "|", ">-", "|-"):
            block = []
            while i < len(body) and (not body[i].strip() or body[i][0].isspace()):
                block.append(body[i].strip())
                i += 1
            value = (" " if value.startswith(">") or not value else "\n").join(b for b in block if b)
        elif len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        meta[key.strip()] = value
    return meta


def validate_skill(pkg: SkillPackage) -> None:
    raw = pkg.files.get(SKILL_FILE)
    if raw is None:
        raise SkillError(f"Skill package has no {SKILL_FILE}.")
    try:
        meta = parse_frontmatter(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise SkillError(f"{SKILL_FILE} is not UTF-8.") from exc
    for key in ("name", "description"):
        if not meta.get(key):
            raise SkillError(f"{SKILL_FILE} frontmatter is missing '{key}'.")
    if meta["name"] != SKILL_NAME:
        raise SkillError(f"{SKILL_FILE} names skill {meta['name']!r}, expected {SKILL_NAME!r}.")


# --- install / inspect / remove ---------------------------------------------

def read_marker(dest: Path) -> dict | None:
    try:
        data = json.loads((dest / MARKER_FILE).read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def is_current(dest: Path, pkg: SkillPackage) -> bool:
    marker = read_marker(dest)
    return (
        marker is not None
        and (dest / SKILL_FILE).is_file()
        and marker.get("version") == pkg.version
        and marker.get("sha256") == pkg.sha256
    )


def install_skill(pkg: SkillPackage, dest: Path) -> None:
    """Write `pkg` to `dest` atomically: stage beside it, then swap by rename."""
    validate_skill(pkg)
    parent = dest.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest.name}-staging-", dir=parent))
    backup: Path | None = None
    try:
        for rel, content in pkg.files.items():
            target = staging / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        marker = {
            "name": SKILL_NAME,
            "version": pkg.version,
            "sha256": pkg.sha256,
            "source": pkg.source,
            "installed_at": datetime.now(UTC).isoformat(timespec="seconds"),
        }
        (staging / MARKER_FILE).write_text(json.dumps(marker, indent=2) + "\n")
        os.chmod(staging, 0o755)  # mkdtemp creates 0700

        if dest.exists() or dest.is_symlink():
            backup = parent / f".{dest.name}-old-{uuid.uuid4().hex[:8]}"
            dest.rename(backup)
        try:
            staging.rename(dest)
        except OSError:
            if backup is not None:
                backup.rename(dest)
                backup = None
            raise
    except OSError as exc:
        raise SkillError(f"Couldn't install the skill to {dest}: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        if backup is not None:
            try:
                _remove_path(backup)
            except OSError:
                pass  # the new skill is in place; a stray hidden backup is harmless


def remove_skill(dest: Path) -> None:
    try:
        _remove_path(dest)
    except OSError as exc:
        raise SkillError(f"Couldn't remove {dest}: {exc}") from exc


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)
