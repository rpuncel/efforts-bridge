import json

import pytest
from click.testing import CliRunner

from conftest import HOST, FakeGh, notification, search_item, search_payload
from gh_inbox import cli
from gh_inbox.config import ConfigError, parse_config
from gh_inbox.note import END_MARKER, START_MARKER

NOTES = "Calendar/Daily Notes"


@pytest.fixture
def fake_gh(monkeypatch):
    gh = FakeGh(
        review=search_payload(search_item(1, "Review me", "2026-01-05T08:00:00Z")),
        notifications=json.dumps([notification(7, "Ping", "2026-01-05T09:00:00Z", "mention")]),
        assigned=search_payload(search_item(3, "Old bug", "2025-06-01T00:00:00Z", pr=False)),
    )
    monkeypatch.setattr(cli, "run_gh", gh)
    return gh


def run(config_file, *args):
    return CliRunner().invoke(cli.main, ["--config", str(config_file), *args])


def test_replaces_existing_block(config_file, vault, fake_gh):
    note = vault / NOTES / "2026-01-05.md"
    before = note.read_text()
    result = run(config_file, "--date", "2026-01-05")
    assert result.exit_code == 0, result.output
    after = note.read_text()
    assert "Stale entry" not in after
    assert "[Old bug]" in after and "`acme/widgets`" in after
    assert after.count(START_MARKER) == 1 and after.count(END_MARKER) == 1
    head, tail = before.split(START_MARKER)[0], before.split(END_MARKER)[1]
    assert after.startswith(head) and after.endswith(tail)


def test_appends_block_when_markers_missing(config_file, vault, fake_gh):
    note = vault / NOTES / "2026-01-06.md"
    before = note.read_text()
    result = run(config_file, "--date", "2026-01-06")
    assert result.exit_code == 0, result.output
    after = note.read_text()
    assert after.startswith(before)
    assert after.rstrip().endswith(END_MARKER)
    assert "updated at" in after


def test_missing_note_exits_nonzero_without_creating(config_file, vault, fake_gh):
    result = run(config_file, "--date", "2026-01-07")
    assert result.exit_code == 1
    assert "does not exist" in result.output
    assert not (vault / NOTES / "2026-01-07.md").exists()
    assert fake_gh.calls == []  # fails before hitting GitHub


def test_dry_run_prints_and_does_not_write(config_file, vault, fake_gh):
    note = vault / NOTES / "2026-01-06.md"
    before = note.read_text()
    result = run(config_file, "--date", "2026-01-06", "--dry-run")
    assert result.exit_code == 0
    assert START_MARKER in result.output
    assert note.read_text() == before


def test_partial_failure_writes_warning_and_exits_1(config_file, vault, monkeypatch):
    monkeypatch.setattr(cli, "run_gh", FakeGh(fail={"notifications"}))
    result = run(config_file, "--date", "2026-01-06")
    assert result.exit_code == 1
    assert "Could not fetch notifications" in (vault / NOTES / "2026-01-06.md").read_text()


def test_total_failure_leaves_note_unchanged(config_file, vault, monkeypatch):
    monkeypatch.setattr(
        cli, "run_gh", FakeGh(fail={"review_requests", "notifications", "assigned"})
    )
    note = vault / NOTES / "2026-01-06.md"
    before = note.read_text()
    result = run(config_file, "--date", "2026-01-06")
    assert result.exit_code == 1
    assert "every source failed" in result.output
    assert note.read_text() == before


def test_missing_config(tmp_path):
    result = run(tmp_path / "nope.toml")
    assert result.exit_code == 1
    assert "config file not found" in result.output


def test_parse_config_defaults_and_validation(tmp_path):
    cfg = parse_config({"github": {"host": HOST}, "vault": {"path": "~/v"}})
    assert cfg.daily_folder == "Calendar/Daily Notes"
    assert cfg.daily_format == "YYYY-MM-DD"
    assert (cfg.inbox.waiting_max, cfg.inbox.waiting_days, cfg.inbox.oldest_max) == (10, 7, 5)
    assert "~" not in str(cfg.vault_path)

    cfg = parse_config(
        {
            "github": {"host": HOST},
            "vault": {"path": "/v"},
            "daily_notes": {"format": "YYYY-MM-DD.md"},
            "inbox": {"waiting_max": 3, "sources": ["assigned"]},
        }
    )
    assert cfg.daily_format == "YYYY-MM-DD"
    assert cfg.inbox.waiting_max == 3 and cfg.inbox.sources == ("assigned",)

    for bad in (
        {"vault": {"path": "/v"}},
        {"github": {"host": "https://x/"}, "vault": {"path": "/v"}},
        {"github": {"host": HOST}, "vault": {"path": "/v"}, "inbox": {"waiting_max": "10"}},
        {"github": {"host": HOST}, "vault": {"path": "/v"}, "inbox": {"sources": ["nope"]}},
    ):
        with pytest.raises(ConfigError):
            parse_config(bad)


def test_example_config_parses():
    import tomllib
    from pathlib import Path

    example = Path(__file__).parent.parent / "config.example.toml"
    cfg = parse_config(tomllib.loads(example.read_text()))
    assert cfg.host == "github.example.com"
