"""Tests of the bot-health bot against a simulated GitHub."""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from blueprint import cli
from blueprint.bot_health import (
    LABEL,
    LABEL_COLOR,
    LABEL_DESCRIPTION,
    LATE,
    MARKER,
    MOST_JOBS,
    MOST_PROBLEMS,
    MOST_STARTS,
    ONE_TRY,
    OWN_ISSUE,
    QUIET_RUNS,
    RENOVATE,
    RENOVATE_TITLE,
    Cron,
    Problem,
    Run,
    code,
    default_branch,
    dispatch_inputs,
    failures,
    marker,
    missed_time,
    open_issue,
    open_issues,
    renovate_problems,
    renovate_report,
    sweep,
    watch_run,
)
from blueprint.github import Api, GitHubError

ROOT = Path(__file__).parents[1]
REPO = "Dennis-Otto/demo"
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
FINDINGS = ".github/workflows/findings.yml"
RELEASE = ".github/workflows/release.yml"
RUN = "https://github.com/Dennis-Otto/repo-blueprint/actions/runs/7"


def stamp(when: datetime) -> str:
    return when.isoformat().replace("+00:00", "Z")


def run_of(
    number: int,
    *,
    name: str = "Release",
    path: str = RELEASE,
    event: str = "schedule",
    branch: str = "main",
    head: str = REPO,
    status: str = "completed",
    conclusion: str | None = "failure",
    attempt: int = 1,
    created: datetime = NOW - timedelta(hours=3),
) -> dict[str, Any]:
    return {
        "id": number,
        "name": name,
        "path": path,
        "event": event,
        "head_branch": branch,
        "head_repository": {"full_name": head},
        "status": status,
        "conclusion": conclusion,
        "run_attempt": attempt,
        "html_url": f"https://github.com/{REPO}/actions/runs/{number}",
        "created_at": stamp(created),
        "updated_at": stamp(created + timedelta(minutes=5)),
    }


