import json
import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
HOST = "github.example.com"


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    dest = tmp_path / "vault"
    shutil.copytree(FIXTURES / "vault", dest)
    return dest


@pytest.fixture
def config_file(tmp_path: Path, vault: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f'[github]\nhost = "{HOST}"\n\n[vault]\npath = "{vault.as_posix()}"\n',
        encoding="utf-8",
    )
    return path


def search_payload(*items: dict) -> str:
    return json.dumps(
        {"total_count": len(items), "incomplete_results": False, "items": list(items)}
    )


def search_item(number: int, title: str, updated: str, repo: str = "acme/widgets", pr=True) -> dict:
    raw = {
        "html_url": f"https://{HOST}/{repo}/{'pull' if pr else 'issues'}/{number}",
        "title": title,
        "repository_url": f"https://{HOST}/api/v3/repos/{repo}",
        "updated_at": updated,
    }
    if pr:
        raw["pull_request"] = {"url": "..."}
    return raw


def notification(
    number: int, title: str, updated: str, reason: str, repo: str = "acme/widgets", kind="Issue"
) -> dict:
    seg = "pulls" if kind == "PullRequest" else "issues"
    return {
        "unread": True,
        "reason": reason,
        "updated_at": updated,
        "subject": {
            "title": title,
            "type": kind,
            "url": f"https://{HOST}/api/v3/repos/{repo}/{seg}/{number}",
        },
        "repository": {"full_name": repo, "html_url": f"https://{HOST}/{repo}"},
    }


class FakeGh:
    """Stands in for `gh`: routes by endpoint and query, records calls."""

    def __init__(self, review="", notifications="[]", assigned="", fail=()):
        self.outputs = {
            "review_requests": review or search_payload(),
            "notifications": notifications,
            "assigned": assigned or search_payload(),
        }
        self.fail = set(fail)
        self.calls: list[list[str]] = []

    def __call__(self, args):
        from gh_inbox.github import GhError

        args = list(args)
        self.calls.append(args)
        if "notifications" in args:
            source = "notifications"
        elif any("review-requested:@me" in a for a in args):
            source = "review_requests"
        else:
            source = "assigned"
        if source in self.fail:
            raise GhError(f"boom ({source})")
        return self.outputs[source]
