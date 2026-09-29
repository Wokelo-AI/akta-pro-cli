"""Tests for `akta-pro connect` / `disconnect` / `connect status`.

Network- and Claude-free: one respx router (the `http` fixture) serves the akta.pro
key check, the skill lookup, and the hosted SKILL.md, and the `claude` CLI is replaced by
`FakeClaude`, which records every call and answers `mcp get/add/remove` from a
scripted state. HOME and the config dir point at a temp dir, so nothing real is
touched.
"""

import hashlib
import io
import json
import stat
import subprocess
import zipfile

import httpx
import pytest
import respx
from typer.testing import CliRunner

from akta_pro_cli.app import app
from akta_pro_cli.config import load_credentials, save_credentials
from akta_pro_cli.connectors import claude_code, codex
from akta_pro_cli.connectors import skill as skill_mod
from akta_pro_cli.connectors.skill import SkillError, check_url, parse_frontmatter

runner = CliRunner()
BASE = "https://api.akta.pro/api/v1"
KEY = "wk_live_secret_key_9876"
BLOB = "https://wokelofiles.blob.core.windows.net/assets/akta-pro"
SKILL_URL = f"{BLOB}/SKILL.md"
SKILL_LOOKUP = f"{BASE}{skill_mod.SKILL_ENDPOINT}"
MANIFEST = f"{BLOB}/manifest.json"
ZIP_URL = f"{BLOB}/akta-pro-skill-2.0.0.zip"
SKILL_MD = b"---\nname: akta-pro\ndescription: Company intelligence via akta.pro.\n---\n\n# akta.pro\n"
SKILL_MD_V2 = SKILL_MD + b"\nNew guidance.\n"


class FakeClaude:
    """Stands in for `subprocess.run` on the `claude` CLI."""

    def __init__(self, scope=None, add_rc=0, add_stderr="", remove_rc=0):
        self.scope = scope  # scope label of an existing 'akta-pro' entry, or None
        self.add_rc, self.add_stderr, self.remove_rc = add_rc, add_stderr, remove_rc
        self.calls = []

    def verbs(self):
        return [c[2] for c in self.calls]

    def __call__(self, argv, **kwargs):
        assert isinstance(argv, list) and not kwargs.get("shell")
        self.calls.append(argv)
        verb = argv[2]
        if verb == "get":
            if self.scope is None:
                return subprocess.CompletedProcess(argv, 1, "", 'No MCP server named "akta-pro".')
            out = f"akta-pro:\n  Scope: {self.scope}\n  Type: http\n  URL: https://mcp.akta.pro/mcp\n"
            return subprocess.CompletedProcess(argv, 0, out, "")
        if verb == "remove":
            if self.scope is None or not self.scope.startswith("User"):
                return subprocess.CompletedProcess(argv, 1, "", 'No MCP server named "akta-pro" in user scope')
            self.scope = None if self.remove_rc == 0 else self.scope
            return subprocess.CompletedProcess(argv, self.remove_rc, "Removed", "")
        if verb == "add":
            if self.add_rc == 0:
                self.scope = "User config (available in all your projects)"
            return subprocess.CompletedProcess(argv, self.add_rc, "", self.add_stderr)
        raise AssertionError(f"unexpected claude call: {argv}")


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / ".config"))
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("AKTA_PRO_API_KEY", raising=False)
    monkeypatch.delenv(skill_mod.SKILL_URL_ENV, raising=False)
    return tmp_path


@pytest.fixture
def http(home):
    """All HTTP for a test. Serves the skill lookup and the hosted SKILL.md by
    default; anything not routed fails the test."""
    with respx.mock(assert_all_called=False) as mock:
        mock.get(SKILL_LOOKUP).mock(return_value=httpx.Response(200, json={"name": "akta-pro", "url": SKILL_URL}))
        mock.get(SKILL_URL).mock(return_value=httpx.Response(200, content=SKILL_MD))
        yield mock


@pytest.fixture
def claude(monkeypatch):
    fake = FakeClaude()
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(claude_code.subprocess, "run", fake)
    return fake


