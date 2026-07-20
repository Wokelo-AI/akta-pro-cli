# Changelog

All notable changes to the Akta CLI are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versions follow SemVer.

## [0.2.5]

### Changed
- Docs: install instructions now cover the PyPI release (`pipx install akta-cli`
  / `pip install akta-cli`), and the project homepage points to
  <https://akta.pro/>. Trimmed roadmap/dev-only wording from the README.

## [0.2.4]

### Changed
- Relicensed under the **MIT License** (was proprietary) and removed the
  `Private :: Do Not Upload` classifier — the CLI is now published to PyPI and
  installable with `pip install akta-cli`.

## [0.2.3]

### Changed
- `company data` now returns **structured JSON** from `/company/enrichment` by
  default; pass `-m`/`--markdown` for the server-rendered Markdown variant
  (`/company/enrichment/markdown`). Both build — and bill — identical sections.
- Review limits are capped to match the API: `reviews employees --limit` max
  **100**, `reviews products --limit` max **50** per product.

### Added
- `news signals` gains richer filters (all optional, repeatable): `--country`,
  `--blacklist`, `--entity-person/-location/-product/-event`, and
  `--naics/--sic/--iptc/--iab` classification codes.

### Removed
- `news signals` no longer **requires** an anchor — `--company/--industry/
  --query/--title` are all optional now.

## [0.2.2]

### Changed
- The `X-Client-Source` request header now carries the CLI version
  (`AKTA-CLI/<version>`, e.g. `AKTA-CLI/0.2.2`) instead of a bare `AKTA-CLI`, so
  backend traffic can be version-tracked, not just attributed to the CLI. The
  value is single-sourced from `akta_cli.__version__`.

## [0.2.1]

### Changed
- `company data` now appends **credits consumed** (and the sections included) as
  an in-body Markdown footer, mirroring the MCP's `company_data`. Previously the
  credit count was dropped entirely for this command — it now survives rendering,
  `--raw`, piping, and `-o` to a file.
- The default `news signals` compact view now returns **id, title, ai_summary,
  url, published_date, publisher** (dropped `sentiment`). The TTY table shows
  Title, AI summary, and URL. Use `--full` for sentiment and the full per-article
  metadata. (Mirrors the same change in the MCP's `news_signals`.)

### Added
- `news detail` renders a readable **reader view** in a terminal — the article
  `full_text` up top, falling back to the AI summary and source URL when a body
  isn't available. `--json` still returns the complete enrichment payload.

## [0.2.0]

### Added
- `akta update` — checks for a newer release (via the repo's git tags, so it
  works for the private repo with no token) and reinstalls it via pipx;
  `--check` reports only, `-y/--yes` skips the prompt.
- `akta --version` now shows a best-effort "update available" hint (interactive
  only, cached ~daily, printed to stderr).
- `INSTALL.md` — team installation, auth, update, and troubleshooting guide.
- `akta config show` and `akta config base-url <url> | --reset` — change or reset
  the stored base URL without re-entering the API key.

### Changed
- `akta login --base-url <url>` (without `--api-key`) now keeps the stored key
  instead of re-prompting — it just switches the endpoint.
- Release workflow verifies the pushed tag matches `__version__` before
  building, so a mismatched version can't ship.

## [0.1.0]

### Added
- Initial release of the `akta` command — a standalone client over the Akta
  REST API (`https://api.akta.pro/api/v1`), extracted from the Akta MCP repo.
- Commands: `account`; `company search|data|concise`; `industry search`;
  `news signals|detail|types`; `headcount`, `traffic`, `jobs`, `posts`;
  `reviews employees|products`; `login|logout|whoami`.
- Auth via API key (`--api-key`, `AKTA_API_KEY`, or `akta login` → JSON stored
  at `~/.config/akta/credentials.json`, mode 0600).
- Endpoint override via `--base-url`, `AKTA_API_BASE_URL`, or persisted login.
- Global `--json`, `-o/--output`, `--quiet`, `--timeout`; exit codes
  0/2/3/4/5.
