"""Effort notes in the vault: which ones are Synced efforts, and where Effort folders are.

A Synced effort is an Effort note that sits directly in one of the Effort folders and
carries the `gh` tag in its frontmatter. Its file name (without `.md`) is its title,
and the folder sets its Effort state and, while open, its Intensity.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import INTENSITIES
from .frontmatter import FrontmatterError, read_frontmatter, tags

SYNC_TAG = "gh"
INTENSITY_LABEL_PREFIX = "intensity/"


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


def missing_effort_folders(vault: Path, effort_folders: dict[str, str]) -> list[tuple[str, Path]]:
    """The Effort folders, by config key, that don't exist in the vault."""
    return [(key, vault / rel) for key, rel in effort_folders.items() if not (vault / rel).is_dir()]


def find_synced_efforts(
    vault: Path, effort_folders: dict[str, str], issue_key: str
) -> tuple[list[SyncedEffort], list[str]]:
    """Every Synced effort directly inside an Effort folder, plus warnings.

    Notes in subfolders, or anywhere else in the vault, are never synced. Check
    `missing_effort_folders` first; a folder that doesn't exist here raises.
    """
    efforts: list[SyncedEffort] = []
    warnings: list[str] = []
    for folder, rel in effort_folders.items():
        directory = vault / rel
        if not directory.is_dir():
            raise FileNotFoundError(f"Effort folder for '{folder}' not found: {directory}")
        for path in sorted(directory.glob("*.md")):
            if not path.is_file():
                continue
            try:
                frontmatter = read_frontmatter(path.read_text(encoding="utf-8"))
            except (FrontmatterError, UnicodeDecodeError) as exc:
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