@pytest.fixture
def key_ok(http):
    return http.get(f"{BASE}/company/search").mock(return_value=httpx.Response(200, json={"data": []}))


def invoke(*args, **kw):
    res = runner.invoke(app, list(args), **kw)
    assert KEY not in res.output, "API key leaked into output"
    return res


def skill_dir(home):
    return home / ".claude" / "skills" / "akta-pro"


def status_entry(res, target):
    return next(e for e in json.loads(res.stdout) if e["target"] == target)


def marker(home):
    return json.loads((skill_dir(home) / ".akta-install.json").read_text())


# --- happy path + key resolution --------------------------------------------

def test_connect_installs_skill_and_registers_mcp(home, claude, key_ok):
    save_credentials({"api_key": KEY})
    res = invoke("connect", "claude-code")
    assert res.exit_code == 0, res.output
    assert (skill_dir(home) / "SKILL.md").read_bytes() == SKILL_MD
    assert marker(home)["source"] == SKILL_URL
    assert marker(home)["sha256"] == hashlib.sha256(SKILL_MD).hexdigest()
    add = claude.calls[-1]
    assert add[1:] == ["mcp", "add", "--transport", "http", "--scope", "user", "akta-pro",
                       "https://mcp.akta.pro/mcp", "--header", f"x-api-key: {KEY}"]
    assert "wk_li…9876" in res.output
    assert key_ok.calls.last.request.headers["x-api-key"] == KEY


def test_api_key_flag_overrides_stored_key(home, claude, key_ok):
    save_credentials({"api_key": "wk_stored_key_000000"})
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 0, res.output
    assert claude.calls[-1][-1] == f"x-api-key: {KEY}"


def test_env_key_used_when_nothing_stored(home, claude, key_ok, monkeypatch):
    monkeypatch.setenv("AKTA_PRO_API_KEY", KEY)
    res = invoke("connect", "claude-code")
    assert res.exit_code == 0, res.output
    assert claude.calls[-1][-1] == f"x-api-key: {KEY}"


def test_no_key_exits_3_and_changes_nothing(home, http, claude):
    res = invoke("connect", "claude-code")  # CliRunner stdin isn't a TTY → no prompt
    assert res.exit_code == 3
    assert "akta-pro login" in res.output
    assert not skill_dir(home).exists() and claude.calls == []


def test_prompts_for_key_and_logs_in_when_none_stored(home, claude, key_ok, monkeypatch):
    from akta_pro_cli.commands import connect as connect_cmd

    monkeypatch.setattr(connect_cmd, "_interactive", lambda: True)
    res = invoke("connect", "claude-code", input=f"{KEY}\n")
    assert res.exit_code == 0, res.output
    assert claude.calls[-1][-1] == f"x-api-key: {KEY}"
    assert load_credentials()["api_key"] == KEY
    assert (skill_dir(home) / "SKILL.md").is_file()


def test_api_key_flag_logs_in_when_none_stored(home, claude, key_ok):
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 0, res.output
    assert load_credentials() == {"api_key": KEY, "base_url": BASE}


def test_existing_login_is_not_overwritten(home, claude, key_ok):
    save_credentials({"api_key": "wk_stored_key_000000"})
    assert invoke("connect", "claude-code", "--api-key", KEY).exit_code == 0
    assert load_credentials()["api_key"] == "wk_stored_key_000000"


def test_env_key_is_not_written_to_disk(home, claude, key_ok, monkeypatch):
    monkeypatch.setenv("AKTA_PRO_API_KEY", KEY)
    assert invoke("connect", "claude-code").exit_code == 0
    assert load_credentials() == {}


def test_rejected_key_exits_3(home, http, claude):
    http.get(f"{BASE}/company/search").mock(return_value=httpx.Response(401, json={}))
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 3
    assert claude.calls == [] and not skill_dir(home).exists()
    assert load_credentials() == {}  # a rejected key is never stored


