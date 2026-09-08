# Installing the akta.pro CLI

The `akta-pro` command-line client for the akta.pro API. Published on
[PyPI](https://pypi.org/project/akta-pro-cli/).

## Prerequisites

- **Python 3.11+** — check with `python3 --version`.
- **pipx** (recommended) — installs the CLI in its own isolated environment and
  puts `akta-pro` on your PATH:
  ```bash
  brew install pipx            # macOS
  # or: python3 -m pip install --user pipx
  pipx ensurepath              # then restart your shell
  ```

## Install

### A. With pipx (recommended)

```bash
pipx install akta-pro-cli
```

### B. Plain pip into a virtualenv (if you don't use pipx)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install akta-pro-cli
```

### C. From source (for development)

```bash
git clone https://github.com/Wokelo-AI/akta-pro-cli && cd akta-pro-cli
pip install -e .
```

## Authenticate

Get an API key at <https://playground.akta.pro> → **API Keys** (shown once).

```bash
akta-pro login                     # prompts for the key (hidden input)
# or non-interactive:
akta-pro login --api-key wk_xxxxxxxx
```

To point at a **non-default endpoint**, pass `--base-url` once — it's persisted,
so every later command follows:

```bash
akta-pro login --api-key wk_xxxxxxxx --base-url https://your-endpoint.example.com/api/v1
```

The key + base URL are stored at `~/.config/akta-pro/credentials.json` (mode `0600`;
`%APPDATA%\akta-pro\` on Windows). Instead of `login` you can also use env vars:
`export AKTA_PRO_API_KEY=wk_xxxxxxxx` (and optionally `AKTA_PRO_API_BASE_URL=...`).

To **switch endpoints later without re-entering your key**:

```bash
akta-pro config base-url https://your-endpoint.example.com/api/v1   # change it (keeps your key)
akta-pro config base-url --reset                                    # back to the default (api.akta.pro)
akta-pro config show                                                # see the stored key (masked) + URL
```
(Equivalently, `akta-pro login --base-url <url>` now keeps your stored key too.)

## Verify

```bash
akta-pro --version
akta-pro whoami                    # shows the active key (masked), endpoint, and validates it
akta-pro account                   # plan tier + credit balance (free)
akta-pro company search "Canva"    # free
```

## Update

```bash
pipx upgrade akta-pro-cli          # pipx install
# or, for a pip/venv install:
pip install --upgrade akta-pro-cli
```

Released versions are listed on [PyPI](https://pypi.org/project/akta-pro-cli/#history).

## Uninstall

```bash
pipx uninstall akta-pro-cli
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `akta-pro: command not found` | Run `pipx ensurepath`, then restart your shell. |
| Exit code `3` on a command | No/invalid key or plan gating. Check `akta-pro whoami` and `akta-pro account`. |
| A call times out (exit `5`) | Some endpoints can be slow — raise it: `akta-pro --timeout 120 <command>`. |
| Need all options | `akta-pro --help`, `akta-pro <command> --help`. |

## Command reference

See the [README](README.md) for the full command list, output formats (`--json`,
`-o`, tables/Markdown), and exit codes.
