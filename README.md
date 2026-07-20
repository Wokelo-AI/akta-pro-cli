# Akta CLI (`akta`)

A command-line client for the Akta REST API (`https://api.akta.pro/api/v1`) — a
sibling of the Akta MCP server. Both are thin clients over the same endpoints;
the CLI is the presentation layer for humans and shell scripts. It ships as its
own self-contained distribution (`akta-cli`) with no MCP-server code.

Source: [`src/akta_cli/`](src/akta_cli). API reference: <https://docs.akta.pro>.

## Install

Published on [PyPI](https://pypi.org/project/akta-cli/). Install with `pipx`
(recommended for CLIs — isolated env) or `pip`:

```bash
pipx install akta-cli
# or
pip install akta-cli
```

Then run `akta --help`. Full prerequisites, auth, update, and troubleshooting
steps are in **[INSTALL.md](INSTALL.md)**.

The `akta` command depends only on `httpx`, `typer`, `rich`.

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

Exit codes: `0` success · `2` bad input · `3` auth (no/invalid key or `403`) ·
`4` other API/network error · `5` timeout.