def test_oauth_registers_without_header_or_key(home, http, claude):
    res = invoke("connect", "claude-code", "--oauth")  # no key-check route: any call would fail
    assert res.exit_code == 0, res.output
    add = claude.calls[-1]
    assert "--header" not in add and add[-1] == "https://mcp.akta.pro/mcp"
    assert "OAuth" in res.output


def test_skill_only_needs_no_key_or_claude(home, http, claude):
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 0, res.output
    assert (skill_dir(home) / "SKILL.md").is_file() and claude.calls == []


def test_conflicting_flags_exit_2(home, claude):
    assert invoke("connect", "claude-code", "--skill-only", "--mcp-only").exit_code == 2
    assert invoke("connect", "claude-code", "--oauth", "--api-key", KEY).exit_code == 2
    assert invoke("connect", "claude-code", "--oauth", "--launch", "--json").exit_code == 2


def test_unknown_target_lists_supported(home):
    res = invoke("connect", "cursor")
    assert res.exit_code == 2
    assert "Supported: claude-code, codex" in res.output


def test_claude_config_dir_is_respected(home, http, claude, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(home / "alt"))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 0, res.output
    assert (home / "alt" / "skills" / "akta-pro" / "SKILL.md").is_file()


def test_json_output(home, claude, key_ok):
    res = invoke("connect", "claude-code", "--api-key", KEY, "--json")
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["steps"]["skill"]["status"] == "ok"
    assert data["steps"]["skill"]["sha256"] == hashlib.sha256(SKILL_MD).hexdigest()
    assert data["steps"]["mcp"] == {**data["steps"]["mcp"], "status": "ok", "auth": "api_key",
                                    "key": "wk_li…9876", "scope": "user"}


def test_launch_execs_claude(home, http, claude, monkeypatch):
    from akta_pro_cli.commands import connect as connect_cmd

    launched = []
    monkeypatch.setattr(connect_cmd.os, "execvp", lambda f, argv: launched.append(argv))
    res = invoke("connect", "claude-code", "--oauth", "--launch")
    assert res.exit_code == 0, res.output
    assert launched == [["/usr/local/bin/claude"]]


# --- MCP registration edge cases --------------------------------------------

