"""Tests of the bot for replaced commits against a simulated GitHub."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from blueprint import branches, cli
from blueprint.github import Api
from blueprint.stale_runs import GRACE, cancel_stale_runs, checks_of

REPO = "Dennis-Otto/demo"
NOW = 1_800_000_000.0
LONG_AGO = "2027-01-15T07:00:00+00:00"
OLD = f"{0xA1:040x}"
HEAD = f"{0xB2:040x}"
OTHER = f"{0xC3:040x}"
WORKFLOW = """on:
  workflow_run:
    # The workflows of the checks.
    workflows: [CI (python), Lint, Pull request title, Docker E2E]
    types: [completed]
"""


def a_run(
    number: int,
    sha: str = OLD,
    *,
    name: str = "Lint",
    event: str = "pull_request",
    status: str = "queued",
    attempt: int = 1,
    created: str = LONG_AGO,
    branch: str = "feat/x",
) -> dict[str, Any]:
    return {
        "id": number,
        "name": name,
        "event": event,
        "status": status,
        "run_attempt": attempt,
        "created_at": created,
        "head_sha": sha,
        "head_branch": branch,
    }


def a_pull(sha: str = HEAD, state: str = "open") -> dict[str, Any]:
    return {"state": state, "head": {"sha": sha}}


class FakeGitHub:
    """The lists of the runs and the pull requests, and the cancel of a run."""

    def __init__(
        self,
        *runs: dict[str, Any],
        pulls: Sequence[dict[str, Any]] = (),
        of_commit: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.runs = list(runs)
        self.pulls = list(pulls)
        self.of_commit = of_commit or {}
        # The cancels, and everything that was asked, in order.
        self.cancelled: list[int] = []
        self.asked: list[str] = []
        # A status for every request whose path starts with one of these.
        self.fail: dict[str, int] = {}

    def __call__(
        self, arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        path = arguments[-1] if "--slurp" in arguments else arguments[4]
        self.asked.append(path)
        for start, code in self.fail.items():
            if path.startswith(start):
                return self.answer(arguments, code, {"message": "simulated failure"})
        if "--slurp" in arguments:
            return subprocess.CompletedProcess(
                arguments, 0, json.dumps(self.pages(path)), ""
            )
        if path.endswith("/cancel"):
            self.cancelled.append(int(path.split("/")[-2]))
            return self.answer(arguments, 202, {})
        sha = path.split("/")[-2]
        return self.answer(arguments, 200, self.of_commit.get(sha, []))

    def pages(self, path: str) -> list[Any]:
        if "/pulls?" in path:
            return [self.pulls]
        status = path.split("status=")[1].split("&")[0]
        found = [run for run in self.runs if run["status"] == status]
        return [{"total_count": len(found), "workflow_runs": found}]

    @staticmethod
    def answer(
        arguments: Sequence[str], code: int, data: Any
    ) -> subprocess.CompletedProcess[str]:
        if "--slurp" in arguments:
            return subprocess.CompletedProcess(
                arguments, 1, "", f"gh: {data.get('message')} (HTTP {code})"
            )
        text = f"HTTP/2.0 {code} X\r\nA: b\r\n\r\n{json.dumps(data)}"
        return subprocess.CompletedProcess(arguments, 0 if code < 400 else 1, text, "")


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / ".github/workflows/update-branches.yml"
    path.parent.mkdir(parents=True)
    path.write_text(WORKFLOW, encoding="utf-8")
    return tmp_path


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("blueprint.stale_runs.time.time", lambda: NOW)


def test_the_checks_are_the_workflows_that_the_branch_bot_follows(root: Path) -> None:
    assert checks_of(root) == {
        "CI (python)",
        "Lint",
        "Pull request title",
        "Docker E2E",
    }


def test_without_a_list_of_the_checks_the_bot_leaves_every_run_alone(
    tmp_path: Path, root: Path
) -> None:
    # No file, and a file that names no workflows: it doesn't even ask GitHub.
    assert checks_of(tmp_path / "elsewhere") == frozenset()
    (root / ".github/workflows/update-branches.yml").write_text("on: push\n", "utf-8")
    assert checks_of(root) == frozenset()
    github = FakeGitHub(a_run(1))
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.asked == []
    assert outcome.warnings == []
    assert "No run of a commit" in outcome.summary


@pytest.mark.parametrize("status", ["queued", "in_progress", "waiting", "pending"])
@pytest.mark.parametrize("event", ["pull_request", "pull_request_target"])
def test_the_run_of_a_replaced_commit_is_cancelled(
    root: Path, status: str, event: str
) -> None:
    github = FakeGitHub(a_run(1, status=status, event=event), pulls=[a_pull()])
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [1]
    assert outcome.warnings == []
    assert outcome.summary == (
        "### Runs of replaced commits\n\n"
        "The bot cancelled 1 run of commits that no open pull request has as its head "
        f"any more:\n\n- `Lint` of `{OLD[:7]}` on `feat/x`\n"
    )


def test_a_run_in_two_lists_is_cancelled_once(root: Path) -> None:
    # It left the queue between two requests.
    github = FakeGitHub(
        a_run(1),
        a_run(1, status="in_progress"),
        a_run(2, OTHER, status="in_progress"),
    )
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [1, 2]
    assert "The bot cancelled 2 runs of commits" in outcome.summary


def test_the_run_of_a_pull_request_that_closed_is_cancelled(root: Path) -> None:
    # Its commit is no head of an open pull request, and the second look finds it closed.
    github = FakeGitHub(a_run(1), of_commit={OLD: [a_pull(OLD, "closed")]})
    cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [1]


@pytest.mark.parametrize(
    "run",
    [
        # The head of a pull request, also one of another branch of the same name.
        a_run(1, HEAD),
        a_run(1, HEAD, branch="main"),
        # A run of main, a schedule, a person and a release.
        a_run(1, event="push"),
        a_run(1, event="schedule"),
        a_run(1, event="workflow_dispatch"),
        a_run(1, event="release"),
        a_run(1, event="workflow_run"),
        # What does something when a pull request closes.
        a_run(1, name="Release"),
        a_run(1, name="Issue lifecycle", event="pull_request_target"),
        a_run(1, name="Area labels", event="pull_request_target"),
        a_run(1, name="Update branches", event="pull_request_target"),
        # A run that someone started again.
        a_run(1, attempt=2),
        # A run so new that a list of GitHub may not know its head yet.
        a_run(1, created="2027-01-15T07:59:50+00:00"),
    ],
)
def test_every_other_run_stays(root: Path, run: dict[str, Any]) -> None:
    github = FakeGitHub(run, pulls=[a_pull()])
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == []
    assert outcome.warnings == []
    assert "No run of a commit" in outcome.summary


def test_a_run_goes_once_it_is_older_than_the_grace(root: Path) -> None:
    created = "2027-01-15T07:59:40+00:00"
    assert datetime.fromisoformat(created).timestamp() == NOW - GRACE
    github = FakeGitHub(a_run(1, created=created))
    cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [1]


def test_the_job_of_the_bot_leaves_its_own_run_alone(root: Path) -> None:
    # Its commit may be replaced while it runs; it still cancels the others.
    github = FakeGitHub(
        a_run(1, name="Pull request title", status="in_progress"), a_run(2)
    )
    cancel_stale_runs(Api(github), REPO, root, own_run="1")
    assert github.cancelled == [2]


def test_the_heads_come_after_the_runs(root: Path) -> None:
    # A push between the two lists makes a run look current, and never the other way
    # round: for a run of the new head, the list of the heads names it.
    github = FakeGitHub(a_run(1, HEAD), pulls=[a_pull()])
    cancel_stale_runs(Api(github), REPO, root)
    positions = [path.split("?")[0].split("/")[-1] for path in github.asked]
    assert positions == ["runs", "runs", "runs", "runs", "pulls"]


def test_without_a_run_to_cancel_it_doesnt_ask_for_the_heads(root: Path) -> None:
    github = FakeGitHub(a_run(1, event="push"))
    cancel_stale_runs(Api(github), REPO, root)
    assert not [path for path in github.asked if "/pulls" in path]


def test_the_second_look_keeps_a_head_that_the_list_missed(root: Path) -> None:
    # The list of the heads doesn't name it, but the list for the commit does.
    github = FakeGitHub(a_run(1), a_run(2), of_commit={OLD: [a_pull(OLD)]})
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == []
    assert "No run of a commit" in outcome.summary


def test_the_second_look_asks_once_for_each_commit(root: Path) -> None:
    github = FakeGitHub(a_run(1), a_run(2), a_run(3, OTHER))
    cancel_stale_runs(Api(github), REPO, root)
    looks = [path for path in github.asked if "/commits/" in path]
    assert looks == [
        f"repos/{REPO}/commits/{OLD}/pulls",
        f"repos/{REPO}/commits/{OTHER}/pulls",
    ]
    assert github.cancelled == [1, 2, 3]


def test_a_commit_that_github_no_longer_knows_is_replaced(root: Path) -> None:
    github = FakeGitHub(a_run(1))
    github.fail[f"repos/{REPO}/commits/"] = 404
    cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [1]


def test_a_second_look_without_an_answer_keeps_the_runs_of_that_commit(
    root: Path,
) -> None:
    github = FakeGitHub(a_run(1), a_run(2, OTHER))
    github.fail[f"repos/{REPO}/commits/{OLD}"] = 422
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [2]
    [warning] = outcome.warnings
    assert warning.startswith(
        f"::warning::The bot for replaced commits couldn't look at {OLD[:7]}: "
    )


@pytest.mark.parametrize("path", ["actions/runs", "pulls"])
def test_a_list_that_fails_cancels_nothing(root: Path, path: str) -> None:
    github = FakeGitHub(a_run(1))
    github.fail[f"repos/{REPO}/{path}"] = 403
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == []
    [warning] = outcome.warnings
    assert warning.startswith(
        "::warning::The bot for replaced commits stopped and cancels no more: "
        "GitHub answered 403"
    )
    assert "No run of a commit" in outcome.summary


def test_what_it_cant_read_cancels_nothing(root: Path) -> None:
    github = FakeGitHub(a_run(1, created="not a date"), a_run(2))
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == []
    [warning] = outcome.warnings
    assert "stopped and cancels no more" in warning


def test_a_run_that_ended_a_moment_ago_is_no_warning(root: Path) -> None:
    github = FakeGitHub(a_run(1), a_run(2))
    github.fail[f"repos/{REPO}/actions/runs/1/cancel"] = 409
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [2]
    assert outcome.warnings == []
    assert "The bot cancelled 1 run of commits" in outcome.summary


def test_a_cancel_that_github_refuses_is_a_warning_and_the_bot_goes_on(
    root: Path,
) -> None:
    github = FakeGitHub(a_run(1), a_run(2))
    github.fail[f"repos/{REPO}/actions/runs/1/cancel"] = 403
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert github.cancelled == [2]
    [warning] = outcome.warnings
    assert warning.startswith(
        "::warning::The bot for replaced commits couldn't cancel run 1: "
    )


def test_a_dry_run_only_says_which(root: Path) -> None:
    github = FakeGitHub(a_run(1), a_run(2, name="Pull request title"))
    outcome = cancel_stale_runs(Api(github), REPO, root, dry_run=True)
    assert github.cancelled == []
    assert "The bot would cancel 2 runs of commits" in outcome.summary


def test_a_branch_name_is_only_code_in_the_summary(root: Path) -> None:
    github = FakeGitHub(a_run(1, branch="x`](http://evil)"))
    outcome = cancel_stale_runs(Api(github), REPO, root)
    assert "`x'](http://evil)`" in outcome.summary


def test_the_command_says_what_it_did_and_never_fails(
    root: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(root)
    monkeypatch.setenv("GITHUB_RUN_ID", "2")
    github = FakeGitHub(a_run(1), a_run(2))
    assert cli.main(["--repo", REPO, "stale-runs"], api=Api(github)) == 0
    assert github.cancelled == [1]
    out, err = capsys.readouterr()
    assert out.startswith("### Runs of replaced commits\n")
    assert err == ""

    # What GitHub refuses is an annotation: this job is a check of the pull request.
    github = FakeGitHub(a_run(1))
    github.fail[f"repos/{REPO}/pulls"] = 500
    assert cli.main(["--repo", REPO, "stale-runs"], api=Api(github)) == 0
    out, err = capsys.readouterr()
    assert "No run of a commit" in out
    assert err.startswith("::warning::The bot for replaced commits stopped")

    github = FakeGitHub(a_run(1))
    assert cli.main(["--repo", REPO, "stale-runs", "--dry-run"], api=Api(github)) == 0
    assert github.cancelled == []
    assert "The bot would cancel 1 run" in capsys.readouterr().out


def test_the_branch_bot_sweeps_in_its_job_with_the_token_of_the_job(
    root: Path,
) -> None:
    # The branch bot's own requests go through its first argument, the token of the
    # release app; the runs through the token of the job, which alone may cancel them.
    app = subprocess_of_the_app()
    github = FakeGitHub(a_run(1))
    job = branches.Job(Api(github), "demo-release[bot]")
    outcome = branches.next_branch(Api(app), REPO, job, root)
    assert github.cancelled == [1]
    assert outcome.summary.startswith("### Branch bot\n")
    assert "\n\n### Runs of replaced commits\n" in outcome.summary
    assert outcome.warnings == []
    assert outcome.notices == []


def test_what_github_refuses_the_sweep_of_the_branch_bot_fails_no_run(
    root: Path,
) -> None:
    github = FakeGitHub(a_run(1))
    github.fail[f"repos/{REPO}/pulls"] = 500
    job = branches.Job(Api(github), "demo-release[bot]")
    outcome = branches.next_branch(Api(subprocess_of_the_app()), REPO, job, root)
    assert github.cancelled == []
    assert outcome.warnings == []
    [notice] = outcome.notices
    assert "stopped and cancels no more" in notice


def test_outside_of_a_job_the_branch_bot_leaves_the_runs_alone(root: Path) -> None:
    # On the computer of a person, or without the checkout that names the checks.
    app = subprocess_of_the_app()
    outcome = branches.next_branch(Api(app), REPO, None, root)
    assert "Runs of replaced commits" not in outcome.summary
    github = FakeGitHub(a_run(1))
    job = branches.Job(Api(github), "demo-release[bot]")
    outcome = branches.next_branch(Api(app), REPO, job)
    assert github.asked == []
    assert "Runs of replaced commits" not in outcome.summary


def subprocess_of_the_app() -> Any:
    """The GitHub of the branch bot with an empty line, and its token."""

    def run(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if arguments[0] == "pr":
            return subprocess.CompletedProcess(arguments, 0, "[]", "")
        path = arguments[4]
        data: Any = {"default_branch": "main"} if path == f"repos/{REPO}" else []
        return subprocess.CompletedProcess(
            arguments, 0, f"HTTP/2.0 200 X\r\nA: b\r\n\r\n{json.dumps(data)}", ""
        )

    return run
