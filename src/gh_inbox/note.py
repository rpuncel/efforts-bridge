"""Locate today's daily note and replace the marked block inside it."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from datetime import date
from pathlib import Path

START_MARKER = "<!-- gh-inbox:start -->"
END_MARKER = "<!-- gh-inbox:end -->"


class NoteError(Exception):
    """Raised when the daily note is missing or its markers are malformed."""


# Moment.js tokens used by Obsidian / Periodic Notes, longest first.
_MOMENT_TOKENS = {
    "YYYY": "%Y",
    "YY": "%y",
    "MMMM": "%B",
    "MMM": "%b",
    "MM": "%m",
    "M": "{month}",
    "DD": "%d",
    "D": "{day}",
    "dddd": "%A",
    "ddd": "%a",
}
_TOKEN_RE = re.compile(r"\[([^\]]*)\]|" + "|".join(sorted(_MOMENT_TOKENS, key=len, reverse=True)))


def format_moment(fmt: str, day: date) -> str:
    """Format `day` with a subset of moment.js tokens; `[text]` is literal."""

    def repl(match: re.Match) -> str:
        if match.group(1) is not None:
            return match.group(1)
        token = _MOMENT_TOKENS[match.group(0)]
        return token.format(month=day.month, day=day.day) if "{" in token else day.strftime(token)

    out, idx = [], 0
    for match in _TOKEN_RE.finditer(fmt):
        out.append(fmt[idx : match.start()].replace("%", "%%"))
        out.append(repl(match).replace("%", "%%"))
        idx = match.end()
    out.append(fmt[idx:].replace("%", "%%"))
    return day.strftime("".join(out))


def daily_note_path(daily_dir: Path, fmt: str, day: date) -> Path:
    return daily_dir / f"{format_moment(fmt, day)}.md"


def replace_block(text: str, body: str) -> str:
    """Replace the text between the markers with `body`, or append markers + body."""
    block = f"{START_MARKER}\n{body}\n{END_MARKER}"
    starts, ends = text.count(START_MARKER), text.count(END_MARKER)
    if starts == 0 and ends == 0:
        if not text:
            return block + "\n"
        if text.endswith("\n\n"):
            sep = ""
        elif text.endswith("\n"):
            sep = "\n"
        else:
            sep = "\n\n"
        return f"{text}{sep}{block}\n"
    if starts != 1 or ends != 1:
        raise NoteError(
            f"expected exactly one {START_MARKER} and one {END_MARKER}, "
            f"found {starts} and {ends}; fix the note by hand"
        )
    start = text.index(START_MARKER)
    end = text.index(END_MARKER)
    if end < start:
        raise NoteError(f"{END_MARKER} appears before {START_MARKER}; fix the note by hand")
    return text[:start] + block + text[end + len(END_MARKER) :]


def update_note(path: Path, body: str) -> None:
    if not path.is_file():
        raise NoteError(
            f"today's daily note does not exist: {path}\n"
            "Create it in Obsidian first; gh-inbox never creates notes."
        )
    with path.open(encoding="utf-8", newline="") as fh:
        text = fh.read()
    new_text = replace_block(text, body)
    if new_text == text:
        return
    # Atomic write so Obsidian never sees a half-written note.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".gh-inbox-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