def test_claude_missing_still_installs_skill(home, key_ok, monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 0, res.output
    assert (skill_dir(home) / "SKILL.md").is_file()
    assert "claude mcp add --transport http --scope user akta-pro" in res.output


def test_claude_missing_with_mcp_only_fails(home, key_ok, monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    res = invoke("connect", "claude-code", "--api-key", KEY, "--mcp-only")
    assert res.exit_code == 4


def test_existing_server_is_skipped_without_force(home, claude, key_ok):
    claude.scope = "User config (available in all your projects)"
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 0, res.output
    assert claude.verbs() == ["get"]
    assert "--force" in res.output


def test_force_replaces_existing_server(home, claude, key_ok):
    claude.scope = "User config (available in all your projects)"
    res = invoke("connect", "claude-code", "--api-key", KEY, "--force")
    assert res.exit_code == 0, res.output
    assert claude.verbs() == ["get", "remove", "add"]
    assert claude.calls[1][1:] == ["mcp", "remove", "akta-pro", "--scope", "user"]


def test_force_with_nothing_registered_just_adds(home, claude, key_ok):
    res = invoke("connect", "claude-code", "--api-key", KEY, "--force")
    assert res.exit_code == 0, res.output
    assert claude.verbs() == ["get", "remove", "add"]


def test_server_in_other_scope_adds_user_entry_with_note(home, claude, key_ok):
    claude.scope = "Local config (private to you in this project)"
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 0, res.output
    assert claude.verbs() == ["get", "add"]
    assert "Local config" in res.output


def test_add_failure_surfaces_stderr_without_key(home, claude, key_ok):
    claude.add_rc, claude.add_stderr = 1, f"invalid header x-api-key: {KEY}"
    res = invoke("connect", "claude-code", "--api-key", KEY)
    assert res.exit_code == 4
    assert "invalid header" in res.output and "wk_li…9876" in res.output


def test_claude_timeout_is_reported(home, key_ok, monkeypatch):
    def hang(argv, **kw):
        raise subprocess.TimeoutExpired(argv, kw.get("timeout"))

    monkeypatch.setattr(claude_code.shutil, "which", lambda name: "/usr/local/bin/claude")
    monkeypatch.setattr(claude_code.subprocess, "run", hang)
    res = invoke("connect", "claude-code", "--api-key", KEY, "--mcp-only")
    assert res.exit_code == 4
    assert "timed out" in res.output


# --- skill install (hosted SKILL.md) -----------------------------------------

def test_skill_reinstall_is_skipped_when_unchanged(home, http, claude):
    assert invoke("connect", "claude-code", "--skill-only").exit_code == 0
    stamp = (skill_dir(home) / ".akta-install.json").read_text()
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 0 and "already installed" in res.output
    assert (skill_dir(home) / ".akta-install.json").read_text() == stamp


def test_skill_is_updated_when_hosted_file_changes(home, http, claude):
    assert invoke("connect", "claude-code", "--skill-only").exit_code == 0
    http.get(SKILL_URL).mock(return_value=httpx.Response(200, content=SKILL_MD_V2))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 0, res.output
    assert (skill_dir(home) / "SKILL.md").read_bytes() == SKILL_MD_V2
    assert f"@{hashlib.sha256(SKILL_MD_V2).hexdigest()[:7]}" in res.output


def test_unmanaged_skill_folder_needs_force(home, http, claude):
    skill_dir(home).mkdir(parents=True)
    (skill_dir(home) / "SKILL.md").write_text("mine")
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4
    assert (skill_dir(home) / "SKILL.md").read_text() == "mine"
    res = invoke("connect", "claude-code", "--skill-only", "--force")
    assert res.exit_code == 0, res.output
    assert (skill_dir(home) / ".akta-install.json").is_file()
    assert [p.name for p in skill_dir(home).parent.iterdir()] == ["akta-pro"]  # no staging/backup left


def test_restart_note_only_when_skills_folder_is_new(home, http, claude):
    assert "restart" in invoke("connect", "claude-code", "--skill-only").output
    assert "restart" not in invoke("connect", "claude-code", "--skill-only", "--force").output


@pytest.mark.parametrize("failure, code", [
    (httpx.ConnectTimeout("slow"), 5),
    (httpx.ConnectError("offline"), 4),
    (httpx.Response(503), 4),
])
def test_unreachable_storage_with_nothing_installed_fails_cleanly(home, http, claude, failure, code):
    route = http.get(SKILL_URL)
    route.mock(return_value=failure) if isinstance(failure, httpx.Response) else route.mock(side_effect=failure)
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == code, res.output
    assert "Nothing was installed" in res.output
    assert not skill_dir(home).exists()


def test_unreachable_storage_keeps_existing_install(home, http, claude):
    http.get(SKILL_URL).mock(return_value=httpx.Response(200, content=SKILL_MD_V2))
    assert invoke("connect", "claude-code", "--skill-only").exit_code == 0
    http.get(SKILL_URL).mock(side_effect=httpx.ConnectTimeout("slow"))
    res = invoke("connect", "claude-code", "--skill-only", "--force")
    assert res.exit_code == 0, res.output
    assert "Kept the installed skill" in res.output
    assert (skill_dir(home) / "SKILL.md").read_bytes() == SKILL_MD_V2


def test_unreachable_storage_does_not_block_mcp_registration(home, http, claude):
    http.get(SKILL_URL).mock(side_effect=httpx.ConnectError("offline"))
    res = invoke("connect", "claude-code", "--oauth")
    assert res.exit_code == 4  # the skill step failed…
    assert claude.verbs()[-1] == "add"  # …but the MCP server was still registered


@pytest.mark.parametrize("status", [403, 404])
def test_hosted_file_client_error_aborts(home, http, claude, status):
    http.get(SKILL_URL).mock(return_value=httpx.Response(status))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and f"HTTP {status}" in res.output
    assert not skill_dir(home).exists()


def test_hosted_file_redirect_is_not_followed(home, http, claude):
    http.get(SKILL_URL).mock(return_value=httpx.Response(302, headers={"Location": "https://evil.example.com/"}))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "redirect" in res.output


def test_hosted_file_with_bad_frontmatter_is_refused(home, http, claude):
    http.get(SKILL_URL).mock(return_value=httpx.Response(200, content=b"<html>error page</html>"))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "frontmatter" in res.output
    assert not skill_dir(home).exists()


def test_hosted_file_with_wrong_name_is_refused(home, http, claude):
    http.get(SKILL_URL).mock(return_value=httpx.Response(200, content=b"---\nname: other\ndescription: x\n---\n"))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "expected 'akta-pro'" in res.output


def test_oversized_hosted_file_is_refused(home, http, claude):
    http.get(SKILL_URL).mock(return_value=httpx.Response(200, content=b"x" * (skill_mod.MAX_SKILL_MD_BYTES + 1)))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "exceeds" in res.output


@pytest.mark.parametrize("url", [
    "http://wokelofiles.blob.core.windows.net/assets/akta-pro/SKILL.md",       # not HTTPS
    "https://evil.example.com/assets/akta-pro/SKILL.md",                        # other host
    "https://wokelofiles.blob.core.windows.net.evil.com/assets/akta-pro/SKILL.md",
    "https://wokelofiles.blob.core.windows.net/assets/other/SKILL.md",          # other path
    "https://wokelofiles.blob.core.windows.net/assets/akta-pro/../x/SKILL.md",  # traversal
    "https://wokelofiles.blob.core.windows.net:8443/assets/akta-pro/SKILL.md",  # other port
])
def test_disallowed_skill_urls_are_refused(url):
    with pytest.raises(SkillError):
        check_url(url)


def test_skill_url_override_must_be_allowlisted(home, http, claude, monkeypatch):
    monkeypatch.setenv(skill_mod.SKILL_URL_ENV, "https://evil.example.com/assets/akta-pro/SKILL.md")
    res = invoke("connect", "claude-code", "--skill-only")  # refused before any request
    assert res.exit_code == 4 and "allowlisted" in res.output


# --- skill lookup (akta.pro API) ----------------------------------------------

def test_skill_lookup_sends_no_api_key(home, http, claude, key_ok):
    assert invoke("connect", "claude-code", "--api-key", KEY).exit_code == 0
    lookup = http.routes[0].calls.last.request
    assert lookup.url == SKILL_LOOKUP and "x-api-key" not in lookup.headers


def test_skill_lookup_honours_base_url(home, http, claude):
    alt = "http://localhost:8000/api/v1"
    route = http.get(f"{alt}{skill_mod.SKILL_ENDPOINT}").mock(
        return_value=httpx.Response(200, json={"name": "akta-pro", "url": SKILL_URL}))
    assert invoke("--base-url", alt, "connect", "claude-code", "--skill-only").exit_code == 0
    assert route.called


def test_skill_lookup_outage_keeps_existing_install(home, http, claude):
    assert invoke("connect", "claude-code", "--skill-only").exit_code == 0
    http.get(SKILL_LOOKUP).mock(return_value=httpx.Response(503))
    res = invoke("connect", "claude-code", "--skill-only", "--force")
    assert res.exit_code == 0 and "Kept the installed skill" in res.output


@pytest.mark.parametrize("response, message", [
    (httpx.Response(404), "HTTP 404"),
    (httpx.Response(200, content=b"<html>"), "invalid JSON"),
    (httpx.Response(200, json={"name": "akta-pro"}), "missing 'url'"),
    (httpx.Response(200, json={"url": "https://evil.example.com/assets/akta-pro/SKILL.md"}), "allowlisted"),
])
def test_bad_skill_lookup_aborts(home, http, claude, response, message):
    http.get(SKILL_LOOKUP).mock(return_value=response)
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and message in res.output
    assert not skill_dir(home).exists()


def test_manifest_url_from_lookup_installs(home, http, claude):
    archive = make_zip({"SKILL.md": SKILL_MD})
    manifest = {"version": "2.0.0", "url": ZIP_URL, "sha256": hashlib.sha256(archive).hexdigest()}
    http.get(SKILL_LOOKUP).mock(return_value=httpx.Response(200, json={"url": MANIFEST}))
    http.get(MANIFEST).mock(return_value=httpx.Response(200, json=manifest))
    http.get(ZIP_URL).mock(return_value=httpx.Response(200, content=archive))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 0 and "v2.0.0" in res.output


# --- remote manifest + zip ----------------------------------------------------

def make_zip(entries: dict[str, bytes], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


@pytest.fixture
def remote(http, monkeypatch):
    monkeypatch.setenv(skill_mod.SKILL_URL_ENV, MANIFEST)

    def serve(archive: bytes, *, sha: str | None = None, url: str = ZIP_URL):
        manifest = {"version": "2.0.0", "url": url, "sha256": sha or hashlib.sha256(archive).hexdigest()}
        http.get(MANIFEST).mock(return_value=httpx.Response(200, json=manifest))
        http.get(url).mock(return_value=httpx.Response(200, content=archive))

    return serve


def test_manifest_skill_installs(home, claude, remote):
    remote(make_zip({"SKILL.md": SKILL_MD, "reference/api.md": b"# api"}))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 0, res.output
    assert "v2.0.0" in res.output
    assert (skill_dir(home) / "reference" / "api.md").read_bytes() == b"# api"
    assert marker(home)["version"] == "2.0.0" and marker(home)["source"] == MANIFEST


def test_manifest_zip_with_wrapping_folder(home, claude, remote):
    remote(make_zip({"akta-pro/SKILL.md": SKILL_MD}))
    assert invoke("connect", "claude-code", "--skill-only").exit_code == 0
    assert (skill_dir(home) / "SKILL.md").read_bytes() == SKILL_MD


def test_manifest_hash_mismatch_aborts(home, claude, remote):
    remote(make_zip({"SKILL.md": SKILL_MD}), sha="0" * 64)
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "checksum mismatch" in res.output
    assert not skill_dir(home).exists()


def test_manifest_zip_url_off_allowlist_is_refused(home, claude, remote):
    remote(make_zip({"SKILL.md": SKILL_MD}), url="https://evil.example.com/skill.zip")
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "allowlisted" in res.output
    assert not skill_dir(home).exists()


@pytest.mark.parametrize("entry", ["../evil.md", "/etc/evil.md", "a/../../evil.md", "C:/evil.md", "a\\..\\evil.md"])
def test_manifest_zip_slip_is_refused(home, claude, remote, entry):
    remote(make_zip({"SKILL.md": SKILL_MD, entry: b"x"}))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "Unsafe path" in res.output
    assert not skill_dir(home).exists()
    assert not (home / ".claude" / "evil.md").exists()


def test_manifest_symlink_entry_is_refused(home, claude, remote):
    remote(make_zip({"SKILL.md": SKILL_MD}, symlink="link.md"))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "Symlink" in res.output


def test_manifest_missing_skill_md_is_refused(home, claude, remote):
    remote(make_zip({"README.md": b"hi"}))
    res = invoke("connect", "claude-code", "--skill-only")
    assert res.exit_code == 4 and "no SKILL.md" in res.output
    assert not skill_dir(home).exists()


# --- disconnect / status -----------------------------------------------------

def test_disconnect_removes_skill_and_server(home, http, claude):
    assert invoke("connect", "claude-code", "--oauth").exit_code == 0
    res = invoke("disconnect", "claude-code")
    assert res.exit_code == 0, res.output
    assert not skill_dir(home).exists()
    assert claude.calls[-1][1:] == ["mcp", "remove", "akta-pro", "--scope", "user"]
    assert claude.scope is None


def test_disconnect_when_nothing_installed(home, claude):
    res = invoke("disconnect", "claude-code")
    assert res.exit_code == 0
    assert "not installed" in res.output and "not registered" in res.output


def test_disconnect_leaves_unmanaged_skill(home, claude):
    skill_dir(home).mkdir(parents=True)
    (skill_dir(home) / "SKILL.md").write_text("mine")
    res = invoke("disconnect", "claude-code")
    assert res.exit_code == 0
    assert (skill_dir(home) / "SKILL.md").read_text() == "mine"


def test_status_json(home, http, claude):
    assert invoke("connect", "claude-code", "--oauth").exit_code == 0
    res = invoke("connect", "status", "--json")
    assert res.exit_code == 0, res.output
    entry = status_entry(res, "claude-code")
    assert entry["target"] == "claude-code"
    assert entry["skill"]["installed"] and entry["skill"]["source"] == SKILL_URL
    assert entry["skill"]["label"] == f"@{hashlib.sha256(SKILL_MD).hexdigest()[:7]}"
    assert entry["mcp"]["registered"] is True and entry["mcp"]["scope"].startswith("User")


def test_status_without_claude(home, monkeypatch):
    monkeypatch.setattr(claude_code.shutil, "which", lambda name: None)
    res = invoke("connect", "status", "--json")
    entry = status_entry(res, "claude-code")
    assert entry["skill"]["installed"] is False
    assert entry["mcp"]["claude_found"] is False and entry["mcp"]["registered"] is None


# --- units -------------------------------------------------------------------

def test_single_file_identity_is_plain_sha256():
    assert skill_mod.content_hash({"SKILL.md": SKILL_MD}) == hashlib.sha256(SKILL_MD).hexdigest()


def test_parse_frontmatter_scalars():
    meta = parse_frontmatter('---\nname: "akta-pro"\ndescription: >\n  folded\n  text\n---\nbody')
    assert meta == {"name": "akta-pro", "description": "folded text"}


def test_parse_frontmatter_requires_block():
    with pytest.raises(SkillError):
        parse_frontmatter("# no frontmatter")
    with pytest.raises(SkillError):
        parse_frontmatter("---\nname: x\n")


# --- codex -------------------------------------------------------------------

@pytest.fixture
def codex_cli(monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: "/usr/local/bin/codex")


def codex_skill(home):
    return home / ".agents" / "skills" / "akta-pro"


def codex_config(home):
    return home / ".codex" / "config.toml"


def codex_servers(home):
    import tomllib
    return tomllib.loads(codex_config(home).read_text()).get("mcp_servers", {})


EXISTING_CODEX = """model = "gpt-5"

# my servers
[mcp_servers.context7]
command = "npx"
args = ["-y", "@upstash/context7-mcp"]

[profiles.fast]
model = "gpt-5-mini"
"""


def test_codex_connect_installs_skill_and_writes_config(home, codex_cli, key_ok):
    save_credentials({"api_key": KEY})
    res = invoke("connect", "codex")
    assert res.exit_code == 0, res.output
    assert (codex_skill(home) / "SKILL.md").read_bytes() == SKILL_MD
    assert codex_servers(home)["akta-pro"] == {"url": "https://mcp.akta.pro/mcp",
                                               "http_headers": {"x-api-key": KEY}}
    assert stat.S_IMODE(codex_config(home).stat().st_mode) == 0o600
    assert "wk_li…9876" in res.output and "Open Codex" in res.output


def test_codex_keeps_the_rest_of_the_config(home, codex_cli, key_ok):
    codex_config(home).parent.mkdir()
    codex_config(home).write_text(EXISTING_CODEX)
    assert invoke("connect", "codex", "--api-key", KEY).exit_code == 0
    text = codex_config(home).read_text()
    assert text.startswith(EXISTING_CODEX.rstrip("\n"))
    assert "# my servers" in text and set(codex_servers(home)) == {"context7", "akta-pro"}


def test_codex_existing_entry_skipped_then_force_replaces(home, codex_cli, key_ok):
    assert invoke("connect", "codex", "--oauth").exit_code == 0
    res = invoke("connect", "codex", "--api-key", KEY)
    assert res.exit_code == 0 and "--force" in res.output
    assert "http_headers" not in codex_servers(home)["akta-pro"]
    assert invoke("connect", "codex", "--api-key", KEY, "--force").exit_code == 0
    assert codex_servers(home)["akta-pro"]["http_headers"] == {"x-api-key": KEY}
    assert codex_config(home).read_text().count("[mcp_servers.akta-pro]") == 1


def test_codex_force_replaces_entry_with_subtables(home, codex_cli, key_ok):
    codex_config(home).parent.mkdir()
    codex_config(home).write_text(
        '[mcp_servers."akta-pro"]\nurl = "https://old.example/mcp"\n\n'
        '[mcp_servers."akta-pro".tools.company_data]\napproval_mode = "approve"\n\n' + EXISTING_CODEX
    )
    assert invoke("connect", "codex", "--api-key", KEY, "--force").exit_code == 0
    servers = codex_servers(home)
    assert servers["akta-pro"]["url"] == "https://mcp.akta.pro/mcp" and "tools" not in servers["akta-pro"]
    assert "context7" in servers


def test_codex_oauth_writes_url_only_and_says_how_to_sign_in(home, http, codex_cli):
    res = invoke("connect", "codex", "--oauth")
    assert res.exit_code == 0, res.output
    assert codex_servers(home)["akta-pro"] == {"url": "https://mcp.akta.pro/mcp"}
    assert "codex mcp login akta-pro" in res.output


def test_codex_home_is_respected(home, http, codex_cli, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(home / "alt"))
    assert invoke("connect", "codex", "--oauth").exit_code == 0
    assert (home / "alt" / "config.toml").is_file() and not codex_config(home).exists()


def test_codex_missing_cli_still_configures_with_note(home, key_ok, monkeypatch):
    monkeypatch.setattr(codex.shutil, "which", lambda name: None)
    res = invoke("connect", "codex", "--api-key", KEY)
    assert res.exit_code == 0, res.output
    assert "akta-pro" in codex_servers(home) and "not found on PATH" in res.output


def test_codex_invalid_toml_is_left_alone(home, http, codex_cli):
    codex_config(home).parent.mkdir()
    codex_config(home).write_text("this is = = not toml\n")
    res = invoke("connect", "codex", "--oauth")
    assert res.exit_code == 4 and "isn't valid TOML" in res.output
    assert codex_config(home).read_text() == "this is = = not toml\n"


def test_codex_unsupported_form_is_refused(home, http, codex_cli):
    original = 'mcp_servers = { "akta-pro" = { url = "https://old.example/mcp" } }\n'
    codex_config(home).parent.mkdir()
    codex_config(home).write_text(original)
    res = invoke("connect", "codex", "--oauth", "--force")
    assert res.exit_code == 4 and "by hand" in res.output
    assert codex_config(home).read_text() == original


def test_codex_disconnect_removes_only_our_entry(home, http, codex_cli):
    codex_config(home).parent.mkdir()
    codex_config(home).write_text(EXISTING_CODEX)
    assert invoke("connect", "codex", "--oauth").exit_code == 0
    res = invoke("disconnect", "codex")
    assert res.exit_code == 0, res.output
    assert not codex_skill(home).exists()
    assert set(codex_servers(home)) == {"context7"}
    assert "not registered" in invoke("disconnect", "codex").output


def test_codex_status_json(home, http, codex_cli):
    assert invoke("connect", "codex", "--oauth").exit_code == 0
    entry = status_entry(invoke("connect", "status", "--json"), "codex")
    assert entry["skill"]["installed"] and entry["mcp"]["registered"] is True
    assert entry["mcp"]["url"] == "https://mcp.akta.pro/mcp" and entry["mcp"]["cli_found"] is True


def test_codex_launch_execs_codex(home, http, codex_cli, monkeypatch):
    from akta_pro_cli.commands import connect as connect_cmd
    launched = []
    monkeypatch.setattr(connect_cmd.os, "execvp", lambda f, argv: launched.append(argv))
    assert invoke("connect", "codex", "--oauth", "--launch").exit_code == 0
    assert launched == [["/usr/local/bin/codex"]]
