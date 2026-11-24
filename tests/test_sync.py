import copy
import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from conftest import HOST
from gh_inbox import cli
from gh_inbox.config import ConfigError, parse_config
from gh_inbox.efforts import find_synced_efforts, missing_effort_folders
from gh_inbox.frontmatter import FrontmatterError, read_frontmatter, set_frontmatter_key, tags
from gh_inbox.github import GhError

REPO = "me/efforts"
DEFAULT_FOLDERS = parse_config({"vault": {"path": "/v"}}).effort_folders


def issue(number, title, state="open", labels=(), state_reason=None, repo=REPO):
    return {
        "number": number,
        "html_url": f"https://{HOST}/{repo}/issues/{number}",
        "title": title,
        "state": state,
        "state_reason": state_reason,
        "labels": [{"name": name} for name in labels],
    }


class FakeSyncGh:
    """Stands in for `gh api` against the Personal repo: GET, POST and PATCH issues."""

    def __init__(self, issues=(), fail_numbers=()):
        self.issues = {raw["number"]: copy.deepcopy(raw) for raw in issues}
        self.fail_numbers = set(fail_numbers)
        self.calls: list[tuple[list[str], dict | None]] = []
        self.next_number = 100

    @property
    def writes(self):
        return [(args, body) for args, body in self.calls if "-X" in args]

    def __call__(self, args, input=None):
        args = list(args)
        body = json.loads(input) if input else None
        self.calls.append((args, body))
        path = next(a for a in args if a.startswith("repos/"))
        method = args[args.index("-X") + 1] if "-X" in args else "GET"
        if method == "POST":
            number, self.next_number = self.next_number, self.next_number + 1
            self.issues[number] = issue(number, body["title"], labels=body.get("labels", []))
            return json.dumps(self.issues[number])
        number = int(path.rsplit("/", 1)[1])
        if number in self.fail_numbers or number not in self.issues:
            raise GhError(f"`gh api {path}` failed: HTTP 404: Not Found")
        raw = self.issues[number]
        if method == "PATCH":
            for key, value in body.items():
                raw[key] = [{"name": n} for n in value] if key == "labels" else value
        return json.dumps(raw)


def existing_issues():
    """Issues behind the fixture notes, each out of step with its note."""
    return [
        # Simmering note: retitle, and swap intensity/on for intensity/simmering.
        issue(7, "Runbook", labels=["intensity/on", "area/ops"]),
        # Done note: still open with an Intensity label; close it and drop the label.
        issue(9, "Ship the pipeline", labels=["intensity/ongoing", "area/ci"]),
    ]


@pytest.fixture
def sync_config(tmp_path: Path, vault: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f'host = "{HOST}"\npersonal_repo = "{REPO}"\n\n[vault]\npath = "{vault.as_posix()}"\n',
        encoding="utf-8",
    )
    return path


@pytest.fixture
def gh(monkeypatch):
    fake = FakeSyncGh(existing_issues())
    monkeypatch.setattr(cli, "run_gh", fake)
    return fake


def run_sync(config_file, *args):
    return CliRunner().invoke(cli.main, ["--config", str(config_file), "sync", *args])


def snapshot(vault: Path) -> dict[str, bytes]:
    return {
        p.relative_to(vault).as_posix(): p.read_bytes() for p in vault.rglob("*") if p.is_file()
    }


# --- Finding Synced efforts ---------------------------------------------------------


def test_finds_only_tagged_notes_directly_in_effort_folders(vault):
    efforts, warnings = find_synced_efforts(vault, DEFAULT_FOLDERS, "gh-issue")
    found = {(e.folder, e.title) for e in efforts}
    assert found == {
        ("on", "Draft the platform plan"),
        ("simmering", "Runbook rewrite"),
        ("done", "Ship the pipeline"),
        ("canceled", "Old idea"),
    }
    assert warnings == []


def test_effort_state_and_intensity_come_from_the_folder(vault):
    efforts, _ = find_synced_efforts(vault, DEFAULT_FOLDERS, "gh-issue")
    by_title = {e.title: e for e in efforts}
    simmering = by_title["Runbook rewrite"]
    assert (simmering.effort_state, simmering.intensity) == ("open", "simmering")
    assert simmering.intensity_label == "intensity/simmering"
    done = by_title["Ship the pipeline"]
    assert (done.effort_state, done.intensity, done.intensity_label) == ("done", None, None)
    assert done.issue_url == f"https://{HOST}/{REPO}/issues/9"


@pytest.mark.parametrize(
    "frontmatter, expected",
    [
        ("tags: [gh, area/x]", {"gh", "area/x"}),
        ("tags:\n  - gh\n  - area/x", {"gh", "area/x"}),
        ("tags:\n- gh", {"gh"}),
        ("tags: gh area/x", {"gh", "area/x"}),
        ("tags: ['#gh']", {"gh"}),
        ("tags: []", set()),
        ("title: no tags", set()),
    ],
)
def test_reads_tags_in_the_shapes_obsidian_writes(frontmatter, expected):
    assert tags(read_frontmatter(f"---\n{frontmatter}\n---\nbody\n")) == expected


