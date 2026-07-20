# Installing the Akta CLI

The `akta` command-line client for the Akta API. Published on
[PyPI](https://pypi.org/project/akta-cli/).

## Prerequisites

- **Python 3.11+** — check with `python3 --version`.
- **pipx** (recommended) — installs the CLI in its own isolated environment and
  puts `akta` on your PATH:
  ```bash
  brew install pipx            # macOS
  # or: python3 -m pip install --user pipx
  pipx ensurepath              # then restart your shell
  ```

## Install

### A. With pipx (recommended)

```bash
pipx install akta-cli
```

### B. Plain pip into a virtualenv (if you don't use pipx)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install akta-cli
```

### C. From source (for development)

```bash
git clone https://github.com/Wokelo-AI/Akta-CLI && cd Akta-CLI
pip install -e .
```

## Authenticate

Get an API key at <https://playground.akta.pro> → **API Keys** (shown once).

```bash
akta login                     # prompts for the key (hidden input)
# or non-interactive:
akta login --api-key wk_xxxxxxxx
```

To point at a **non-default endpoint**, pass `--base-url` once — it's persisted,
so every later command follows:

```bash
akta login --api-key wk_xxxxxxxx --base-url https://your-endpoint.example.com/api/v1
```

The key + base URL are stored at `~/.config/akta/credentials.json` (mode `0600`;
`%APPDATA%\akta\` on Windows). Instead of `login` you can also use env vars:
`export AKTA_API_KEY=wk_xxxxxxxx` (and optionally `AKTA_API_BASE_URL=...`).

To **switch endpoints later without re-entering your key**:

```bash
akta config base-url https://your-endpoint.example.com/api/v1   # change it (keeps your key)
akta config base-url --reset                                    # back to the default (api.akta.pro)
akta config show                                                # see the stored key (masked) + URL
```
(Equivalently, `akta login --base-url <url>` now keeps your stored key too.)

## Verify

```bash
akta --version
akta whoami                    # shows the active key (masked), endpoint, and validates it
akta account                   # plan tier + credit balance (free)
akta company search "Canva"    # free
```

## Update

```bash
pipx upgrade akta-cli          # pipx install
# or, for a pip/venv install:
pip install --upgrade akta-cli
```

Released versions are listed on [PyPI](https://pypi.org/project/akta-cli/#history).

## Uninstall

```bash
pipx uninstall akta-cli
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `akta: command not found` | Run `pipx ensurepath`, then restart your shell. |
| Exit code `3` on a command | No/invalid key or plan gating. Check `akta whoami` and `akta account`. |
| A call times out (exit `5`) | Some endpoints can be slow on dev — raise it: `akta --timeout 120 <command>`. |
| Need all options | `akta --help`, `akta <command> --help`. |

## Command reference

See the [README](README.md) for the full command list, output formats (`--json`,
`-o`, tables/Markdown), and exit codes.
