"""Read a note's frontmatter and set one key in it, leaving every other byte alone.

Used by every part of Sync to find which notes opt in and to write an issue URL back.
The parser is deliberately small: top-level `key: value` lines, flow lists (`[a, b]`)
and block lists (`- a`). That covers what Obsidian's Properties editor writes.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

_FENCE = re.compile(r"^---[ \t]*(\r?\n|$)")
_KEY_LINE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$")
_BLOCK_ITEM = re.compile(r"^[ \t]+-[ \t]+(.*?)[ \t]*$|^-[ \t]+(.*?)[ \t]*$")


class FrontmatterError(Exception):
    """Raised when a note's frontmatter can't be read or written safely."""


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def _frontmatter_span(lines: list[str]) -> tuple[int, int] | None:
    """Line indexes of the opening and closing `---`, or None without frontmatter."""
    if not lines or not _FENCE.match(lines[0]):
        return None
    for idx in range(1, len(lines)):
        if _FENCE.match(lines[idx]):
            return 0, idx
    return None


def read_frontmatter(text: str) -> dict[str, str | list[str]]:
    """Top-level frontmatter keys. Lists come back as lists, everything else as text."""
    lines = text.splitlines(keepends=True)
    span = _frontmatter_span(lines)
    if span is None:
        return {}
    body = [line.rstrip("\r\n") for line in lines[span[0] + 1 : span[1]]]
    data: dict[str, str | list[str]] = {}
    idx = 0
    while idx < len(body):
        match = _KEY_LINE.match(body[idx])
        idx += 1
        if not match:
            continue
        key, rest = match.groups()
        if rest.startswith("["):
            if not rest.endswith("]"):
                raise FrontmatterError(f"can't read the '{key}' list in the frontmatter")
            inner = rest[1:-1].strip()
            data[key] = [_unquote(v) for v in inner.split(",") if v.strip()] if inner else []
        elif rest:
            data[key] = _unquote(rest)
        else:
            items = []
            while idx < len(body) and (item := _BLOCK_ITEM.match(body[idx])):
                items.append(_unquote(item.group(1) or item.group(2)))
                idx += 1
            data[key] = items if items else ""
    return data


def tags(frontmatter: dict[str, str | list[str]]) -> set[str]:
    raw = frontmatter.get("tags", [])
    values = raw if isinstance(raw, list) else re.split(r"[,\s]+", raw)
    return {v.strip().lstrip("#") for v in values if v.strip()}


def set_frontmatter_key(text: str, key: str, value: str) -> str:
    """Set `key: value` in the frontmatter, changing nothing else in the note.

    Replaces the key's line if it is there (only when it is empty), otherwise adds
    the line just before the closing `---`, with the note's own line ending.
    """
    lines = text.splitlines(keepends=True)
    span = _frontmatter_span(lines)
    if span is None:
        raise FrontmatterError("the note has no frontmatter to write into")
    opening, closing = span
    newline = "\r\n" if lines[opening].endswith("\r\n") else "\n"
    new_line = f"{key}: {value}{newline}"
    for idx in range(opening + 1, closing):
        match = _KEY_LINE.match(lines[idx].rstrip("\r\n"))
        if match and match.group(1) == key:
            if match.group(2):
                raise FrontmatterError(f"'{key}' is already set; not overwriting it")
            ending = lines[idx][len(lines[idx].rstrip("\r\n")) :] or newline
            lines[idx] = f"{key}: {value}{ending}"
            return "".join(lines)
    lines.insert(closing, new_line)
    return "".join(lines)


def write_frontmatter_key(path: Path, key: str, value: str) -> None:
    """Set `key: value` in a note's frontmatter on disk, atomically."""
    with path.open(encoding="utf-8", newline="") as fh:
        text = fh.read()
    new_text = set_frontmatter_key(text, key, value)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".gh-inbox-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