def test_note_without_frontmatter_has_no_tags():
    assert read_frontmatter("tags: [gh]\n") == {}


# --- Writing the Effort issue URL back ----------------------------------------------


def test_adds_issue_key_before_closing_fence_and_nothing_else():
    text = "---\ntags: [gh]\n---\n\nbody\n---\nnot frontmatter\n"
    out = set_frontmatter_key(text, "gh-issue", "U")
    assert out == "---\ntags: [gh]\ngh-issue: U\n---\n\nbody\n---\nnot frontmatter\n"


def test_keeps_crlf_line_endings():
    text = "---\r\ntags: [gh]\r\n---\r\nbody\r\n"
    out = set_frontmatter_key(text, "gh-issue", "U")
    assert out == "---\r\ntags: [gh]\r\ngh-issue: U\r\n---\r\nbody\r\n"


def test_fills_an_empty_issue_key_in_place():
    text = "---\ngh-issue:\ntags: [gh]\n---\n"
    assert set_frontmatter_key(text, "gh-issue", "U") == "---\ngh-issue: U\ntags: [gh]\n---\n"


def test_never_overwrites_an_existing_issue_url():
    with pytest.raises(FrontmatterError):
        set_frontmatter_key("---\ngh-issue: A\n---\n", "gh-issue", "B")


# --- Missing Effort folders ---------------------------------------------------------


def test_missing_effort_folders_are_listed_by_key(vault):
    (vault / "Efforts/Sleeping/.gitkeep").unlink()
    (vault / "Efforts/Sleeping").rmdir()
    assert missing_effort_folders(vault, DEFAULT_FOLDERS) == [
        ("sleeping", vault / "Efforts/Sleeping")
    ]


@pytest.mark.parametrize("flag", [(), ("--dry-run",)])
def test_a_missing_effort_folder_stops_sync_before_github(sync_config, vault, gh, flag):
    for name in ("Sleeping", "Ongoing"):
        (vault / f"Efforts/{name}/.gitkeep").unlink()
        (vault / f"Efforts/{name}").rmdir()
    before = snapshot(vault)
    result = run_sync(sync_config, *flag)
    assert result.exit_code == 1
    assert "Effort folders not found" in result.output
    assert f"ongoing: {vault / 'Efforts/Ongoing'}" in result.output
    assert f"sleeping: {vault / 'Efforts/Sleeping'}" in result.output
    assert "or create them in the vault" in result.output
    assert "Sync stopped before touching GitHub" in result.output
    assert gh.calls == []
    assert snapshot(vault) == before


# --- sync --dry-run -----------------------------------------------------------------


def test_dry_run_prints_every_planned_action_and_writes_nothing(sync_config, vault, gh):
    before = snapshot(vault)
    result = run_sync(sync_config, "--dry-run")
    assert result.exit_code == 0, result.output
    out = result.output
    assert 'create  "Draft the platform plan" in me/efforts, label intensity/on' in out
    assert "then write gh-issue into Efforts/On/Draft the platform plan.md" in out
    assert (
        'update  #7 "Runbook rewrite": retitle from "Runbook"; +intensity/simmering -intensity/on'
        in out
    )
    assert 'update  #9 "Ship the pipeline": close as completed; -intensity/ongoing' in out
    assert "skip    Efforts/Canceled/Old idea.md" in out
    assert "Dry run: nothing was written." in out
    assert gh.writes == []
    assert snapshot(vault) == before


# --- sync -------------------------------------------------------------------------


def test_creates_effort_issue_and_writes_its_url_into_the_note(sync_config, vault, gh):
    note = vault / "Efforts/On/Draft the platform plan.md"
    before = note.read_text(encoding="utf-8")
    result = run_sync(sync_config)
    assert result.exit_code == 0, result.output

    creates = [body for args, body in gh.writes if "POST" in args]
    assert creates == [{"title": "Draft the platform plan", "labels": ["intensity/on"]}]
    url = f"https://{HOST}/{REPO}/issues/100"
    after = note.read_text(encoding="utf-8")
    # The rest of the note is byte-for-byte unchanged.
    assert after == before.replace("---\n\n", f"gh-issue: {url}\n---\n\n", 1)


def test_retitles_and_replaces_the_intensity_label(sync_config, gh):
    assert run_sync(sync_config).exit_code == 0
    assert gh.issues[7]["title"] == "Runbook rewrite"
    assert [label["name"] for label in gh.issues[7]["labels"]] == [
        "area/ops",
        "intensity/simmering",
    ]
    assert gh.issues[7]["state"] == "open"


def test_done_closes_as_completed_and_drops_the_intensity_label(sync_config, gh):
    assert run_sync(sync_config).exit_code == 0
    raw = gh.issues[9]
    assert (raw["state"], raw["state_reason"]) == ("closed", "completed")
    assert [label["name"] for label in raw["labels"]] == ["area/ci"]


