"""Tests for the `akta-pro` CLI (src/akta_pro_cli).

Self-contained and network-free: drives the real Typer app via CliRunner with
the HTTP layer mocked by respx. Run just these with:

    pytest tests/test_akta_pro_cli.py

(The rest of tests/ is stale template debris — see tests/CLAUDE.md.)
"""

import json
import sys

import httpx
import respx
from typer.testing import CliRunner

from akta_pro_cli import __version__
from akta_pro_cli import update as _upd
from akta_pro_cli.app import app
from akta_pro_cli.config import load_credentials, save_credentials

runner = CliRunner()
BASE = "https://api.akta.pro/api/v1"


# --- auth / input validation (no network) ---

def test_no_key_exits_3(tmp_path):
    res = runner.invoke(app, ["company", "search", "Canva"],
                        env={"XDG_CONFIG_HOME": str(tmp_path), "AKTA_PRO_API_KEY": ""})
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


@respx.mock
def test_news_signals_forwards_primary_company():
    route = respx.get(f"{BASE}/news").mock(
        return_value=httpx.Response(200, json={"total": 0, "count": 0,
                                               "credits_consumed": 0.1, "data": []}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals",
                              "--primary-company", "canva.com", "--json"])
    assert res.exit_code == 0
    params = route.calls.last.request.url.params
    assert params.get("primary_company") == "canva.com"
    assert "company" not in params


@respx.mock
def test_news_signals_group_articles_uses_unique_article_key():
    """The API names this filter `unique_article`; sending `group_articles`
    was silently ignored and returned ungrouped results."""
    route = respx.get(f"{BASE}/news").mock(
        return_value=httpx.Response(200, json={"total": 0, "count": 0,
                                               "credits_consumed": 0.1, "data": []}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals",
                              "--company", "canva.com", "--group-articles", "--json"])
    assert res.exit_code == 0
    params = route.calls.last.request.url.params
    assert params.get("unique_article") == "true"
    assert "group_articles" not in params


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
    assert req.headers.get("x-client-source", "").startswith("AKTA-PRO-CLI/")
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


# --- industry / region ---

@respx.mock
def test_industry_search_forwards_level():
    route = respx.get(f"{BASE}/industry/search").mock(
        return_value=httpx.Response(200, json={"credits_consumed": 0, "data": []}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "industry", "search", "fintech",
                              "--level", "l2", "--level", "l3", "--json"])
    assert res.exit_code == 0
    assert route.calls.last.request.url.params.get("level") == "l2,l3"


@respx.mock
def test_region_search():
    respx.get(f"{BASE}/region/search").mock(
        return_value=httpx.Response(200, json={"credits_consumed": 0,
                                               "data": [{"code": "150", "name": "Europe"}]}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "region", "search", "europe", "--json"])
    assert res.exit_code == 0
    assert '"code": "150"' in res.stdout


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
    from akta_pro_cli.commands.news import _detail_view
    view = _detail_view({"data": [{"id": 7, "title": "T", "publisher": "Reuters",
                                   "full_text": "THE FULL ARTICLE BODY.", "url": "http://x"}]})
    text = _render(view)
    assert "THE FULL ARTICLE BODY." in text
    assert "Reuters" in text


def test_news_detail_reader_falls_back_when_body_empty():
    from akta_pro_cli.commands.news import _detail_view
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


# --- company add / status / list generation ---

@respx.mock
def test_company_add_posts_json_body():
    route = respx.post(f"{BASE}/company/addition-requests").mock(
        return_value=httpx.Response(200, json={"already_exists": False, "request_id": "abc-123",
                                               "status": "pending", "domain": "solios.co",
                                               "credits_consumed": 0}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "company", "add", "Solios", "solios.co", "--json"])
    assert res.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"company_name": "Solios", "website": "solios.co"}
    assert '"request_id": "abc-123"' in res.stdout


@respx.mock
def test_status_fetches_by_request_id():
    route = respx.get(f"{BASE}/status/abc-123").mock(
        return_value=httpx.Response(200, json={"request_id": "abc-123", "request_type": "company_addition",
                                               "detail": {"status": "pending"}}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "status", "abc-123", "--json"])
    assert res.exit_code == 0
    assert route.called
    assert '"status": "pending"' in res.stdout


@respx.mock
def test_list_generate_requires_query_or_filters():
    res = runner.invoke(app, ["--api-key", "wk_dummy", "list", "generate", "companies"])
    assert res.exit_code == 2


def test_list_generate_missing_filters_file_exits_2():
    res = runner.invoke(app, ["--api-key", "wk_dummy", "list", "generate", "companies",
                              "--filters", "@/nonexistent/nope.json"])
    assert res.exit_code == 2
    assert "Cannot read --filters file" in res.output


def test_news_signals_rejects_both_company_flags():
    res = runner.invoke(app, ["--api-key", "wk_dummy", "news", "signals",
                              "--company", "canva.com", "--primary-company", "nvidia.com"])
    assert res.exit_code == 2


