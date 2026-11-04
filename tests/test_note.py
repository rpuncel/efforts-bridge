from datetime import date

import pytest

from gh_inbox.note import (
    END_MARKER,
    START_MARKER,
    NoteError,
    daily_note_path,
    format_moment,
    replace_block,
    update_note,
)

BODY = "*updated at now*\n\n**Waiting on you**\n- [ ] thing"


def test_format_moment():
    d = date(2026, 3, 7)
    assert format_moment("YYYY-MM-DD", d) == "2026-03-07"
    assert format_moment("YYYY/MM/YYYY-MM-DD ddd", d) == "2026/03/2026-03-07 Sat"
    assert format_moment("D MMMM YY", d) == "7 March 26"
    assert format_moment("[Week of] YYYY-M-D %", d) == "Week of 2026-3-7 %"


def test_daily_note_path(tmp_path):
    p = daily_note_path(tmp_path / "Calendar/Daily Notes", "YYYY-MM-DD", date(2026, 1, 5))
    assert p == tmp_path / "Calendar/Daily Notes/2026-01-05.md"


def test_replace_existing_block_only():
    text = f"before\n{START_MARKER}\nold\nstuff\n{END_MARKER}\nafter\n"
    out = replace_block(text, BODY)
    assert out == f"before\n{START_MARKER}\n{BODY}\n{END_MARKER}\nafter\n"


def test_replace_is_idempotent():
    text = f"a\n{START_MARKER}\nold\n{END_MARKER}\nb"
    once = replace_block(text, BODY)
    assert replace_block(once, BODY) == once


@pytest.mark.parametrize(
    ("text", "expected_prefix"),
    [
        ("note", "note\n\n"),
        ("note\n", "note\n\n"),
        ("note\n\n", "note\n\n"),
        ("", ""),
    ],
)
def test_append_when_markers_missing(text, expected_prefix):
    out = replace_block(text, BODY)
    assert out == f"{expected_prefix}{START_MARKER}\n{BODY}\n{END_MARKER}\n"


@pytest.mark.parametrize(
    "text",
    [
        f"{START_MARKER}\nno end",
        f"no start\n{END_MARKER}",
        f"{END_MARKER}\n{START_MARKER}",
        f"{START_MARKER}\n{END_MARKER}\n{START_MARKER}\n{END_MARKER}",
    ],
)
def test_malformed_markers_raise(text):
    with pytest.raises(NoteError):
        replace_block(text, BODY)


def test_update_note_missing_raises_and_does_not_create(tmp_path):
    path = tmp_path / "2026-01-07.md"
    with pytest.raises(NoteError, match="does not exist"):
        update_note(path, BODY)
    assert not path.exists()


def test_update_note_preserves_crlf_and_rest_of_note(tmp_path):
    path = tmp_path / "n.md"
    path.write_bytes(b"line1\r\nline2\r\n")
    update_note(path, BODY)
    data = path.read_bytes()
    assert data.startswith(b"line1\r\nline2\r\n")
    assert START_MARKER.encode() in data
