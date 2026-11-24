"""Sync: push Synced efforts one way, from Effort notes to Effort issues.

This slice covers the Effort issue itself: create or match it, its title (the Effort
note's file name), its one `intensity/` label and whether it is open or closed. The
Effort note is authoritative (ADR 0001), and Effort issues live only in the Personal
repo (ADR 0008), so Sync refuses to touch an issue anywhere else.

Every Synced effort turns into a planned `Change`, which is printed and, outside a dry
run, applied. A dry run still reads Effort issues from GitHub but writes nothing,
neither to GitHub nor to the vault.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .efforts import INTENSITY_LABEL_PREFIX, SyncedEffort, write_issue_url
from .github import GhError

Runner = Callable[..., str]  # runner(args, input=None) -> stdout; see github.run_gh

CLOSE_REASONS = {"done": "completed", "canceled": "not_planned"}

_ISSUE_URL = re.compile(
    r"^https?://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<name>[^/\s]+)/issues/(?P<number>\d+)/?$"
)


class SyncError(Exception):
    """Raised for one Synced effort that can't be synced; the others carry on."""


@dataclass(frozen=True)
class EffortIssue:
    """The parts of an Effort issue this slice of Sync owns or checks."""

    number: int
    url: str
    title: str
    state: str  # "open" or "closed"
    state_reason: str | None
    labels: tuple[str, ...]

    @classmethod
    def from_api(cls, raw: dict) -> EffortIssue:
        if "pull_request" in raw:
            raise SyncError(f"{raw.get('html_url')} is a pull request, not an issue")
        return cls(
            number=raw["number"],
            url=raw["html_url"],
            title=raw.get("title") or "",
            state=raw["state"],
            state_reason=raw.get("state_reason"),
            labels=tuple(label["name"] for label in raw.get("labels", [])),
        )


@dataclass
class Change:
    """What Sync will do for one Synced effort."""

    effort: SyncedEffort
    kind: str  # "create", "update", "unchanged" or "skip"
    issue: EffortIssue | None = None
    patch: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)  # human-readable parts of the change


def parse_issue_url(url: str, host: str, personal_repo: str) -> int:
    """The issue number, if `url` is an issue in the Personal repo on this host."""
    match = _ISSUE_URL.match(url.strip())
    if not match:
        raise SyncError(f"not an issue URL: {url}")
    repo = f"{match['owner']}/{match['name']}"
    if match["host"].lower() != host.lower() or repo.lower() != personal_repo.lower():
        raise SyncError(
            f"{url} is not in the Personal repo ({host}/{personal_repo}); "
            "Sync only touches Effort issues there"
        )
    return int(match["number"])


def get_issue(host: str, repo: str, number: int, runner: Runner) -> EffortIssue:
    out = runner(["api", "--hostname", host, f"repos/{repo}/issues/{number}"])
    return EffortIssue.from_api(json.loads(out))


def create_issue(host: str, repo: str, body: dict, runner: Runner) -> EffortIssue:
    args = ["api", "--hostname", host, "-X", "POST", f"repos/{repo}/issues", "--input", "-"]
    return EffortIssue.from_api(json.loads(runner(args, input=json.dumps(body))))


def update_issue(host: str, repo: str, number: int, patch: dict, runner: Runner) -> EffortIssue:
    args = ["api", "--hostname", host, "-X", "PATCH", f"repos/{repo}/issues/{number}"]
    out = runner([*args, "--input", "-"], input=json.dumps(patch))
    return EffortIssue.from_api(json.loads(out))


def desired_labels(effort: SyncedEffort, current: Sequence[str]) -> list[str]:
    """Current labels with every `intensity/` label replaced by the Effort's one, if any.

    Labels Sync doesn't own are kept, in their order.
    """
    kept = [name for name in current if not name.startswith(INTENSITY_LABEL_PREFIX)]
    return kept + ([effort.intensity_label] if effort.intensity_label else [])


def plan_existing(effort: SyncedEffort, issue: EffortIssue) -> Change:
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
                number = parse_issue_url(effort.issue_url, host, personal_repo)
                issue = get_issue(host, personal_repo, number, runner)
                # GitHub follows an issue that was moved; never follow it out of the repo.
                parse_issue_url(issue.url, host, personal_repo)
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
        write_issue_url(change.effort.path, issue_key, issue.url)
    except Exception as exc:
        raise SyncError(
            f"created {issue.url} but could not write it into the note ({exc}). "
            f"Add '{issue_key}: {issue.url}' to its frontmatter by hand before the next "
            "sync, or Sync will create a second Effort issue"
        ) from exc
    echo(f"        created {issue.url}")
