"""Tests of the override that the release bot writes into each merged pull request
for release-please, against a simulated GitHub."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Sequence
from typing import Any

import pytest

from blueprint import cli
from blueprint.github import Api
from blueprint.overrides import (
    END,
    START,
    matters,
    override,
    since_last_release,
    with_override,
    write_overrides,
)

REPO = "Dennis-Otto/demo"
TAG = "v1.0.7"
# The squash commit of a security update of Renovate, whose description quotes the
# release notes and an advisory: the line with print( made release-please skip it.
RENOVATE = """\
fix(deps): update dependency pillow to v13 [security] (#383)

This PR contains the following updates:

| Package | Change |
|---|---|
| pillow | `==12.3.0` → `==13.0.0` |

##### `trigger.py`

```python
print("format=%s mode=%s size=%s" % (im.format, im.mode, im.size), flush=True)
```

**[(Full
Changelog)](https://redirect.github.com/python-pillow/Pillow/compare/12.3.0...13.0.0)**

Signed-off-by: dennis-otto-release-automation[bot] <bot@users.noreply.github.com>
"""


def commit(sha: str, message: str) -> dict[str, Any]:
    """A commit as the compare and the list of commits of GitHub show it."""
    return {"sha": sha, "commit": {"message": message}}


def merged(number: int, sha: str, body: str | None = "The description.") -> Any:
    """A pull request whose squash merge made the commit, as GitHub lists it."""
    return {
        "number": number,
        "merge_commit_sha": sha,
        "merged_at": "2026-10-22T10:00:00Z",
        "body": body,
    }


class FakeGitHub:
    """The parts of GitHub's API that the release bot's overrides use."""

    def __init__(self, commits: Sequence[dict[str, Any]], *, released: bool = True):
        self.released = released
        self.commits = list(commits)
        # The commits that the compare of the latest release and main lists, at most;
        # None when GitHub no longer knows the tag.
        self.compared: int | None = len(self.commits)
        self.pulls: dict[str, list[Any]] = {}
        self.edited: list[tuple[int, str]] = []
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        code, data = self.route(method, path, json.loads(body) if body else None)
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if code < 400 else 1,
            f"HTTP/2.0 {code} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        own = f"repos/{REPO}"
        if (method, path) == ("GET", own):
            return 200, {"default_branch": "main"}
        if (method, path) == ("GET", f"{own}/releases/latest"):
            return (200, {"tag_name": TAG}) if self.released else (404, None)
        found = re.fullmatch(
            rf"{own}/compare/{TAG}\.\.\.main\?per_page=100&page=(\d+)", path
        )
        if method == "GET" and found:
            if self.compared is None:
                return 404, None
            page = int(found[1])
            listed = self.commits[: self.compared]
            return 200, {
                "total_commits": len(self.commits),
                "commits": listed[(page - 1) * 100 : page * 100],
            }
        if (method, path) == ("GET", f"{own}/commits?sha=main&per_page=100"):
            return 200, list(reversed(self.commits))[:100]
        found = re.fullmatch(rf"{own}/commits/(\w+)/pulls", path)
        if method == "GET" and found:
            return 200, self.pulls.get(found[1], [])
        found = re.fullmatch(rf"{own}/pulls/(\d+)", path)
        if method == "PATCH" and found:
            self.edited.append((int(found[1]), body["body"]))
            return 200, {}
        raise AssertionError(f"unexpected request {method} {path}")


@pytest.mark.parametrize(
    ("message", "wanted"),
    [
        ("fix(deps): update pillow (#1)", True),
        ("feat: a dark mode (#2)\n\nThe body.", True),
        ("perf: faster (#3)", True),
        ("revert: the dark mode (#4)", True),
        ("refactor!: drop the old settings (#5)", True),
        ("docs: the guide (#6)\n\nBREAKING CHANGE: the guide moves", True),
        ("chore: tidy (#7)\n\nRelease-As: 2.0.0", True),
        ("chore: tidy (#8)\n\nrelease-as: v2.0.0", True),
        ("docs: a typo (#9)", False),
        ("chore(deps): update ruff (#10)\n\n**[(Full", False),
        ("chore: release 1.0.8 (#11)", False),
        ("Merge branch 'main'", False),
        ("chore: tidy (#12)\n\nWe talk about Release-As: in the text.", False),
    ],
)
def test_only_a_commit_that_can_change_the_release_matters(
    message: str, wanted: bool
) -> None:
    assert matters(message) is wanted


def test_the_override_is_the_title_and_the_lines_that_release_please_reads() -> None:
    message = (
        "feat!: move the settings (#12)\r\n\r\nSome (text\nRelease-As: 2.0.0  \n"
        "BREAKING CHANGE: the settings move (see the guide\n"
        "Signed-off-by: A Person <a@example.com>\n"
    ).replace("\r\n", "\n")

    assert override(message) == (
        "feat!: move the settings (#12)\n\n"
        "Release-As: 2.0.0\n"
        "BREAKING CHANGE: the settings move (see the guide"
    )
    assert override(RENOVATE) == (
        "fix(deps): update dependency pillow to v13 [security] (#383)"
    )


def test_the_override_is_hidden_at_the_end_of_the_description() -> None:
    assert with_override("The description.\n\n", "fix: x (#1)") == (
        f"The description.\n\n<!-- {START}\nfix: x (#1)\n{END} -->"
    )
    assert (
        with_override("  \n", "fix: x (#1)") == f"<!-- {START}\nfix: x (#1)\n{END} -->"
    )


def test_release_please_reads_only_the_override_of_the_description() -> None:
    # As release-please's preprocessCommitMessage takes it: the text between the
    # markers, trimmed, also inside the HTML comment.
    body = with_override("Fixes #1.\n\n| a | b |", "fix: x (#1)\n\nRelease-As: 1.0.0")
    read = body.split(START)[1].split(END)[0].strip()

    assert read == "fix: x (#1)\n\nRelease-As: 1.0.0"


def test_a_fix_whose_description_breaks_the_parser_gets_its_override() -> None:
    github = FakeGitHub(
        [
            commit("a1", RENOVATE),
            commit("b2", "docs: the guide (#384)\n\nA (b"),
            commit("c3", "chore: release 1.0.8 (#385)\n\nThe notes."),
        ]
    )
    github.pulls = {"a1": [merged(383, "a1")], "b2": [merged(384, "b2")]}

    summary = write_overrides(Api(github), REPO)

    assert github.edited == [
        (
            383,
            f"The description.\n\n<!-- {START}\n"
            f"fix(deps): update dependency pillow to v13 [security] (#383)\n{END} -->",
        )
    ]
    # A commit of a kind that changes nothing of the release is left alone.
    assert ("GET", f"repos/{REPO}/commits/b2/pulls") not in github.calls
    assert summary == (
        "release-please reads the title of these pull requests instead of their"
        " description, which its parser might not take:\n\n"
        "- #383: release-please reads"
        " `fix(deps): update dependency pillow to v13 [security] (#383)`\n"
    )


def test_a_pull_request_with_an_override_or_without_more_is_left_alone() -> None:
    github = FakeGitHub(
        [
            commit("a1", "fix: x (#1)\n\nThe body."),
            commit("b2", "fix: y (#2)"),
            commit("c3", "fix: z (#3)\n\nPushed without a pull request."),
            commit("d4", "fix: w (#4)\n\nThe body."),
        ]
    )
    own = f"<!-- {START}\nfix: w, as the author wants it (#4)\n{END} -->"
    github.pulls = {
        "a1": [merged(1, "a1", f"Text.\n\n<!-- {START}\nfix: x (#1)\n{END} -->")],
        # A pull request that only names the commit, not the one whose merge made it.
        "c3": [{**merged(9, "c3"), "merged_at": None}, merged(10, "other")],
        "d4": [merged(4, "d4", own)],
    }

    summary = write_overrides(Api(github), REPO)

    assert github.edited == []
    # A message that is its own override parses as it is.
    assert ("GET", f"repos/{REPO}/commits/b2/pulls") not in github.calls
    assert summary == (
        "No merged pull request since the last release needs an override.\n"
    )


def test_an_empty_description_gets_the_override_alone() -> None:
    github = FakeGitHub(
        [commit("a1", "feat: a dark mode (#7)\n\nSigned-off-by: A <a@b.c>")]
    )
    github.pulls = {"a1": [merged(7, "a1", None)]}

    write_overrides(Api(github), REPO)

    assert github.edited == [(7, f"<!-- {START}\nfeat: a dark mode (#7)\n{END} -->")]


def shas(github: FakeGitHub) -> list[str]:
    return [each["sha"] for each in since_last_release(Api(github), REPO, "main")]


def test_the_commits_since_the_last_release_come_from_every_page() -> None:
    github = FakeGitHub([commit(f"c{index}", "docs: x") for index in range(230)])

    assert shas(github) == [f"c{index}" for index in range(230)]
    assert [path for _, path in github.calls if "/compare/" in path] == [
        f"repos/{REPO}/compare/{TAG}...main?per_page=100&page={page}"
        for page in (1, 2, 3)
    ]


def test_the_compare_stops_at_a_page_without_commits() -> None:
    github = FakeGitHub([commit(f"c{index}", "docs: x") for index in range(150)])
    # GitHub lists 100 of the 150 commits, and its second page is empty.
    github.compared = 100

    assert shas(github) == [f"c{index}" for index in range(100)]


def test_the_compare_reads_at_most_the_commits_that_github_compares() -> None:
    # GitHub's compare lists 250 commits at most, and three pages hold them.
    github = FakeGitHub([commit(f"c{index}", "docs: x") for index in range(400)])

    assert len(shas(github)) == 300
    assert len([path for _, path in github.calls if "/compare/" in path]) == 3


def test_before_the_first_release_the_latest_commits_of_the_branch_count() -> None:
    github = FakeGitHub(
        [commit("a1", "fix: x"), commit("b2", "fix: y")], released=False
    )

    assert shas(github) == ["b2", "a1"]


def test_a_tag_that_github_no_longer_knows_falls_back_to_the_latest_commits() -> None:
    github = FakeGitHub([commit("a1", "fix: x")])
    github.compared = None

    assert shas(github) == ["a1"]


def test_a_later_page_that_github_no_longer_has_ends_the_commits() -> None:
    github = FakeGitHub([commit(f"c{index}", "docs: x") for index in range(150)])

    real = github.route

    def route(method: str, path: str, body: Any) -> tuple[int, Any]:
        if path.endswith("page=2"):
            return 404, None
        return real(method, path, body)

    github.route = route  # type: ignore[method-assign]

    assert shas(github) == [f"c{index}" for index in range(100)]


def test_the_command_prints_the_summary(capsys: pytest.CaptureFixture[str]) -> None:
    github = FakeGitHub([commit("a1", RENOVATE)])
    github.pulls = {"a1": [merged(383, "a1")]}

    assert cli.main(["--repo", REPO, "commit-overrides"], api=Api(github)) == 0
    assert "- #383: release-please reads" in capsys.readouterr().out
    assert [number for number, _ in github.edited] == [383]
