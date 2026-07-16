"""Tests for the `akta` CLI (src/akta_cli).

Self-contained and network-free: drives the real Typer app via CliRunner with
the HTTP layer mocked by respx. Run just these with:

    pytest tests/test_akta_cli.py

(The rest of tests/ is stale template debris — see tests/CLAUDE.md.)
"""

import json

import httpx
import respx
from typer.testing import CliRunner

from akta_cli import __version__
from akta_cli import update as _upd
from akta_cli.app import app
from akta_cli.config import load_credentials, save_credentials

runner = CliRunner()
BASE = "https://api.akta.pro/api/v1"


# --- auth / input validation (no network) ---

def test_no_key_exits_3(tmp_path):
    res = runner.invoke(app, ["company", "search", "Canva"],
                        env={"XDG_CONFIG_HOME": str(tmp_path), "AKTA_API_KEY": ""})
    assert res.exit_code == 3


def test_missing_section_exits_2(tmp_path):
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "data", "canva.com"],
                        env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 2


@respx.mock
def test_news_signals_anchors_are_optional():
    # Filters are optional — an un-anchored call still hits /news.
    route = respx.get(f"{BASE}/news").mock(
        return_value=httpx.Response(200, json={"total": 0, "count": 0,
                                               "credits_consumed": 0.1, "data": []}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals", "--json"])
    assert res.exit_code == 0
    assert route.called


@respx.mock
def test_news_signals_forwards_new_filters():
    route = respx.get(f"{BASE}/news").mock(
        return_value=httpx.Response(200, json={"total": 0, "count": 0,
                                               "credits_consumed": 0.1, "data": []}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals",
                              "--country", "USA", "--country", "GBR",
                              "--entity-person", "Melanie Perkins",
                              "--naics", "5112", "--blacklist", "example.com", "--json"])
    assert res.exit_code == 0
    params = route.calls.last.request.url.params
    assert params.get("countries") == "USA,GBR"
    assert params.get("entity_person_list") == "Melanie Perkins"
    assert params.get("naics_code_list") == "5112"
    assert params.get("blacklisted") == "example.com"


# --- core success paths ---

@respx.mock
def test_search_sends_headers_and_query():
    route = respx.get(f"{BASE}/company/search").mock(
        return_value=httpx.Response(200, json={"credits_consumed": 0,
                                               "data": [{"name": "Canva", "uuid": "abc-123"}]})
    )
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "search", "Canva", "--json"])
    assert res.exit_code == 0
    assert '"uuid": "abc-123"' in res.stdout
    req = route.calls.last.request
    assert req.headers.get("x-api-key") == "wk_dummy"
    assert req.headers.get("x-client-source", "").startswith("AKTA-CLI/")
    assert req.url.params.get("query") == "Canva"


@respx.mock
def test_account():
    respx.get(f"{BASE}/mcp/account").mock(
        return_value=httpx.Response(200, json={"is_enterprise": False, "package_type": "top_up",
                                               "credit_balance": 42.5, "currency": "USD",
                                               "credits_consumed": 0})
    )
    res = runner.invoke(app, ["--api-key", "wk_dummy", "account", "--json"])
    assert res.exit_code == 0
    assert '"package_type": "top_up"' in res.stdout


# --- news group ---

@respx.mock
def test_news_signals_compact_and_sends_type_list():
    route = respx.get(f"{BASE}/news").mock(
        return_value=httpx.Response(200, json={"total": 1, "credits_consumed": 0.11,
                                               "data": [{"id": 7, "title": "T", "url": "u",
                                                         "full_text": "LONG BODY", "industries": ["x"]}]})
    )
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals", "--query", "oil",
                              "-t", "SD01", "-t", "CM03", "--json"])
    assert res.exit_code == 0
    assert "LONG BODY" not in res.stdout            # bodies never in the list
    assert '"id": 7' in res.stdout
    params = route.calls.last.request.url.params
    assert params.get("type_list") == "SD01,CM03"
    assert params.get("full_text") == "false"


@respx.mock
def test_news_signals_full_keeps_metadata_not_body():
    respx.get(f"{BASE}/news").mock(
        return_value=httpx.Response(200, json={"total": 1, "credits_consumed": 0.11,
                                               "data": [{"id": 7, "title": "T", "full_text": "BODY",
                                                         "industries": ["fintech"]}]})
    )
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals", "--query", "x", "--full", "--json"])
    assert res.exit_code == 0
    assert "fintech" in res.stdout      # extra metadata present with --full
    assert "BODY" not in res.stdout     # ...but never the body


@respx.mock
def test_news_detail_fetches_bodies():
    route = respx.get(f"{BASE}/news/by-id/").mock(
        return_value=httpx.Response(200, json={"count": 2, "credits_consumed": 0.12,
                                               "data": [{"id": 7, "full_text": "BODY"}]})
    )
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "detail", "7", "8", "--json"])
    assert res.exit_code == 0
    assert '"full_text": "BODY"' in res.stdout
    assert route.calls.last.request.url.params.get("news_ids") == "7,8"