@respx.mock
def test_list_generate_with_filters():
    route = respx.post(f"{BASE}/list/generate/companies").mock(
        return_value=httpx.Response(200, json={"data": [], "count": 0, "total_count": 0,
                                               "credits_consumed": 0}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "list", "generate", "companies",
                              "--filters", '{"location.hq.country": "USA"}', "--json"])
    assert res.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body["filters"] == {"location.hq.country": "USA"}
    assert body["query"] is None


@respx.mock
def test_list_filters():
    respx.get(f"{BASE}/filters/list").mock(
        return_value=httpx.Response(200, json={"count": 1, "usage": "...", "filters": [
            {"filter": "firmographic.company_type", "value_shape": "string | list[string]",
             "description": "...", "how_to_get_values": "look up with /list/options/",
             "dropdown_type": "firmographic.company_type"}]}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "list", "filters", "--json"])
    assert res.exit_code == 0


@respx.mock
def test_list_filter_options():
    route = respx.post(f"{BASE}/filters/options").mock(
        return_value=httpx.Response(200, json={"results": [
            {"dropdown_type": "location.hq.country", "query": None, "count": 1,
             "total_available": 1, "truncated": False,
             "data": [{"label": "United States", "value": "USA"}]}]}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "list", "filter-options",
                              "location.hq.country", "--json"])
    assert res.exit_code == 0
    body = json.loads(route.calls.last.request.content)
    assert body["dropdowns"] == [{"dropdown_type": "location.hq.country", "query": None, "limit": 100}]


@respx.mock
def test_list_filter_builder():
    route = respx.post(f"{BASE}/list/filter-builder").mock(
        return_value=httpx.Response(200, json={"data": {"filters": {"industry.industry": "fintech"}},
                                               "credits_consumed": 2.5}))
    res = runner.invoke(app, ["--api-key", "wk_dummy", "list", "filter-builder",
                              "US fintechs", "--json"])
    assert res.exit_code == 0
    assert json.loads(route.calls.last.request.content) == {"query": "US fintechs"}


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
    monkeypatch.setattr("akta_pro_cli.update.latest_version", lambda timeout=5.0: __version__)
    res = runner.invoke(app, ["update"], env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    assert "up to date" in res.stdout


def test_update_available_check_only(tmp_path, monkeypatch):
    monkeypatch.setattr("akta_pro_cli.update.latest_version", lambda timeout=5.0: "99.0.0")
    monkeypatch.setattr("akta_pro_cli.update.install_method", lambda *a, **k: "pipx")
    monkeypatch.setattr("akta_pro_cli.update.upgrade_command", lambda *a, **k: ["pipx", "upgrade", "akta-pro-cli"])
    res = runner.invoke(app, ["update", "--check"], env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 0
    assert "Update available" in res.stdout
    assert "pipx upgrade akta-pro-cli" in res.stdout  # shows the command, does not run it


def test_update_detects_install_method(monkeypatch):
    monkeypatch.delenv("UV_TOOL_DIR", raising=False)
    monkeypatch.delenv("PIPX_HOME", raising=False)
    site = "/lib/python3.11/site-packages/akta_pro_cli"

    def method(prefix):
        return _upd.install_method(prefix, prefix + site)

    assert method("/home/u/.local/share/uv/tools/akta-pro-cli") == "uv"
    assert method("/home/u/.local/pipx/venvs/akta-pro-cli") == "pipx"
    assert method("/home/u/.local/share/pipx/venvs/akta-pro-cli") == "pipx"
    assert method("/home/u/project/.venv") == "pip"
    # An editable checkout lives outside site-packages: no installer to run.
    assert _upd.install_method("/home/u/project/.venv", "/home/u/project/src/akta_pro_cli") == "source"


def test_upgrade_command_per_install_method(monkeypatch):
    monkeypatch.setattr(_upd, "install_method", lambda *a, **k: "uv")
    assert _upd.upgrade_command() == ["uv", "tool", "upgrade", "akta-pro-cli"]
    monkeypatch.setattr(_upd, "install_method", lambda *a, **k: "pipx")
    assert _upd.upgrade_command() == ["pipx", "upgrade", "akta-pro-cli"]
    monkeypatch.setattr(_upd, "install_method", lambda *a, **k: "pip")
    assert _upd.upgrade_command() == [sys.executable, "-m", "pip", "install", "--upgrade", "akta-pro-cli"]
    monkeypatch.setattr(_upd, "install_method", lambda *a, **k: "source")
    assert _upd.upgrade_command() is None


def test_update_source_checkout_refuses(tmp_path, monkeypatch):
    monkeypatch.setattr("akta_pro_cli.update.latest_version", lambda timeout=5.0: "99.0.0")
    monkeypatch.setattr("akta_pro_cli.update.upgrade_command", lambda *a, **k: None)
    res = runner.invoke(app, ["update", "--yes"], env={"XDG_CONFIG_HOME": str(tmp_path)})
    assert res.exit_code == 4
    assert "source checkout" in res.stderr


def test_update_unreachable_exits_4(tmp_path, monkeypatch):
    monkeypatch.setattr("akta_pro_cli.update.latest_version", lambda timeout=5.0: None)
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
    cred = tmp_path / "akta-pro" / "credentials.json"
    assert cred.exists()
    data = json.loads(cred.read_text())
    assert data == {"api_key": "wk_test", "base_url": "http://local.test/api/v1"}
