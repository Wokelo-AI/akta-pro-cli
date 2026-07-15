# Installing the Akta CLI

The `akta` command-line client for the Akta API. Distributed via tagged
**GitHub Releases** (not yet on a package index).

## Prerequisites

- **Python 3.11+** — check with `python3 --version`.
- **pipx** (recommended) — installs the CLI in its own isolated environment and
  puts `akta` on your PATH:
  ```bash
  brew install pipx            # macOS
  # or: python3 -m pip install --user pipx
  pipx ensurepath              # then restart your shell
  ```
- **Read access** to `github.com/Wokelo-AI/Akta-CLI` (for the git-install
  method). The wheel-download method only needs the downloaded file.

## Install

Pick one method.

### A. From the tagged release via pipx (recommended)

```bash
pipx install "git+https://github.com/Wokelo-AI/Akta-CLI@v0.2.1"
```

Because the repo is private, git needs GitHub credentials. Easiest options:
- GitHub CLI: `gh auth login` (then the command above just works), or
- a Personal Access Token with `repo` read scope configured in your git
  credential helper.

If you can't set up git auth, use method B instead.

### B. From the downloaded wheel (no git auth needed)

1. Open <https://github.com/Wokelo-AI/Akta-CLI/releases/tag/v0.2.1>
2. Download `akta_cli-0.2.1-py3-none-any.whl` from the **Assets**.
3. Install it:
   ```bash
   pipx install ./akta_cli-0.2.1-py3-none-any.whl
   ```

### C. Plain pip into a virtualenv (if you don't use pipx)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install "git+https://github.com/Wokelo-AI/Akta-CLI@v0.2.1"
```

## Authenticate

Get an API key at <https://playground.akta.pro> → **API Keys** (shown once).

```bash
akta login                     # prompts for the key (hidden input)
# or non-interactive:
akta login --api-key wk_xxxxxxxx
```

To point at a **non-default endpoint** (staging, self-hosted, etc.), pass
`--base-url` once — it's persisted, so every later command follows (ask your
team for the endpoint URL):

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

Reinstall the version you want with `--force`:

```bash
pipx install --force "git+https://github.com/Wokelo-AI/Akta-CLI@v0.2.1"
```

> Note: `pipx upgrade akta-cli` is a **no-op** for a tag-pinned install — always
> reinstall the new tag with `--force`. Available versions are on the
> [Releases page](https://github.com/Wokelo-AI/Akta-CLI/releases).

## Uninstall

```bash
pipx uninstall akta-cli
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `akta: command not found` | Run `pipx ensurepath`, then restart your shell. |
| Auth error cloning the private repo | Set up `gh auth login` or a PAT with `repo` read — or use the wheel (method B). |
| Exit code `3` on a command | No/invalid key or plan gating. Check `akta whoami` and `akta account`. |
| A call times out (exit `5`) | Some endpoints can be slow on dev — raise it: `akta --timeout 120 <command>`. |
| Need all options | `akta --help`, `akta <command> --help`. |

## Command reference

See the [README](README.md) for the full command list, output formats (`--json`,
`-o`, tables/Markdown), and exit codes.