def job_of(
    number: int,
    name: str,
    conclusion: str,
    steps: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    return {
        "id": number,
        "name": name,
        "conclusion": conclusion,
        "html_url": f"https://github.com/{REPO}/actions/runs/1/job/{number}",
        "steps": [{"name": step, "conclusion": result} for step, result in steps or []],
    }


def failure(level: str, message: str) -> dict[str, str]:
    return {"annotation_level": level, "message": message}


class FakeGitHub:
    """The parts of GitHub's API that the bot-health bot uses, kept in memory."""

    def __init__(self) -> None:
        self.known = True
        self.runs: dict[int, dict[str, Any]] = {}
        self.jobs: dict[tuple[int, int], list[dict[str, Any]]] = {}
        self.annotations: dict[int, list[dict[str, str]]] = {}
        self.issues: dict[int, dict[str, Any]] = {}
        self.comments: dict[int, list[str]] = {}
        self.labels: dict[str, dict[str, str]] = {}
        self.workflows: list[dict[str, Any]] = []
        self.workflow_runs: dict[int, list[dict[str, Any]]] = {}
        self.reruns: list[int] = []
        self.enabled: list[int] = []
        self.dispatched: list[tuple[int, Any]] = []
        self.others: dict[str, dict[str, Any] | int] = {}
        # A status that answers a request instead of the simulation.
        self.fail: dict[tuple[str, str], int] = {}
        # What a refused second try finds: the run as another bot left it.
        self.rerun_by_another: dict[str, Any] | None = None
        self.calls: list[tuple[str, str]] = []

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        method, path = arguments[3], arguments[4]
        self.calls.append((method, path))
        payload = json.loads(body) if body else None
        status: int = self.fail.get((method, path), 0)
        data: Any = {"message": "simulated failure"} if status else None
        if not status:
            status, data = self.route(method, path, payload)
        text = "" if data is None else json.dumps(data)
        return subprocess.CompletedProcess(
            arguments,
            0 if status < 400 else 1,
            f"HTTP/2.0 {status} X\r\nA: b\r\n\r\n{text}",
            "",
        )

    def route(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        own = f"repos/{REPO}"
        if path != own and not path.startswith(f"{own}/"):
            other = self.others.get(path.removeprefix("repos/"), 404)
            return (other, None) if isinstance(other, int) else (200, other)
        for pattern, handler in (
            (r"", self.repository),
            (r"/actions/runs/(\d+)", self.run),
            (r"/actions/runs/(\d+)/rerun-failed-jobs", self.rerun),
            (r"/actions/runs/(\d+)/attempts/(\d+)/jobs\?per_page=100", self.run_jobs),
            (r"/check-runs/(\d+)/annotations\?per_page=50", self.job_annotations),
            (r"/issues\?labels=bot-failure&state=open&per_page=100", self.open_list),
            (r"/issues", self.new_issue),
            (r"/issues/(\d+)", self.issue),
            (r"/issues/(\d+)/comments", self.comment),
            (r"/labels(?:/([\w-]+))?", self.label),
            (r"/actions/workflows\?per_page=100", self.workflow_list),
            (
                r"/actions/workflows/(\d+)/runs\?branch=main&exclude_pull_requests=true&per_page=50",
                self.runs_of_workflow,
            ),
            (r"/actions/workflows/(\d+)/enable", self.enable),
            (r"/actions/workflows/(\d+)/dispatches", self.dispatch),
        ):
            match = re.fullmatch(pattern, path.removeprefix(own))
            if match:
                result: tuple[int, Any] = handler(method, body, *match.groups())
                return result
        raise AssertionError(f"unexpected request {method} {path}")

    def repository(self, method: str, body: Any) -> tuple[int, Any]:
        if not self.known:
            return 404, {"message": "Not Found"}
        return 200, {"default_branch": "main", "private": False}

    def run(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        run = self.runs.get(int(number))
        return (200, run) if run else (404, {"message": "Not Found"})

    def rerun(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        if self.rerun_by_another is not None:
            self.runs[int(number)] = self.rerun_by_another
            return 403, {"message": "This workflow run cannot be rerun."}
        self.reruns.append(int(number))
        return 201, {}

    def run_jobs(
        self, method: str, body: Any, number: str, attempt: str
    ) -> tuple[int, Any]:
        return 200, {"jobs": self.jobs.get((int(number), int(attempt)), [])}

    def job_annotations(self, method: str, body: Any, job: str) -> tuple[int, Any]:
        return 200, self.annotations.get(int(job), [])

    def open_list(self, method: str, body: Any) -> tuple[int, Any]:
        listed = [
            issue
            for issue in self.issues.values()
            if issue["state"] == "open" and LABEL in issue["labels"]
        ]
        return 200, sorted(listed, key=lambda issue: -issue["number"])

    def new_issue(self, method: str, body: Any) -> tuple[int, Any]:
        assert method == "POST"
        number = len(self.issues) + 1
        self.issues[number] = {**body, "number": number, "state": "open"}
        return 201, self.issues[number]

    def issue(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        assert method == "PATCH"
        self.issues[int(number)].update(body)
        return 200, self.issues[int(number)]

    def comment(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        self.comments.setdefault(int(number), []).append(body["body"])
        return 201, {}

    def label(self, method: str, body: Any, name: str | None) -> tuple[int, Any]:
        if method == "GET":
            assert name is not None
            known = self.labels.get(name)
            return (200, known) if known else (404, {"message": "Not Found"})
        self.labels[body["name"]] = body
        return 201, body

    def workflow_list(self, method: str, body: Any) -> tuple[int, Any]:
        return 200, {"total_count": len(self.workflows), "workflows": self.workflows}

    def runs_of_workflow(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        return 200, {"workflow_runs": self.workflow_runs.get(int(number), [])}

    def enable(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        assert method == "PUT"
        self.enabled.append(int(number))
        return 204, None

    def dispatch(self, method: str, body: Any, number: str) -> tuple[int, Any]:
        self.dispatched.append((int(number), body))
        return 204, None

    # ------------------------------------------------------------------ helpers

    def add_issue(self, key: str, **state: Any) -> int:
        number = len(self.issues) + 1
        body = f"{marker({'key': key, **state})}\nThe text of the issue.\n"
        self.issues[number] = {
            "number": number,
            "title": "Release fails on main",
            "body": body,
            "labels": [LABEL],
            "state": "open",
        }
        return number

    def state_of(self, number: int) -> dict[str, Any]:
        match = MARKER.search(self.issues[number]["body"])
        assert match, self.issues[number]["body"]
        state: dict[str, Any] = json.loads(match[1])
        return state


@pytest.fixture
def github() -> FakeGitHub:
    return FakeGitHub()


def api_of(github: FakeGitHub) -> Api:
    return Api(github)


def writes(github: FakeGitHub) -> list[tuple[str, str]]:
    return [call for call in github.calls if call[0] != "GET"]


# ---------------------------------------------------------------- the end of a run


def test_a_first_failure_runs_its_failed_jobs_once_more(github: FakeGitHub) -> None:
    github.runs[1] = run_of(1)

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: failed: runs the failed jobs once more."
    assert github.reruns == [1]
    assert github.issues == {}


def test_a_failure_that_stays_opens_one_issue(github: FakeGitHub) -> None:
    github.runs[1] = run_of(1, attempt=2, event="push")
    github.jobs[(1, 2)] = [
        job_of(
            11,
            "release",
            "failure",
            [("Set up job", "success"), ("Run release-please", "failure")],
        ),
        job_of(12, "notes", "success"),
    ]
    github.annotations[11] = [
        failure("warning", "Node 20 is deprecated"),
        failure("failure", "Process completed with exit code 1."),
        failure("failure", "release-please failed: <!DOCTYPE html>"),
    ]

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: fails: opened #1."
    issue = github.issues[1]
    assert issue["title"] == "Release fails on main"
    assert issue["labels"] == [LABEL, "maintenance"]
    body = issue["body"]
    assert (
        "The workflow **Release** fails on `main` since 2026-10-13, 1 failed run"
        in (body)
    )
    assert "attempt 2, started by a push." in body
    assert (
        f"| [`release`](https://github.com/{REPO}/actions/runs/1/job/11) "
        "| `Run release-please` | `release-please failed: <!DOCTYPE html>` |"
    ) in body
    assert "`notes`" not in body
    assert "*Actions → Release*" in body
    state = github.state_of(1)
    assert re.fullmatch(r"[0-9a-f]{12}", state.pop("where"))
    assert state == {
        "key": RELEASE,
        "run": 1,
        "attempt": 2,
        "failed": 1,
        "since": "2026-10-13",
    }
    # The label of the bot, for a repository whose labels.toml lacks it.
    assert github.labels[LABEL] == {
        "name": LABEL,
        "color": LABEL_COLOR,
        "description": LABEL_DESCRIPTION,
    }
    assert len(LABEL_DESCRIPTION) <= 100
    assert github.comments == {}


def test_a_failure_in_the_same_place_updates_the_issue_quietly(
    github: FakeGitHub,
) -> None:
    api = api_of(github)
    github.labels[LABEL] = {"name": LABEL}
    for number in (1, 2):
        github.runs[number] = run_of(number, attempt=2)
        github.jobs[(number, 2)] = [
            job_of(10 + number, "release", "failure", [("Tag", "failure")])
        ]
    watch_run(api, REPO, 1, NOW)

    result = watch_run(api, REPO, 2, NOW)

    assert result == "Release: fails again: updated #1."
    assert len(github.issues) == 1
    assert github.state_of(1)["run"] == 2
    assert github.state_of(1)["failed"] == 2
    assert github.state_of(1)["since"] == "2026-10-13"
    assert "2 failed runs so far" in github.issues[1]["body"]
    assert github.comments == {}
    assert ("POST", f"repos/{REPO}/labels") not in github.calls


def test_a_failure_in_another_place_adds_a_comment(github: FakeGitHub) -> None:
    number = github.add_issue(RELEASE, run=1, attempt=2, failed=3, where="old")
    github.runs[2] = run_of(2, attempt=2)
    github.jobs[(2, 2)] = [job_of(21, "sign", "timed_out", [("Sign", "cancelled")])]

    result = watch_run(api_of(github), REPO, 2, NOW)

    assert result == f"Release: fails in another place: updated #{number}."
    assert github.state_of(number)["failed"] == 4
    # An issue without the day of its first failure gets the day of this one.
    assert github.state_of(number)["since"] == "2026-10-13"
    (comment,) = github.comments[number]
    assert comment.startswith("It now fails in another place, in [the run of ")
    assert "| `Sign` |" in comment


def test_a_run_is_reported_once(github: FakeGitHub) -> None:
    number = github.add_issue(RELEASE, run=1, attempt=2, failed=1, where="x")
    github.runs[1] = run_of(1, attempt=2)

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == f"Release: fails: #{number} has this run."
    assert writes(github) == []


def test_a_run_that_passes_closes_the_issue(github: FakeGitHub) -> None:
    number = github.add_issue(RELEASE, run=1, attempt=2, failed=2, where="x")
    github.runs[3] = run_of(3, conclusion="success")

    result = watch_run(api_of(github), REPO, 3, NOW)

    assert result == f"Release: passes again: closed #{number}."
    assert github.issues[number]["state"] == "closed"
    assert github.issues[number]["state_reason"] == "completed"
    assert github.comments[number] == [
        "Passes again in [the run of 2026-10-13 09:00 UTC]"
        f"(https://github.com/{REPO}/actions/runs/3), after 2 failed runs."
    ]


def test_an_older_run_that_passed_leaves_the_issue_open(github: FakeGitHub) -> None:
    number = github.add_issue(RELEASE, run=5, attempt=1, failed=1, where="x")
    github.runs[4] = run_of(4, conclusion="success")

    result = watch_run(api_of(github), REPO, 4, NOW)

    assert result == f"Release: passes, in a run older than the failure of #{number}."
    assert writes(github) == []
    # The run of the failure itself, passing in a later attempt, closes it.
    github.runs[5] = run_of(5, conclusion="success", attempt=2)

    assert watch_run(api_of(github), REPO, 5, NOW).endswith(f"closed #{number}.")


def test_one_failed_run_is_one(github: FakeGitHub) -> None:
    number = github.add_issue(RELEASE, run=1, attempt=2, failed=1, where="x")
    github.runs[3] = run_of(3, conclusion="success")

    watch_run(api_of(github), REPO, 3, NOW)

    assert github.comments[number][0].endswith("after 1 failed run.")


def test_a_run_that_passes_without_an_issue_changes_nothing(
    github: FakeGitHub,
) -> None:
    github.runs[1] = run_of(1, conclusion="success")

    assert watch_run(api_of(github), REPO, 1, NOW) == "Release: passes."
    assert writes(github) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"event": "pull_request"},
        {"event": "pull_request_target"},
        {"branch": "feature"},
        # A fork's branch may be called main too.
        {"head": "someone/demo"},
    ],
)
def test_runs_of_pull_requests_and_other_branches_change_nothing(
    github: FakeGitHub, changes: dict[str, str]
) -> None:
    github.runs[1] = run_of(1, attempt=2, **changes)  # type: ignore[arg-type]

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: not a run of `main`, nothing to do."
    assert writes(github) == []


def test_a_run_that_runs_again_counts_at_its_next_end(github: FakeGitHub) -> None:
    github.runs[1] = run_of(1, status="in_progress", conclusion=None, attempt=2)

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: runs again, its next end counts."
    assert writes(github) == []


def test_a_run_that_github_does_not_know(github: FakeGitHub) -> None:
    assert watch_run(api_of(github), REPO, 9, NOW) == "GitHub doesn't know the run 9."


@pytest.mark.parametrize(
    ("conclusion", "said"), [("cancelled", "cancelled"), (None, "completed")]
)
def test_a_cancelled_run_is_no_failure(
    github: FakeGitHub, conclusion: str | None, said: str
) -> None:
    github.runs[1] = run_of(1, conclusion=conclusion)

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == f"Release: ended as {said}: no failure."
    assert writes(github) == []


@pytest.mark.parametrize("name", sorted(ONE_TRY))
def test_a_finding_is_reported_without_a_second_try(
    github: FakeGitHub, name: str
) -> None:
    github.runs[1] = run_of(1, name=name, path=FINDINGS)

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == f"{name}: fails: opened #1."
    assert github.reruns == []
    assert "The run names no failed job; its page says why" in github.issues[1]["body"]


def test_a_run_that_github_could_not_start_is_reported_at_once(
    github: FakeGitHub,
) -> None:
    github.runs[1] = run_of(1, conclusion="startup_failure")

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: fails: opened #1."
    assert github.reruns == []
    assert "GitHub couldn't start the run" in github.issues[1]["body"]
    assert not any("/jobs" in path for _, path in github.calls)


@pytest.mark.parametrize(
    "latest",
    [
        {"run_attempt": 2, "status": "queued"},
        {"run_attempt": 2, "status": "completed"},
        {"run_attempt": 1, "status": "in_progress"},
    ],
)
def test_another_bot_may_run_it_again_first(
    github: FakeGitHub, latest: dict[str, Any]
) -> None:
    github.runs[1] = run_of(1)
    github.rerun_by_another = {**run_of(1), **latest}

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: failed: another bot runs it again."
    assert github.issues == {}


def test_a_second_try_that_github_refuses_is_reported(github: FakeGitHub) -> None:
    github.runs[1] = run_of(1)
    github.rerun_by_another = run_of(1)

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: fails: opened #1 (GitHub refused to run it again)."


def test_the_failed_jobs_name_their_place_and_their_first_error(
    github: FakeGitHub,
) -> None:
    run = Run.of(run_of(1, attempt=2))
    github.jobs[(1, 2)] = [
        job_of(1, "only cancelled", "cancelled", [("Wait", "cancelled")]),
        job_of(2, "passed", "success"),
    ]
    github.fail[("GET", f"repos/{REPO}/check-runs/1/annotations?per_page=50")] = 403

    (found,) = failures(api_of(github), REPO, run)

    assert (found.job, found.step, found.error) == ("only cancelled", "Wait", "")

    github.jobs[(1, 2)] = [
        {**job_of(number, f"job {number}", "failure"), "steps": None}
        for number in range(MOST_JOBS + 2)
    ]
    github.annotations[0] = [failure("failure", "Process completed with exit code 2.")]
    found_all = failures(api_of(github), REPO, run)

    assert len(found_all) == MOST_JOBS
    assert found_all[0].step == ""
    # Only the annotation that every failed step gets: better than none.
    assert found_all[0].error == "Process completed with exit code 2."
    assert found_all[1].error == ""


def test_text_of_a_run_stays_plain_code_in_a_table() -> None:
    assert code("") == ""
    assert code("\n  \n") == ""
    assert code("\n first `line` | @someone\x1b[31m\nsecond") == (
        "`first 'line' \\| @someone [31m`"
    )
    long = code("x" * 300)
    assert long == f"`{'x' * 199}…`"


def test_the_state_of_an_issue_never_ends_its_comment() -> None:
    state = {"key": ".github/workflows/a--b.yml", "since": "2026-10-13"}

    text = marker(state)

    assert text.count("--") == 2
    match = MARKER.search(text)
    assert match
    assert json.loads(match[1]) == state


def test_the_issues_of_the_bot_are_found_by_their_state(github: FakeGitHub) -> None:
    older = github.add_issue(RELEASE, run=1)
    newer = github.add_issue(RELEASE, run=2)
    github.add_issue(FINDINGS)
    for number, body in (
        (10, "No state"),
        (11, "<!-- bot-health {not json} -->"),
        (12, '<!-- bot-health {"run": 1} -->'),
        (13, None),
    ):
        github.issues[number] = {
            "number": number,
            "body": body,
            "labels": [LABEL],
            "state": "open",
        }
    github.issues[14] = {
        **github.issues[newer],
        "number": 14,
        "body": github.issues[newer]["body"].replace(RELEASE, "pr"),
        "pull_request": {},
    }

    found = open_issues(api_of(github), REPO)

    assert set(found) == {RELEASE, FINDINGS}
    assert found[RELEASE].number == newer != older


def test_the_label_that_another_run_just_created_is_fine(github: FakeGitHub) -> None:
    github.fail[("POST", f"repos/{REPO}/labels")] = 422

    assert open_issue(api_of(github), REPO, "A title", "A body", []) == 1
    assert github.issues[1]["labels"] == [LABEL]


def test_a_label_that_cannot_be_created_stops_the_bot(github: FakeGitHub) -> None:
    github.fail[("POST", f"repos/{REPO}/labels")] = 403

    with pytest.raises(GitHubError):
        open_issue(api_of(github), REPO, "A title", "A body", [])
    assert github.issues == {}


def test_a_repository_that_github_does_not_know(github: FakeGitHub) -> None:
    github.known = False

    with pytest.raises(GitHubError, match="doesn't know the repository"):
        default_branch(api_of(github), REPO)


def test_the_names_of_the_workflows_exist() -> None:
    names = {
        match[1]
        for path in (ROOT / ".github/workflows").glob("*.yml")
        if (match := re.search(r"^name: (.+)$", path.read_text("utf-8"), re.M))
    }
    assert names >= ONE_TRY | OWN_ISSUE


# ---------------------------------------------------------------- the daily look

SCHEDULED = """name: Clean-up
on:
  schedule:
    - cron: "40 5 * * 0"
  workflow_dispatch:
jobs: {}
"""


def workflow(
    number: int,
    name: str,
    *,
    path: str | None = None,
    state: str = "active",
) -> dict[str, Any]:
    return {
        "id": number,
        "name": name,
        "path": path or f".github/workflows/w{number}.yml",
        "state": state,
    }


def write(root: Path, number: int, text: str) -> None:
    path = root / f".github/workflows/w{number}.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_the_daily_look_reports_what_the_events_missed(
    github: FakeGitHub, tmp_path: Path
) -> None:
    path = ".github/workflows/w{}.yml"
    github.workflows = [
        workflow(1, "Findings"),
        workflow(2, "Release"),
        workflow(3, "Clean-up"),
        workflow(4, "Links"),
        workflow(5, "Docs"),
        workflow(6, "Labels"),
        workflow(7, "Newest Python"),
        workflow(8, "Dependabot", path="dynamic/dependabot/dependabot-updates"),
        workflow(9, "Old", state="disabled_manually"),
    ]
    github.workflow_runs = {
        # A finding fails at once, and an older run that passed doesn't count.
        1: [
            run_of(10, name="Findings", path=path.format(1)),
            run_of(11, name="Findings", path=path.format(1), conclusion="success"),
        ],
        # Still on its way to its second try.
        2: [
            run_of(
                20,
                path=path.format(2),
                created=NOW - timedelta(minutes=20),
            )
        ],
        # A first failure whose event GitHub lost; before it, a run of a pull request
        # and one that is still running.
        3: [
            run_of(30, name="Clean-up", path=path.format(3), status="queued"),
            run_of(31, name="Clean-up", path=path.format(3), event="pull_request"),
            run_of(32, name="Clean-up", path=path.format(3), conclusion="skipped"),
            run_of(33, name="Clean-up", path=path.format(3)),
        ],
        4: [run_of(40, name="Links", path=path.format(4), conclusion="success")],
        6: [run_of(60, name="Labels", path=path.format(6), conclusion="success")],
    }
    links = github.add_issue(path.format(4), run=39, failed=1)
    reported = github.add_issue(path.format(6), run=59, failed=1)
    github.issues[reported]["state"] = "closed"

    summary, healthy = sweep(api_of(github), REPO, tmp_path, NOW)

    assert healthy
    assert summary.splitlines()[:6] == [
        "### Bot health",
        "",
        "The latest finished run of every workflow on `main`, and the schedules that "
        "GitHub missed.",
        "",
        "| Workflow | State |",
        "| --- | --- |",
    ]
    rows = summary.splitlines()[6:]
    assert rows == [
        "| `Clean-up` | fails: opened #3 |",
        "| `Docs` | no finished run on `main` |",
        "| `Findings` | fails: opened #4 |",
        "| `Labels` | passes |",
        f"| `Links` | passes again: closed #{links} |",
        "| `Release` | failed: its second try may still come |",
    ]
    assert github.reruns == []
    assert github.dispatched == []


def test_the_daily_look_starts_a_workflow_whose_schedule_github_missed(
    github: FakeGitHub, tmp_path: Path
) -> None:
    findings = SCHEDULED.replace(
        "  workflow_dispatch:\n",
        "  workflow_dispatch:\n    inputs:\n      dry_run:\n        type: boolean\n",
    )
    texts = {
        1: SCHEDULED,
        2: findings,
        3: SCHEDULED.replace("  workflow_dispatch:\n", ""),
        4: SCHEDULED.replace('"40 5 * * 0"', '"61 5 * * 0"'),
        5: SCHEDULED,
        6: SCHEDULED,
    }
    for number, text in texts.items():
        write(tmp_path, number, text)
    github.workflows = [
        workflow(1, "A missed"),
        workflow(2, "B dry run", state="disabled_inactivity"),
        workflow(3, "C not by hand"),
        workflow(4, "D unreadable"),
        workflow(5, "E on time"),
        workflow(6, "F never ran"),
        workflow(7, "G no file"),
    ]
    # The schedule's last time before NOW minus LATE: Sunday, 2026-10-11 05:40.
    missed = datetime(2026, 10, 11, 5, 40, tzinfo=UTC)
    assert missed <= NOW - LATE
    for number in (1, 2, 3, 4):
        github.workflow_runs[number] = [
            run_of(
                number * 10,
                name="x",
                conclusion="success",
                created=missed - timedelta(days=6),
            )
        ]
    github.workflow_runs[5] = [
        run_of(50, name="x", conclusion="success", created=missed + timedelta(hours=3))
    ]

    summary, healthy = sweep(api_of(github), REPO, tmp_path, NOW)

    assert healthy
    rows = summary.splitlines()[6:]
    assert rows == [
        "| `A missed` | passes; missed its run of 2026-10-11 05:40 UTC: started |",
        "| `B dry run` | passes; GitHub had switched it off for inactivity: on again; "
        "missed its run of 2026-10-11 05:40 UTC: started |",
        "| `C not by hand` | passes; missed its run of 2026-10-11 05:40 UTC, and "
        "can't be started by hand |",
        "| `D unreadable` | passes; a schedule that can't be read |",
        "| `E on time` | passes |",
        "| `F never ran` | no finished run on `main`; missed its run of "
        "2026-10-11 05:40 UTC: started |",
        "| `G no file` | no finished run on `main` |",
    ]
    assert github.enabled == [2]
    assert github.dispatched == [
        (1, {"ref": "main", "inputs": {}}),
        (2, {"ref": "main", "inputs": {"dry_run": "false"}}),
        (6, {"ref": "main", "inputs": {}}),
    ]


def test_the_daily_look_starts_a_few_workflows_a_day(
    github: FakeGitHub, tmp_path: Path
) -> None:
    for number in range(MOST_STARTS + 1):
        write(tmp_path, number, SCHEDULED)
        github.workflows.append(workflow(number, f"W{number}"))

    summary, _ = sweep(api_of(github), REPO, tmp_path, NOW)

    assert len(github.dispatched) == MOST_STARTS
    assert summary.splitlines()[-1] == (
        f"| `W{MOST_STARTS}` | no finished run on `main`; missed its run of "
        f"2026-10-11 05:40 UTC: starts in a later look, {MOST_STARTS} a day |"
    )


def test_the_daily_look_goes_on_after_an_error(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.workflows = [workflow(1, "Broken"), workflow(2, "Fine")]
    github.fail[
        (
            "GET",
            f"repos/{REPO}/actions/workflows/1/runs"
            "?branch=main&exclude_pull_requests=true&per_page=50",
        )
    ] = 502

    summary, healthy = sweep(api_of(github), REPO, tmp_path, NOW)

    assert not healthy
    assert summary.splitlines()[6:] == [
        "| `Broken` | couldn't look: `GitHub answered 502: simulated failure` |",
        "| `Fine` | no finished run on `main` |",
    ]


@pytest.mark.parametrize(
    ("schedule", "before", "last"),
    [
        ("17 7 * * *", "2026-10-13 07:17", "2026-10-13 07:17"),
        ("17 7 * * *", "2026-10-13 07:16", "2026-10-12 07:17"),
        ("10,40 * * * *", "2026-10-13 12:39", "2026-10-13 12:10"),
        ("*/30 * * * *", "2026-10-13 00:29", "2026-10-13 00:00"),
        ("25 * * * *", "2026-10-13 00:10", "2026-10-12 23:25"),
        ("17 */2 * * *", "2026-10-13 03:00", "2026-10-13 02:17"),
        # Mondays; 2026-10-13 is a Tuesday.
        ("0 6 * * 1", "2026-10-13 12:00", "2026-10-12 06:00"),
        # Sundays, as 0 and as 7.
        ("40 5 * * 0", "2026-10-13 12:00", "2026-10-11 05:40"),
        ("40 5 * * 7", "2026-10-13 12:00", "2026-10-11 05:40"),
        ("0 9-17/2 * * 1-5", "2026-10-13 12:00", "2026-10-13 11:00"),
        ("5/15 * * * *", "2026-10-13 12:00", "2026-10-13 11:50"),
        ("0 0 1 * *", "2026-10-13 12:00", "2026-10-01 00:00"),
        ("0 0 1 1 *", "2026-10-13 12:00", "2026-01-01 00:00"),
        # The 13th or a Friday, as in cron.
        ("0 0 13 * 5", "2026-10-12 12:00", "2026-10-09 00:00"),
        ("0 0 13 * 5", "2026-10-13 12:00", "2026-10-13 00:00"),
        # Only a 13th that is a Friday would need both.
        ("0 0 13 * *", "2026-10-12 12:00", "2026-09-13 00:00"),
    ],
)
def test_the_times_of_a_schedule(schedule: str, before: str, last: str) -> None:
    cron = Cron.parse(schedule)
    assert cron is not None

    moment = datetime.fromisoformat(before).replace(tzinfo=UTC)

    assert cron.last(moment) == datetime.fromisoformat(last).replace(tzinfo=UTC)


@pytest.mark.parametrize(
    "schedule",
    ["* * * *", "60 * * * *", "a * * * *", "*/0 * * * *", "5-3 * * * *", "0 0 0 * *"],
)
def test_a_schedule_that_cannot_be_read(schedule: str) -> None:
    assert Cron.parse(schedule) is None


def test_a_schedule_that_never_comes() -> None:
    cron = Cron.parse("0 0 30 2 *")
    assert cron is not None

    assert cron.last(NOW) is None
    assert missed_time('    - cron: "0 0 30 2 *"\n', NOW) == (None, True)


def test_the_missed_time_of_several_schedules() -> None:
    text = "  schedule:\n    - cron: \"0 1 * * *\"\n    - cron: '0 3 * * *'\n"

    assert missed_time(text, NOW) == (datetime(2026, 10, 13, 3, 0, tzinfo=UTC), True)
    assert missed_time("", NOW) == (None, True)
    assert Cron.parse("0 0 * * *") == Cron.parse("0 0 * * 0-7")
    assert Cron.parse("0 0 * * 0") != Cron.parse("0 0 * * *")
    assert date(2026, 10, 13).isoweekday() == 2


def test_the_inputs_that_start_a_workflow_as_its_schedule_does() -> None:
    assert dispatch_inputs("on:\n  schedule:\n    - cron: x\n") is None
    assert dispatch_inputs("on:\n  workflow_dispatch:\njobs:\n") == {}
    assert (
        dispatch_inputs(
            "on:\n  workflow_dispatch:\n    inputs:\n\n      seed:\n        type: string\n"
        )
        == {}
    )
    assert dispatch_inputs(
        "on:\n  workflow_dispatch:\n    inputs:\n      dry_run:\n        default: true\n"
    ) == {"dry_run": "false"}
    # A dry_run of another event isn't one of the start by hand.
    assert (
        dispatch_inputs(
            "on:\n  workflow_dispatch:\n  workflow_call:\n    inputs:\n      dry_run:\n"
        )
        == {}
    )


@pytest.mark.parametrize(
    "name", ["findings.yml", "issue-lifecycle.yml", "properties.yml", "release.yml"]
)
def test_the_workflows_of_the_blueprint_start_as_their_schedules_do(
    name: str,
) -> None:
    text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")

    inputs = dispatch_inputs(text)

    dry = name in ("findings.yml", "issue-lifecycle.yml")
    assert inputs == ({"dry_run": "false"} if dry else {})
    assert missed_time(text, NOW)[0] is not None


# ---------------------------------------------------------------- Renovate


def log_line(level: int, message: str, **details: Any) -> str:
    return json.dumps({"name": "renovate", "level": level, "msg": message, **details})


LOG = [
    "not JSON",
    "[1, 2]",
    json.dumps({"level": "warn", "msg": "a level that isn't a number"}),
    log_line(30, "Repository started", repository="Dennis-Otto/app"),
    log_line(
        40,
        "Error executing pip-compile",
        repository="Dennis-Otto/app",
        packageFile="requirements-test.in",
        err={"message": "unknown option --unsafe-package\nmore"},
    ),
    log_line(
        40,
        "Error executing pip-compile",
        repository="Dennis-Otto/app",
        packageFile="requirements-test.in",
        err={"message": "unknown option --unsafe-package\nmore"},
    ),
    log_line(40, "Base branch is missing", repository="Dennis-Otto/app"),
    log_line(50, "Repository has unknown error", repository="Dennis-Otto/secret"),
    log_line(60, "A | fatal", err="no dict", branch="renovate/x"),
    log_line(40, "In another", repository="Dennis-Otto/gone"),
    log_line(40, "Strange name", repository="no name"),
    log_line(40, "Error", repository="Dennis-Otto/flaky"),
]


def test_the_problems_in_the_log_of_renovate() -> None:
    problems = renovate_problems(LOG)

    assert problems == {
        Problem(
            "Dennis-Otto/app",
            "WARN",
            "Error executing pip-compile",
            "requirements-test.in",
            "unknown option --unsafe-package\nmore",
        ): 2,
        Problem("Dennis-Otto/app", "WARN", "Base branch is missing", "", ""): 1,
        Problem(
            "Dennis-Otto/secret", "ERROR", "Repository has unknown error", "", ""
        ): 1,
        Problem("", "ERROR", "A | fatal", "renovate/x", ""): 1,
        Problem("Dennis-Otto/gone", "WARN", "In another", "", ""): 1,
        Problem("no name", "WARN", "Strange name", "", ""): 1,
        Problem("Dennis-Otto/flaky", "WARN", "Error", "", ""): 1,
    }


def test_renovate_keeps_one_issue_of_its_problems(
    github: FakeGitHub, tmp_path: Path
) -> None:
    api = api_of(github)
    log = tmp_path / "problems.json"
    log.write_text("\n".join(LOG) + "\n", encoding="utf-8")
    github.others = {
        "Dennis-Otto/app": {"private": False},
        "Dennis-Otto/secret": {"private": True},
        "Dennis-Otto/flaky": 502,
    }

    summary = renovate_report(api, REPO, log, RUN)

    issue = github.issues[1]
    assert issue["title"] == RENOVATE_TITLE
    assert issue["labels"] == [LABEL, "maintenance", "dependencies"]
    assert github.state_of(1) == {"key": RENOVATE, "quiet": 0}
    body = issue["body"]
    assert body.split("\n", 1)[1] + "\nOpened #1.\n" == summary
    assert f"Renovate logged warnings or errors in [its run]({RUN})." in body
    assert (
        "### Dennis-Otto/app\n\n"
        "| Level | Message | Where | Detail | Times |\n"
        "| --- | --- | --- | --- | --- |\n"
        "| WARN | `Base branch is missing` |  |  | 1 |\n"
        "| WARN | `Error executing pip-compile` | `requirements-test.in` "
        "| `unknown option --unsafe-package` | 2 |\n"
    ) in body
    assert "### Renovate itself\n" in body
    assert "| ERROR | `A \\| fatal` | `renovate/x` |  | 1 |" in body
    # Private, gone, an odd name and an error of GitHub: no name in a public issue.
    for hidden in ("secret", "gone", "no name", "flaky"):
        assert hidden not in body, hidden
    assert body.endswith(
        "\n4 more in private repositories, which a public issue doesn't name.\n"
    )
    asked = [path for method, path in github.calls if path.startswith("repos/Dennis")]
    assert asked.count("repos/Dennis-Otto/app") == 1
    assert "repos/no name" not in asked

    # A later run with problems replaces them.
    log.write_text(log_line(40, "Only this") + "\n", encoding="utf-8")
    number = github.add_issue(RENOVATE, quiet=2)
    github.issues[1]["state"] = "closed"

    summary = renovate_report(api, REPO, log, RUN)

    assert summary.endswith(f"\nUpdated #{number}.\n")
    assert github.state_of(number) == {"key": RENOVATE, "quiet": 0}
    assert "`Only this`" in github.issues[number]["body"]


def test_the_issue_of_renovate_closes_after_quiet_runs(
    github: FakeGitHub, tmp_path: Path
) -> None:
    api = api_of(github)
    log = tmp_path / "problems.json"
    log.write_text("", encoding="utf-8")
    number = github.add_issue(RENOVATE, quiet=0)
    text = github.issues[number]["body"].split("\n", 1)[1]

    for quiet in range(1, QUIET_RUNS):
        summary = renovate_report(api, REPO, log, RUN)

        assert summary == (
            f"Renovate logged no problem; #{number} closes after "
            f"{QUIET_RUNS - quiet} more runs like this.\n"
        )
        assert github.state_of(number)["quiet"] == quiet
        assert github.issues[number]["body"].split("\n", 1)[1] == text

    summary = renovate_report(api, REPO, log, RUN)

    assert summary == f"Renovate logged no problem: closed #{number}.\n"
    assert github.issues[number]["state"] == "closed"
    assert github.comments[number] == [
        f"Renovate logged no problem in {QUIET_RUNS} runs in a row, the latest "
        f"[this one]({RUN})."
    ]
    assert renovate_report(api, REPO, log, RUN) == (
        "Renovate logged no warning and no error.\n"
    )


def test_without_a_log_the_issue_of_renovate_stays(
    github: FakeGitHub, tmp_path: Path
) -> None:
    github.add_issue(RENOVATE, quiet=0)

    summary = renovate_report(api_of(github), REPO, tmp_path / "missing.json", RUN)

    assert summary == "Renovate wrote no log of problems; the issue stays as it is.\n"
    assert writes(github) == []


def test_the_issue_of_renovate_lists_a_few_problems(
    github: FakeGitHub, tmp_path: Path
) -> None:
    log = tmp_path / "problems.json"
    log.write_text(
        "\n".join(log_line(40, f"Problem {n:03}") for n in range(MOST_PROBLEMS + 5)),
        encoding="utf-8",
    )

    summary = renovate_report(api_of(github), REPO, log, RUN)

    assert summary.count("| WARN |") == MOST_PROBLEMS
    assert "\nAnd 5 more in the log of the run.\n" in summary
    assert "private" not in summary


# ---------------------------------------------------------------- the command line


def test_the_command_line_of_the_bot(
    github: FakeGitHub,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    github.runs[1] = run_of(1)
    arguments = ["--repo", REPO, "bot-health"]

    assert cli.main([*arguments, "run", "1"], Api(github), tmp_path) == 0
    assert capsys.readouterr().out == (
        "Release: failed: runs the failed jobs once more.\n"
    )

    github.workflows = [workflow(1, "Broken")]
    github.fail[
        (
            "GET",
            f"repos/{REPO}/actions/workflows/1/runs"
            "?branch=main&exclude_pull_requests=true&per_page=50",
        )
    ] = 500
    assert cli.main([*arguments, "sweep"], Api(github), tmp_path) == 1
    assert "| `Broken` | couldn't look:" in capsys.readouterr().out
    github.workflows = []
    assert cli.main([*arguments, "sweep"], Api(github), tmp_path) == 0
    assert capsys.readouterr().out.startswith("### Bot health\n")

    log = tmp_path / "log.json"
    log.write_text("", encoding="utf-8")
    command = [*arguments, "renovate", str(log), "--run", RUN]
    assert cli.main(command, Api(github), tmp_path) == 0
    assert capsys.readouterr().out == "Renovate logged no warning and no error.\n"

    # An error of GitHub ends the command as every other one.
    github.known = False
    assert cli.main([*arguments, "run", "1"], Api(github), tmp_path) == 2
    assert "doesn't know the repository" in capsys.readouterr().err
