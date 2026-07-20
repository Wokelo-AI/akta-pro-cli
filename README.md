# akta.pro CLI (`akta-pro`)

A command-line client for the akta.pro REST API (`https://api.akta.pro/api/v1`) — a
sibling of the akta.pro MCP server. Both are thin clients over the same endpoints;
the CLI is the presentation layer for humans and shell scripts. It ships as its
own self-contained distribution (`akta-pro-cli`) with no MCP-server code.

Source: [`src/akta_pro_cli/`](src/akta_pro_cli). API reference: <https://docs.akta.pro>.

## Install

Published on [PyPI](https://pypi.org/project/akta-pro-cli/). Install with `pipx`
(recommended for CLIs — isolated env) or `pip`:

```bash
pipx install akta-pro-cli
# or
pip install akta-pro-cli
```

Then run `akta-pro --help`. Full prerequisites, auth, update, and troubleshooting
steps are in **[INSTALL.md](INSTALL.md)**.

The `akta-pro` command depends only on `httpx`, `typer`, `rich`.

## Authentication

v1 authenticates with an akta.pro API key (`wk_...`), minted at
<https://playground.akta.pro> (sign up → **API Keys**). Three ways to supply it,
in precedence order:

```bash
akta-pro --api-key wk_...  company search Canva     # 1. explicit flag
export AKTA_PRO_API_KEY=wk_...                       # 2. environment variable
akta-pro login                                       # 3. stored (prompts, or --api-key)
```

`akta-pro login` validates the key against a free endpoint and stores it at
`~/.config/akta-pro/credentials.json` (mode 0600; `%APPDATA%\akta-pro` on Windows).

```bash
akta-pro login --api-key wk_...   # store without the prompt
akta-pro whoami                   # show the active key (masked), its source, and validate
akta-pro logout                   # remove the stored key
```

## Commands

| Command | Cost | Notes |
|---|---|---|
| `akta-pro account` | free | your tier + credit balance |
| `akta-pro company search <query>` | free | run first; returns `uuid` |
| `akta-pro company data <company> -s ...` | per section | requires ≥1 `--section`; `--markdown` for a rendered report |
| `akta-pro company concise <company>` | 8 | slimmed JSON |
| `akta-pro industry search <query>` | free | codes feed `news signals --industry` |
| `akta-pro news signals [filters]` | 0.1 + 0.01/article | anchor with `--company/--industry/--query/--title` (all optional); rich filters (`--country`, `--entity-*`, `--naics/--sic/--iptc/--iab`, `--blacklist`); compact list with `id`s |
| `akta-pro news detail <id>...` | 0.1 + 0.01/article | full bodies for ids from `signals` (max 10) |
| `akta-pro news types` | free | tag codes for `--type-code`; offline, no key |
| `akta-pro headcount <company>` | 2.5 | Subscription/Enterprise |
| `akta-pro traffic <company>` | 1.5 | Subscription/Enterprise |
| `akta-pro jobs <company>` | 3 | Subscription/Enterprise |
| `akta-pro posts <company>` | 1.5 | Subscription/Enterprise |
| `akta-pro reviews employees <company>` | 1.5/50 | Subscription/Enterprise; `-n/--limit` max 100 |
| `akta-pro reviews products <company>` | 1.5/50 | catalog first, then `--product-id`; `-n/--limit` max 50 per product |

`company data` sections (each billed separately): `firmographic`,
`business_model`, `company_assessment`, `trust_signal`, `company_hierarchy`,
`digital_presence`, `financial_estimate`, `location`, `management_profile`,
`product_offering`, `strategic_signal`, `customer_profile`, `industry`,
`technology`, plus enterprise-only `funding_detail` (3) and `mna_and_investment`
(5). There is no "all" — choose explicitly. The two enterprise sections are
auto-skipped (not an error) for non-enterprise callers, with a note.

Run `akta-pro <command> --help` for every flag.

### Examples

```bash
akta-pro account                                                  # check tier + credits
akta-pro company search "Canva"
akta-pro company data canva.com -s firmographic -s technology     # rendered Markdown
akta-pro company data canva.com -s firmographic --raw             # raw Markdown (pipe/save)
akta-pro industry search "warehouse automation"
akta-pro news types                                               # find type codes
akta-pro news signals --company canva.com -t SD01 -n 20           # product-launch news
akta-pro news signals --query "crude oil prices" --json | jq '.data[].id'
akta-pro news detail 12345 12346                                  # full bodies for those ids
akta-pro headcount canva.com
akta-pro reviews products canva.com                               # list catalog + ids
akta-pro reviews products canva.com --product-id p_123 -n 50
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
