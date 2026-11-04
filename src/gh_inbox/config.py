"""Load and validate the TOML config file."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("~/.config/gh-inbox/config.toml")

ALL_SOURCES = ("review_requests", "notifications", "assigned")

# Notification reasons that count as "waiting on you" (mentions and direct replies).
# See https://docs.github.com/rest/activity/notifications#about-notification-reasons
DEFAULT_WAITING_REASONS = (
    "review_requested",
    "mention",
    "team_mention",
    "author",  # activity on a thread you opened
    "comment",  # activity on a thread you commented on
)


class ConfigError(Exception):
    """Raised when the config file is missing or invalid."""


@dataclass(frozen=True)
class InboxConfig:
    waiting_max: int = 10
    waiting_days: int = 7
    oldest_max: int = 5
    waiting_reasons: tuple[str, ...] = DEFAULT_WAITING_REASONS
    sources: tuple[str, ...] = ALL_SOURCES


@dataclass(frozen=True)
class Config:
    host: str
    vault_path: Path
    daily_folder: str = "Calendar/Daily Notes"
    daily_format: str = "YYYY-MM-DD"
    inbox: InboxConfig = field(default_factory=InboxConfig)

    @property
    def daily_dir(self) -> Path:
        return self.vault_path / self.daily_folder


def _get(table: dict, key: str, typ: type | tuple[type, ...], where: str, default=None):
    value = table.get(key, default)
    if value is None:
        raise ConfigError(f"missing required key '{where}.{key}'")
    if not isinstance(value, typ) or (typ is int and isinstance(value, bool)):
        raise ConfigError(f"'{where}.{key}' has the wrong type: {value!r}")
    return value


def _str_list(table: dict, key: str, where: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = table.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ConfigError(f"'{where}.{key}' must be a list of strings")
    return tuple(value)


def parse_config(data: dict) -> Config:
    github = data.get("github", {})
    vault = data.get("vault", {})
    daily = data.get("daily_notes", {})
    inbox = data.get("inbox", {})

    host = _get(github, "host", str, "github").strip()
    if not host or "/" in host:
        raise ConfigError("'github.host' must be a bare hostname, e.g. github.example.com")

    defaults = InboxConfig()
    inbox_cfg = InboxConfig(
        waiting_max=_get(inbox, "waiting_max", int, "inbox", defaults.waiting_max),
        waiting_days=_get(inbox, "waiting_days", int, "inbox", defaults.waiting_days),
        oldest_max=_get(inbox, "oldest_max", int, "inbox", defaults.oldest_max),
        waiting_reasons=_str_list(inbox, "waiting_reasons", "inbox", defaults.waiting_reasons),
        sources=_str_list(inbox, "sources", "inbox", defaults.sources),
    )
    for name in ("waiting_max", "waiting_days", "oldest_max"):
        if getattr(inbox_cfg, name) < 0:
            raise ConfigError(f"'inbox.{name}' must not be negative")
    unknown = set(inbox_cfg.sources) - set(ALL_SOURCES)
    if unknown:
        raise ConfigError(
            f"unknown 'inbox.sources' entries {sorted(unknown)}; valid: {list(ALL_SOURCES)}"
        )

    fmt = _get(daily, "format", str, "daily_notes", "YYYY-MM-DD")
    if fmt.endswith(".md"):
        fmt = fmt[: -len(".md")]

    return Config(
        host=host,
        vault_path=Path(_get(vault, "path", str, "vault")).expanduser(),
        daily_folder=_get(daily, "folder", str, "daily_notes", "Calendar/Daily Notes"),
        daily_format=fmt,
        inbox=inbox_cfg,
    )


def load_config(path: Path) -> Config:
    path = path.expanduser()
    if not path.is_file():
        raise ConfigError(
            f"config file not found: {path}\n"
            "Copy config.example.toml there and fill in your values, or pass --config."
        )
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"could not parse {path}: {exc}") from exc
    try:
        return parse_config(data)
    except ConfigError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
