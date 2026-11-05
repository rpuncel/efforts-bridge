"""Merge, cap and render inbox items as markdown."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from .config import InboxConfig
from .github import Item

REASON_LABELS = {
    "review_requested": "review requested",
    "mention": "mentioned",
    "team_mention": "team mentioned",
    "author": "reply on your thread",
    "comment": "reply",
    "assigned": "assigned",
    "assign": "assigned",
    "state_change": "state change",
    "subscribed": "watching",
    "ci_activity": "CI",
    "security_alert": "security alert",
    "manual": "subscribed",
}


@dataclass
class Inbox:
    waiting: list[Item]
    oldest: list[Item]
    hidden: int
    total: int


def merge(items: Iterable[Item]) -> list[Item]:
    """De-duplicate by URL, unioning reasons and keeping the latest update time."""
    by_url: dict[str, Item] = {}
    for item in items:
        existing = by_url.get(item.url)
        if existing is None:
            by_url[item.url] = Item(
                url=item.url,
                title=item.title,
                repo=item.repo,
                updated_at=item.updated_at,
                kind=item.kind,
                reasons=set(item.reasons),
            )
            continue
        existing.reasons |= item.reasons
        if item.updated_at > existing.updated_at:
            existing.updated_at = item.updated_at
        if existing.kind not in ("pr", "issue") and item.kind in ("pr", "issue"):
            existing.kind = item.kind
    return list(by_url.values())


def build_inbox(items: Iterable[Item], cfg: InboxConfig, now: datetime) -> Inbox:
    merged = merge(items)
    cutoff = now - timedelta(days=cfg.waiting_days)
    waiting_reasons = set(cfg.waiting_reasons)

    candidates = [it for it in merged if it.reasons & waiting_reasons and it.updated_at >= cutoff]
    candidates.sort(key=lambda it: (it.updated_at, it.url), reverse=True)
    waiting = candidates[: cfg.waiting_max]

    shown = {it.url for it in waiting}
    rest = sorted(
        (it for it in merged if it.url not in shown), key=lambda it: (it.updated_at, it.url)
    )
    oldest = rest[: cfg.oldest_max]

    hidden = len(merged) - len(waiting) - len(oldest)
    return Inbox(waiting=waiting, oldest=oldest, hidden=hidden, total=len(merged))


def _escape(text: str) -> str:
    text = " ".join(text.split())
    for ch in ("\\", "[", "]", "<", ">", "|"):
        text = text.replace(ch, "\\" + ch)
    return text


def _age(updated_at: datetime, now: datetime) -> str:
    seconds = max(0, int((now - updated_at).total_seconds()))
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def _reason_text(reasons: set[str]) -> str:
    labels = []
    for reason in sorted(reasons):
        label = REASON_LABELS.get(reason, reason.replace("_", " "))
        if label not in labels:
            labels.append(label)
    return ", ".join(labels)


def render_item(item: Item, now: datetime) -> str:
    return (
        f"- [ ] [{_escape(item.title)}]({item.url}) · `{item.repo}`"
        f" · {_reason_text(item.reasons)} · {_age(item.updated_at, now)}"
    )


def render_block(
    inbox: Inbox,
    now: datetime,
    host: str,
    errors: Mapping[str, str] | None = None,
) -> str:
    """Render the text that goes between the markers (without the markers)."""
    lines = [f"*updated at {now.strftime('%Y-%m-%d %H:%M')} from {host}*", ""]
    for source, message in sorted((errors or {}).items()):
        lines.append(f"> [!warning] Could not fetch {source}: {_escape(message)}")
    if errors:
        lines.append("")

    lines.append("**Waiting on you**")
    lines.extend(render_item(it, now) for it in inbox.waiting)
    if not inbox.waiting:
        lines.append("- Nothing waiting on you.")
    lines.append("")

    lines.append("**Oldest**")
    lines.extend(render_item(it, now) for it in inbox.oldest)
    if not inbox.oldest:
        lines.append("- Nothing else open.")
    lines.append("")

    noun = "item" if inbox.hidden == 1 else "items"
    lines.append(f"*{inbox.hidden} more {noun} hidden ({inbox.total} total).*")
    return "\n".join(lines)
