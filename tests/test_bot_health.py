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
from hypothesis import given
from hypothesis import strategies as st

from blueprint import cli
from blueprint.bot_health import (
    LABEL,
    LABEL_COLOR,
    LABEL_DESCRIPTION,
    LATE,
    MARKER,
    MONTHS,
    MOST_JOBS,
    MOST_PROBLEMS,
    MOST_STARTS,
    ONE_TRY,
    OWN_ISSUE,
    QUIET_RUNS,
    RENOVATE,
    RENOVATE_TITLE,
    WEEKDAYS,
    Cron,
    Problem,
    Run,
    after_pull_requests,
    code,
    default_branch,
    dispatch_inputs,
    events_of,
    failures,
    field_values,
    marker,
    missed_time,
    open_issue,
    open_issues,
    own_issue,
    renovate_problems,
    renovate_report,
    started_after,
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


def job_of_a_run(
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
            (
                r"/actions/workflows/(\d+)/runs\?branch=main&event=(\w+)"
                r"&exclude_pull_requests=true&per_page=1",
                self.runs_of_event,
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
        # The newest runs first, a page of them, as GitHub lists them.
        return 200, {"workflow_runs": self.workflow_runs.get(int(number), [])[:50]}

    def runs_of_event(
        self, method: str, body: Any, number: str, event: str
    ) -> tuple[int, Any]:
        runs = self.workflow_runs.get(int(number), [])
        return 200, {
            "workflow_runs": [run for run in runs if run["event"] == event][:1]
        }

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
        job_of_a_run(
            11,
            "release",
            "failure",
            [("Set up job", "success"), ("Run release-please", "failure")],
        ),
        job_of_a_run(12, "notes", "success"),
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
            job_of_a_run(10 + number, "release", "failure", [("Tag", "failure")])
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
    github.jobs[(2, 2)] = [
        job_of_a_run(21, "sign", "timed_out", [("Sign", "cancelled")])
    ]

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


OUT_OF_TIME = "The job has exceeded the maximum execution time of 5m0s"


def test_a_job_that_ran_out_of_time_gets_a_second_try(github: FakeGitHub) -> None:
    # A job that hangs until its time limit ends as cancelled, even after its last step.
    github.runs[1] = run_of(1, conclusion="cancelled")
    github.jobs[(1, 1)] = [
        job_of_a_run(11, "release", "cancelled", [("Run it", "success")]),
        job_of_a_run(12, "notes", "success"),
    ]
    github.annotations[11] = [failure("failure", OUT_OF_TIME)]

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: failed: runs the failed jobs once more."
    assert [write[:2] for write in writes(github)] == [
        ("POST", f"repos/{REPO}/actions/runs/1/rerun-failed-jobs")
    ]


def test_a_job_that_runs_out_of_time_twice_is_reported(github: FakeGitHub) -> None:
    github.runs[1] = run_of(1, conclusion="cancelled", attempt=2)
    github.jobs[(1, 2)] = [job_of_a_run(11, "release", "cancelled")]
    github.annotations[11] = [failure("failure", OUT_OF_TIME)]

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: fails: opened #1."
    assert OUT_OF_TIME in github.issues[1]["body"]


@pytest.mark.parametrize(
    ("job", "annotations"),
    [
        # A person or a newer run cancelled it, or a job that didn't run out of time.
        ("cancelled", [failure("failure", "The operation was canceled.")]),
        ("cancelled", []),
        ("success", [failure("failure", OUT_OF_TIME)]),
    ],
)
def test_a_run_that_only_something_else_cancelled_is_no_failure(
    github: FakeGitHub, job: str, annotations: list[dict[str, str]]
) -> None:
    github.runs[1] = run_of(1, conclusion="cancelled")
    github.jobs[(1, 1)] = [job_of_a_run(11, "release", job)]
    github.annotations[11] = annotations

    result = watch_run(api_of(github), REPO, 1, NOW)

    assert result == "Release: ended as cancelled: no failure."
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
        job_of_a_run(1, "only cancelled", "cancelled", [("Wait", "cancelled")]),
        job_of_a_run(2, "passed", "success"),
    ]
    github.fail[("GET", f"repos/{REPO}/check-runs/1/annotations?per_page=50")] = 403

    (found,) = failures(api_of(github), REPO, run)

    assert (found.job, found.step, found.error) == ("only cancelled", "Wait", "")

    github.jobs[(1, 2)] = [
        {**job_of_a_run(number, f"job {number}", "failure"), "steps": None}
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
    # Two runs of the bot that opened an issue each at the same moment: the older one
    # points to the newer one and closes.
    assert github.issues[older]["state"] == "closed"
    assert github.issues[older]["state_reason"] == "not_planned"
    assert github.comments[older] == [f"Continued in #{newer}."]
    assert github.issues[newer]["state"] == "open"
    assert writes(github) == [
        ("POST", f"repos/{REPO}/issues/{older}/comments"),
        ("PATCH", f"repos/{REPO}/issues/{older}"),
    ]


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
    # Each keeps an issue of its own, and a second one would repeat it.
    assert {"Diagrams", "Newest Node", "Newest Python", "Next runner"} <= OWN_ISSUE


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
        workflow(10, "Next runner"),
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
        "| `Newest Python` | keeps an issue of its own |",
        "| `Next runner` | keeps an issue of its own |",
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


# The schedule's last time before NOW minus LATE, Sunday, 2026-10-11 05:40, as the
# daily look writes it.
MISSED = datetime(2026, 10, 11, 5, 40, tzinfo=UTC)
MISSED_TEXT = "missed its run of 2026-10-11 05:40 UTC"
OWN = SCHEDULED.replace(
    "name: Clean-up\n", "name: Demo\n# bot-health: own-issue, The demo breaks\n"
)


def test_a_workflow_that_keeps_an_issue_of_its_own_gets_none_of_the_bot(
    github: FakeGitHub, tmp_path: Path
) -> None:
    path = ".github/workflows/w{}.yml"
    write(tmp_path, 1, OWN)
    write(tmp_path, 2, OWN.replace("name: Demo", "name: Docker E2E"))
    # Without the line, as the workflows of the blueprint that keep their own.
    write(tmp_path, 3, SCHEDULED.replace("name: Clean-up", "name: Newest Python"))
    github.workflows = [
        workflow(1, "Demo"),
        workflow(2, "Docker E2E"),
        workflow(3, "Newest Python"),
    ]
    github.workflow_runs = {
        # Its weekly canary failed: the workflow says so in an issue of its own.
        1: [
            run_of(
                10,
                name="Demo",
                path=path.format(1),
                created=MISSED + timedelta(hours=1),
            )
        ],
        # A push passes after the schedule failed: the issue that the bot opened
        # before the workflow said that it keeps its own closes as continued there.
        2: [
            run_of(
                21,
                name="Docker E2E",
                path=path.format(2),
                event="push",
                conclusion="success",
                created=MISSED + timedelta(hours=2),
            ),
            run_of(
                20,
                name="Docker E2E",
                path=path.format(2),
                created=MISSED + timedelta(hours=1),
            ),
        ],
        # Its schedule is missed all the same, and a missed one starts.
        3: [
            run_of(
                30,
                name="Newest Python",
                path=path.format(3),
                created=MISSED - timedelta(days=6),
            )
        ],
    }
    before = github.add_issue(path.format(2), run=19, failed=1)

    summary, healthy = sweep(api_of(github), REPO, tmp_path, NOW)

    assert healthy
    assert summary.splitlines()[6:] == [
        "| `Demo` | keeps an issue of its own |",
        f"| `Docker E2E` | keeps an issue of its own: closed #{before} |",
        f"| `Newest Python` | keeps an issue of its own; {MISSED_TEXT}: started |",
    ]
    assert github.issues[before]["state"] == "closed"
    assert github.issues[before]["state_reason"] == "not_planned"
    assert github.comments[before] == [
        "`Docker E2E` keeps an issue of its own about its failures now, so this one "
        "closes."
    ]
    assert [number for number, issue in github.issues.items()] == [before]
    assert github.reruns == []
    assert github.dispatched == [(3, {"ref": "main", "inputs": {}})]


@pytest.mark.parametrize(
    ("text", "own"),
    [
        ("# bot-health: own-issue\n", True),
        ("name: Demo\n  #bot-health:own-issue (The demo breaks)\n", True),
        ("#  bot-health:  own-issue\r\n", True),
        ("# bot-health: own-issues\n", False),
        ("# bot-health: own issue\n", False),
        ("name: Demo # bot-health: own-issue\n", False),
        ("        run: echo '# bot-health: own-issue'\n", False),
        ("", False),
    ],
)
def test_the_line_of_a_workflow_that_keeps_an_issue_of_its_own(
    text: str, own: bool
) -> None:
    assert own_issue(text) is own


def test_only_a_run_of_its_schedule_or_by_hand_does_what_a_schedule_does(
    github: FakeGitHub, tmp_path: Path
) -> None:
    # A push starts the workflow too, but only its schedule tests the coming release.
    text = SCHEDULED.replace("on:\n", "on:\n  push:\n    branches: [main]\n")
    names = (
        "A pushed since",
        "B by hand since",
        "C on time",
        "D many pushes, on time",
        "E many pushes, missed",
    )
    for number, name in enumerate(names, 1):
        write(tmp_path, number, text)
        github.workflows.append(workflow(number, name))

    def run(number: int, event: str, created: datetime) -> dict[str, Any]:
        return run_of(
            number, name="x", event=event, conclusion="success", created=created
        )

    pushes = [
        run(100 - minutes, "push", MISSED + timedelta(hours=2, minutes=minutes))
        for minutes in range(55)
    ][::-1]
    late, before = MISSED + timedelta(minutes=20), MISSED - timedelta(days=6)
    github.workflow_runs = {
        1: [run(11, "push", MISSED + timedelta(hours=1)), run(10, "schedule", before)],
        2: [run(21, "workflow_dispatch", late), run(20, "schedule", before)],
        3: [run(31, "push", MISSED + timedelta(hours=1)), run(30, "schedule", late)],
        # More pushes since than a page of runs holds: GitHub names the latest run of
        # its schedule, and of a start by hand.
        4: [*pushes, run(40, "schedule", late)],
        5: [*pushes, run(50, "schedule", before)],
    }

    summary, healthy = sweep(api_of(github), REPO, tmp_path, NOW)

    assert healthy
    assert summary.splitlines()[6:] == [
        f"| `A pushed since` | passes; {MISSED_TEXT}: started |",
        "| `B by hand since` | passes |",
        "| `C on time` | passes |",
        "| `D many pushes, on time` | passes |",
        f"| `E many pushes, missed` | passes; {MISSED_TEXT}: started |",
    ]
    assert github.dispatched == [
        (1, {"ref": "main", "inputs": {}}),
        (5, {"ref": "main", "inputs": {}}),
    ]
    asked = [path.split("/actions/")[1] for _, path in github.calls if "event=" in path]
    assert asked == [
        f"workflows/{number}/runs?branch=main&event={event}"
        "&exclude_pull_requests=true&per_page=1"
        for number, event in (
            (4, "schedule"),
            (5, "schedule"),
            (5, "workflow_dispatch"),
        )
    ]


AFTER_CHECKS = """name: After the checks
on:
  workflow_run:
    # The checks.
    workflows: [CI (python), "Docs"]
    types: [completed]
jobs: {}
"""


def test_the_daily_look_leaves_the_runs_after_the_checks_of_pull_requests_alone(
    github: FakeGitHub, tmp_path: Path
) -> None:
    write(tmp_path, 1, "name: CI (python)\non:\n  push:\n  pull_request:\njobs: {}\n")
    write(tmp_path, 2, AFTER_CHECKS)
    # After the end of a run that follows the checks, in turn.
    write(
        tmp_path,
        3,
        "name: Comment\non:\n  workflow_run:\n    workflows:\n"
        "      - After the checks\n    types: [completed]\njobs: {}\n",
    )
    # After the end of a release, which no pull request runs.
    write(
        tmp_path,
        4,
        "name: Rollout\non:\n  workflow_run:\n    workflows: [Release]\n"
        "  workflow_dispatch:\njobs: {}\n",
    )
    findings = ".github/workflows/w5.yml"
    write(
        tmp_path,
        5,
        "name: Findings\non:\n  workflow_run:\n    workflows: [CI (python)]\n"
        "  schedule:\n    - cron: '0 0 * * *'\n  workflow_dispatch:\njobs: {}\n",
    )
    github.workflows = [
        workflow(1, "CI (python)"),
        workflow(2, "After the checks"),
        workflow(3, "Comment"),
        workflow(4, "Rollout"),
        workflow(5, "Findings", path=findings),
    ]
    # GitHub gives the runs after the checks of a pull request the default branch,
    # its latest commit and the repository itself.
    github.workflow_runs = {
        2: [run_of(20, name="After the checks", event="workflow_run")],
        3: [run_of(30, name="Comment", event="workflow_run", conclusion="success")],
        4: [run_of(40, name="Rollout", event="workflow_run")],
        5: [
            run_of(50, name="Findings", path=findings, event="workflow_run"),
            run_of(
                51,
                name="Findings",
                path=findings,
                conclusion="success",
                created=NOW - timedelta(hours=7),
            ),
        ],
    }
    comment = github.add_issue(".github/workflows/w3.yml", run=29, failed=1)

    summary, healthy = sweep(api_of(github), REPO, tmp_path, NOW)

    assert healthy
    assert summary.splitlines()[6:] == [
        "| `After the checks` | no finished run on `main` |",
        "| `CI (python)` | no finished run on `main` |",
        "| `Comment` | no finished run on `main` |",
        # Its runs after the checks don't count, those of its schedule do.
        "| `Findings` | passes |",
        "| `Rollout` | fails: opened #2 |",
    ]
    assert github.issues[comment]["state"] == "open"
    assert set(github.issues) == {comment, 2}
    assert github.dispatched == []


@pytest.mark.parametrize(
    ("text", "events"),
    [
        (
            "on:\n  push:\n    branches: [main]\n\n  pull_request:\njobs:\n",
            {"push", "pull_request"},
        ),
        ("on: [push, pull_request_target]\n", {"push", "pull_request_target"}),
        ("on: push\n", {"push"}),
        ("on: []\n", set()),
        ("name: No events\n", set()),
    ],
)
def test_the_events_of_a_workflow(text: str, events: set[str]) -> None:
    assert events_of(text) == events


@pytest.mark.parametrize(
    ("text", "names"),
    [
        (AFTER_CHECKS, {"CI (python)", "Docs"}),
        (
            "on:\n  workflow_run:\n    workflows:\n      - 'A'\n      - B C\n"
            "    types: [completed]\n",
            {"A", "B C"},
        ),
        ("on:\n  workflow_run:\n    workflows: []\n", set()),
        ("on:\n  push:\n", set()),
        # A list that can't be read: it may name the checks.
        ("on:\n  workflow_run:\n    types: [completed]\n", None),
        ("on:\n  workflow_run:\n    workflows: ${{ x }}\n", None),
    ],
)
def test_the_workflows_whose_end_starts_a_workflow(
    text: str, names: set[str] | None
) -> None:
    assert started_after(text) == names


def test_a_workflow_after_an_unreadable_one_follows_the_checks() -> None:
    unreadable = "on:\n  workflow_run:\n    types: [completed]\n"
    found = after_pull_requests(
        [
            ("Unreadable", unreadable),
            ("After it", "on:\n  workflow_run:\n    workflows: [Unreadable]\n"),
            ("Release", "on:\n  push:\n"),
            ("Rollout", "on:\n  workflow_run:\n    workflows: [Release]\n"),
        ]
    )
    assert found == {"Unreadable", "After it"}


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


def cron_of(text: str) -> Cron:
    cron = Cron.parse(text)
    assert cron is not None, text
    return cron


@pytest.mark.parametrize(
    ("text", "low", "high", "names", "values"),
    [
        ("*", 0, 59, (), set(range(60))),
        ("5", 0, 59, (), {5}),
        # Lists, ranges and steps, also of a range and from a value to the end.
        ("1,3,5", 0, 59, (), {1, 3, 5}),
        ("1-5", 0, 23, (), {1, 2, 3, 4, 5}),
        ("*/15", 0, 59, (), {0, 15, 30, 45}),
        ("10-50/20", 0, 59, (), {10, 30, 50}),
        ("5/20", 0, 59, (), {5, 25, 45}),
        ("1-3,20-23/2", 0, 23, (), {1, 2, 3, 20, 22}),
        # Names, in any case, among numbers.
        ("JAN,mar-May,12", 1, 12, MONTHS, {1, 3, 4, 5, 12}),
        ("MON-FRI", 0, 7, WEEKDAYS, {1, 2, 3, 4, 5}),
    ],
)
def test_the_values_of_a_field_of_a_cron(
    text: str, low: int, high: int, names: tuple[str, ...], values: set[int]
) -> None:
    assert field_values(text, low, high, names) == values


@pytest.mark.parametrize(
    "text",
    [
        "60 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * * 13 *",
        "* * * * 8",
        "*/0 * * * *",
        "5-1 * * * *",
        "1- * * * *",
        "-1 * * * *",
        "1,,2 * * * *",
        "MON * * * *",
        "1_0 * * * *",
        "+5 * * * *",
        "? * * * *",
        "* * * *",
        "* * * * * *",
    ],
)
def test_a_cron_that_cron_cant_read(text: str) -> None:
    assert Cron.parse(text) is None


def test_sunday_is_0_and_7() -> None:
    assert cron_of("0 0 * * 7").weekdays == {0}
    assert cron_of("0 0 * * SUN,6-7").weekdays == {0, 6}


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_the_days_of_a_cron() -> None:
    # Both kinds of day limited: either matches, as in cron; Friday the 9th and
    # Tuesday the 13th.
    either = cron_of("0 0 13 * FRI")
    assert either.either
    assert either.runs_on(utc("2026-10-09").date())
    assert either.runs_on(utc("2026-10-13").date())
    assert not either.runs_on(utc("2026-10-12").date())
    # A field that starts with * limits nothing: both must match, an odd day that is
    # a Monday, the 5th and the 19th of October 2026, but not Monday the 12th.
    both = cron_of("0 0 */2 * 1")
    assert not both.either
    assert both.runs_on(utc("2026-10-05").date())
    assert both.runs_on(utc("2026-10-19").date())
    assert not both.runs_on(utc("2026-10-12").date())
    assert not both.runs_on(utc("2026-10-07").date())
    # A month that the cron doesn't name has no day of it.
    assert not cron_of("0 0 * NOV *").runs_on(utc("2026-10-08").date())


@pytest.mark.parametrize(
    ("cron", "moment", "due"),
    [
        # The same minute, whatever its seconds.
        ("17 4 * * *", "2026-10-08T04:17:59", "2026-10-08T04:17"),
        # A minute before: the day before.
        ("17 4 * * *", "2026-10-08T04:16:00", "2026-10-07T04:17"),
        # An hour whose minute is still ahead, then an earlier hour of the day.
        ("30 */6 * * *", "2026-10-08T06:10:00", "2026-10-08T00:30"),
        ("5,35 * * * *", "2026-10-08T06:20:00", "2026-10-08T06:05"),
        # Wednesday before Thursday, and the new year before October.
        ("17 4 * * 3", "2026-10-08T06:05:00", "2026-10-07T04:17"),
        ("0 0 1 1 *", "2026-10-08T06:05:00", "2026-01-01T00:00"),
    ],
)
def test_the_last_time_a_cron_was_due(cron: str, moment: str, due: str) -> None:
    assert cron_of(cron).last(utc(moment)) == utc(due)


def listing_of(values: set[int]) -> str:
    return ",".join(str(value) for value in sorted(values))


@given(
    st.sets(st.integers(0, 59), min_size=1),
    st.sets(st.integers(0, 23), min_size=1),
    st.sets(st.integers(0, 7), min_size=1),
    st.datetimes(datetime(2026, 1, 1), datetime(2027, 12, 31)),
)
def test_a_cron_was_due_last_where_a_search_of_every_minute_finds_it(
    minutes: set[int], hours: set[int], weekdays: set[int], moment: datetime
) -> None:
    cron = cron_of(
        f"{listing_of(minutes)} {listing_of(hours)} * * {listing_of(weekdays)}"
    )
    moment = moment.replace(tzinfo=UTC)
    due = moment.replace(second=0, microsecond=0)
    while not (
        due.minute in minutes
        and due.hour in hours
        and due.isoweekday() % 7 in {weekday % 7 for weekday in weekdays}
    ):
        due -= timedelta(minutes=1)

    assert cron.last(moment) == due


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
    "name",
    [
        "findings.yml",
        "issue-lifecycle.yml",
        "properties.yml",
        "release.yml",
        "sync-issue-assistant.yml",
    ],
)
def test_the_workflows_of_the_blueprint_start_as_their_schedules_do(
    name: str,
) -> None:
    text = (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")

    inputs = dispatch_inputs(text)

    dry = name in ("findings.yml", "issue-lifecycle.yml", "sync-issue-assistant.yml")
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