def test_canceled_closes_as_not_planned(sync_config, vault, gh):
    note = vault / "Efforts/Canceled/Old idea.md"
    note.write_text(f"---\ntags: gh\ngh-issue: https://{HOST}/{REPO}/issues/9\n---\n")
    (vault / "Efforts/Done/Ship the pipeline.md").unlink()
    assert run_sync(sync_config).exit_code == 0
    assert (gh.issues[9]["state"], gh.issues[9]["state_reason"]) == ("closed", "not_planned")


def test_moving_back_to_an_intensity_folder_reopens_and_sets_intensity(sync_config, vault, gh):
    gh.issues[9].update(state="closed", state_reason="completed", labels=[])
    done = vault / "Efforts/Done/Ship the pipeline.md"
    done.rename(vault / "Efforts/On/Ship the pipeline.md")
    assert run_sync(sync_config).exit_code == 0
    raw = gh.issues[9]
    assert raw["state"] == "open"
    assert [label["name"] for label in raw["labels"]] == ["intensity/on"]


def test_second_run_is_a_no_op(sync_config, vault, gh):
    assert run_sync(sync_config).exit_code == 0
    writes = len(gh.writes)
    result = run_sync(sync_config)
    assert result.exit_code == 0, result.output
    assert len(gh.writes) == writes
    assert "Planned: 0 create, 0 update, 3 unchanged, 1 skipped" in result.output


def test_terminal_note_without_an_issue_is_skipped_not_created(sync_config, gh):
    assert run_sync(sync_config).exit_code == 0
    titles = [body["title"] for args, body in gh.writes if "POST" in args]
    assert "Old idea" not in titles


# --- Safety -------------------------------------------------------------------------


def test_never_touches_an_issue_outside_the_personal_repo(sync_config, vault, gh):
    team = f"https://{HOST}/acme/team-repo/issues/3"
    (vault / "Efforts/Done/Ship the pipeline.md").write_text(
        f"---\ntags: [gh]\ngh-issue: {team}\n---\n"
    )
    result = run_sync(sync_config)
    assert result.exit_code == 1
    assert "not in the Personal repo" in result.output
    assert not any("acme/team-repo" in arg for args, _ in gh.calls for arg in args)
    # The other Synced efforts still sync.
    assert gh.issues[7]["title"] == "Runbook rewrite"


def test_an_issue_that_moved_out_of_the_personal_repo_is_left_alone(sync_config, gh):
    gh.issues[7]["html_url"] = f"https://{HOST}/acme/team-repo/issues/41"
    result = run_sync(sync_config)
    assert result.exit_code == 1
    assert "not in the Personal repo" in result.output
    assert not any("issues/7" in args[-3] for args, _ in gh.writes)


def test_an_issue_url_in_two_notes_is_an_error_for_both(sync_config, vault, gh):
    url = f"https://{HOST}/{REPO}/issues/7"
    (vault / "Efforts/Done/Ship the pipeline.md").write_text(
        f"---\ntags: [gh]\ngh-issue: {url}\n---\n"
    )
    result = run_sync(sync_config)
    assert result.exit_code == 1
    assert result.output.count("more than one Effort note") == 2
    assert not any("issues/7" in args[-3] for args, _ in gh.writes)


def test_a_failed_lookup_is_reported_and_the_rest_carry_on(sync_config, gh):
    gh.fail_numbers.add(7)
    result = run_sync(sync_config)
    assert result.exit_code == 1
    assert "Efforts/Simmering/Runbook rewrite.md" in result.output and "404" in result.output
    assert gh.issues[9]["state"] == "closed"


def test_a_pull_request_url_is_rejected(sync_config, gh):
    gh.issues[7]["pull_request"] = {"url": "..."}
    result = run_sync(sync_config)
    assert result.exit_code == 1
    assert "is a pull request" in result.output


def test_sync_requires_personal_repo(config_file, gh):
    result = CliRunner().invoke(cli.main, ["--config", str(config_file), "sync", "--dry-run"])
    assert result.exit_code == 1
    assert "personal_repo" in result.output
    assert gh.calls == []


def test_config_flag_after_sync_works(sync_config, gh):
    result = CliRunner().invoke(cli.main, ["sync", "--config", str(sync_config), "--dry-run"])
    assert result.exit_code == 0, result.output


# --- Config -------------------------------------------------------------------------


def test_effort_folders_default_and_override():
    cfg = parse_config({"vault": {"path": "/v"}, "efforts": {"on": "Work/On/"}})
    assert cfg.effort_folders["on"] == "Work/On"
    assert cfg.effort_folders["canceled"] == "Efforts/Canceled"
    assert cfg.issue_key == "gh-issue" and cfg.personal_repo is None


@pytest.mark.parametrize(
    "data",
    [
        {"efforts": {"active": "Efforts/Active"}},
        {"personal_repo": "no-slash"},
        {"frontmatter": {"issue_key": "bad:key"}},
    ],
)
def test_bad_sync_config_is_rejected(data):
    with pytest.raises(ConfigError):
        parse_config({"vault": {"path": "/v"}, **data})