def _render(renderable) -> str:
    import io

    from rich.console import Console
    buf = io.StringIO()
    Console(file=buf, width=200, force_terminal=False).print(renderable)
    return buf.getvalue()


def test_news_detail_reader_shows_body():
    from akta_cli.commands.news import _detail_view
    view = _detail_view({"data": [{"id": 7, "title": "T", "publisher": "Reuters",
                                   "full_text": "THE FULL ARTICLE BODY.", "url": "http://x"}]})
    text = _render(view)
    assert "THE FULL ARTICLE BODY." in text
    assert "Reuters" in text


def test_news_detail_reader_falls_back_when_body_empty():
    from akta_cli.commands.news import _detail_view
    view = _detail_view({"data": [{"id": 7, "title": "T", "full_text": "",
                                   "ai_summary": "SHORT SUMMARY", "url": "http://src"}]})
    text = _render(view)
    assert "unavailable" in text.lower()
    assert "SHORT SUMMARY" in text     # falls back to the AI summary
    assert "http://src" in text        # ...and points at the source


def test_news_types_offline_no_key():
    # Free + offline: no key needed, no network hit.
    res = runner.invoke(app, ["news", "types", "--json"])
    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["count"] == 77
    assert any(t["code"] == "CM03" for cat in data["categories"] for t in cat["codes"])


# --- error → exit-code mapping ---

@respx.mock
def test_403_maps_to_exit_3():
    respx.get(f"{BASE}/company/headcount-trends").mock(
        return_value=httpx.Response(403, json={"detail": "plan does not cover this"}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "headcount", "canva.com"])
    assert res.exit_code == 3


@respx.mock
def test_400_maps_to_exit_2():
    respx.get(f"{BASE}/company/enrichment/concise").mock(
        return_value=httpx.Response(400, json={"detail": "bad company"}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "concise", "???"])
    assert res.exit_code == 2


@respx.mock
def test_company_data_defaults_to_json_endpoint():
    # No --markdown → the structured JSON endpoint, emitted as JSON.
    route = respx.get(f"{BASE}/company/enrichment").mock(
        return_value=httpx.Response(200, json={
            "data": {"uuid": "abc-123", "firmographic": {"name": "Canva"}},
            "credits_consumed": 2.0,
        }))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "data", "canva.com",
                              "-s", "firmographic", "--json"])
    assert res.exit_code == 0
    assert route.called
    assert route.calls.last.request.url.params.get("sections") == "firmographic"
    assert '"firmographic"' in res.stdout  # JSON body, not Markdown


@respx.mock
def test_markdown_passthrough_with_raw():
    respx.get(f"{BASE}/company/enrichment/markdown").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/markdown"},
                                    text="# Canva\n\nDesign platform."))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "data", "canva.com",
                              "-s", "firmographic", "--markdown", "--raw"])
    assert res.exit_code == 0
    assert res.stdout.strip().startswith("# Canva")


@respx.mock
def test_company_data_envelope_appends_credits_footer():
    # Real server shape: a JSON envelope {data: markdown, sections_included,
    # credits_consumed, …}. `company data` unwraps `data` and appends an in-body
    # footer with credits + sections (mirrors the MCP) so it survives --raw, -o,
    # and piping. Regression for credits going missing on `company data`.
    respx.get(f"{BASE}/company/enrichment/markdown").mock(
        return_value=httpx.Response(200, json={
            "data": "# Canva\n\nDesign platform.",
            "uuid": "abc-123",
            "sections_included": ["firmographic"],
            "credits_consumed": 2.0,
        }))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "data", "canva.com",
                              "-s", "firmographic", "--markdown", "--raw"])
    assert res.exit_code == 0
    assert res.stdout.strip().startswith("# Canva")  # markdown body unwrapped
    assert '"data"' not in res.stdout                # envelope itself never printed
    assert "Credits consumed: 2.0" in res.stdout     # in the Markdown, not stderr
    assert "Sections included: firmographic" in res.stdout


@respx.mock
def test_company_data_footer_survives_output_file(tmp_path):
    respx.get(f"{BASE}/company/enrichment/markdown").mock(
        return_value=httpx.Response(200, json={"data": "# Canva", "credits_consumed": 2.0}))
    dest = tmp_path / "canva.md"
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "data", "canva.com",
                              "-s", "firmographic", "--markdown", "-o", str(dest)])
    assert res.exit_code == 0
    assert "Credits consumed: 2.0" in dest.read_text()  # persisted to the file


