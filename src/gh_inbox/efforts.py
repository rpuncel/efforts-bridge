"""Find Synced efforts in the vault and write the Effort issue URL back into a note.

A Synced effort is an Effort note that sits directly in one of the Effort folders and
carries the `gh` tag in its frontmatter. Its file name (without `.md`) is its title,
and the folder sets its Effort state and, while open, its Intensity.

Frontmatter is read with a deliberately small parser: top-level `key: value` lines,
flow lists (`[a, b]`) and block lists (`- a`). That covers what Obsidian's Properties
editor writes. The only write is one `<issue_key>: <url>` line; every other byte of
the note is left as it was.
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .config import INTENSITIES

SYNC_TAG = "gh"
INTENSITY_LABEL_PREFIX = "intensity/"

_FENCE = re.compile(r"^---[ \t]*(\r?\n|$)")
_KEY_LINE = re.compile(r"^([A-Za-z0-9_][A-Za-z0-9_-]*):[ \t]*(.*?)[ \t]*$")
_BLOCK_ITEM = re.compile(r"^[ \t]+-[ \t]+(.*?)[ \t]*$|^-[ \t]+(.*?)[ \t]*$")


class EffortNoteError(Exception):
    """Raised when an Effort note's frontmatter can't be read or written safely."""


@dataclass(frozen=True)
class SyncedEffort:
    """An Effort note that has opted in to Sync."""

    path: Path
    folder: str  # Effort folder key: an Intensity, "done" or "canceled"
    issue_url: str | None

    @property
    def title(self) -> str:
        return self.path.stem

    @property
    def intensity(self) -> str | None:
        """The Intensity while open; done and canceled Efforts have none."""
        return self.folder if self.folder in INTENSITIES else None

    @property
    def effort_state(self) -> str:
        return "open" if self.intensity else self.folder

    @property
    def intensity_label(self) -> str | None:
        return f"{INTENSITY_LABEL_PREFIX}{self.intensity}" if self.intensity else None


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
                raise EffortNoteError(f"can't read the '{key}' list in the frontmatter")
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
        raise EffortNoteError("the note has no frontmatter to write into")
    opening, closing = span
    newline = "\r\n" if lines[opening].endswith("\r\n") else "\n"
    new_line = f"{key}: {value}{newline}"
    for idx in range(opening + 1, closing):
        match = _KEY_LINE.match(lines[idx].rstrip("\r\n"))
        if match and match.group(1) == key:
            if match.group(2):
                raise EffortNoteError(f"'{key}' is already set; not overwriting it")
            ending = lines[idx][len(lines[idx].rstrip("\r\n")) :] or newline
            lines[idx] = f"{key}: {value}{ending}"
            return "".join(lines)
    lines.insert(closing, new_line)
    return "".join(lines)


def write_issue_url(path: Path, key: str, url: str) -> None:
    """Write the Effort issue URL into the note's frontmatter, atomically."""
    with path.open(encoding="utf-8", newline="") as fh:
        text = fh.read()
    new_text = set_frontmatter_key(text, key, url)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".gh-inbox-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(new_text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def find_synced_efforts(
    vault: Path, effort_folders: dict[str, str], issue_key: str
) -> tuple[list[SyncedEffort], list[str]]:
    """Every Synced effort directly inside an Effort folder, plus warnings.

    Notes in subfolders, or anywhere else in the vault, are never synced.
    """
    efforts: list[SyncedEffort] = []
    warnings: list[str] = []
    for folder, rel in effort_folders.items():
        directory = vault / rel
        if not directory.is_dir():
            warnings.append(f"Effort folder for '{folder}' not found: {directory}")
            continue
        for path in sorted(directory.glob("*.md")):
            if not path.is_file():
                continue
            try:
                frontmatter = read_frontmatter(path.read_text(encoding="utf-8"))
            except (EffortNoteError, UnicodeDecodeError) as exc:
                warnings.append(f"{path}: skipped, {exc}")
                continue
            if SYNC_TAG not in tags(frontmatter):
                continue
            url = frontmatter.get(issue_key)
            if isinstance(url, list):
                warnings.append(f"{path}: skipped, '{issue_key}' must be a single URL")
                continue
            efforts.append(SyncedEffort(path=path, folder=folder, issue_url=url or None))
    return efforts, warnings
