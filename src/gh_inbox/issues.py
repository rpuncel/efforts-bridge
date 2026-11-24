"""GitHub issues as Sync sees them: read, create and update through `gh api`.

Nothing here knows about Efforts; every part of Sync uses it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass

Runner = Callable[..., str]  # runner(args, input=None) -> stdout; see github.run_gh

_ISSUE_URL = re.compile(
    r"^https?://(?P<host>[^/\s]+)/(?P<owner>[^/\s]+)/(?P<name>[^/\s]+)/issues/(?P<number>\d+)/?$"
)


class SyncError(Exception):
    """Raised for one note that can't be synced; the others carry on."""


@dataclass(frozen=True)
class Issue:
    """The parts of a GitHub issue that Sync owns or checks."""

    number: int
    url: str
    title: str
    state: str  # "open" or "closed"
    state_reason: str | None
    labels: tuple[str, ...]

    @classmethod
    def from_api(cls, raw: dict) -> Issue:
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


def issue_number(url: str, host: str, repo: str, repo_name: str = "the expected repo") -> int:
    """The issue number, if `url` is an issue in `repo` on this host; else SyncError."""
    match = _ISSUE_URL.match(url.strip())
    if not match:
        raise SyncError(f"not an issue URL: {url}")
    found = f"{match['owner']}/{match['name']}"
    if match["host"].lower() != host.lower() or found.lower() != repo.lower():
        raise SyncError(f"{url} is not in {repo_name} ({host}/{repo}); Sync won't touch it")
    return int(match["number"])


def get_issue(host: str, repo: str, number: int, runner: Runner) -> Issue:
    out = runner(["api", "--hostname", host, f"repos/{repo}/issues/{number}"])
    return Issue.from_api(json.loads(out))


def create_issue(host: str, repo: str, body: dict, runner: Runner) -> Issue:
    args = ["api", "--hostname", host, "-X", "POST", f"repos/{repo}/issues", "--input", "-"]
    return Issue.from_api(json.loads(runner(args, input=json.dumps(body))))


def update_issue(host: str, repo: str, number: int, patch: dict, runner: Runner) -> Issue:
    args = ["api", "--hostname", host, "-X", "PATCH", f"repos/{repo}/issues/{number}"]
    out = runner([*args, "--input", "-"], input=json.dumps(patch))
    return Issue.from_api(json.loads(out))
