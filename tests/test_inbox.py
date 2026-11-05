from datetime import UTC, datetime, timedelta

from conftest import HOST, FakeGh, notification, search_item, search_payload
from gh_inbox.config import InboxConfig
from gh_inbox.github import (
    Item,
    fetch_all,
    notification_html_url,
    parse_json_stream,
)
from gh_inbox.inbox import build_inbox, merge, render_block, render_item

NOW = datetime(2026, 1, 6, 9, 0, tzinfo=UTC)


def iso(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def item(n: int, days_ago: float, reasons=("review_requested",), repo="acme/widgets") -> Item:
    return Item(
        url=f"https://{HOST}/{repo}/pull/{n}",
        title=f"Item {n}",
        repo=repo,
        updated_at=NOW - timedelta(days=days_ago),
        kind="pr",
        reasons=set(reasons),
    )


# --- fetching / parsing (gh mocked) -------------------------------------------------


def test_fetch_all_uses_hostname_and_parses_sources():
    gh = FakeGh(
        review=search_payload(search_item(1, "Review me", iso(1))),
        notifications=f"[{__import__('json').dumps(notification(7, 'Ping', iso(2), 'mention'))}]",
        assigned=search_payload(search_item(3, "Fix bug", iso(30), pr=False)),
    )
    items, errors = fetch_all(HOST, ["review_requests", "notifications", "assigned"], gh)
    assert errors == {}
    assert all(call[:3] == ["api", "--hostname", HOST] for call in gh.calls)
    assert not any("github.com" in a and HOST not in a for call in gh.calls for a in call)
    by_title = {it.title: it for it in items}
    assert by_title["Review me"].repo == "acme/widgets"
    assert by_title["Review me"].kind == "pr"
    assert by_title["Fix bug"].kind == "issue"
    assert by_title["Fix bug"].reasons == {"assigned"}
    assert by_title["Ping"].url == f"https://{HOST}/acme/widgets/issues/7"
    assert by_title["Ping"].reasons == {"mention"}


def test_fetch_all_reports_failed_source_and_keeps_others():
    gh = FakeGh(review=search_payload(search_item(1, "Review me", iso(1))), fail={"notifications"})
    items, errors = fetch_all(HOST, ["review_requests", "notifications"], gh)
    assert [it.title for it in items] == ["Review me"]
    assert set(errors) == {"notifications"}


def test_fetch_all_respects_sources():
    gh = FakeGh()
    fetch_all(HOST, ["assigned"], gh)
    assert len(gh.calls) == 1 and "notifications" not in gh.calls[0]


def test_parse_json_stream_handles_paginated_output():
    assert parse_json_stream("[1, 2]\n[3]") == [[1, 2], [3]]
    assert parse_json_stream("") == []


def test_notification_html_url_variants():
    pr = notification(5, "t", iso(1), "comment", kind="PullRequest")
    assert notification_html_url(pr) == f"https://{HOST}/acme/widgets/pull/5"
    release = notification(1, "v1", iso(1), "subscribed", kind="Release")
    release["subject"]["url"] = f"https://{HOST}/api/v3/repos/acme/widgets/releases/99"
    assert notification_html_url(release) == f"https://{HOST}/acme/widgets/releases"
    check = notification(1, "CI", iso(1), "ci_activity", kind="CheckSuite")
    check["subject"]["url"] = None
    assert notification_html_url(check) == f"https://{HOST}/acme/widgets"


# --- merging / capping / sorting ----------------------------------------------------


def test_merge_dedupes_by_url_and_unions_reasons():
    a = item(1, 3, ("review_requested",))
    b = item(1, 1, ("mention",))
    merged = merge([a, b])
    assert len(merged) == 1
    assert merged[0].reasons == {"review_requested", "mention"}
    assert merged[0].updated_at == NOW - timedelta(days=1)


def test_waiting_is_recent_newest_first_and_capped():
    items = [item(n, n * 0.5) for n in range(1, 15)]  # 0.5 .. 7 days ago
    inbox = build_inbox(items, InboxConfig(waiting_max=10, waiting_days=7), NOW)
    assert [it.title for it in inbox.waiting] == [f"Item {n}" for n in range(1, 11)]


def test_waiting_excludes_old_and_non_waiting_reasons():
    items = [
        item(1, 1, ("review_requested",)),
        item(2, 8, ("review_requested",)),  # too old
        item(3, 1, ("assigned",)),  # not a waiting reason
        item(4, 1, ("subscribed",)),
        item(5, 2, ("comment",)),
    ]
    inbox = build_inbox(items, InboxConfig(), NOW)
    assert [it.title for it in inbox.waiting] == ["Item 1", "Item 5"]


def test_oldest_is_stalest_of_the_rest_and_capped():
    items = [item(n, n * 10, ("assigned",)) for n in range(1, 9)] + [item(99, 0.1)]
    inbox = build_inbox(items, InboxConfig(oldest_max=5), NOW)
    assert [it.title for it in inbox.waiting] == ["Item 99"]
    assert [it.title for it in inbox.oldest] == [f"Item {n}" for n in (8, 7, 6, 5, 4)]
    assert inbox.hidden == 3
    assert inbox.total == 9


def test_overflowed_waiting_items_can_appear_in_oldest():
    items = [item(n, 1 + n * 0.01) for n in range(1, 4)]
    inbox = build_inbox(items, InboxConfig(waiting_max=1, oldest_max=5), NOW)
    assert [it.title for it in inbox.waiting] == ["Item 1"]
    assert [it.title for it in inbox.oldest] == ["Item 3", "Item 2"]
    assert inbox.hidden == 0


def test_zero_caps():
    inbox = build_inbox([item(1, 1)], InboxConfig(waiting_max=0, oldest_max=0), NOW)
    assert inbox.waiting == [] and inbox.oldest == [] and inbox.hidden == 1


# --- rendering ----------------------------------------------------------------------


def test_render_item_is_checkbox_with_link_and_repo():
    line = render_item(item(42, 2, ("review_requested", "mention")), NOW)
    assert line == (
        f"- [ ] [Item 42](https://{HOST}/acme/widgets/pull/42) · `acme/widgets`"
        " · mentioned, review requested · 2d ago"
    )


def test_render_item_escapes_title():
    it = item(1, 0.0001)
    it.title = "Fix [WIP] <thing> | pipes\nnewline"
    line = render_item(it, NOW)
    assert "[Fix \\[WIP\\] \\<thing\\> \\| pipes newline](" in line
    assert line.endswith("0m ago")


def test_render_block_layout():
    items = [item(1, 1), item(2, 40, ("assigned",)), item(3, 20, ("assigned",))]
    inbox = build_inbox(items, InboxConfig(oldest_max=1), NOW)
    body = render_block(inbox, NOW, HOST)
    lines = body.splitlines()
    assert lines[0] == f"*updated at 2026-01-06 09:00 from {HOST}*"
    assert "**Waiting on you**" in lines and "**Oldest**" in lines
    assert lines.index("**Waiting on you**") < lines.index("**Oldest**")
    assert lines[-1] == "*1 more item hidden (3 total).*"
    assert "<!--" not in body


def test_render_block_empty_and_errors():
    inbox = build_inbox([], InboxConfig(), NOW)
    body = render_block(inbox, NOW, HOST, {"notifications": "HTTP 403"})
    assert "> [!warning] Could not fetch notifications: HTTP 403" in body
    assert "- Nothing waiting on you." in body
    assert "- Nothing else open." in body
    assert body.endswith("*0 more items hidden (0 total).*")
