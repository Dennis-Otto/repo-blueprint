"""Tests of the branch bot against a simulated GitHub."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Sequence
from typing import Any

import pytest

from blueprint import branches, cli
from blueprint.branches import (
    CONFLICT_COMMENT,
    FIELDS,
    LIMIT,
    MARKER,
    NO_TIME,
    Job,
    Pull,
    State,
    decides_what_runs,
    job_from,
    latest_checks,
    next_branch,
    state_of,
    waiting,
)
from blueprint.github import Api, GitHubError, run_gh_as
from blueprint.update import LABEL

REPO = "Dennis-Otto/demo"
REQUIRED = ("check (python)", "lint")
EARLY = "2026-10-17T08:00:00Z"
LATER = "2026-10-17T09:00:00Z"
LATEST = "2026-10-17T10:00:00Z"
# The account of the release app, a contributor, and commits of a pull request from a
# fork: its parent and the newest commit of the contributor, and one of main.
ACCOUNT = "demo-release[bot]"
CONTRIBUTOR = "a-contributor"
PARENT = f"{0x60:040x}"
OWN = f"{0x70:040x}"
MAIN = f"{0xAA:040x}"


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
    editable: bool = False,
    review: str | None = None,
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
        "maintainerCanModify": editable,
        "mergeable": mergeable,
        "labels": [{"name": name} for name in labels],
        "reviewDecision": review,
        "statusCheckRollup": passed() if checks is None else checks,
    }


def sha_of(number: int) -> str:
    return f"{number:040x}"


def head_of(number: int) -> str:
    """The head of a pull request of pull()."""
    return sha_of(number)


def a_commit(
    sha: str,
    *below: str,
    author: str | None = CONTRIBUTOR,
    committer: str | None = CONTRIBUTOR,
    signed: bool = True,
) -> dict[str, Any]:
    """A commit as a comparison of GitHub lists it."""
    return {
        "sha": sha,
        "parents": [{"sha": parent} for parent in below],
        "author": {"login": author} if author else None,
        "committer": {"login": committer} if committer else None,
        "commit": {
            "verification": {
                "verified": signed,
                "reason": "valid" if signed else "unsigned",
            }
        },
    }


def merge_of_the_bot(
    sha: str,
    first: str,
    *,
    second: str = MAIN,
    author: str = ACCOUNT,
    committer: str = "web-flow",
    signed: bool = True,
) -> dict[str, Any]:
    """The merge of base that GitHub makes when the bot updates a branch."""
    return a_commit(
        sha, first, second, author=author, committer=committer, signed=signed
    )


def a_run(
    identifier: int,
    sha: str,
    *,
    conclusion: str | None = "action_required",
    status: str = "completed",
    attempt: int = 1,
    event: str = "pull_request",
) -> dict[str, Any]:
    """A workflow run as GitHub lists it."""
    return {
        "id": identifier,
        "head_sha": sha,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "html_url": f"https://github.com/{REPO}/actions/runs/{identifier}",
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
        self.messages: dict[tuple[str, str], str] = {}
        self.listed: list[Sequence[str]] = []
        self.list_error = ""
        self.calls: list[tuple[str, str]] = []
        # Whether the rules want every conversation resolved, and the conversations of
        # each pull request: resolved or not.
        self.thread_rule = False
        self.threads: dict[int, list[bool]] = {}
        self.queried: list[int] = []
        self.graphql_error = ""
        # Whether the rules want every commit signed, and what a comparison of the head
        # of each pull request lists.
        self.signature_rule = False
        self.commits: dict[int, list[dict[str, Any]]] = {}
        self.files: dict[int, list[dict[str, Any]]] = {}
        self.total: dict[int, int] = {}
        # The commits on main, and the workflow runs of each commit: GitHub would filter
        # them, but the bot has to rely on nothing but what it checks itself.
        self.on_main = {MAIN}
        self.runs: dict[str, list[dict[str, Any]]] = {}
        self.approved: list[int] = []
        self.dispatched: list[Any] = []
        # The token of the job may read the runs, and so may a person. The token of the
        # release app may not.
        self.by_job = False
        self.person = False

    def as_job(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        self.by_job = True
        try:
            return self(arguments, body)
        finally:
            self.by_job = False

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "pr":
            self.listed.append(arguments)
            if self.list_error:
                return subprocess.CompletedProcess(arguments, 1, "", self.list_error)
            return subprocess.CompletedProcess(arguments, 0, json.dumps(self.pulls), "")
        if arguments[1] == "graphql":
            return self.graphql(arguments)
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        payload = json.loads(body) if body else None
        code = self.fail.get((method, path), 0)
        message = self.messages.get((method, path), "simulated failure")
        data: Any = {"message": message} if code else None
        if not code:
            code, data = self.route(method, path, payload)
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if code < 400 else 1,
            f"HTTP/2.0 {code} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def graphql(self, arguments: Sequence[str]) -> subprocess.CompletedProcess[str]:
        query = arguments[3]
        found = re.search(
            r'repository\(owner: "Dennis-Otto", name: "demo"\) \{ pullRequest\(number: (\d+)\)',
            query,
        )
        assert found, query
        assert "reviewThreads(first: 100) { nodes { isResolved } }" in query
        number = int(found[1])
        self.queried.append(number)
        if self.graphql_error:
            return subprocess.CompletedProcess(arguments, 1, "", self.graphql_error)
        nodes = [{"isResolved": done} for done in self.threads.get(number, [])]
        data = {
            "data": {"repository": {"pullRequest": {"reviewThreads": {"nodes": nodes}}}}
        }
        return subprocess.CompletedProcess(arguments, 0, json.dumps(data), "")

    def actions(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        own = f"repos/{REPO}"
        if not self.by_job and not self.person:
            return 403, {"message": "Resource not accessible by integration"}
        found = re.fullmatch(
            rf"{own}/actions/runs\?head_sha=([0-9a-f]{{40}})"
            r"&(?:status=action_required|event=pull_request)&per_page=100",
            path,
        )
        if method == "GET" and found:
            runs = self.runs.get(found[1], [])
            return 200, {"total_count": len(runs), "workflow_runs": runs}
        found = re.fullmatch(rf"{own}/actions/runs/(\d+)/approve", path)
        if method == "POST" and found:
            assert self.by_job
            self.approved.append(int(found[1]))
            return 201, {}
        if (method, path) == (
            "POST",
            f"{own}/actions/workflows/update-branches.yml/dispatches",
        ):
            assert self.by_job
            self.dispatched.append(body)
            return 204, None
        raise AssertionError(f"unexpected request {method} {path}")

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        own = f"repos/{REPO}"
        if path.startswith(f"{own}/actions/"):
            return self.actions(method, path, body)
        if (method, path) == ("GET", own):
            return 200, {"default_branch": "main"}
        if (method, path) == ("GET", f"{own}/rules/branches/main?per_page=100"):
            signatures = (
                [{"type": "required_signatures"}] if self.signature_rule else []
            )
            return 200, [
                *signatures,
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_review_thread_resolution": self.thread_rule
                    },
                },
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
            if found[1] in self.on_main:
                return 200, {"behind_by": 3, "ahead_by": 0}
            number = int(found[1], 16)
            if number not in self.behind:
                return 404, None
            commits = self.commits.get(number, [])
            return 200, {
                "behind_by": self.behind[number],
                "ahead_by": 1,
                "total_commits": self.total.get(number, len(commits)),
                "commits": commits,
                "files": self.files.get(number, []),
            }
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


def with_job(github: FakeGitHub) -> tuple[str, list[str]]:
    """A run of the bot in the workflow, with the token of its job."""
    outcome = next_branch(Api(github), REPO, Job(Api(github.as_job), ACCOUNT))
    return outcome.summary, outcome.warnings


def forked() -> FakeGitHub:
    """A pull request from a fork that the bot may approve, and one behind it in the
    line: the head is a merge of the bot, on top of a commit of the contributor that a
    person approved, and it changes nothing that decides what a workflow runs."""
    github = FakeGitHub(
        pull(7, cross=True, editable=True, checks=[]),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 0, 8: 1}
    github.commits[7] = [a_commit(OWN, PARENT), merge_of_the_bot(head_of(7), OWN)]
    github.files[7] = [{"filename": "src/app.py"}]
    github.runs[OWN] = [a_run(1, OWN, conclusion="success", attempt=2)]
    github.runs[head_of(7)] = [a_run(2, head_of(7)), a_run(3, head_of(7))]
    return github


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


def test_only_pull_requests_that_wait_for_auto_merge_count() -> None:
    github = FakeGitHub(
        pull(1, enabled=None),
        pull(2, cross=True, enabled=None),
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


@pytest.mark.parametrize(
    ("review", "reason"),
    [
        ("CHANGES_REQUESTED", "changes were requested in a review"),
        ("REVIEW_REQUIRED", "it waits for an approving review"),
    ],
)
def test_a_pull_request_that_waits_for_a_review_is_not_brought_up_to_date(
    review: str, reason: str
) -> None:
    # Its checks would pass and it still wouldn't merge, after every merge again.
    github = FakeGitHub(pull(1, review=review), pull(2, enabled=LATER))
    github.behind = {1: 2, 2: 1}

    summary, warnings = bot(github)

    assert warnings == []
    assert [number for number, _ in github.updated] == [2]
    assert notes(summary)[1] == (
        f"{reason}, so it can't merge yet: the bot leaves it as it is, and the next "
        "one takes its place."
    )
    assert github.queried == []


def test_an_approved_pull_request_is_brought_up_to_date() -> None:
    github = FakeGitHub(pull(1, review="APPROVED"))
    github.behind = {1: 1}

    bot(github)

    assert [number for number, _ in github.updated] == [1]


def test_a_conversation_to_resolve_holds_a_pull_request_back_where_the_rules_say_so() -> (
    None
):
    github = FakeGitHub(pull(1), pull(2, enabled=LATER), pull(3, enabled=LATEST))
    github.behind = {1: 1, 2: 1, 3: 1}
    github.thread_rule = True
    github.threads = {1: [True, False], 2: [True]}

    summary, warnings = bot(github)

    assert warnings == []
    assert [number for number, _ in github.updated] == [2]
    assert notes(summary)[1].startswith("it has a conversation to resolve, so it can't")
    # None is asked about after the one that moves.
    assert github.queried == [1, 2]


def test_conversations_dont_count_where_the_rules_dont_want_them_resolved() -> None:
    github = FakeGitHub(pull(1))
    github.behind = {1: 1}
    github.threads = {1: [False]}

    bot(github)

    assert [number for number, _ in github.updated] == [1]
    assert github.queried == []


def test_an_up_to_date_pull_request_with_a_conversation_to_resolve_is_not_in_flight() -> (
    None
):
    # Its checks run, but it can't merge after them, and their end starts no run of
    # the bot: the next one moves up instead of waiting behind it.
    pending = [run("lint", None, status="IN_PROGRESS"), run("check (python)")]
    github = FakeGitHub(pull(1, checks=pending), pull(2, enabled=LATER))
    github.behind = {1: 0, 2: 1}
    github.thread_rule = True
    github.threads = {1: [False]}

    summary, _ = bot(github)

    assert [number for number, _ in github.updated] == [2]
    assert notes(summary)[2].startswith("was 1 commit behind")
    assert github.queried == [1, 2]


def test_conversations_that_github_doesnt_list_are_a_warning() -> None:
    github = FakeGitHub(pull(1), pull(2, enabled=LATER))
    github.behind = {1: 1, 2: 1}
    github.thread_rule = True
    github.graphql_error = "HTTP 502: Bad Gateway"

    summary, warnings = bot(github)

    assert github.updated == []
    assert len(warnings) == 2
    assert "Bad Gateway" in notes(summary)[1]


def test_a_conflict_that_the_update_reports_is_a_conflict() -> None:
    # The list didn't know yet, and neither does GitHub, asked again; the answer to the
    # update does.
    github = FakeGitHub(pull(1, mergeable="UNKNOWN"), pull(2, enabled=LATER))
    github.behind = {1: 1, 2: 1}
    update = ("PUT", f"repos/{REPO}/pulls/1/update-branch")
    github.fail[update] = 422
    github.messages[update] = "merge conflict between base and head"
    github.mergeable[1] = None

    summary, warnings = bot(github)

    assert warnings == []
    assert github.added == [1]
    assert "it has the label merge-conflict" in notes(summary)[1]
    assert [number for number, _ in github.updated] == [2]


def test_a_pull_request_that_got_a_commit_since_the_list_is_in_flight() -> None:
    github = FakeGitHub(pull(1), pull(2, enabled=LATER))
    github.behind = {1: 1, 2: 1}
    update = ("PUT", f"repos/{REPO}/pulls/1/update-branch")
    github.fail[update] = 422
    github.messages[update] = "expected head sha didn't match current head ref."

    summary, warnings = bot(github)

    assert warnings == []
    assert github.updated == []
    assert notes(summary)[1] == (
        "got a new commit since the list, so its checks run now: it merges next."
    )
    assert notes(summary)[2] == "waits in line."


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

    assert found == Pull(9, "feat/change-9", f"{9:040x}", "", "UNKNOWN", True, "", {})
    required = frozenset(REQUIRED)
    assert found.pending(required)
    assert found.failed(required) == []


def test_the_line_needs_the_list_of_github() -> None:
    github = FakeGitHub()
    github.list_error = "HTTP 502: Bad Gateway"

    with pytest.raises(GitHubError, match="Bad Gateway"):
        waiting(Api(github), REPO, "main")


# --------------------------------------------------------------------------- forks


def test_a_pull_request_from_a_fork_takes_its_place_in_the_line() -> None:
    github = FakeGitHub(
        pull(7, cross=True, editable=True),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 2, 8: 1}

    summary, warnings = with_job(github)

    # The expected head keeps a push of the contributor from racing the update.
    assert github.updated == [(7, {"expected_head_sha": head_of(7)})]
    assert warnings == []
    said = notes(summary)
    assert said[7] == (
        "was 2 commits behind `main`: brought up to date. GitHub may hold its runs for "
        "an approval, which the next run of the bot looks at."
    )
    assert said[8] == "waits in line."
    # No event tells the bot of the runs of the new head, so it starts its next run.
    assert github.dispatched == [{"ref": "main"}]


def test_the_name_of_a_forks_branch_makes_it_no_bot_of_this_repository() -> None:
    github = FakeGitHub(
        pull(
            7,
            cross=True,
            editable=True,
            branch="release-please--branches--main",
        ),
        pull(
            8, cross=True, editable=True, branch="renovate/x", mergeable="CONFLICTING"
        ),
    )
    github.behind = {7: 1}

    summary, _ = with_job(github)

    assert [number for number, _ in github.updated] == [7]
    # A conflict of a fork is one for its author, whatever its branch is called.
    assert github.added == [8]
    assert "it has the label" in notes(summary)[8]


def test_a_fork_without_edits_by_maintainers_stays_out_of_the_line_and_says_so() -> (
    None
):
    github = FakeGitHub(
        pull(7, cross=True, editable=False, mergeable="CONFLICTING"),
        pull(8, enabled=LATER),
    )
    github.behind = {8: 1}

    summary, warnings = with_job(github)

    assert [number for number, _ in github.updated] == [8]
    assert warnings == []
    assert github.added == []
    assert notes(summary)[7] == (
        "its author doesn't allow edits by maintainers, so the bot can't bring it up to "
        "date: it stays out of the line until they do, and the next one takes its place."
    )
    # Nothing is asked about it.
    assert not any(head_of(7) in path for _, path in github.calls)


def test_github_refusing_the_update_of_a_fork_is_a_warning_and_the_next_one_moves_up() -> (
    None
):
    github = FakeGitHub(
        pull(7, cross=True, editable=True),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 1, 8: 1}
    path = ("PUT", f"repos/{REPO}/pulls/7/update-branch")
    github.fail[path] = 403
    github.messages[path] = "Resource not accessible by integration"

    summary, warnings = with_job(github)

    assert [number for number, _ in github.updated] == [8]
    assert warnings == [
        "::warning::The branch bot couldn't handle #7: GitHub answered 403: "
        "Resource not accessible by integration"
    ]
    assert "GitHub refused a request" in notes(summary)[7]
    # The update didn't happen, so no new head has runs to look at.
    assert github.dispatched == []


def test_a_push_of_the_contributor_during_the_update_leaves_the_place_to_the_next_one() -> (
    None
):
    github = FakeGitHub(
        pull(7, cross=True, editable=True),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 1, 8: 1}
    path = ("PUT", f"repos/{REPO}/pulls/7/update-branch")
    github.fail[path] = 422
    github.messages[path] = "expected head sha didn't match current head ref."

    summary, warnings = with_job(github)

    assert [number for number, _ in github.updated] == [8]
    assert warnings == []
    # The runs of its new commit wait for a person, so it isn't in flight.
    assert notes(summary)[7] == (
        "got a new commit since the list, so the bot leaves it as it is, and the next "
        "one takes its place."
    )
    assert github.dispatched == []


@pytest.mark.parametrize(
    ("behind", "checks"),
    [(0, []), (2, []), (0, [run("pull request title", started=LATER)])],
)
def test_a_fork_whose_runs_wait_for_a_person_doesnt_stop_the_line(
    behind: int, checks: list[dict[str, Any]]
) -> None:
    # Its head is the contributor's own commit, which nobody approved. An empty rollup
    # isn't in flight, as it is for one that the bot has just brought up to date, and
    # it isn't brought up to date again: every merge would start its runs for nothing.
    github = FakeGitHub(
        pull(7, cross=True, editable=True, checks=checks),
        pull(8, enabled=LATER),
    )
    github.behind = {7: behind, 8: 1}
    github.commits[7] = [a_commit(head_of(7), PARENT)]
    github.files[7] = [{"filename": "src/app.py"}]
    github.runs[head_of(7)] = [a_run(2, head_of(7))]

    summary, warnings = with_job(github)

    assert [number for number, _ in github.updated] == [8]
    assert github.approved == []
    assert warnings == []
    assert notes(summary)[7] == (
        "1 run of its head waits for a person to approve, since its head isn't a merge "
        "that the bot made: the bot doesn't bring it up to date until then, and the "
        "next one takes its place."
    )


def test_a_fork_that_someone_approved_is_in_flight_again() -> None:
    github = FakeGitHub(
        pull(
            7,
            cross=True,
            editable=True,
            checks=[run(name, None, status="IN_PROGRESS") for name in REQUIRED],
        ),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 0, 8: 1}
    github.runs[head_of(7)] = [
        a_run(2, head_of(7), conclusion=None, status="in_progress", attempt=2)
    ]

    summary, warnings = with_job(github)

    assert github.updated == []
    assert github.approved == []
    assert warnings == []
    said = notes(summary)
    assert said[7] == "up to date with `main`, and its checks run: it merges next."
    assert said[8] == "waits in line."


def test_a_fork_whose_required_check_failed_leaves_its_place_like_any_other() -> None:
    github = FakeGitHub(
        pull(7, cross=True, editable=True, checks=[run("lint", "FAILURE")]),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 1, 8: 1}

    summary, _ = with_job(github)

    assert [number for number, _ in github.updated] == [8]
    assert "the required check `lint` failed" in notes(summary)[7]


@pytest.mark.parametrize(
    ("unverified", "said"),
    [
        (1, "1 commit of it, such as `0000000`, has no verified signature"),
        (2, "2 commits of it, such as `0000000`, have no verified signature"),
    ],
)
def test_a_fork_with_an_unverified_commit_waits_outside_the_line(
    unverified: int, said: str
) -> None:
    github = FakeGitHub(
        pull(7, cross=True, editable=True),
        pull(8, enabled=LATER),
    )
    github.signature_rule = True
    github.behind = {7: 1, 8: 1}
    github.commits[7] = [
        a_commit(f"{index:040x}", PARENT, signed=False) for index in range(unverified)
    ] + [a_commit(head_of(7), PARENT)]

    summary, warnings = with_job(github)

    assert [number for number, _ in github.updated] == [8]
    assert warnings == []
    assert notes(summary)[7] == (
        f"{said}, which the rules of `main` require: it can't merge, so it stays out of "
        "the line until they are signed."
    )
    # One request tells that, and it doesn't ask for the runs of what can't merge.
    assert [path for _, path in github.calls if head_of(7) in path] == [
        f"repos/{REPO}/compare/main...{head_of(7)}"
    ]


def test_without_the_rule_an_unverified_commit_holds_nothing_up() -> None:
    github = FakeGitHub(pull(7, cross=True, editable=True))
    github.behind = {7: 1}
    github.commits[7] = [a_commit(head_of(7), PARENT, signed=False)]

    with_job(github)

    assert [number for number, _ in github.updated] == [7]


def test_a_fork_is_compared_once_in_a_run() -> None:
    github = FakeGitHub(pull(7, cross=True, editable=True))
    github.signature_rule = True
    github.behind = {7: 1}
    github.commits[7] = [a_commit(head_of(7), PARENT)]

    with_job(github)

    compared = f"repos/{REPO}/compare/main...{head_of(7)}"
    assert github.calls.count(("GET", compared)) == 1


def test_a_failed_request_about_a_fork_leaves_it_out_of_the_line() -> None:
    # Without the token of the job, GitHub answers the release app that it may not read
    # the runs: no update, whatever they say.
    github = FakeGitHub(
        pull(7, cross=True, editable=True),
        pull(8, enabled=LATER),
    )
    github.behind = {7: 1, 8: 1}

    summary, warnings = bot(github)

    assert [number for number, _ in github.updated] == [8]
    assert len(warnings) == 1
    assert warnings[0].startswith("::warning::The branch bot couldn't handle #7:")
    assert "GitHub refused a request" in notes(summary)[7]


def test_a_pull_request_of_this_repository_asks_nothing_about_runs() -> None:
    github = FakeGitHub(pull(1), pull(2, enabled=LATER))
    github.signature_rule = True
    github.behind = {1: 3, 2: 1}

    summary, warnings = with_job(github)

    assert notes(summary)[1] == (
        "was 3 commits behind `main`: brought up to date, its checks run now."
    )
    assert warnings == []
    assert github.dispatched == []
    assert [path for _, path in github.calls] == [
        f"repos/{REPO}",
        f"repos/{REPO}/rules/branches/main?per_page=100",
        f"repos/{REPO}/compare/main...{head_of(1)}",
        f"repos/{REPO}/pulls/1/update-branch",
    ]


# ------------------------------------------------------------------- approvals of forks


def test_the_bot_approves_the_runs_of_a_head_that_it_made_itself() -> None:
    github = forked()

    summary, warnings = with_job(github)

    assert github.approved == [2, 3]
    assert github.updated == []
    assert warnings == []
    said = notes(summary)
    # Each approval is in the summary, with the pull request and the run.
    assert said[7] == (
        f"approved [run 2](https://github.com/{REPO}/actions/runs/2) of its head. "
        f"approved [run 3](https://github.com/{REPO}/actions/runs/3) of its head. "
        "Its head is a merge of the bot on top of commits that a person approved, so "
        "nothing new from the fork runs: its checks run now, and it merges next."
    )
    # It is in flight now.
    assert said[8] == "waits in line."
    assert github.dispatched == []


def test_the_runs_of_a_new_head_are_for_the_next_run_of_the_bot_to_find() -> None:
    # The first run looks before GitHub made them, the next run needs no memory of it.
    github = forked()
    runs = github.runs.pop(head_of(7))

    with_job(github)
    assert github.approved == []

    github.runs[head_of(7)] = runs
    with_job(github)
    assert github.approved == [2, 3]


def test_a_head_on_top_of_an_approved_merge_of_the_bot_counts_as_well() -> None:
    # The contributor's commit lost its runs to time. Below the head there is a merge of
    # the bot that has the same newest commit of the contributor and that ran.
    github = forked()
    older = sha_of(0x71)
    github.commits[7] = [
        a_commit(OWN, PARENT),
        merge_of_the_bot(older, OWN),
        merge_of_the_bot(head_of(7), older),
    ]
    github.runs[OWN] = []
    github.runs[older] = [a_run(4, older, conclusion="failure", attempt=2)]

    with_job(github)

    assert github.approved == [2, 3]


def test_the_merges_of_the_bot_lead_down_to_the_commit_that_ran() -> None:
    github = forked()
    older = sha_of(0x71)
    github.commits[7] = [
        a_commit(OWN, PARENT),
        merge_of_the_bot(older, OWN),
        merge_of_the_bot(head_of(7), older),
    ]
    # A run that a person approved and that still runs shows it as well.
    github.runs[OWN] = [a_run(4, OWN, conclusion=None, status="in_progress", attempt=2)]

    with_job(github)

    assert github.approved == [2, 3]


def unknown_commit(github: FakeGitHub) -> None:
    github.commits[7] = [merge_of_the_bot(head_of(7), OWN)]


def pressed_update_branch(github: FakeGitHub) -> None:
    github.commits[7][-1] = merge_of_the_bot(head_of(7), OWN, author=CONTRIBUTOR)


def a_person_pressed_update_branch(github: FakeGitHub) -> None:
    github.commits[7][-1] = merge_of_the_bot(head_of(7), OWN, author="Dennis-Otto")


def pushed_a_merge(github: FakeGitHub) -> None:
    github.commits[7][-1] = merge_of_the_bot(head_of(7), OWN, committer=CONTRIBUTOR)


def named_the_bot_without_a_signature(github: FakeGitHub) -> None:
    github.commits[7][-1] = merge_of_the_bot(head_of(7), OWN, signed=False)


def no_merge(github: FakeGitHub) -> None:
    commit = merge_of_the_bot(head_of(7), OWN)
    commit["parents"] = commit["parents"][:1]
    github.commits[7][-1] = commit


def merged_something_else(github: FakeGitHub) -> None:
    github.commits[7][-1] = merge_of_the_bot(head_of(7), OWN, second=sha_of(0x99))


def merged_a_commit_that_base_lacks(github: FakeGitHub) -> None:
    other = sha_of(0x99)
    github.commits[7][-1] = merge_of_the_bot(head_of(7), OWN, second=other)
    github.behind[0x99] = 0


def head_not_listed(github: FakeGitHub) -> None:
    del github.commits[7][-1]


def nobody_approved_the_commit(github: FakeGitHub) -> None:
    github.runs[OWN] = [a_run(4, OWN)]


def it_ran_without_a_wait(github: FakeGitHub) -> None:
    github.runs[OWN] = [a_run(4, OWN, conclusion="success")]


def it_was_cancelled(github: FakeGitHub) -> None:
    github.runs[OWN] = [a_run(4, OWN, conclusion="cancelled", attempt=2)]


def it_is_only_queued(github: FakeGitHub) -> None:
    github.runs[OWN] = [a_run(4, OWN, conclusion=None, status="queued", attempt=2)]


def only_a_run_of_the_base_ran(github: FakeGitHub) -> None:
    github.runs[OWN] = [
        a_run(4, OWN, conclusion="success", attempt=2, event="pull_request_target")
    ]


def a_run_of_another_commit(github: FakeGitHub) -> None:
    github.runs[OWN] = [a_run(4, sha_of(0x99), conclusion="success", attempt=2)]


def a_new_commit_below_the_head(github: FakeGitHub) -> None:
    # The contributor pushed after a person approved, and something brought it up to
    # date: the merge is the bot's, but the commit below it never ran.
    new = sha_of(0x72)
    github.commits[7] = [
        a_commit(OWN, PARENT),
        a_commit(new, OWN),
        merge_of_the_bot(head_of(7), new),
    ]


def a_new_commit_on_the_head(github: FakeGitHub) -> None:
    merged = sha_of(0x72)
    github.commits[7] = [
        a_commit(OWN, PARENT),
        merge_of_the_bot(merged, OWN),
        a_commit(head_of(7), merged),
    ]


def a_merge_below_that_isnt_the_bots(github: FakeGitHub) -> None:
    older = sha_of(0x71)
    github.commits[7] = [
        a_commit(OWN, PARENT),
        merge_of_the_bot(older, OWN, author=CONTRIBUTOR),
        merge_of_the_bot(head_of(7), older),
    ]


def more_commits_than_listed(github: FakeGitHub) -> None:
    github.total[7] = 300


def a_changed_workflow(github: FakeGitHub) -> None:
    github.files[7] = [{"filename": ".github/workflows/ci.yml"}]


def a_workflow_renamed_away(github: FakeGitHub) -> None:
    github.files[7] = [
        {"filename": "docs/ci.yml", "previous_filename": ".github/workflows/ci.yml"}
    ]


def a_changed_script(github: FakeGitHub) -> None:
    github.files[7] = [{"filename": "src/app.py"}, {"filename": "scripts/check.sh"}]


def no_files(github: FakeGitHub) -> None:
    github.files[7] = []


def more_files_than_listed(github: FakeGitHub) -> None:
    github.files[7] = [{"filename": f"src/{index}.py"} for index in range(300)]


def another_event_waits(github: FakeGitHub) -> None:
    github.runs[head_of(7)].append(
        a_run(5, head_of(7), event="pull_request_review"),
    )


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (unknown_commit, "GitHub doesn't show a commit of it below a merge of the bot"),
        (pressed_update_branch, "its head isn't a merge that the bot made"),
        (a_person_pressed_update_branch, "its head isn't a merge that the bot made"),
        (pushed_a_merge, "its head isn't a merge that the bot made"),
        (named_the_bot_without_a_signature, "its head isn't a merge that the bot made"),
        (no_merge, "its head isn't a merge that the bot made"),
        (merged_something_else, "its head isn't a merge that the bot made"),
        (merged_a_commit_that_base_lacks, "its head isn't a merge that the bot made"),
        (head_not_listed, "its head isn't a merge that the bot made"),
        (a_new_commit_on_the_head, "its head isn't a merge that the bot made"),
        (nobody_approved_the_commit, "nobody has approved its newest commit yet"),
        (it_ran_without_a_wait, "nobody has approved its newest commit yet"),
        (it_was_cancelled, "nobody has approved its newest commit yet"),
        (it_is_only_queued, "nobody has approved its newest commit yet"),
        (only_a_run_of_the_base_ran, "nobody has approved its newest commit yet"),
        (a_run_of_another_commit, "nobody has approved its newest commit yet"),
        (a_new_commit_below_the_head, "nobody has approved its newest commit yet"),
        (a_merge_below_that_isnt_the_bots, "nobody has approved its newest commit yet"),
        (more_commits_than_listed, "GitHub doesn't list all of its commits"),
        (
            a_changed_workflow,
            "it changes `.github/workflows/ci.yml`, which decides what a workflow runs",
        ),
        (
            a_workflow_renamed_away,
            "it changes `.github/workflows/ci.yml`, which decides what a workflow runs",
        ),
        (
            a_changed_script,
            "it changes `scripts/check.sh`, which decides what a workflow runs",
        ),
        (no_files, "GitHub doesn't list all of its files"),
        (more_files_than_listed, "GitHub doesn't list all of its files"),
        (
            another_event_waits,
            "a run of another event than a pull request waits as well",
        ),
    ],
)
def test_the_bot_doesnt_approve_what_a_person_has_to_approve(
    change: Callable[[FakeGitHub], None], reason: str
) -> None:
    github = forked()
    change(github)

    summary, warnings = with_job(github)

    assert github.approved == []
    assert warnings == []
    # It waits for a person, isn't updated, and the next one moves up.
    assert [number for number, _ in github.updated] == [8]
    said = notes(summary)[7]
    assert f"for a person to approve, since {reason}:" in said
    assert "the next one takes its place." in said


def test_only_runs_of_exactly_this_head_that_wait_are_approved() -> None:
    github = forked()
    other = a_run(4, sha_of(0x99))
    done = a_run(5, head_of(7), conclusion="success")
    github.runs[head_of(7)] += [other, done]

    with_job(github)

    assert github.approved == [2, 3]


@pytest.mark.parametrize(
    "path",
    [
        f"repos/{REPO}/compare/main...{head_of(7)}",
        f"repos/{REPO}/compare/main...{MAIN}",
        f"repos/{REPO}/actions/runs?head_sha={head_of(7)}"
        "&status=action_required&per_page=100",
        f"repos/{REPO}/actions/runs?head_sha={OWN}&event=pull_request&per_page=100",
    ],
)
def test_any_failed_request_means_no_approval(path: str) -> None:
    github = forked()
    github.fail[("GET", path)] = 500

    summary, warnings = with_job(github)

    assert github.approved == []
    assert [number for number, _ in github.updated] == [8]
    assert len(warnings) == 1
    assert warnings[0].startswith("::warning::The branch bot couldn't handle #7:")
    assert "GitHub refused a request" in notes(summary)[7]


def test_an_approval_that_github_refuses_is_a_warning_and_the_next_one_moves_up() -> (
    None
):
    github = forked()
    path = ("POST", f"repos/{REPO}/actions/runs/3/approve")
    github.fail[path] = 403
    github.messages[path] = "Resource not accessible by integration"

    summary, warnings = with_job(github)

    # What GitHub did approve is in the summary all the same.
    assert github.approved == [2]
    assert [number for number, _ in github.updated] == [8]
    assert warnings == [
        "::warning::The branch bot couldn't handle #7: GitHub answered 403: "
        "Resource not accessible by integration"
    ]
    said = notes(summary)[7]
    assert said.startswith("approved [run 2]")
    assert "GitHub refused a request" in said


def test_outside_of_a_job_the_bot_approves_nothing_and_starts_no_run() -> None:
    # A person who runs the command: their account reads the runs, and that is all.
    github = forked()
    github.person = True

    summary, warnings = bot(github)

    assert github.approved == []
    assert warnings == []
    assert "since only a run of the workflow may approve them:" in notes(summary)[7]
    # The update of a fork starts no further run either.
    assert github.dispatched == []


def test_the_bot_brings_a_head_up_to_date_rather_than_approve_what_cant_merge() -> None:
    github = forked()
    github.behind[7] = 1

    summary, _ = with_job(github)

    assert github.approved == []
    assert [number for number, _ in github.updated] == [7]
    assert "brought up to date" in notes(summary)[7]
    assert github.dispatched == [{"ref": "main"}]


def test_a_head_that_cant_merge_for_a_review_gets_no_approval() -> None:
    github = forked()
    github.pulls[0]["reviewDecision"] = "REVIEW_REQUIRED"

    summary, _ = with_job(github)

    assert github.approved == []
    assert [number for number, _ in github.updated] == [8]
    assert notes(summary)[7].startswith("it waits for an approving review")


def test_a_head_gets_no_approval_while_another_one_is_in_flight() -> None:
    github = forked()
    # One of the line that has been up to date before it, and whose checks run.
    github.pulls[1]["statusCheckRollup"] = [
        run(name, None, status="IN_PROGRESS") for name in REQUIRED
    ]
    github.behind[8] = 0

    summary, _ = with_job(github)

    assert github.approved == []
    assert github.updated == []
    said = notes(summary)
    assert said[7] == "waits in line."
    assert said[8] == "up to date with `main`, and its checks run: it merges next."


def test_a_head_whose_check_failed_gets_no_approval() -> None:
    # The title's check runs on pull_request_target, for which GitHub holds nothing.
    github = forked()
    github.pulls[0]["statusCheckRollup"] = [run("lint", "FAILURE")]

    summary, _ = with_job(github)

    assert github.approved == []
    assert "the required check `lint` failed" in notes(summary)[7]


def test_a_next_run_that_github_doesnt_start_is_a_warning() -> None:
    github = FakeGitHub(pull(7, cross=True, editable=True))
    github.behind = {7: 1}
    github.fail[
        ("POST", f"repos/{REPO}/actions/workflows/update-branches.yml/dispatches")
    ] = 403

    summary, warnings = with_job(github)

    assert [number for number, _ in github.updated] == [7]
    assert "brought up to date" in notes(summary)[7]
    assert len(warnings) == 1
    assert warnings[0].startswith(
        "::warning::The branch bot couldn't start its next run"
    )


@pytest.mark.parametrize(
    ("path", "decides"),
    [
        (".github/workflows/ci.yml", True),
        (".github/blueprint.py", True),
        (".GitHub/actions/x/action.yml", True),
        ("template/.github/workflows/ci.yml.jinja", True),
        (".githooks/pre-push", True),
        ("scripts/check.sh", True),
        ("action.yml", True),
        ("actions/x/action.yaml", True),
        ("Dockerfile", True),
        ("docker/Dockerfile.e2e", True),
        ("Makefile", True),
        ("package.json", True),
        ("package-lock.json", True),
        ("pyproject.toml", True),
        ("requirements-dev.txt", True),
        ("uv.lock", True),
        ("mkdocs.yml", True),
        ("compose.yaml", True),
        ("src/app.py", False),
        ("tests/test_app.py", False),
        ("docs/github.md", False),
        ("README.md", False),
        ("src/scripts.py", False),
    ],
)
def test_what_decides_what_a_workflow_runs(path: str, decides: bool) -> None:
    assert decides_what_runs(path) is decides


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

    # A run that shows as a check of a pull request passes with the warnings alone.
    assert (
        cli.main(["--repo", REPO, "next-branch", "--warnings-only"], api=Api(github))
        == 0
    )
    _, err = capsys.readouterr()
    assert err.startswith("::warning::The branch bot couldn't handle #1:")


def test_the_command_fails_when_github_lists_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    github = FakeGitHub()
    github.list_error = "HTTP 401: Bad credentials"

    assert cli.main(["--repo", REPO, "next-branch"], api=Api(github)) == 2
    assert "Bad credentials" in capsys.readouterr().err


def test_the_command_acts_with_the_token_and_the_account_of_its_job(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    github = forked()
    monkeypatch.setenv("ACTIONS_TOKEN", "the-token-of-the-job")
    monkeypatch.setenv("BOT_ACCOUNT", ACCOUNT)
    tokens: list[str] = []

    def job_runner(token: str) -> Any:
        tokens.append(token)
        return github.as_job

    monkeypatch.setattr(branches, "run_gh_as", job_runner)

    assert cli.main(["--repo", REPO, "next-branch"], api=Api(github)) == 0

    assert tokens == ["the-token-of-the-job"]
    assert github.approved == [2, 3]
    assert "approved [run 2]" in capsys.readouterr().out


@pytest.mark.parametrize(
    "environment",
    [
        {},
        {"ACTIONS_TOKEN": "a-token"},
        {"BOT_ACCOUNT": ACCOUNT},
        {"ACTIONS_TOKEN": "", "BOT_ACCOUNT": ACCOUNT},
    ],
)
def test_without_the_token_and_the_account_there_is_no_job(
    environment: dict[str, str],
) -> None:
    assert job_from(environment) is None


def test_a_token_of_its_own_replaces_that_of_the_environment_for_the_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Any] = []

    def run(command: Sequence[str], **options: Any) -> Any:
        seen.append((command, options["env"]["GH_TOKEN"], options["input"]))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setenv("GH_TOKEN", "the-token-of-the-app")

    run_gh_as("the-token-of-the-job")(["api", "x"], "a body")

    assert seen == [(["gh", "api", "x"], "the-token-of-the-job", "a body")]
