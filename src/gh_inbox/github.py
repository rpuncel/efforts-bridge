"""Fetch inbox items through `gh api --hostname <host>`.

Only long-standing REST endpoints are used so this works on GitHub Enterprise
Server as well as github.com:

* GET search/issues  (review requests, assigned issues)
* GET notifications  (unread notifications)
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime

Runner = Callable[[Sequence[str]], str]


class GhError(Exception):
    """Raised when a `gh` call fails."""


@dataclass
class Item:
    url: str
    title: str
    repo: str
    updated_at: datetime
    kind: str  # "pr", "issue", or a notification subject type in lower case
    reasons: set[str] = field(default_factory=set)


def run_gh(args: Sequence[str]) -> str:
    """Run `gh` and return stdout. Raises GhError with gh's stderr on failure."""
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, check=False, timeout=120
        )
    except FileNotFoundError as exc:
        raise GhError(
            "the `gh` CLI was not found on PATH; install it from https://cli.github.com"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise GhError(f"`gh {' '.join(args)}` timed out") from exc
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout).strip() or f"exit code {proc.returncode}"
        raise GhError(f"`gh {' '.join(args)}` failed: {msg}")
    return proc.stdout


def parse_json_stream(text: str) -> list:
    """Parse one or more concatenated JSON documents (what `gh api --paginate` prints)."""
    decoder = json.JSONDecoder()
    docs, idx = [], 0
    text = text.strip()
    while idx < len(text):
        doc, end = decoder.raw_decode(text, idx)
        docs.append(doc)
        idx = end
        while idx < len(text) and text[idx].isspace():
            idx += 1
    return docs


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _repo_from_api_url(repository_url: str) -> str:
    # ".../repos/<owner>/<name>" on both github.com and GHES (".../api/v3/repos/...").
    parts = repository_url.rstrip("/").split("/")
    return "/".join(parts[-2:])


def search_items(host: str, query: str, reason: str, runner: Runner = run_gh) -> list[Item]:
    out = runner(
        [
            "api",
            "--hostname",
            host,
            "-X",
            "GET",
            "search/issues",
            "-f",
            f"q={query}",
            "-f",
            "per_page=100",
            "-f",
            "sort=updated",
        ]
    )
    items = []
    for doc in parse_json_stream(out):
        for raw in doc.get("items", []):
            items.append(
                Item(
                    url=raw["html_url"],
                    title=raw.get("title") or "(untitled)",
                    repo=_repo_from_api_url(raw["repository_url"]),
                    updated_at=parse_time(raw["updated_at"]),
                    kind="pr" if "pull_request" in raw else "issue",
                    reasons={reason},
                )
            )
    return items


_SUBJECT_URL = re.compile(r"/repos/[^/]+/[^/]+/(issues|pulls|commits)/([^/]+)$")


def notification_html_url(raw: dict) -> str:
    """Turn a notification's API subject URL into a browser URL.

    Built from repository.html_url so no hostname is assumed.
    """
    repo_url = raw["repository"]["html_url"].rstrip("/")
    subject = raw.get("subject") or {}
    api_url = subject.get("url") or ""
    match = _SUBJECT_URL.search(api_url)
    if match:
        kind, ident = match.groups()
        path = {"issues": "issues", "pulls": "pull", "commits": "commit"}[kind]
        return f"{repo_url}/{path}/{ident}"
    stype = subject.get("type")
    if stype == "Release":
        return f"{repo_url}/releases"
    if stype == "Discussion":
        return f"{repo_url}/discussions"
    return repo_url


def notification_items(host: str, runner: Runner = run_gh) -> list[Item]:
    # Unread only is the endpoint default (all=false).
    out = runner(["api", "--hostname", host, "--paginate", "-X", "GET", "notifications"])
    items = []
    for doc in parse_json_stream(out):
        for raw in doc:
            if not raw.get("unread", True):
                continue
            subject = raw.get("subject") or {}
            stype = (subject.get("type") or "").lower()
            items.append(
                Item(
                    url=notification_html_url(raw),
                    title=subject.get("title") or "(untitled)",
                    repo=raw["repository"]["full_name"],
                    updated_at=parse_time(raw["updated_at"]),
                    kind={"pullrequest": "pr"}.get(stype, stype or "notification"),
                    reasons={raw.get("reason") or "notification"},
                )
            )
    return items


REVIEW_QUERY = "is:open is:pr review-requested:@me archived:false"
ASSIGNED_QUERY = "is:open is:issue assignee:@me archived:false"


def fetch_all(
    host: str, sources: Sequence[str], runner: Runner = run_gh
) -> tuple[list[Item], dict[str, str]]:
    """Fetch every enabled source. Returns (items, errors-by-source)."""
    fetchers: dict[str, Callable[[], list[Item]]] = {
        "review_requests": lambda: search_items(host, REVIEW_QUERY, "review_requested", runner),
        "notifications": lambda: notification_items(host, runner),
        "assigned": lambda: search_items(host, ASSIGNED_QUERY, "assigned", runner),
    }
    items: list[Item] = []
    errors: dict[str, str] = {}
    for source in sources:
        try:
            items.extend(fetchers[source]())
        except (GhError, ValueError, KeyError, TypeError) as exc:
            errors[source] = str(exc) or type(exc).__name__
    return items, errors
