# Akta CLI (`akta`)

A command-line client for the Akta REST API (`https://api.akta.pro/api/v1`) — a
sibling of the Akta MCP server. Both are thin clients over the same endpoints;
the CLI is the presentation layer for humans and shell scripts. It ships as its
own self-contained distribution (`akta-cli`) with no MCP-server code.

Source: [`src/akta_cli/`](src/akta_cli). API reference: <https://docs.akta.pro>.

## Install

Distributed via tagged **GitHub Releases**. Quickest path (needs read access to
the private repo):

```bash
pipx install "git+https://github.com/Wokelo-AI/Akta-CLI@v0.2.1"
```

Or download the wheel from the [latest release](https://github.com/Wokelo-AI/Akta-CLI/releases)
and `pipx install ./akta_cli-*.whl`. Full prerequisites, auth, update, and
troubleshooting steps are in **[INSTALL.md](INSTALL.md)**.

The `akta` command depends only on `httpx`, `typer`, `rich`. A package-index
release (PyPI / private feed), standalone binary, and Homebrew tap are on the
roadmap.

## Authentication

v1 authenticates with an Akta API key (`wk_...`), minted at
<https://playground.akta.pro> (sign up → **API Keys**). Three ways to supply it,
in precedence order:

```bash
akta --api-key wk_...  company search Canva     # 1. explicit flag
export AKTA_API_KEY=wk_...                       # 2. environment variable
akta login                                       # 3. stored (prompts, or --api-key)
```

`akta login` validates the key against a free endpoint and stores it at
`~/.config/akta/credentials.json` (mode 0600; `%APPDATA%\akta` on Windows).

```bash
akta login --api-key wk_...   # store without the prompt
akta whoami                   # show the active key (masked), its source, and validate
akta logout                   # remove the stored key
```

> **Browser / device OAuth** (`akta login` with no key) is planned for v2. It
> depends on the Akta backend exposing a public/native OAuth client — today's
> OAuth is a confidential client whose secret a CLI can't embed. Until then, use
> an API key.

### Overriding the API endpoint (local / dev testing)

The default endpoint is `https://api.akta.pro/api/v1`. Override it three ways
(precedence: flag → env → stored → default):

```bash
akta --base-url http://localhost:8000/api/v1 company search Canva   # per command
export AKTA_API_BASE_URL=http://localhost:8000/api/v1               # per shell
akta login --api-key wk_test --base-url http://localhost:8000/api/v1  # persist it
```

After `akta login --base-url …`, every later command targets that endpoint until
you `akta login` again or pass `--base-url`. `akta whoami` prints the endpoint in
effect.

## Commands

| Command | Endpoint | Cost | Notes |
|---|---|---|---|
| `akta account` | `/mcp/account` | free | your tier + credit balance |
| `akta company search <query>` | `/company/search` | free | run first; returns `uuid` |
| `akta company data <company> -s ...` | `/company/enrichment` (JSON; `--markdown` → `/company/enrichment/markdown`) | per section | requires ≥1 `--section` |
| `akta company concise <company>` | `/company/enrichment/concise` | 8 | slimmed JSON |
| `akta industry search <query>` | `/industry/search` | free | codes feed `news signals --industry` |
| `akta news signals [filters]` | `/news` | 0.1 + 0.01/article | anchor with `--company/--industry/--query/--title` (all optional); rich filters (`--country`, `--entity-*`, `--naics/--sic/--iptc/--iab`, `--blacklist`); compact list with `id`s |
| `akta news detail <id>...` | `/news/by-id/` | 0.1 + 0.01/article | full bodies for ids from `signals` (max 10) |
| `akta news types` | none (embedded) | free | tag codes for `--type-code`; offline, no key |
| `akta headcount <company>` | `/company/headcount-trends` | 2.5 | Subscription/Enterprise |
| `akta traffic <company>` | `/company/website-traffic` | 1.5 | Subscription/Enterprise |
| `akta jobs <company>` | `/company/jobs` | 3 | Subscription/Enterprise |
| `akta posts <company>` | `/company/posts` | 1.5 | Subscription/Enterprise |
| `akta reviews employees <company>` | `/company/employee-reviews` | 1.5/50 | Subscription/Enterprise; `-n/--limit` max 100 |
| `akta reviews products <company>` | `/company/product-reviews` | 1.5/50 | catalog first, then `--product-id`; `-n/--limit` max 50 per product |

`company data` sections (each billed separately): `firmographic`,
`business_model`, `company_assessment`, `trust_signal`, `company_hierarchy`,
`digital_presence`, `financial_estimate`, `location`, `management_profile`,
`product_offering`, `strategic_signal`, `customer_profile`, `industry`,
`technology`, plus enterprise-only `funding_detail` (3) and `mna_and_investment`
(5). There is no "all" — choose explicitly. The two enterprise sections are
auto-skipped (not an error) for non-enterprise callers, with a note.

Run `akta <command> --help` for every flag.

### Examples

```bash
akta account                                                  # check tier + credits
akta company search "Canva"
akta company data canva.com -s firmographic -s technology     # rendered Markdown
akta company data canva.com -s firmographic --raw             # raw Markdown (pipe/save)
akta industry search "warehouse automation"
akta news types                                               # find type codes
akta news signals --company canva.com -t SD01 -n 20           # product-launch news
akta news signals --query "crude oil prices" --json | jq '.data[].id'
akta news detail 12345 12346                                  # full bodies for those ids
akta headcount canva.com
akta reviews products canva.com                               # list catalog + ids
akta reviews products canva.com --product-id p_123 -n 50
```

## Output & exit codes

- **Default (TTY):** a Rich table for list results (search, industry, news),
  rendered Markdown for `company data`, and pretty-printed JSON for nested
  objects.
- **`--json`:** clean, unstyled JSON on **stdout** (valid for `| jq`). Applied
  automatically when stdout is piped/redirected. For `company data`, `--json`
  (alias `--raw`) emits the raw Markdown.
- **`-o/--output FILE`:** writes the raw JSON/text payload to a file.
- **`credits_consumed`** is printed to **stderr** (silence with `-q/--quiet`),
  so it never pollutes piped JSON.

Exit codes: `0` success · `2` bad input · `3` auth (no/invalid key, plan gating
403) · `4` other API/network error · `5` timeout.

## Caveats

- `company data` (`/enrichment/markdown`) and `company concise`
  (`/enrichment/concise`) are available where deployed; on environments that
  don't have them yet they return `404`.
- Alternative signals (headcount/traffic/jobs/posts/reviews) require
  Subscription or Enterprise; Pay-as-you-go returns `403` → exit `3`.

## Roadmap

- **v2 — OAuth:** `akta login` browser flow + `--device` (needs the backend
  public/native client).
- **v3 — packaging breadth:** standalone binary + `curl … | sh` installer,
  Homebrew tap (`brew install akta/tap/akta`), npm wrapper, and `akta update`.
