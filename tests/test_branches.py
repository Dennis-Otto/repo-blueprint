"""Tests of the branch bot against a simulated GitHub."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Sequence
from typing import Any

import pytest

from blueprint import cli
from blueprint.branches import (
    CONFLICT_COMMENT,
    FIELDS,
    LIMIT,
    MARKER,
    NO_TIME,
    Pull,
    State,
    latest_checks,
    next_branch,
    state_of,
    waiting,
)
from blueprint.github import Api, GitHubError
from blueprint.update import LABEL

REPO = "Dennis-Otto/demo"
REQUIRED = ("check (python)", "lint")
EARLY = "2026-10-17T08:00:00Z"
LATER = "2026-10-17T09:00:00Z"
LATEST = "2026-10-17T10:00:00Z"


def run(
    name: str,
    conclusion: str | None = "SUCCESS",
    *,
    status: str = "COMPLETED",
    started: str = EARLY,
) -> dict[str, Any]:
    """A check run as the rollup of gh pr list shows it."""
    return {
        "__typename": "CheckRun",
        "name": name,
        "status": status,
        "conclusion": conclusion or "",
        "startedAt": started,
        "workflowName": "CI",
    }


def status(context: str, state: str) -> dict[str, Any]:
    """A commit status as the rollup of gh pr list shows it."""
    return {
        "__typename": "StatusContext",
        "context": context,
        "state": state,
        "startedAt": EARLY,
    }


def passed() -> list[dict[str, Any]]:
    return [run(name) for name in REQUIRED]


def pull(
    number: int,
    *,
    enabled: str | None = EARLY,
    branch: str | None = None,
    mergeable: str = "MERGEABLE",
    labels: Sequence[str] = (),
    checks: list[dict[str, Any]] | None = None,
    cross: bool = False,
) -> dict[str, Any]:
    """An open pull request as gh pr list shows it."""
    return {
        "number": number,
        "headRefName": branch or f"feat/change-{number}",
        "headRefOid": f"{number:040x}",
        "autoMergeRequest": None
        if enabled is None
        else {"enabledAt": enabled, "mergeMethod": "SQUASH"},
        "isCrossRepository": cross,
        "mergeable": mergeable,
        "labels": [{"name": name} for name in labels],
        "statusCheckRollup": passed() if checks is None else checks,
    }


class FakeGitHub:
    """The parts of GitHub that the branch bot uses, kept in memory."""

    def __init__(self, *pulls: dict[str, Any]) -> None:
        self.pulls = list(pulls)
        self.required: list[str] = list(REQUIRED)
        # The commits of main that the head of each pull request lacks.
        self.behind: dict[int, int] = {}
        self.comments: dict[int, list[str]] = {}
        # What GitHub answers when asked for one pull request again.
        self.mergeable: dict[int, bool | None] = {}
        self.updated: list[tuple[int, Any]] = []
        self.added: list[int] = []
        self.removed: list[int] = []
        # A status that answers a request instead of the simulation.
        self.fail: dict[tuple[str, str], int] = {}
        self.listed: list[Sequence[str]] = []
        self.list_error = ""
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "pr":
            self.listed.append(arguments)
            if self.list_error:
                return subprocess.CompletedProcess(arguments, 1, "", self.list_error)
            return subprocess.CompletedProcess(arguments, 0, json.dumps(self.pulls), "")
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        payload = json.loads(body) if body else None
        code = self.fail.get((method, path), 0)
        data: Any = {"message": "simulated failure"} if code else None
        if not code:
            code, data = self.route(method, path, payload)
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
        if (method, path) == ("GET", f"{own}/rules/branches/main?per_page=100"):
            return 200, [
                {"type": "pull_request", "parameters": {}},
                {
                    "type": "required_status_checks",
                    "parameters": {
                        "required_status_checks": [
                            {"context": name, "integration_id": 15368}
                            for name in self.required
                        ]
                    },
                },
            ]
        found = re.fullmatch(rf"{own}/compare/main\.\.\.([0-9a-f]{{40}})", path)
        if method == "GET" and found:
            number = int(found[1], 16)
            if number not in self.behind:
                return 404, None
            return 200, {"behind_by": self.behind[number], "ahead_by": 1}
        found = re.fullmatch(rf"{own}/pulls/(\d+)/update-branch", path)
        if method == "PUT" and found:
            self.updated.append((int(found[1]), body))
            return 202, {"message": "Updating pull request branch."}
        found = re.fullmatch(rf"{own}/pulls/(\d+)", path)
        if method == "GET" and found:
            return 200, {"mergeable": self.mergeable.get(int(found[1]))}
        found = re.fullmatch(rf"{own}/issues/(\d+)/labels", path)
        if method == "POST" and found:
            assert body == {"labels": [LABEL]}
            self.added.append(int(found[1]))
            return 200, [{"name": LABEL}]
        found = re.fullmatch(rf"{own}/issues/(\d+)/labels/{LABEL}", path)
        if method == "DELETE" and found:
            self.removed.append(int(found[1]))
            return 200, []
        found = re.fullmatch(rf"{own}/issues/(\d+)/comments(\?.*)?", path)
        if found and method == "GET":
            assert found[2] == "?per_page=100&page=1"
            bodies = self.comments.get(int(found[1]), [])
            return 200, [{"body": text} for text in bodies]
        if found and method == "POST":
            self.comments.setdefault(int(found[1]), []).append(body["body"])
            return 201, {"id": 1}
        raise AssertionError(f"unexpected request {method} {path}")


def bot(github: FakeGitHub) -> tuple[str, list[str]]:
    outcome = next_branch(Api(github), REPO)
    return outcome.summary, outcome.warnings


def notes(summary: str) -> dict[int, str]:
    """What the summary says about each pull request."""
    return {
        int(found[1]): found[2]
        for found in re.finditer(r"^- #(\d+) `[^`]*`: (.*)$", summary, re.M)
    }


# --------------------------------------------------------------------------- the line


def test_only_the_pull_request_whose_auto_merge_came_first_is_brought_up_to_date() -> (
    None
):
    # The order is that of auto-merge, not of the numbers.
    github = FakeGitHub(
        pull(3, enabled=LATER),
        pull(5, enabled=EARLY),
        pull(4, enabled=LATEST),
    )
    github.behind = {3: 2, 4: 1, 5: 3}

    summary, warnings = bot(github)

    assert github.updated == [(5, {"expected_head_sha": f"{5:040x}"})]
    assert warnings == []
    said = notes(summary)
    assert list(said) == [5, 3, 4]
    assert (
        said[5]
        == "was 3 commits behind `main`: brought up to date, its checks run now."
    )
    assert said[3] == said[4] == "waits in line."
    assert summary.startswith("### Branch bot\n\n`main` takes a pull request only when")
    # Only the pull requests that wait for auto-merge are listed, into main.
    assert list(github.listed[0]) == [
        "pr",
        "list",
        "--repo",
        REPO,
        "--state",
        "open",
        "--base",
        "main",
        "--limit",
        str(LIMIT),
        "--json",
        FIELDS,
    ]


def test_one_commit_behind_is_said_in_the_singular() -> None:
    github = FakeGitHub(pull(1))
    github.behind = {1: 1}

    summary, _ = bot(github)

    assert notes(summary)[1].startswith("was 1 commit behind `main`:")


def test_while_the_checks_of_the_first_run_up_to_date_nothing_else_is_updated() -> None:
    # 7 was brought up to date before, and its checks run: it merges next, and its
    # merge starts the next run of the bot.
    github = FakeGitHub(
        pull(6, enabled=EARLY, checks=passed()),
        pull(
            7,
            enabled=LATER,
            checks=[run("lint"), run("check (python)", None, status="IN_PROGRESS")],
        ),
        pull(8, enabled=LATEST),
    )
    github.behind = {6: 1, 7: 0, 8: 4}

    summary, warnings = bot(github)

    assert github.updated == []
    assert warnings == []
    said = notes(summary)
    assert said[7] == "up to date with `main`, and its checks run: it merges next."
    # Even one that came first waits: its turn comes after the merge.
    assert said[6] == said[8] == "waits in line."


def test_a_head_without_any_check_yet_is_in_flight() -> None:
    # Right after the bot updated it, GitHub hasn't started its checks yet.
    github = FakeGitHub(pull(1, checks=[]), pull(2, enabled=LATER))
    github.behind = {1: 0, 2: 1}

    summary, _ = bot(github)

    assert github.updated == []
    assert notes(summary)[1].endswith("it merges next.")


def test_a_pull_request_whose_checks_run_while_it_is_behind_is_brought_up_to_date() -> (
    None
):
    # Its checks test a merge with an older main, whose result the rules don't take.
    github = FakeGitHub(
        pull(1, checks=[run("lint", None, status="QUEUED"), run("check (python)")])
    )
    github.behind = {1: 2}

    bot(github)

    assert [number for number, _ in github.updated] == [1]
    # GitHub is asked once how far behind it is.
    compares = [call for call in github.calls if "/compare/" in call[1]]
    assert len(compares) == 1


def test_a_pull_request_whose_required_check_failed_leaves_its_place() -> None:
    github = FakeGitHub(
        pull(1, checks=[run("lint", "FAILURE"), run("check (python)")]),
        pull(
            2,
            enabled=LATER,
            checks=[
                run("lint", "TIMED_OUT"),
                run("check (python)", None, status="IN_PROGRESS"),
            ],
        ),
        pull(3, enabled=LATEST),
    )
    github.behind = {1: 1, 2: 0, 3: 1}

    summary, warnings = bot(github)

    # 2 is up to date and still runs a check, but one failed: it can't merge.
    assert [number for number, _ in github.updated] == [3]
    assert warnings == []
    said = notes(summary)
    assert said[1] == (
        "the required check `lint` failed: it waits for a fix, and the next one takes "
        "its place."
    )
    assert said[2].startswith("the required check `lint` failed")


def test_a_check_that_isnt_required_doesnt_hold_up_the_line() -> None:
    checks = [*passed(), run("links", "FAILURE"), run("fuzz", None, status="QUEUED")]
    github = FakeGitHub(pull(1, checks=checks), pull(2, enabled=LATER))
    github.behind = {1: 3, 2: 1}

    bot(github)

    assert [number for number, _ in github.updated] == [1]


def test_without_required_checks_every_check_counts() -> None:
    github = FakeGitHub(
        pull(1, checks=[run("links", "FAILURE")]), pull(2, enabled=LATER)
    )
    github.required = []
    github.behind = {1: 1, 2: 1}

    summary, _ = bot(github)

    assert [number for number, _ in github.updated] == [2]
    assert "`links` failed" in notes(summary)[1]


def test_a_pull_request_that_is_up_to_date_and_done_waits_for_something_else() -> None:
    # Its checks passed and it is up to date, yet it hasn't merged: a conversation to
    # resolve, a cancelled check or the seconds before auto-merge merges it.
    github = FakeGitHub(
        pull(1, checks=[run("lint", "CANCELLED"), run("check (python)")]),
        pull(2, enabled=LATER),
    )
    github.behind = {1: 0, 2: 1}

    summary, _ = bot(github)

    assert [number for number, _ in github.updated] == [2]
    assert notes(summary)[1] == (
        "up to date with `main`, and its checks ended: auto-merge merges it once "
        "nothing else holds it up, such as a conversation to resolve or a check that "
        "was cancelled."
    )


def test_only_pull_requests_of_this_repository_that_wait_for_auto_merge_count() -> None:
    github = FakeGitHub(
        pull(1, enabled=None),
        pull(2, cross=True),
        pull(3, branch="release-please--branches--main--components--demo"),
        pull(4, enabled=LATEST),
    )
    github.behind = {1: 1, 2: 1, 3: 1, 4: 1}

    summary, _ = bot(github)

    assert [number for number, _ in github.updated] == [4]
    assert list(notes(summary)) == [4]


def test_without_a_pull_request_that_waits_the_bot_says_so() -> None:
    github = FakeGitHub(pull(1, enabled=None))

    summary, warnings = bot(github)

    assert summary == "### Branch bot\n\nNo pull request waits for auto-merge.\n"
    assert warnings == []
    # The rules and the line, nothing else.
    assert github.calls == [
        ("GET", f"repos/{REPO}"),
        ("GET", f"repos/{REPO}/rules/branches/main?per_page=100"),
    ]


def test_branch_names_are_only_code_in_the_summary() -> None:
    github = FakeGitHub(pull(1, branch="feat/`x`|<b>@all"))
    github.behind = {1: 1}

    summary, _ = bot(github)

    assert "- #1 `feat/'x'\\|<b>@all`: was 1 commit behind" in summary


# --------------------------------------------------------------------------- conflicts


def test_a_conflict_gets_the_label_and_one_comment_and_the_next_one_moves_up() -> None:
    github = FakeGitHub(pull(1, mergeable="CONFLICTING"), pull(2, enabled=LATER))
    github.behind = {1: 5, 2: 1}

    summary, warnings = bot(github)

    assert github.added == [1]
    assert github.comments[1] == [f"{MARKER}\n{CONFLICT_COMMENT.format(base='main')}"]
    assert "Merge `main` into the branch" in github.comments[1][0]
    assert [number for number, _ in github.updated] == [2]
    assert warnings == []
    assert notes(summary)[1] == (
        "conflicts with `main`: it has the label merge-conflict and waits for a person "
        "to merge `main` into it."
    )


def test_a_later_conflict_brings_back_only_the_label() -> None:
    github = FakeGitHub(pull(1, mergeable="CONFLICTING"))
    github.comments[1] = ["Thanks!", f"{MARKER}\nThis pull request conflicts."]

    bot(github)

    assert github.added == [1]
    assert len(github.comments[1]) == 2


def test_a_labelled_conflict_is_left_as_it_is() -> None:
    github = FakeGitHub(pull(1, mergeable="CONFLICTING", labels=[LABEL]))

    summary, _ = bot(github)

    assert github.added == []
    assert github.comments == {}
    assert "it has the label merge-conflict" in notes(summary)[1]


def test_renovate_builds_a_branch_that_conflicts_anew() -> None:
    github = FakeGitHub(
        pull(1, branch="renovate/ruff-0.x", mergeable="CONFLICTING"),
        pull(2, enabled=LATER),
    )
    github.behind = {2: 1}

    summary, _ = bot(github)

    assert github.added == []
    assert github.comments == {}
    assert (
        notes(summary)[1] == "conflicts with `main`; Renovate builds its branch anew."
    )
    assert [number for number, _ in github.updated] == [2]


def test_the_label_goes_once_github_finds_no_conflict() -> None:
    github = FakeGitHub(
        pull(1, labels=[LABEL]),
        # GitHub hasn't computed it yet: the label stays until it knows.
        pull(2, enabled=LATER, mergeable="UNKNOWN", labels=[LABEL]),
    )
    github.behind = {1: 0, 2: 1}

    bot(github)

    assert github.removed == [1]
    assert [number for number, _ in github.updated] == [2]


def test_a_conflict_that_the_list_didnt_know_yet_is_a_conflict() -> None:
    # Right after a merge into main, GitHub's list doesn't know yet whether a pull
    # request conflicts; the update then fails, and GitHub knows.
    github = FakeGitHub(pull(1, mergeable="UNKNOWN"), pull(2, enabled=LATER))
    github.behind = {1: 1, 2: 1}
    github.fail[("PUT", f"repos/{REPO}/pulls/1/update-branch")] = 422
    github.mergeable[1] = False

    summary, warnings = bot(github)

    assert warnings == []
    assert github.added == [1]
    assert "it has the label merge-conflict" in notes(summary)[1]
    assert [number for number, _ in github.updated] == [2]


# --------------------------------------------------------------------------- errors


def test_a_failed_update_of_a_mergeable_pull_request_is_a_warning() -> None:
    github = FakeGitHub(pull(1), pull(2, enabled=LATER), pull(3, enabled=LATEST))
    github.behind = {1: 1, 2: 1, 3: 1}
    github.fail[("PUT", f"repos/{REPO}/pulls/1/update-branch")] = 422

    summary, warnings = bot(github)

    # No label and no comment: it doesn't conflict.
    assert github.added == []
    assert github.comments == {}
    assert warnings == [
        "::warning::The branch bot couldn't handle #1: GitHub answered 422: "
        "simulated failure"
    ]
    assert notes(summary)[1] == (
        "GitHub refused a request: `GitHub answered 422: simulated failure`."
    )
    # The next one moves up, and the one after it waits.
    assert [number for number, _ in github.updated] == [2]
    assert notes(summary)[3] == "waits in line."


def test_an_update_that_github_still_finds_no_conflict_for_is_a_warning() -> None:
    github = FakeGitHub(pull(1, mergeable="UNKNOWN"))
    github.behind = {1: 1}
    github.fail[("PUT", f"repos/{REPO}/pulls/1/update-branch")] = 502
    github.mergeable[1] = None

    _, warnings = bot(github)

    assert github.added == []
    assert len(warnings) == 1
    assert "GitHub answered 502" in warnings[0]


def test_a_pull_request_that_is_gone_is_a_warning() -> None:
    github = FakeGitHub(pull(1))
    github.behind = {1: 1}
    github.fail[("PUT", f"repos/{REPO}/pulls/1/update-branch")] = 404

    _, warnings = bot(github)

    assert warnings == [
        "::warning::The branch bot couldn't handle #1: GitHub answered 404: no pull "
        "request #1 to update"
    ]


def test_a_comparison_that_github_refuses_is_a_warning_and_the_next_one_moves_up() -> (
    None
):
    pending = [run("lint", None, status="IN_PROGRESS"), run("check (python)")]
    github = FakeGitHub(
        pull(1, checks=pending), pull(2, enabled=LATER), pull(3, enabled=LATEST)
    )
    # GitHub knows no comparison for 1, and refuses that of 2.
    github.behind = {3: 1}
    github.fail[("GET", f"repos/{REPO}/compare/main...{2:040x}")] = 500

    summary, warnings = bot(github)

    assert len(warnings) == 2
    assert "no comparison of" in warnings[0]
    assert "GitHub answered 500" in warnings[1]
    assert notes(summary)[1].startswith("GitHub refused a request")
    assert [number for number, _ in github.updated] == [3]


def test_a_label_that_github_refuses_stops_no_other_pull_request() -> None:
    github = FakeGitHub(
        pull(1, mergeable="CONFLICTING"),
        pull(2, enabled=LATER, labels=[LABEL]),
        pull(3, enabled=LATEST),
    )
    github.behind = {2: 1, 3: 1}
    github.fail[("POST", f"repos/{REPO}/issues/1/labels")] = 403
    github.fail[("DELETE", f"repos/{REPO}/issues/2/labels/{LABEL}")] = 500

    summary, warnings = bot(github)

    assert len(warnings) == 2
    assert github.comments == {}
    assert [number for number, _ in github.updated] == [3]
    assert set(notes(summary)) == {1, 2, 3}


# --------------------------------------------------------------------------- checks


@pytest.mark.parametrize(
    ("entry", "state"),
    [
        (run("a"), State.PASSED),
        (run("a", "NEUTRAL"), State.PASSED),
        (run("a", "SKIPPED"), State.PASSED),
        (run("a", None, status="QUEUED"), State.PENDING),
        (run("a", None, status="WAITING"), State.PENDING),
        (run("a", "FAILURE"), State.FAILED),
        (run("a", "TIMED_OUT"), State.FAILED),
        (run("a", "STARTUP_FAILURE"), State.FAILED),
        (run("a", "ACTION_REQUIRED"), State.FAILED),
        (run("a", "CANCELLED"), State.STOPPED),
        (run("a", "STALE"), State.STOPPED),
        (run("a", "SOMETHING_NEW"), State.STOPPED),
        (status("a", "SUCCESS"), State.PASSED),
        (status("a", "PENDING"), State.PENDING),
        (status("a", "EXPECTED"), State.PENDING),
        (status("a", "FAILURE"), State.FAILED),
        (status("a", "ERROR"), State.FAILED),
        (status("a", "SOMETHING_NEW"), State.STOPPED),
    ],
)
def test_the_state_of_a_check(entry: dict[str, Any], state: State) -> None:
    assert state_of(entry) is state


def test_the_latest_run_of_a_check_decides() -> None:
    checks = latest_checks(
        [
            run("title", "SUCCESS", started=LATER),
            run("title", "CANCELLED", started=EARLY),
            run("changelog", "FAILURE", started=EARLY),
            run("changelog", None, status="QUEUED", started=NO_TIME),
            run("lint", "FAILURE", started=EARLY),
            run("lint", "SUCCESS", started=EARLY),
            status("dco", "SUCCESS"),
            {"__typename": "CheckRun", "name": "new", "status": "QUEUED"},
        ]
    )

    assert checks == {
        "title": State.PASSED,
        # A run that hasn't started is the newest of all.
        "changelog": State.PENDING,
        # Of two at the same time, the later in the list.
        "lint": State.PASSED,
        "dco": State.PASSED,
        "new": State.PENDING,
    }


def test_a_pull_request_takes_what_gh_lists() -> None:
    data = pull(9, labels=["bug", LABEL], mergeable="")
    data["autoMergeRequest"] = {}
    data["statusCheckRollup"] = None

    found = Pull.of(data)

    assert found == Pull(9, "feat/change-9", f"{9:040x}", "", "UNKNOWN", True, {})
    required = frozenset(REQUIRED)
    assert found.pending(required)
    assert found.failed(required) == []


def test_the_line_needs_the_list_of_github() -> None:
    github = FakeGitHub()
    github.list_error = "HTTP 502: Bad Gateway"

    with pytest.raises(GitHubError, match="Bad Gateway"):
        waiting(Api(github), REPO, "main")


# --------------------------------------------------------------------------- command


def test_the_command_writes_the_summary_and_the_warnings(
    capsys: pytest.CaptureFixture[str],
) -> None:
    github = FakeGitHub(pull(1), pull(2, enabled=LATER))
    github.behind = {1: 1, 2: 1}

    assert cli.main(["--repo", REPO, "next-branch"], api=Api(github)) == 0
    out, err = capsys.readouterr()
    assert out.startswith("### Branch bot\n")
    assert err == ""

    # One pull request that GitHub refuses: a warning for the run, which fails.
    github = FakeGitHub(pull(1))
    github.behind = {1: 1}
    github.fail[("PUT", f"repos/{REPO}/pulls/1/update-branch")] = 500
    assert cli.main(["--repo", REPO, "next-branch"], api=Api(github)) == 1
    out, err = capsys.readouterr()
    assert "GitHub refused a request" in out
    assert err.startswith("::warning::The branch bot couldn't handle #1:")


def test_the_command_fails_when_github_lists_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    github = FakeGitHub()
    github.list_error = "HTTP 401: Bad credentials"

    assert cli.main(["--repo", REPO, "next-branch"], api=Api(github)) == 2
    assert "Bad credentials" in capsys.readouterr().err
