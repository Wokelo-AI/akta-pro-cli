"""`akta-pro connect <target>` / `disconnect <target>` / `connect status`.

Sets akta.pro up inside an AI agent: installs the akta-pro skill and registers
the akta.pro MCP server with the user's API key (or for OAuth). Targets come
from `connectors.registry`, so each new agent is a subcommand automatically.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer
from rich.markup import escape
from typer.core import TyperGroup

from akta_pro_cli.config import load_credentials, save_credentials, stored_api_key
from akta_pro_cli.connectors import registry
from akta_pro_cli.connectors.base import (
    ERROR,
    OK,
    SKIPPED,
    WARNING,
    ConnectOptions,
    Report,
    display_path,
)
from akta_pro_cli.console import err, out
from akta_pro_cli.options import JsonOpt
from akta_pro_cli.runtime import (
    EXIT_API,
    EXIT_AUTH,
    EXIT_BAD_INPUT,
    AppContext,
    resolve_api_key,
    resolve_base_url,
    validate_key,
)

TRY_PROMPT = "Tell me about Stripe, recent news and headcount."
KEYS_URL = "https://playground.akta.pro/dashboard/manage/api-keys"

_ICONS = {OK: "[green]✓[/]", SKIPPED: "[dim]•[/]", WARNING: "[yellow]![/]", ERROR: "[red]✗[/]"}


class TargetGroup(TyperGroup):
    """Lists the supported targets when given one it doesn't know."""

    def resolve_command(self, ctx, args):
        # ctx.fail() raises whichever click Typer runs on (newer Typer vendors it).
        if args and not args[0].startswith("-") and self.get_command(ctx, args[0]) is None:
            ctx.fail(f"Unknown target '{args[0]}'. Supported: {', '.join(registry.names())}.")
        return super().resolve_command(ctx, args)


connect_app = typer.Typer(
    cls=TargetGroup,
    no_args_is_help=True,
    help="Set up akta.pro (skill + MCP server) in an AI agent, e.g. `akta-pro connect claude-code`.",
)
disconnect_app = typer.Typer(
    cls=TargetGroup,
    no_args_is_help=True,
    help="Remove the akta-pro skill and MCP server from an AI agent.",
)


def _print_report(report: Report, heading: str) -> None:
    out.print(heading)
    for step in report.steps.values():
        first, *rest = step.message.splitlines()
        out.print(f"  {_ICONS[step.status]} {escape(first)}", soft_wrap=True)
        for line in rest:
            out.print(f"    {escape(line)}", soft_wrap=True)
    for note in report.notes:
        out.print(f"  [dim]{escape(note)}[/]", soft_wrap=True)


def _interactive() -> bool:
    return sys.stdin.isatty()


def _resolve_key(cfg: AppContext, api_key: str | None, json_out: bool) -> str:
    """The key to register, logging in along the way when none is stored.

    Order matches every other command: --api-key here → global --api-key /
    AKTA_PRO_API_KEY → stored by `akta-pro login`. With none of those, prompt
    in a terminal (so a first-time user needs just this one command); in a
    script, fail the same way other commands do.
    """
    key = (api_key or "").strip()
    given = bool(key)  # typed here (flag or prompt), so worth remembering
    key = key or cfg.api_key or stored_api_key()
    if not key and _interactive() and not json_out:
        err.print(f"No akta.pro API key found. Get one at {KEYS_URL}")
        key = typer.prompt("Paste your akta.pro API key (wk_...)", hide_input=True, err=True).strip()
        given = True
    if not key:
        return resolve_api_key(cfg)  # prints the standard "no key" help and exits 3

    ok, message = validate_key(resolve_base_url(cfg), key)
    if not ok:
        err.print(f"[red]API {message}.[/] Check it with [bold]akta-pro whoami[/].")
        raise typer.Exit(code=EXIT_AUTH)

    # First run: also log the CLI in, so `akta-pro …` commands work afterwards.
    # An existing login is never overwritten here (that's `akta-pro login`), and
    # a key from AKTA_PRO_API_KEY stays in the environment, not on disk.
    if given and not stored_api_key():
        creds = load_credentials()
        creds["api_key"] = key
        creds.setdefault("base_url", resolve_base_url(cfg))
        path = save_credentials(creds)
        if not json_out:
            err.print(f"[green]✓[/] Logged in the akta-pro CLI too ({message}). Stored at {path}")
    return key


def _launch(argv: list[str]) -> None:
    """Hand the terminal to the agent. Replaces this process where the OS can."""
    sys.stdout.flush()
    sys.stderr.flush()
    if os.name == "nt":  # no real exec on Windows: run it, then exit with its code
        raise typer.Exit(code=subprocess.run(argv).returncode)
    os.execvp(argv[0], argv)


