"""Effort sync: the part of Sync that pushes Effort notes to Effort issues.

This slice covers the Effort issue itself: create or match it, its title (the Effort
note's file name), its one `intensity/` label and whether it is open or closed. The
Effort note is authoritative (ADR 0001), and Effort issues live only in the Personal
repo (ADR 0008), so Effort sync refuses to touch an issue anywhere else.

Every Synced effort turns into a planned `Change`, which is printed and, outside a dry
run, applied. A dry run still reads Effort issues from GitHub but writes nothing,
neither to GitHub nor to the vault.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .config import Config
from .efforts import (
    INTENSITY_LABEL_PREFIX,
    SyncedEffort,
    find_synced_efforts,
    missing_effort_folders,
)
from .frontmatter import write_frontmatter_key
from .github import GhError
from .issues import (
    Issue,
    Runner,
    SyncError,
    create_issue,
    get_issue,
    issue_number,
    update_issue,
)

PERSONAL_REPO = "the Personal repo"
CLOSE_REASONS = {"done": "completed", "canceled": "not_planned"}


@dataclass
class Change:
    """What Sync will do for one Synced effort."""

    effort: SyncedEffort
    kind: str  # "create", "update", "unchanged" or "skip"
    issue: Issue | None = None
    patch: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # human-readable parts of the change


def desired_labels(effort: SyncedEffort, current: Sequence[str]) -> list[str]:
    """Current labels with every `intensity/` label replaced by the Effort's one, if any.

    Labels Sync doesn't own are kept, in their order.
    """
    kept = [name for name in current if not name.startswith(INTENSITY_LABEL_PREFIX)]
    return kept + ([effort.intensity_label] if effort.intensity_label else [])


def plan_existing(effort: SyncedEffort, issue: Issue) -> Change:
    patch: dict = {}
    notes: list[str] = []
    if issue.title != effort.title:
        patch["title"] = effort.title
        notes.append(f'retitle from "{issue.title}"')

    if effort.intensity:
        if issue.state != "open":
            patch["state"] = "open"
            notes.append("reopen")
    else:
        reason = CLOSE_REASONS[effort.folder]
        if issue.state != "closed" or issue.state_reason != reason:
            patch["state"] = "closed"
            patch["state_reason"] = reason
            notes.append(f"close as {reason.replace('_', ' ')}")

    labels = desired_labels(effort, issue.labels)
    if set(labels) != set(issue.labels):
        patch["labels"] = labels
        added = [name for name in labels if name not in issue.labels]
        removed = [name for name in issue.labels if name not in labels]
        notes.append(" ".join([*(f"+{n}" for n in added), *(f"-{n}" for n in removed)]))

    return Change(effort, "update" if patch else "unchanged", issue, patch, notes)


def plan_new(effort: SyncedEffort) -> Change:
    if not effort.intensity:
        # A note that reached done or canceled before it was ever synced has no issue
        # to close. Creating one just to close it is left out until it is asked for.
        return Change(
            effort,
            "skip",
            notes=[f"in the {effort.folder} folder with no Effort issue yet; not creating one"],
        )
    body = {"title": effort.title, "labels": [effort.intensity_label]}
    return Change(effort, "create", patch=body, notes=[f"label {effort.intensity_label}"])


@dataclass
class SyncResult:
    changes: list[Change] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    summary: str = ""

    def counts(self) -> Counter:
        return Counter(change.kind for change in self.changes)


def _duplicate_urls(efforts: Sequence[SyncedEffort]) -> set[str]:
    seen = Counter(e.issue_url.strip().rstrip("/") for e in efforts if e.issue_url)
    return {url for url, count in seen.items() if count > 1}


def sync_efforts(
    efforts: Sequence[SyncedEffort],
    *,
    host: str,
    personal_repo: str,
    issue_key: str,
    vault: Path,
    runner: Runner,
    dry_run: bool,
    echo: Callable[[str], None],
) -> SyncResult:
    """Plan every Synced effort and, unless `dry_run`, apply the plan."""
    result = SyncResult()
    duplicates = _duplicate_urls(efforts)

    for effort in efforts:
        where = effort.path.relative_to(vault).as_posix()
        try:
            if effort.issue_url and effort.issue_url.strip().rstrip("/") in duplicates:
                raise SyncError(
                    f"{effort.issue_url} is in more than one Effort note; "
                    "one Effort note is one Effort issue, so fix the notes first"
                )
            if effort.issue_url:
                number = issue_number(effort.issue_url, host, personal_repo, PERSONAL_REPO)
                issue = get_issue(host, personal_repo, number, runner)
                # GitHub follows an issue that was moved; never follow it out of the repo.
                issue_number(issue.url, host, personal_repo, PERSONAL_REPO)
                change = plan_existing(effort, issue)
            else:
                change = plan_new(effort)
        except (SyncError, GhError, ValueError, KeyError, TypeError) as exc:
            result.errors.append(f"{where}: {exc}")
            echo(f"error   {where}: {exc}")
            continue

        result.changes.append(change)
        _describe(change, where, personal_repo, issue_key, echo)
        if dry_run or change.kind in ("unchanged", "skip"):
            continue
        try:
            _apply(change, host, personal_repo, issue_key, runner, echo)
        except (SyncError, GhError, ValueError, KeyError, TypeError, OSError) as exc:
            result.errors.append(f"{where}: {exc}")
            echo(f"error   {where}: {exc}")
    return result


def _describe(change: Change, where: str, repo: str, issue_key: str, echo) -> None:
    title = change.effort.title
    if change.kind == "create":
        echo(f'create  "{title}" in {repo}, {", ".join(change.notes)}')
        echo(f"        then write {issue_key} into {where}")
    elif change.kind == "update":
        echo(f'update  #{change.issue.number} "{title}": {"; ".join(change.notes)}')
    elif change.kind == "skip":
        echo(f"skip    {where}: {'; '.join(change.notes)}")


def _apply(change: Change, host: str, repo: str, issue_key: str, runner: Runner, echo) -> None:
    if change.kind == "update":
        update_issue(host, repo, change.issue.number, change.patch, runner)
        return
    issue = create_issue(host, repo, change.patch, runner)
    change.issue = issue
    try:
        write_frontmatter_key(change.effort.path, issue_key, issue.url)
    except Exception as exc:
        raise SyncError(
            f"created {issue.url} but could not write it into the note ({exc}). "
            f"Add '{issue_key}: {issue.url}' to its frontmatter by hand before the next "
            "sync, or Effort sync will create a second Effort issue"
        ) from exc
    echo(f"        created {issue.url}")


class EffortSync:
    """Effort sync as one part of Sync: a preflight check, then the run."""

    name = "Effort sync"

    def __init__(self, cfg: Config, runner: Runner):
        self.cfg = cfg
        self.runner = runner

    def preflight(self) -> list[str]:
        """Problems that must stop Sync before it touches GitHub."""
        missing = missing_effort_folders(self.cfg.vault_path, self.cfg.effort_folders)
        if not missing:
            return []
        lines = "\n".join(f"  {key}: {path}" for key, path in missing)
        return [
            f"Effort folders not found:\n{lines}\n"
            "Check that [efforts] in the config points at the right folders, "
            "or create them in the vault."
        ]

    def run(self, *, dry_run: bool, echo: Callable[[str], None]) -> SyncResult:
        cfg = self.cfg
        efforts, warnings = find_synced_efforts(cfg.vault_path, cfg.effort_folders, cfg.issue_key)
        for warning in warnings:
            echo(f"warning {warning}")
        result = sync_efforts(
            efforts,
            host=cfg.host,
            personal_repo=cfg.personal_repo,
            issue_key=cfg.issue_key,
            vault=cfg.vault_path,
            runner=self.runner,
            dry_run=dry_run,
            echo=echo,
        )
        counts = result.counts()
        result.summary = (
            f"{len(efforts)} Synced efforts. Planned: {counts['create']} create, "
            f"{counts['update']} update, {counts['unchanged']} unchanged, "
            f"{counts['skip']} skipped. Errors: {len(result.errors)}"
        )
        return result
