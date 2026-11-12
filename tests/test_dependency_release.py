"""Tests of the decision whether a release of dependency updates merges itself
(decision 0087), against a simulated GitHub."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from blueprint import cli
from blueprint.dependency_release import (
    FIRST,
    HELD,
    LATER,
    NOW,
    Verdict,
    decide,
    dependency_release,
    holds_back,
)
from blueprint.github import Api

REPO = "Dennis-Otto/demo"
BOT = {"login": "dennis-otto-release-automation[bot]", "type": "Bot"}
PERSON = {"login": "Dennis-Otto", "type": "User"}
UPDATE = "fix(deps): update the issue assistant to v1.10.6 (#814)"


def commit(message: str, author: Any = BOT) -> dict[str, Any]:
    """A commit as GitHub's compare lists it, by default one of the release app."""
    return {"sha": "a1", "commit": {"message": message}, "author": author}


@pytest.mark.parametrize(
    ("message", "author", "holds"),
    [
        # Dependency updates, by whoever titled them so, as before.
        (UPDATE, BOT, False),
        ("chore(deps-dev): update mypy (#2)", PERSON, False),
        ("build(deps): pin the image (#3)", BOT, False),
        ("fix(deps): update ruff (#4)\r\n\r\n**[(Full\r\n", BOT, False),
        # A bot's commit that release-please makes nothing of: the issue of #841.
        ("docs: renew the pictures (#813)", BOT, False),
        ("chore: update to the blueprint v1.2.3 (#40)", BOT, False),
        ("docs: update the screenshots (#41)", BOT, False),
        # A person's change waits, whether release-please lists it or not.
        ("feat: a dark mode (#5)", PERSON, True),
        ("fix: the dark mode (#6)", PERSON, True),
        ("docs: a typo (#7)", PERSON, True),
        ("refactor: tidy the template (#8)", PERSON, True),
        ("docs: a typo (#9)", None, True),
        ("docs: a typo (#9)", {"login": "ghost"}, True),
        # A change for users of a bot is in the release too.
        ("fix: a bot's fix (#10)", BOT, True),
        ("Merge branch 'main'", PERSON, True),
        # A version of its own: a hidden type with !, Release-As or BREAKING CHANGE.
        ("chore!: drop Python 3.12 (#11)", BOT, True),
        ("docs: the guide (#12)\n\nRelease-As: 2.0.0", BOT, True),
        ("docs: the guide (#13)\n\nBREAKING CHANGE: the guide moves", BOT, True),
        ("fix(deps)!: update the runtime to v2 (#14)", BOT, True),
        (f"{UPDATE}\n\nBREAKING CHANGE: the old API goes", BOT, True),
        (f"{UPDATE}\n\nRelease-As: 2.0.0", BOT, True),
        ("fix(depsy): no update (#15)", BOT, True),
    ],
)
def test_only_a_change_beside_the_dependency_updates_holds_the_release_back(
    message: str, author: Any, holds: bool
) -> None:
    assert holds_back(commit(message, author)) is holds


def test_the_release_of_841_merges_itself_in_the_daily_run() -> None:
    commits = [commit("docs: renew the pictures (#813)"), commit(UPDATE)]

    assert decide(commits, "schedule") == Verdict(True, NOW)
    assert decide(commits, "workflow_dispatch") == Verdict(True, NOW)
    # The run of the merge leaves it to the daily run, as with the updates alone.
    assert decide(commits, "push") == Verdict(False, LATER)


def test_a_release_with_a_change_of_a_person_waits_and_names_it() -> None:
    commits = [
        commit(UPDATE),
        commit("feat: a dark mode (#5)\n\nThe body.", PERSON),
        commit("docs: renew the pictures (#813)"),
        commit("docs: the guide (#12)\r\n\r\nRelease-As: 2.0.0"),
    ]

    assert decide(commits, "schedule") == Verdict(
        False, f"{HELD}\nfeat: a dark mode (#5)\ndocs: the guide (#12)"
    )


@pytest.mark.parametrize(
    ("titles", "merges"),
    [
        (["fix(deps): update ruff (#7)", "chore(deps): update uv (#8)"], False),
        (["fix(deps): update ruff (#7)", "fix(deps): update uv [SECURITY] (#8)"], True),
        (["fix(deps): update pillow to v13 [security] (#9)"], True),
        (["docs: renew the pictures (#813)"], False),
    ],
)
def test_a_fix_of_a_vulnerability_merges_in_the_run_of_its_merge(
    titles: list[str], merges: bool
) -> None:
    verdict = decide([commit(title) for title in titles], "push")

    assert verdict == (Verdict(True, NOW) if merges else Verdict(False, LATER))


class FakeGitHub:
    """The parts of GitHub's API that the decision reads."""

    def __init__(self, commits: Sequence[dict[str, Any]], *, released: bool = True):
        self.commits = list(commits)
        self.released = released

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        method, path = arguments[3], arguments[4]
        code, data = self.route(method, path)
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if code < 400 else 1,
            f"HTTP/2.0 {code} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def route(self, method: str, path: str) -> tuple[int, Any]:
        own = f"repos/{REPO}"
        assert method == "GET", f"the decision only reads: {method} {path}"
        if path == own:
            return 200, {"default_branch": "main"}
        if path == f"{own}/releases/latest":
            return (200, {"tag_name": "v1.17.0"}) if self.released else (404, None)
        if path == f"{own}/compare/v1.17.0...main?per_page=100&page=1":
            return 200, {"total_commits": len(self.commits), "commits": self.commits}
        raise AssertionError(f"unexpected request {method} {path}")


def test_the_commits_since_the_latest_release_decide() -> None:
    github = FakeGitHub([commit("docs: renew the pictures (#813)"), commit(UPDATE)])

    assert dependency_release(Api(github), REPO, "schedule") == Verdict(True, NOW)


def test_the_first_release_waits_for_the_maintainer() -> None:
    github = FakeGitHub([commit(UPDATE)], released=False)

    assert dependency_release(Api(github), REPO, "schedule") == Verdict(False, FIRST)


@pytest.mark.parametrize(
    ("commits", "line", "said"),
    [
        ([commit(UPDATE)], "merge=true", NOW),
        ([commit("feat: a dark mode (#5)", PERSON)], "merge=false", HELD),
    ],
)
def test_the_command_writes_the_verdict_for_the_step(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    commits: list[dict[str, Any]],
    line: str,
    said: str,
) -> None:
    output = tmp_path / "dependency-only"
    argv = ["--repo", REPO, "release", "dependency-only", "--event", "schedule"]

    code = cli.main([*argv, "--output", str(output)], api=Api(FakeGitHub(commits)))

    assert code == 0
    assert output.read_text(encoding="utf-8") == f"{line}\n"
    assert capsys.readouterr().out.startswith(said)