def _connect(
    cfg: AppContext,
    target: str,
    *,
    api_key: str | None,
    oauth: bool,
    skill_only: bool,
    mcp_only: bool,
    force: bool,
    launch: bool,
    json_out: bool,
) -> None:
    if skill_only and mcp_only:
        err.print("[red]--skill-only and --mcp-only can't be combined.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    if launch and json_out:
        err.print("[red]--launch can't be combined with --json.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)
    if oauth and api_key:
        err.print("[red]--oauth and --api-key can't be combined.[/]")
        raise typer.Exit(code=EXIT_BAD_INPUT)

    connector = registry.get(target)
    opts = ConnectOptions(api_key=None, oauth=oauth, skill=not mcp_only, mcp=not skill_only, force=force)

    if opts.mcp and not oauth:
        opts.api_key = _resolve_key(cfg, api_key, json_out)

    with err.status(f"Connecting akta.pro to {connector.display_name}…"):
        report = connector.connect(opts)

    if json_out:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_report(report, f"Connecting akta.pro to {connector.display_name}")
        if report.ok:
            out.print(f'Done. Open {connector.display_name} and try: "{TRY_PROMPT}"', soft_wrap=True)

    if not report.ok:
        raise typer.Exit(code=report.exit_code)
    if launch:
        argv = connector.launch_command()
        if argv is None:
            err.print(f"[yellow]Can't launch {connector.display_name}: not found on PATH.[/]")
            raise typer.Exit(code=EXIT_API)
        _launch(argv)


def _make_connect(target: str) -> Callable[..., None]:
    def command(
        ctx: typer.Context,
        api_key: Annotated[
            str | None,
            typer.Option("--api-key", help="akta.pro API key (wk_...). Defaults to the key from `akta-pro login`; prompted for if there is none.", show_default=False),
        ] = None,
        oauth: Annotated[
            bool, typer.Option("--oauth", help="Register the MCP server without a key; sign in through the agent on first use."),
        ] = False,
        skill_only: Annotated[bool, typer.Option("--skill-only", help="Only install the skill.")] = False,
        mcp_only: Annotated[bool, typer.Option("--mcp-only", help="Only register the MCP server.")] = False,
        force: Annotated[
            bool, typer.Option("--force", help="Reinstall the skill and replace an existing MCP server entry."),
        ] = False,
        launch: Annotated[bool, typer.Option("--launch", help="Start the agent when done.")] = False,
        json_out: JsonOpt = False,
    ) -> None:
        _connect(ctx.obj, target, api_key=api_key, oauth=oauth, skill_only=skill_only,
                 mcp_only=mcp_only, force=force, launch=launch, json_out=json_out)

    return command


def _make_disconnect(target: str) -> Callable[..., None]:
    def command(json_out: JsonOpt = False) -> None:
        connector = registry.get(target)
        with err.status(f"Disconnecting akta.pro from {connector.display_name}…"):
            report = connector.disconnect()
        if json_out:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_report(report, f"Disconnecting akta.pro from {connector.display_name}")
        if not report.ok:
            raise typer.Exit(code=report.exit_code)

    return command


@connect_app.command("status")
def status(json_out: JsonOpt = False) -> None:
    """Show what's installed for each agent: skill version and whether the MCP server is registered."""
    results = [registry.get(name).status() for name in registry.names()]
    if json_out:
        print(json.dumps(results, indent=2))
        return
    for res in results:
        skill, mcp = res["skill"], res["mcp"]
        out.print(f"[bold]{res['name']}[/] ({res['target']})")
        path = display_path(Path(skill["path"]))
        if skill["installed"] and skill["managed"]:
            out.print(f"  [green]✓[/] Skill {skill['label']} → {path}/  [dim](installed {skill['installed_at']})[/]", soft_wrap=True)
        elif skill["installed"]:
            out.print(f"  [yellow]![/] Skill at {path}/ wasn't installed by akta-pro", soft_wrap=True)
        else:
            out.print(f"  [dim]•[/] Skill not installed ({path}/)", soft_wrap=True)
        if not mcp["claude_found"]:
            out.print("  [yellow]![/] MCP: agent CLI not found on PATH")
        elif mcp.get("error"):
            out.print(f"  [red]✗[/] MCP: {escape(mcp['error'])}")
        elif mcp["registered"]:
            where = f" — {mcp['scope']}" if mcp["scope"] else ""
            out.print(f"  [green]✓[/] MCP server '{mcp['name']}' registered{escape(where)}", soft_wrap=True)
        else:
            out.print(f"  [dim]•[/] MCP server '{mcp['name']}' not registered")


for _name, _cls in registry.CONNECTORS.items():
    connect_app.command(_name, help=f"Install the akta-pro skill and register the akta.pro MCP server in {_cls.display_name}.")(
        _make_connect(_name)
    )
    disconnect_app.command(_name, help=f"Remove the akta-pro skill and MCP server from {_cls.display_name}.")(
        _make_disconnect(_name)
    )


def register(app: typer.Typer, panel: str | None = None) -> None:
    app.add_typer(connect_app, name="connect", rich_help_panel=panel)
    app.add_typer(disconnect_app, name="disconnect", rich_help_panel=panel)
