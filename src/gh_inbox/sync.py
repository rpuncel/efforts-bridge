"""Sync: the one-way push from the vault to GitHub, made of parts.

Each part syncs one kind of note to its issues. Effort sync (Effort notes to Effort
issues) is the only part so far; notes tied to other, non-Effort issues can become
another part later without changing what `gh-inbox sync` means.

Every part runs a preflight check first. If any part reports a problem, Sync stops
before it touches GitHub or the vault.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .config import Config
from .effort_sync import EffortSync, SyncResult
from .issues import Runner


class SyncStopped(Exception):
    """Raised when a preflight check fails; nothing has been read from or written to GitHub."""


class SyncPart(Protocol):
    name: str

    def preflight(self) -> list[str]: ...

    def run(self, *, dry_run: bool, echo: Callable[[str], None]) -> SyncResult: ...


def sync_parts(cfg: Config, runner: Runner) -> list[SyncPart]:
    return [EffortSync(cfg, runner)]


def preflight(cfg: Config, parts: list[SyncPart]) -> None:
    problems = []
    if not cfg.personal_repo:
        problems.append("Sync needs 'personal_repo' (owner/name) in the config.")
    for part in parts:
        problems.extend(part.preflight())
    if problems:
        raise SyncStopped("\n".join(problems) + "\nSync stopped before touching GitHub.")


def run_sync(
    cfg: Config, runner: Runner, *, dry_run: bool, echo: Callable[[str], None]
) -> list[tuple[str, SyncResult]]:
    """Check every part, then run them in order. Raises SyncStopped if a check fails."""
    parts = sync_parts(cfg, runner)
    preflight(cfg, parts)
    return [(part.name, part.run(dry_run=dry_run, echo=echo)) for part in parts]