@respx.mock
def test_enterprise_section_skipped_for_non_enterprise():
    # tier probe says non-enterprise → mna_and_investment dropped, firmographic kept
    respx.get(f"{BASE}/mcp/account").mock(
        return_value=httpx.Response(200, json={"is_enterprise": False}))
    route = respx.get(f"{BASE}/company/enrichment/markdown").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/markdown"}, text="# Canva"))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "data", "canva.com",
                              "-s", "firmographic", "-s", "mna_and_investment", "--markdown", "--raw"])
    assert res.exit_code == 0
    assert route.calls.last.request.url.params.get("sections") == "firmographic"


# --- base URL override ---

@respx.mock
def test_base_url_flag_overrides_host():
    route = respx.get("http://local.test/api/v1/company/search").mock(
        return_value=httpx.Response(200, json={"credits_consumed": 0, "data": []}))
    res = runner.invoke(app, ["--base-url", "http://local.test/api/v1", "--api-key", "wk_dummy",
                              "company", "search", "Canva", "--json"])
    assert res.exit_code == 0
    assert route.called


@respx.mock
def test_stored_base_url_used_when_no_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_credentials({"api_key": "wk_stored", "base_url": "http://local.test/api/v1"})
    route = respx.get("http://local.test/api/v1/company/search").mock(
        return_value=httpx.Response(200, json={"credits_consumed": 0, "data": []}))
    res = runner.invoke(app, ["company", "search", "Canva", "--json"],
                        env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    assert route.called
    assert route.calls.last.request.headers.get("x-api-key") == "wk_stored"


# --- update / version-check ---

def test_version_parsing_and_is_newer():
    assert _upd.parse_version("1.2.3") == (1, 2, 3)
    assert _upd.is_newer("0.2.0", "0.1.0")
    assert not _upd.is_newer("0.1.0", "0.1.0")
    assert not _upd.is_newer("0.1.0", "0.2.0")


def test_update_up_to_date(tmp_path, monkeypatch):
    monkeypatch.setattr("akta_cli.update.latest_tag", lambda timeout=5.0: __version__)
    res = runner.invoke(app, ["update"], env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    assert "up to date" in res.stdout


def test_update_available_check_only(tmp_path, monkeypatch):
    monkeypatch.setattr("akta_cli.update.latest_tag", lambda timeout=5.0: "99.0.0")
    res = runner.invoke(app, ["update", "--check"], env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    assert "Update available" in res.stdout
    assert "pipx install --force" in res.stdout  # shows the command, does not run it


def test_update_unreachable_exits_4(tmp_path, monkeypatch):
    monkeypatch.setattr("akta_cli.update.latest_tag", lambda timeout=5.0: None)
    res = runner.invoke(app, ["update"], env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 4


# --- config / partial credential updates ---

def test_config_base_url_set_keeps_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_credentials({"api_key": "wk_keep", "base_url": "https://api.akta.pro/api/v1"})
    res = runner.invoke(app, ["config", "base-url", "https://example.test/api/v1"],
                        env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    creds = load_credentials()
    assert creds["api_key"] == "wk_keep"                       # key untouched
    assert creds["base_url"] == "https://example.test/api/v1"  # url changed


def test_config_base_url_reset_keeps_key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_credentials({"api_key": "wk_keep", "base_url": "https://example.test/api/v1"})
    res = runner.invoke(app, ["config", "base-url", "--reset"],
                        env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    creds = load_credentials()
    assert creds["api_key"] == "wk_keep"       # key untouched
    assert "base_url" not in creds             # reset → falls back to default


@respx.mock
def test_login_base_url_only_keeps_stored_key_no_prompt(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    save_credentials({"api_key": "wk_stored", "base_url": "https://api.akta.pro/api/v1"})
    respx.get("http://local.test/api/v1/company/search").mock(
        return_value=httpx.Response(200, json={"data": []}))
    # empty stdin: if it tried to prompt, key would be blank -> exit 2. It must NOT prompt.
    res = runner.invoke(app, ["login", "--base-url", "http://local.test/api/v1"],
                        env={"XDG_CONFIG_HOME": str(tmp_path)}, input="")
    assert res.exit_code == 0, res.output
    creds = load_credentials()
    assert creds["api_key"] == "wk_stored"                      # kept the stored key
    assert creds["base_url"] == "http://local.test/api/v1"      # updated the URL


@respx.mock
def test_login_stores_credentials_json(tmp_path):
    # login accepts a LOCAL --base-url and validates against it, then persists JSON.
    respx.get("http://local.test/api/v1/company/search").mock(
        return_value=httpx.Response(200, json={"data": []}))
    res = runner.invoke(app, ["login", "--api-key", "wk_test", "--base-url", "http://local.test/api/v1"],
                        env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    cred = tmp_path / "akta" / "credentials.json"
    assert cred.exists()
    data = json.loads(cred.read_text())
    assert data == {"api_key": "wk_test", "base_url": "http://local.test/api/v1"}
