"""Click entry point: `gh-inbox` refreshes the inbox block in today's daily note."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import click

from . import __version__
from .config import DEFAULT_CONFIG_PATH, ConfigError, load_config
from .github import fetch_all, run_gh
from .inbox import build_inbox, render_block
from .note import NoteError, daily_note_path, replace_block, update_note


@click.group(invoke_without_command=True)
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=str(DEFAULT_CONFIG_PATH),
    show_default=True,
    envvar="GH_INBOX_CONFIG",
    help="Path to the TOML config file (env: GH_INBOX_CONFIG).",
)
@click.option(
    "--date",
    "for_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=None,
    help="Use this day's note instead of today's (YYYY-MM-DD).",
)
@click.option("--dry-run", is_flag=True, help="Print the block instead of writing the note.")
@click.version_option(__version__, prog_name="gh-inbox")
@click.pass_context
def main(ctx: click.Context, config_path: Path, for_date: datetime | None, dry_run: bool) -> None:
    """Refresh the GitHub inbox block in today's Obsidian daily note."""
    if ctx.invoked_subcommand is not None:
        return
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc

    day: date = for_date.date() if for_date else date.today()
    note = daily_note_path(cfg.daily_dir, cfg.daily_format, day)
    if not dry_run and not note.is_file():
        raise click.ClickException(
            f"today's daily note does not exist: {note}\n"
            "Create it in Obsidian first; gh-inbox never creates notes."
        )

    items, errors = fetch_all(cfg.host, cfg.inbox.sources, run_gh)
    for source, message in errors.items():
        click.echo(f"warning: could not fetch {source}: {message}", err=True)
    if cfg.inbox.sources and len(errors) == len(cfg.inbox.sources):
        raise click.ClickException("every source failed; note left unchanged")

    now = datetime.now().astimezone()
    body = render_block(build_inbox(items, cfg.inbox, now), now, cfg.host, errors)

    if dry_run:
        click.echo(replace_block("", body), nl=False)
    else:
        try:
            update_note(note, body)
        except NoteError as exc:
            raise click.ClickException(str(exc)) from exc
        click.echo(f"updated {note}", err=True)

    if errors:
        ctx.exit(1)
