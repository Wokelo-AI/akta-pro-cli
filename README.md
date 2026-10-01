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

**1. Get a key** — sign up at <https://playground.akta.pro>, then **API Keys** → create one (`wk_...`).

**2. Log in** — stores the key locally so every future command just works:

```bash
akta-pro login                    # paste your key when prompted
# or: akta-pro login --api-key wk_...   (skip the prompt)
```

This validates the key against a free endpoint and saves it to
`~/.config/akta-pro/credentials.json` (mode 0600; `%APPDATA%\akta-pro` on Windows).

**3. Verify**, then use any command:

```bash
akta-pro whoami                   # confirms the key is stored and valid
akta-pro company search Canva
```

`akta-pro logout` removes the stored key.

```bash
akta-pro --api-key wk_...  company search Canva     # explicit flag
export AKTA_PRO_API_KEY=wk_...                       # environment variable
```

## Connect to Claude Code

One command sets akta.pro up inside [Claude Code](https://claude.com/claude-code),
with nothing installed first:

```bash
pipx run --spec akta-pro-cli akta-pro connect claude-code
# or, with uv:
uvx --from akta-pro-cli akta-pro connect claude-code
```

To install the CLI and connect in one go, so `akta-pro` stays on your PATH:

```bash
pipx install akta-pro-cli && akta-pro connect claude-code
# or, with uv:
uv tool install akta-pro-cli && akta-pro connect claude-code
```

If this is the first tool pipx or uv has installed, run `pipx ensurepath` (or
`uv tool update-shell`) and restart your shell first, or the second half fails
with `command not found`.

It asks for your API key (get one at
<https://playground.akta.pro/dashboard/manage/api-keys>), or skip the prompt with
`--api-key wk_...`. If the CLI is already installed and logged in, run
`akta-pro connect claude-code` and it uses the stored key.

It does two things:

1. **Installs the akta-pro skill** to `~/.claude/skills/akta-pro/`. The skill
   tells Claude when to use akta.pro and how to keep credit use low. It's downloaded
   from akta.pro's storage, so you always get the latest version.
2. **Registers the akta.pro MCP server** (`https://mcp.akta.pro/mcp`) with your
   key, the same as running
   `claude mcp add --transport http --scope user akta-pro https://mcp.akta.pro/mcp --header "x-api-key: wk_..."`.

Both go to Claude Code's user scope, so they work in every project and the key
stays in `~/.claude.json` on your machine, never in a repo. If the CLI wasn't
logged in yet, the key you entered is saved for it too, as `akta-pro login`
would. An existing login is never changed, and a key from `AKTA_PRO_API_KEY`
isn't written to disk. Then open Claude
Code and ask, for example, *"Tell me about Stripe, recent news and headcount."*

| Flag | Effect |
|---|---|
| `--api-key wk_...` | Use this key instead of the stored one or the prompt |
| `--oauth` | Register without a key; Claude Code asks you to sign in on first use |
| `--skill-only` / `--mcp-only` | Do only one of the two steps |
| `--force` | Reinstall the skill and replace an existing `akta-pro` MCP entry |
| `--launch` | Start `claude` when done |
| `--json` | Print a structured result for scripts |

If `claude` isn't on your PATH, the skill is still installed and the command
prints the `claude mcp add` line to run once Claude Code is installed. Running
`connect` again is safe. It updates the skill only if a newer one has been
published, and leaves an existing server alone unless you pass `--force`.

```bash
akta-pro connect status              # skill version and MCP registration
akta-pro disconnect claude-code      # remove both
```

`disconnect` only deletes a skill folder that `connect` installed. If you
created `~/.claude/skills/akta-pro/` by hand, it is left alone.

## Connect to Codex

The same setup for [OpenAI Codex](https://developers.openai.com/codex), with
the same flags:

```bash
pipx run --spec akta-pro-cli akta-pro connect codex
# or install the CLI and connect in one go:
pipx install akta-pro-cli && akta-pro connect codex
```

1. **Installs the akta-pro skill** to `~/.agents/skills/akta-pro/`, Codex's
   user skills folder.
2. **Adds the akta.pro MCP server** to `~/.codex/config.toml` (or
   `$CODEX_HOME/config.toml`), which the Codex CLI, IDE extension, and desktop
   app share:

   ```toml
   [mcp_servers.akta-pro]
   url = "https://mcp.akta.pro/mcp"
   http_headers = { "x-api-key" = "wk_..." }
   ```

`codex mcp add` can't set the `x-api-key` header, so `connect` writes this
entry itself. The rest of the file is left untouched, and the file is set to
mode 0600 because it now holds your key. If the file isn't valid TOML, or the
entry is written in a form `connect` doesn't edit (such as an inline
`mcp_servers = { … }` table), nothing is changed and you're told to fix it by
hand. With `--oauth` the entry has only the `url`; sign in once with
`codex mcp login akta-pro`. Codex doesn't need to be installed first: the entry
is picked up when it next starts.

```bash
akta-pro disconnect codex            # remove the skill and the config entry
```

## Commands

| Command | Cost | Notes |
|---|---|---|
| `akta-pro connect claude-code` | free | install the skill + register the MCP server in Claude Code ([above](#connect-to-claude-code)) |
| `akta-pro connect codex` | free | the same for Codex ([above](#connect-to-codex)) |
| `akta-pro connect status` / `disconnect <agent>` | free | show / remove that setup |
| `akta-pro account` | free | your tier + credit balance |
| `akta-pro company search <query>` | free | run first; returns `uuid`. `--include-children` also matches subsidiaries/divisions (rows name their parent) |
| `akta-pro company data <company> -s ...` | per section | requires ≥1 `--section`; `--markdown` for a rendered report |
| `akta-pro company concise <company>` | 8 | slimmed JSON |
| `akta-pro company add <name> <website>` | free | submit a missing company; returns `request_id` (or `already_exists`) |
| `akta-pro status <request_id>` | free | poll an async request, e.g. from `company add` |
| `akta-pro industry search <query>` | free | codes feed `news signals --industry` / list filters; `--level l1..l4/all` (repeatable) |
| `akta-pro region search [query]` | free | codes feed list filters; `--level region\|sub-region\|intermediate-region` |
| `akta-pro news signals [filters]` | 0.1 + 0.01/article | anchor with `--company/--primary-company/--industry/--query/--title` (all optional); rich filters (`--country`, `--entity-*`, `--naics/--sic/--iptc/--iab`, `--blacklist`); `-n/--limit` max 100; compact list with `id`s |
| `akta-pro news detail <id>...` | 0.1 + 0.01/article | full bodies for ids from `signals` (max 10) |
| `akta-pro news types` | free | tag codes for `--type-code`; offline, no key |
| `akta-pro list generate companies` | 1.5/call + 0.2/company + sections | `--query` (NL, +2.5 for translation) or `--filters` (JSON/@file), `-s/--section`, `--sort-by/--sort-order`, `-n/--limit`, `--offset` |
| `akta-pro list filters` | free | fields `--filters` accepts, and which have lookup-able values |
| `akta-pro list filter-options <dropdown_type>` | free | allowed values for one filter field; `--query`, `-n/--limit`, `--level` |
| `akta-pro list filter-builder <query>` | 2.5 | translate free text into structured `--filters` JSON for `list generate companies` |
| `akta-pro headcount <company>` | 2.5 | Subscription/Enterprise |
| `akta-pro traffic <company>` | 1.5 | Subscription/Enterprise |
| `akta-pro jobs <company>` | 4/10 returned | Subscription/Enterprise |
| `akta-pro posts <company>` | 1/10 returned | Subscription/Enterprise |
| `akta-pro reviews employees <company>` | 1.5/50 | Subscription/Enterprise; `-n/--limit` max 100 |
| `akta-pro reviews products <company>` | 1.5/50, or 0.5 to list the catalog | catalog first, then `--product-id`; `-n/--limit` max 50 per product |

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
akta-pro company add "Solios" solios.co                           # request a missing company
akta-pro status <request_id>                                      # poll that request
akta-pro list filters                                             # which fields --filters accepts
akta-pro list filter-options location.hq.country                  # -> allowed values for that field
akta-pro list filter-builder "US fintechs founded after 2015"     # -> structured filters
akta-pro list generate companies --filters '{"location.hq.country":"USA"}' -s firmographic
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
