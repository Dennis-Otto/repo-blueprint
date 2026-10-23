"""Tests of dashboard.py against a simulated GitHub."""

from __future__ import annotations

import base64
import contextlib
import dataclasses
import io
import json
import subprocess
import urllib.error
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest
from shell import BASH
from workflow_steps import run_step

import dashboard
from blueprint.github import Api

NOW = datetime(2026, 10, 8, 6, 5, tzinfo=UTC)


def content(text: str) -> dict[str, str]:
    return {"content": base64.b64encode(text.encode()).decode()}


def run(status: str, conclusion: str | None = None, **more: Any) -> dict[str, Any]:
    return {
        "status": status,
        "conclusion": conclusion,
        "html_url": "https://run",
        "event": "push",
        **more,
    }


def listed(*found: dict[str, Any]) -> dict[str, Any]:
    return {"total_count": len(found), "workflow_runs": list(found)}


def last_runs(repo: str, workflow: str) -> str:
    return (
        f"repos/Dennis-Otto/{repo}/actions/workflows/{workflow}/runs"
        f"?branch=main&per_page={dashboard.LAST_RUNS}&exclude_pull_requests=true"
    )


def workflows(*files: str, deleted: Sequence[str] = ()) -> dict[str, Any]:
    found = [{"path": f".github/workflows/{name}", "state": "active"} for name in files]
    found += [
        {"path": f".github/workflows/{name}", "state": "deleted"} for name in deleted
    ]
    return {"total_count": len(found), "workflows": found}


ROUTES: dict[str, tuple[int, Any]] = {
    "repos/Dennis-Otto/repo-blueprint/releases/latest": (200, {"tag_name": "v0.3.0"}),
    "users/Dennis-Otto/repos?type=owner&per_page=100": (
        200,
        [
            {
                "full_name": "Dennis-Otto/demo",
                "description": "A demo <of> the blueprint",
                "homepage": "https://dennis-otto.github.io/demo/",
                "stargazers_count": 12,
            },
            {"full_name": "Dennis-Otto/old", "archived": True},
            {"full_name": "Dennis-Otto/fork", "fork": True},
            {"full_name": "Dennis-Otto/secret", "private": True},
            {"full_name": "Dennis-Otto/behind"},
            {"full_name": "Dennis-Otto/plain"},
            {"full_name": "Dennis-Otto/repo-blueprint"},
        ],
    ),
    "repos/Dennis-Otto/demo/contents/.copier-answers.yml": (
        200,
        content("_commit: v0.3.0\nproject_type: github-action\nowner: Dennis-Otto\n"),
    ),
    "repos/Dennis-Otto/behind/contents/.copier-answers.yml": (
        200,
        content("_commit: v0.2.0\nproject_type: nextcloud-app\n"),
    ),
    "repos/Dennis-Otto/demo/releases/latest": (
        200,
        {"tag_name": "v1.2.2", "published_at": "2026-10-07T12:00:00Z"},
    ),
    "repos/Dennis-Otto/demo/pulls?state=open&per_page=100": (
        200,
        [
            {
                "title": "chore: release 1.3.0",
                "html_url": "https://pull/5",
                "labels": [{"name": "autorelease: pending"}],
            },
            {"title": "feat: a", "html_url": "https://pull/6", "labels": []},
            {
                "title": "fix: b",
                "html_url": "https://pull/7",
                "labels": [{"name": "merge-conflict"}],
            },
        ],
    ),
    "repos/Dennis-Otto/demo/actions/workflows?per_page=100": (
        200,
        workflows(
            "ci.yml",
            "codeql.yml",
            "release.yml",
            "verify-release.yml",
            "docs.yml",
            "findings.yml",
            "links.yml",
            "mutation.yml",
            deleted=["settings.yml"],
        ),
    ),
    last_runs("demo", "ci.yml"): (200, listed(run("completed", "success"))),
    last_runs("demo", "codeql.yml"): (200, listed(run("completed", "failure"))),
    last_runs("demo", "release.yml"): (200, listed(run("in_progress"))),
    last_runs("demo", "links.yml"): (200, listed()),
    last_runs("demo", "docs.yml"): (
        200,
        listed(run("completed", "success", html_url="https://docs")),
    ),
    # A run of Findings that the CodeQL of a pull request started is skipped on main,
    # and a pull request from the main of a fork runs on a branch of that name too:
    # neither says how main does.
    last_runs("demo", "findings.yml"): (
        200,
        listed(
            run("completed", "success", event="pull_request"),
            # A busy hour of pull requests skips more than ten runs in a row.
            *[run("completed", "skipped")] * 12,
            run("completed", "failure", html_url="https://findings"),
        ),
    ),
    last_runs("demo", "mutation.yml"): (
        200,
        listed(run("completed", "failure", html_url="https://mutation")),
    ),
    # The weekly verification failed before the release that the Release workflow
    # verified since.
    last_runs("demo", "verify-release.yml"): (
        200,
        listed(
            run("completed", "failure", created_at="2026-10-01T05:17:00Z"),
        ),
    ),
    "repos/Dennis-Otto/demo/commits/v1.2.2": (200, {"sha": "abc123"}),
    "repos/Dennis-Otto/demo/commits/v0.1.0": (200, {"sha": "fff000"}),
    "repos/Dennis-Otto/demo/actions/workflows/release.yml/runs?head_sha=abc123&event=push&per_page=1": (
        200,
        listed({"id": 50}),
    ),
    "repos/Dennis-Otto/demo/actions/runs/50/jobs?per_page=100": (
        200,
        {
            "jobs": [
                {"name": "release pull request", "status": "completed"},
                {
                    "name": "verify / verify the release",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-10-07T12:05:00Z",
                    "html_url": "https://verify",
                },
            ]
        },
    ),
    # The blueprint runs a CI for each stack; its own is that of Python.
    "repos/Dennis-Otto/repo-blueprint/actions/workflows?per_page=100": (
        200,
        workflows("ci-node.yml", "ci-python.yml", "renovate.yml"),
    ),
    last_runs("repo-blueprint", "ci-python.yml"): (
        200,
        listed(run("completed", "success", html_url="https://ci-python")),
    ),
    last_runs("repo-blueprint", "renovate.yml"): (
        200,
        listed(run("completed", "failure", html_url="https://renovate")),
    ),
}


def simulated(routes: dict[str, tuple[int, Any]]) -> Api:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        if "--paginate" in arguments:
            # gh api --paginate --slurp: every page in one list; here one page.
            status, data = routes.get(arguments[-1], (404, {"message": "Not Found"}))
            if status >= 400:
                error = f"gh: {data['message']} (HTTP {status})"
                return subprocess.CompletedProcess(arguments, 1, "", error)
            return subprocess.CompletedProcess(arguments, 0, json.dumps([data]), "")
        status, data = routes.get(arguments[4], (404, {"message": "Not Found"}))
        answer = f"HTTP/2.0 {status} X\n\n{json.dumps(data)}"
        return subprocess.CompletedProcess(arguments, 0, answer, "")

    return Api(runner)


def opener(url: str, timeout: float) -> io.BytesIO:
    # No request may wait forever on a server that doesn't answer.
    assert timeout == dashboard.TIMEOUT
    if url.endswith("/demo"):
        return io.BytesIO(json.dumps({"score": 7.6}).encode())
    if url.endswith("/behind"):
        return io.BytesIO(json.dumps({"score": "unknown"}).encode())
    raise urllib.error.URLError("offline")


def test_a_repository_on_the_blueprint() -> None:
    row = dashboard.collect(simulated(ROUTES), "Dennis-Otto/demo", opener)

    assert (row.kind, row.blueprint, row.ci) == ("github-action", "v0.3.0", "ci.yml")
    assert (row.release, row.released) == ("v1.2.2", "2026-10-07")
    assert (row.next_release, row.next_url) == ("1.3.0", "https://pull/5")
    assert (row.pulls, row.conflicts, row.update) == (2, 1, None)
    assert row.runs["CI"].state == "success"
    assert row.runs["CodeQL"].state == "failure"
    assert row.runs["Release"].state == "running"
    assert row.runs["Links"].state == "none"
    assert row.runs["Website"] == dashboard.Run("success", "https://docs")
    assert row.runs["Findings"] == dashboard.Run("failure", "https://findings")
    assert row.runs["Mutation"] == dashboard.Run("failure", "https://mutation")
    # The Settings workflow is gone, and Renovate runs in the blueprint alone.
    assert row.runs["Settings"].state == "absent"
    assert row.runs["Renovate"].state == "absent"
    assert row.scorecard == 7.6


def test_the_verification_is_the_newer_of_its_own_run_and_that_of_the_release() -> None:
    api = simulated(ROUTES)
    older = dashboard.Run("failure", "https://weekly", "2026-10-01T05:17:00Z")
    newer = dashboard.Run("failure", "https://weekly", "2026-10-08T05:17:00Z")
    verified = dashboard.Run("success", "https://verify", "2026-10-07T12:05:00Z")

    assert dashboard.verification(api, "Dennis-Otto/demo", "v1.2.2", older) == verified
    assert dashboard.verification(api, "Dennis-Otto/demo", "v1.2.2", newer) == newer
    # Without a release, a commit of its tag or a run of the Release workflow for
    # it, the verification's own runs are all there is.
    for tag in ("", "v0.0.1", "v0.1.0"):
        assert dashboard.verification(api, "Dennis-Otto/demo", tag, older) == older


def test_the_verification_comes_from_the_push_that_made_the_release() -> None:
    # A scheduled run of Release on the same commit is newer and skips its
    # verification; the push run that merged the release pull request holds it.
    routes = dict(ROUTES)
    routes[
        "repos/Dennis-Otto/demo/actions/workflows/release.yml/runs?head_sha=abc123&per_page=1"
    ] = (200, listed({"id": 60, "event": "schedule"}))
    routes["repos/Dennis-Otto/demo/actions/runs/60/jobs?per_page=100"] = (
        200,
        {"jobs": [{"name": "verify", "status": "completed", "conclusion": "skipped"}]},
    )
    older = dashboard.Run("failure", "https://weekly", "2026-10-01T05:17:00Z")

    assert dashboard.verification(
        simulated(routes), "Dennis-Otto/demo", "v1.2.2", older
    ) == dashboard.Run("success", "https://verify", "2026-10-07T12:05:00Z")


def test_a_release_run_without_a_verification() -> None:
    routes = dict(ROUTES)
    routes["repos/Dennis-Otto/demo/actions/runs/50/jobs?per_page=100"] = (
        200,
        {"jobs": [{"name": "verify", "status": "completed", "conclusion": "skipped"}]},
    )
    none = dashboard.Run("none")

    assert (
        dashboard.verification(simulated(routes), "Dennis-Otto/demo", "v1.2.2", none)
        == none
    )


def test_the_verification_of_a_repository_on_the_page() -> None:
    row = dashboard.collect(simulated(ROUTES), "Dennis-Otto/demo", opener)

    assert row.runs["Verification"] == dashboard.Run(
        "success", "https://verify", "2026-10-07T12:05:00Z"
    )


def test_the_blueprint_finds_its_own_ci() -> None:
    row = dashboard.collect(simulated(ROUTES), "Dennis-Otto/repo-blueprint", opener)

    assert row.ci == "ci-python.yml"
    assert row.runs["CI"] == dashboard.Run("success", "https://ci-python")
    assert row.runs["Renovate"] == dashboard.Run("failure", "https://renovate")


def test_the_scorecard_closes_the_answer_of_an_error() -> None:
    error = http_error(dashboard.SCORECARD_API + "Dennis-Otto/demo", 404, "Not Found")

    def failing(url: str, timeout: float) -> io.BytesIO:
        raise error

    assert dashboard.scorecard("Dennis-Otto/demo", failing) is None
    assert error.closed


def test_repositories_without_the_blueprint_or_a_release() -> None:
    api = simulated(ROUTES)
    blueprint_row = dashboard.collect(api, "Dennis-Otto/repo-blueprint", opener)
    behind = dashboard.collect(api, "Dennis-Otto/behind", opener)

    assert (blueprint_row.kind, blueprint_row.blueprint) == ("", "")
    assert blueprint_row.release == "v0.3.0"
    assert blueprint_row.scorecard is None
    assert (behind.kind, behind.blueprint) == ("nextcloud-app", "v0.2.0")
    assert (behind.release, behind.next_release, behind.pulls) == ("", "", 0)
    assert behind.scorecard is None
    # A repository without workflows has the CI of the blueprint's projects, in name.
    assert behind.ci == "ci.yml"
    assert {item.state for item in behind.runs.values()} == {"absent"}


def update_pull(sha: str = "def456") -> dict[str, Any]:
    return {
        "number": 226,
        "title": "chore: update to the blueprint v0.10.1",
        "html_url": "https://pull/226",
        "labels": [],
        "head": {"ref": "blueprint/update", "sha": sha},
    }


@pytest.mark.parametrize(
    ("checks", "state"),
    [
        ([], "running"),
        (
            [
                {"status": "in_progress"},
                {"status": "completed", "conclusion": "success"},
            ],
            "running",
        ),
        (
            [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "skipped"},
                {"status": "completed", "conclusion": "neutral"},
            ],
            "success",
        ),
        (
            [
                {"status": "in_progress"},
                {"status": "completed", "conclusion": "failure"},
            ],
            "failure",
        ),
    ],
)
def test_an_update_of_the_blueprint_in_flight(
    checks: list[dict[str, str]], state: str
) -> None:
    routes = dict(ROUTES)
    routes["repos/Dennis-Otto/behind/pulls?state=open&per_page=100"] = (
        200,
        [update_pull()],
    )
    routes["repos/Dennis-Otto/behind/commits/def456/check-runs?per_page=100"] = (
        200,
        {"total_count": len(checks), "check_runs": checks},
    )

    row = dashboard.collect(simulated(routes), "Dennis-Otto/behind", opener)

    assert row.pulls == 1
    assert row.update == dashboard.Update("v0.10.1", 226, "https://pull/226", state)


def test_an_update_with_an_unusual_title() -> None:
    pull = update_pull(sha="")
    pull["title"] = "chore: update the blueprint"

    assert dashboard.update(simulated({}), "Dennis-Otto/behind", pull) == (
        dashboard.Update("", 226, "https://pull/226", "running")
    )


def test_the_repositories_are_the_public_ones_of_the_owner() -> None:
    api = simulated(ROUTES)
    found = dashboard.listing(api, "Dennis-Otto")

    assert dashboard.repositories(api, "Dennis-Otto") == [
        "Dennis-Otto/behind",
        "Dennis-Otto/demo",
        "Dennis-Otto/plain",
        "Dennis-Otto/repo-blueprint",
    ]
    # What GitHub lists about each one stays for the data of the dashboard.
    assert [repo["full_name"] for repo in found] == dashboard.repositories(
        api, "Dennis-Otto"
    )
    assert found[1]["stargazers_count"] == 12


def test_the_page_shows_each_state(tmp_path: Path) -> None:
    out = tmp_path / "site" / "index.html"
    assert (
        dashboard.main(
            ["--owner", "Dennis-Otto", "--out", str(out)],
            api=simulated(ROUTES),
            opener=opener,
            now=NOW,
        )
        == 0
    )
    page = out.read_text(encoding="utf-8")

    assert "as of 2026-10-08 06:05 UTC" in page
    assert "latest release is v0.3.0" in page
    assert '<td class="ok">✔ v0.3.0</td>' in page
    assert '<td class="wait">v0.2.0 → v0.3.0</td>' in page
    assert '<td class="ok">the blueprint</td>' in page
    assert '<td class="wait">not on it</td>' in page
    assert '<a href="https://pull/5">1.3.0</a>' in page
    assert "2, 1 in conflict" in page
    assert 'title="CodeQL: failed"' in page
    assert 'title="Release: running"' in page
    assert 'title="Links: no run"' in page
    assert 'title="Settings: not set up"' in page
    assert 'title="Verification: passed"><a href="https://verify">✔</a>' in page
    assert 'title="Website: passed"><a href="https://docs">✔</a>' in page
    assert "<th>Verification</th><th>Website</th>" in page
    # A feed reader and a script find the data of the page from its head.
    assert (
        '<link rel="alternate" type="application/atom+xml" '
        'title="The releases of every repository" href="releases.atom">'
    ) in page
    assert '<link rel="alternate" type="application/json"' in page
    for name in ("repos.json", "history.json", "releases.atom"):
        assert f'<a href="{name}">{name}</a>' in page
    assert ">7.6</a>" in page
    assert "<th>Mutation</th><th>Renovate</th>" in page
    assert "<th>First answer by a person</th>" in page
    # The head and a row for each repository, in the table of the state and of health.
    assert page.count("<tr>") == 10


def test_the_page_shows_an_update_in_flight() -> None:
    rows = [
        dashboard.Row(
            "Dennis-Otto/behind",
            blueprint="v0.9.1",
            update=dashboard.Update("v0.10.1", 226, "https://pull/226", state),
        )
        for state in ("success", "failure", "running")
    ]
    rows.append(
        dashboard.Row(
            "Dennis-Otto/odd",
            blueprint="v0.9.1",
            update=dashboard.Update("", 227, "https://pull/227", "running"),
        )
    )

    page = dashboard.render(rows, "Dennis-Otto", "v0.10.2", NOW)

    for css, words in (("ok", "passed"), ("bad", "failed"), ("wait", "running")):
        assert (
            f'<td class="{css}" title="the update of the blueprint: checks {words}">'
            '<a href="https://pull/226">v0.9.1 → v0.10.1 · #226</a></td>'
        ) in page
    assert ">v0.9.1 → v0.10.2 · #227</a>" in page


def test_a_failure_of_github_stops_the_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    routes = dict(ROUTES)
    routes["users/Dennis-Otto/repos?type=owner&per_page=100"] = (
        502,
        {"message": "Bad"},
    )
    out = tmp_path / "index.html"

    assert (
        dashboard.main(
            ["--owner", "Dennis-Otto", "--out", str(out)],
            api=simulated(routes),
            opener=opener,
        )
        == 2
    )
    assert "502" in capsys.readouterr().err
    assert not out.exists()


# ------------------------------------------------------------------------- health


def zipped(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, text in files.items():
            archive.writestr(name, text)
    return buffer.getvalue()


def successful(workflow: str) -> str:
    return (
        f"repos/Dennis-Otto/demo/actions/workflows/{workflow}/runs"
        "?branch=main&status=success&per_page=10&exclude_pull_requests=true"
    )


HEALTH: dict[str, tuple[int, Any]] = {
    # A pull request from the main of a fork runs on a branch of that name too; it
    # tells nothing about main.
    successful("ci.yml"): (
        200,
        {
            "workflow_runs": [
                {
                    "id": 10,
                    "event": "pull_request",
                    "run_started_at": "2026-10-06T09:00:00Z",
                    "updated_at": "2026-10-06T10:00:00Z",
                },
                {
                    "id": 11,
                    "event": "push",
                    "run_started_at": "2026-10-06T10:00:00Z",
                    "updated_at": "2026-10-06T10:04:00Z",
                },
                {"run_started_at": None, "updated_at": "2026-10-06T10:04:00Z"},
            ]
        },
    ),
    "repos/Dennis-Otto/demo/actions/runs/11/artifacts": (
        200,
        {
            "artifacts": [
                {"id": 1, "name": "coverage", "expired": True},
                {"id": 2, "name": "other"},
                {"id": 3, "name": "coverage"},
            ]
        },
    ),
    successful("mutation.yml"): (
        200,
        {
            "workflow_runs": [
                {"id": 21, "event": "pull_request_target"},
                {"id": 22, "event": "workflow_dispatch"},
            ]
        },
    ),
    "repos/Dennis-Otto/demo/actions/runs/21/artifacts": (
        200,
        {"artifacts": [{"id": 5, "name": "mutation"}]},
    ),
    "repos/Dennis-Otto/demo/actions/runs/22/artifacts": (
        200,
        {"artifacts": [{"id": 4, "name": "mutation"}]},
    ),
    "repos/Dennis-Otto/demo/releases?per_page=100": (
        200,
        [
            {"published_at": "2026-10-01T00:00:00Z"},
            {"published_at": "2026-10-02T00:00:00Z", "prerelease": True},
            {"published_at": None},
            {"published_at": "2026-01-01T00:00:00Z"},
        ],
    ),
    "repos/Dennis-Otto/demo/issues?state=all&since=2026-07-10T06:05:00Z&per_page=100": (
        200,
        [
            {"number": 9, "pull_request": {}},
            {
                "number": 8,
                "created_at": "2026-10-01T00:00:00Z",
                "user": {"login": "reporter", "type": "User"},
            },
            {
                "number": 7,
                "created_at": "2026-10-02T00:00:00Z",
                "user": {"login": "reporter", "type": "User"},
            },
            {
                "number": 6,
                "created_at": "2026-05-01T00:00:00Z",
                "user": {"login": "reporter", "type": "User"},
            },
            # An issue that a bot opened, such as a report of a failed bot, waits for
            # no person.
            {
                "number": 5,
                "created_at": "2026-10-03T00:00:00Z",
                "user": {"login": "release-app[bot]", "type": "Bot"},
            },
        ],
    ),
    # The issue assistant answers within minutes; the first answer of a person counts.
    "repos/Dennis-Otto/demo/issues/8/comments?per_page=30": (
        200,
        [
            {"user": {"login": "reporter"}, "created_at": "2026-10-01T01:00:00Z"},
            {
                "user": {"login": "issue-assistant", "type": "Bot"},
                "created_at": "2026-10-01T01:05:00Z",
            },
            {
                "user": {"login": "github-actions[bot]"},
                "created_at": "2026-10-01T01:06:00Z",
            },
            {
                "user": {"login": "maintainer", "type": "User"},
                "created_at": "2026-10-01T04:00:00Z",
            },
        ],
    ),
    "repos/Dennis-Otto/demo/issues/7/comments?per_page=30": (200, []),
    "repos/Dennis-Otto/demo/issues/5/comments?per_page=30": (
        200,
        [{"user": {"login": "maintainer"}, "created_at": "2026-10-03T00:30:00Z"}],
    ),
}


def downloader(path: str) -> bytes:
    if path.endswith("/3/zip"):
        return zipped({"coverage.xml": '<coverage line-rate="0.5"/>'})
    assert path.endswith("/4/zip"), path
    return zipped({"results.txt": "a: killed\nb: killed\nc: killed\nd: survived\n"})


def test_the_health_of_a_repository() -> None:
    health = dashboard.health(simulated(HEALTH), downloader, "Dennis-Otto/demo", NOW)

    assert health == dashboard.Health(
        coverage=50.0, mutation=75.0, releases=1, answer_hours=4.0, ci_minutes=4.0
    )


def test_the_health_of_a_repository_with_its_own_ci() -> None:
    routes = {
        successful("ci-python.yml") if key == successful("ci.yml") else key: value
        for key, value in HEALTH.items()
    }

    health = dashboard.health(
        simulated(routes), downloader, "Dennis-Otto/demo", NOW, "ci-python.yml"
    )

    assert (health.coverage, health.ci_minutes) == (50.0, 4.0)


def test_a_repository_without_reports_has_no_health_values() -> None:
    health = dashboard.health(simulated({}), downloader, "Dennis-Otto/demo", NOW)

    assert health == dashboard.Health()


def broken_zip(path: str) -> bytes:
    if path.endswith("/3/zip"):
        return b"no zip"
    return downloader(path)


def broken_xml(path: str) -> bytes:
    if path.endswith("/3/zip"):
        return zipped({"coverage.xml": "<coverage"})
    return downloader(path)


def broken_rate(path: str) -> bytes:
    if path.endswith("/3/zip"):
        return zipped({"coverage.xml": '<coverage line-rate="many"/>'})
    return downloader(path)


def gh_fails(path: str) -> bytes:
    if path.endswith("/3/zip"):
        raise subprocess.CalledProcessError(1, ["gh", "api", path])
    return downloader(path)


@pytest.mark.parametrize("download", [broken_zip, broken_xml, broken_rate, gh_fails])
def test_a_broken_report_leaves_out_its_value_alone(
    download: dashboard.Downloader, capsys: pytest.CaptureFixture[str]
) -> None:
    health = dashboard.health(simulated(HEALTH), download, "Dennis-Otto/demo", NOW)

    assert health == dashboard.Health(
        coverage=None, mutation=75.0, releases=1, answer_hours=4.0, ci_minutes=4.0
    )
    assert (
        "the coverage report of Dennis-Otto/demo is unreadable"
        in capsys.readouterr().err
    )


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (
            {"build/infection-summary.log": "Mutation Score Indicator (MSI): 81.5%\n"},
            81.5,
        ),
        # The artifact of a Nextcloud app: the output of Infection next to its logs.
        # Its score is that of the code that the tests run, as that of mutmut, which
        # leaves out the mutants that no test runs.
        (
            {
                "infection-summary.log": "Total: 40\n\nKilled by Test Framework: 30\n",
                "infection-output.log": "Metrics:\n"
                "         Mutation Score Indicator (MSI): 75%\n"
                "         Mutation Code Coverage: 87%\n"
                "         Covered Code MSI: 86%\n",
            },
            86.0,
        ),
        ({"results.txt": "nothing ran\n"}, None),
        ({}, None),
    ],
)
def test_the_score_of_the_mutants(
    files: dict[str, str], expected: float | None
) -> None:
    data = {name: text.encode() for name, text in files.items()}

    assert dashboard.mutation(data) == expected


def test_a_coverage_report_without_a_rate() -> None:
    assert dashboard.coverage({"coverage.xml": b"<coverage/>"}) is None
    assert dashboard.coverage({"notes.txt": b"no report"}) is None
    assert dashboard.coverage({"lcov.info": b"SF:a.ts\nend_of_record\n"}) is None


def test_the_coverage_of_a_node_package_comes_from_its_lcov_report() -> None:
    lcov = b"SF:src/a.ts\nDA:1,1\nDA:2,0\nend_of_record\nSF:src/b.ts\nDA:1,3\n"

    assert dashboard.coverage({"lcov.info": lcov}) == pytest.approx(200 / 3)
    with pytest.raises(dashboard.UNREADABLE):
        dashboard.coverage({"lcov.info": b"SF:\xff\n"})


def http_error(url: str, code: int, msg: str) -> urllib.error.HTTPError:
    """An error as urlopen raises it: the answer of the server too, with its body."""
    return urllib.error.HTTPError(url, code, msg, Message(), io.BytesIO(b"{}"))


def published(url: str, timeout: float) -> io.BytesIO:
    """The website of the dashboard, with its history, and a few broken ones."""
    assert timeout == dashboard.TIMEOUT
    if url == "https://site/history.json":
        return io.BytesIO(
            json.dumps(
                [
                    {"date": "2026-10-01", "repos": {}},
                    "noise",
                    {"date": 20261002},
                    {"date": "2026-10-03", "repos": []},
                    {"date": "2026-10-04"},
                ]
            ).encode()
        )
    if url == "https://site/object.json":
        return io.BytesIO(b'{"date": "2026-10-01"}')
    if url == "https://site/torn.json":
        return io.BytesIO(b'[{"date": "2026-10-01", "re')
    if url == "https://site/gone.json":
        raise http_error(url, 404, "Not Found")
    if url == "https://site/busy.json":
        raise http_error(url, 503, "Unavailable")
    if url == "https://site/slow.json":
        raise TimeoutError("timed out")
    return opener(url, timeout)


def test_the_history_comes_from_the_published_dashboard() -> None:
    assert dashboard.load_history("https://site/history.json", published) == [
        {"date": "2026-10-01", "repos": {}},
        {"date": "2026-10-04"},
    ]
    # Nothing is published yet: the history starts today.
    assert dashboard.load_history("https://site/gone.json", published) == []
    assert dashboard.load_history("", published) == []


@pytest.mark.parametrize("code", [404, 503])
def test_the_history_closes_the_answer_of_an_error(code: int) -> None:
    # Left open, it warns as the garbage collector closes it, which the newest Python
    # does for every error that urlopen raises, and the tests fail on the warning.
    error = http_error("https://site/history.json", code, "Failed")

    def opener(url: str, timeout: float) -> io.BytesIO:
        raise error

    with contextlib.suppress(dashboard.HistoryError):
        dashboard.load_history("https://site/history.json", opener)

    assert error.closed


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("https://site/busy.json", "HTTP Error 503"),
        ("https://site/slow.json", "timed out"),
        ("https://site/offline.json", "offline"),
        ("https://site/torn.json", "Unterminated string"),
        ("https://site/object.json", "holds no list"),
    ],
)
def test_a_history_that_cant_be_read_is_never_replaced(url: str, reason: str) -> None:
    with pytest.raises(dashboard.HistoryError, match=reason):
        dashboard.load_history(url, published)


def test_the_dashboard_keeps_its_page_when_the_history_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "site" / "index.html"

    code = dashboard.main(
        [
            "--owner",
            "Dennis-Otto",
            "--out",
            str(out),
            "--history",
            "https://site/busy.json",
        ],
        api=simulated(ROUTES),
        opener=published,
        now=NOW,
        download=downloader,
    )

    assert code == 2
    assert "the history at https://site/busy.json" in capsys.readouterr().err
    assert not (tmp_path / "site").exists()


def test_the_history_keeps_one_entry_a_day() -> None:
    row = dashboard.Row("Dennis-Otto/demo", health=dashboard.Health(coverage=100.0))
    history: list[dict[str, Any]] = [
        {"date": f"2026-06-{day:02d}"} for day in range(1, 31)
    ] * 5
    history.append({"date": "2026-10-08", "repos": {}})

    kept = dashboard.add_to_history(history, [row], NOW)

    assert len(kept) == dashboard.HISTORY
    assert kept[-1] == {
        "date": "2026-10-08",
        "repos": {"Dennis-Otto/demo": dataclasses.asdict(row.health)},
    }
    assert sum(1 for entry in kept if entry["date"] == "2026-10-08") == 1


def test_the_values_of_a_week_ago() -> None:
    history = [
        {"date": "2026-09-29", "repos": {"a": 1}},
        {"date": "2026-10-01", "repos": {"a": 2}},
        {"date": "2026-10-05", "repos": {"a": 3}},
    ]

    assert dashboard.week_before(history, NOW) == {"a": 2}
    assert dashboard.week_before(history[2:], NOW) == {}


def test_the_health_table_shows_where_a_value_moved() -> None:
    row = dashboard.Row(
        "Dennis-Otto/demo",
        health=dashboard.Health(
            coverage=99.0, mutation=80.0, releases=2, answer_hours=0.5, ci_minutes=12.0
        ),
    )
    previous = {
        "Dennis-Otto/demo": {
            "coverage": 100.0,
            "mutation": 80.0,
            "releases": 1,
            "answer_hours": None,
            "ci_minutes": 10.0,
        }
    }

    page = dashboard.render([row], "Dennis-Otto", "v0.6.0", NOW, previous)

    assert '<td class="bad" title="a week ago 100.0 %">99.0 % ↓</td>' in page
    assert "<td>80.0 %</td>" in page
    assert '<td class="ok" title="a week ago 1">2 ↑</td>' in page
    assert "<td>&lt; 1 h</td>" in page
    assert '<td class="bad" title="a week ago 10 min">12 min ↑</td>' in page


def test_the_health_table_shows_a_failed_run_instead_of_no_value() -> None:
    row = dashboard.Row(
        "Dennis-Otto/demo",
        runs={
            "CI": dashboard.Run("failure", "https://ci"),
            "Mutation": dashboard.Run("failure", "https://mutation"),
        },
        health=dashboard.Health(ci_minutes=0.4),
    )

    page = dashboard.render([row], "Dennis-Otto", "v0.6.0", NOW)

    assert (
        '<td class="bad" title="CI: the last run failed">'
        '<a href="https://ci">✘ failed</a></td>'
    ) in page
    assert '<a href="https://mutation">✘ failed</a>' in page
    # A value that a successful run left stays, however short the run.
    assert "<td>&lt; 1 min</td>" in page


@pytest.mark.parametrize(
    ("hours", "text"),
    [(None, dashboard.DASH), (0.2, "< 1 h"), (5.4, "5 h"), (72.0, "3 d")],
)
def test_the_time_to_a_first_answer(hours: float | None, text: str) -> None:
    assert dashboard.shown("answer_hours", hours) == text


def test_the_dashboard_writes_its_history(tmp_path: Path) -> None:
    out = tmp_path / "site" / "index.html"

    code = dashboard.main(
        [
            "--owner",
            "Dennis-Otto",
            "--out",
            str(out),
            "--history",
            "https://site/history.json",
        ],
        api=simulated(ROUTES),
        opener=published,
        now=NOW,
        download=downloader,
    )

    assert code == 0
    history = json.loads(
        (tmp_path / "site" / "history.json").read_text(encoding="utf-8")
    )
    assert [entry["date"] for entry in history] == [
        "2026-10-01",
        "2026-10-04",
        "2026-10-08",
    ]
    assert "Dennis-Otto/demo" in history[-1]["repos"]


def test_a_run_without_the_artifact() -> None:
    files = dashboard.artifact(
        simulated(HEALTH), downloader, "Dennis-Otto/demo", "ci.yml", "absent"
    )

    assert files == {}


# --------------------------------------------------------------------------- data

ATOM = "{http://www.w3.org/2005/Atom}"

RELEASES: dict[str, tuple[int, Any]] = {
    # The older release first: the feed puts the newest first itself.
    "repos/Dennis-Otto/demo/releases?per_page=100": (
        200,
        [
            {
                "tag_name": "v1.2.1",
                "html_url": "https://github.com/Dennis-Otto/demo/releases/tag/v1.2.1",
                "published_at": "2026-09-01T08:00:00Z",
                "body": "",
            },
            {
                "tag_name": "v1.2.2",
                "html_url": "https://github.com/Dennis-Otto/demo/releases/tag/v1.2.2",
                "published_at": "2026-10-07T12:00:00Z",
                "body": "### Bug fixes\r\n\r\n* a fix",
            },
            {
                "tag_name": "v1.3.0-beta.1",
                "html_url": "https://github.com/Dennis-Otto/demo/releases/tag/v1.3.0-beta.1",
                "published_at": "2026-10-07T13:00:00Z",
                "prerelease": True,
            },
            {"tag_name": "v1.3.0", "draft": True, "published_at": None},
        ],
    ),
    # A release without its address on GitHub gets the address of its tag.
    "repos/Dennis-Otto/repo-blueprint/releases?per_page=100": (
        200,
        [{"tag_name": "v0.3.0", "published_at": "2026-10-05T10:00:00Z", "body": "N"}],
    ),
}


def test_the_stable_releases_of_a_repository() -> None:
    api = simulated(RELEASES)

    found = dashboard.stable_releases(api, "Dennis-Otto/demo")
    (blueprint,) = dashboard.stable_releases(api, "Dennis-Otto/repo-blueprint")

    assert [release.tag for release in found] == ["v1.2.2", "v1.2.1"]
    assert found[0].notes == "### Bug fixes\r\n\r\n* a fix"
    assert blueprint.url == (
        "https://github.com/Dennis-Otto/repo-blueprint/releases/tag/v0.3.0"
    )
    # A repository without a release adds none.
    assert dashboard.stable_releases(api, "Dennis-Otto/behind") == []


def test_the_dashboard_publishes_its_data_and_its_feed(tmp_path: Path) -> None:
    out = tmp_path / "site" / "index.html"

    code = dashboard.main(
        ["--owner", "Dennis-Otto", "--out", str(out)],
        api=simulated({**ROUTES, **HEALTH, **RELEASES}),
        opener=opener,
        now=NOW,
        download=downloader,
    )

    assert code == 0
    found = json.loads((out.parent / "repos.json").read_text(encoding="utf-8"))
    assert {key: value for key, value in found.items() if key != "repos"} == {
        "schema": 1,
        "generated": "2026-10-08T06:05:00Z",
        "owner": "Dennis-Otto",
        "blueprint": "v0.3.0",
    }
    assert [repo["name"] for repo in found["repos"]] == [
        "behind",
        "demo",
        "plain",
        "repo-blueprint",
    ]
    # Every repository has every field, also where nothing is known.
    fields = {field.name for field in dataclasses.fields(dashboard.Row)}
    assert all(
        set(repo) == {"name", "url", "release_url", *fields} for repo in found["repos"]
    )
    behind, demo, _, _ = found["repos"]
    assert demo["repo"] == "Dennis-Otto/demo"
    assert demo["url"] == "https://github.com/Dennis-Otto/demo"
    assert (demo["description"], demo["homepage"], demo["stars"]) == (
        "A demo <of> the blueprint",
        "https://dennis-otto.github.io/demo/",
        12,
    )
    assert (demo["release"], demo["released"], demo["release_url"]) == (
        "v1.2.2",
        "2026-10-07",
        "https://github.com/Dennis-Otto/demo/releases/tag/v1.2.2",
    )
    assert demo["runs"]["Website"] == {
        "state": "success",
        "url": "https://docs",
        "started": None,
    }
    assert demo["scorecard"] == 7.6
    assert (demo["health"]["coverage"], demo["health"]["releases"]) == (50.0, 2)
    # null where nothing is known, never an empty text.
    assert [behind[key] for key in ("description", "homepage", "release")] == [
        None,
        None,
        None,
    ]
    assert [behind[key] for key in ("release_url", "update", "scorecard")] == [
        None,
        None,
        None,
    ]
    assert behind["stars"] == 0
    assert behind["runs"]["CI"] == {"state": "absent", "url": None, "started": None}
    assert behind["health"]["coverage"] is None

    feed = ElementTree.fromstring((out.parent / "releases.atom").read_bytes())
    entries = feed.findall(f"{ATOM}entry")
    # The newest first, from every repository, without prereleases and drafts.
    assert [entry.findtext(f"{ATOM}title") for entry in entries] == [
        "demo v1.2.2",
        "repo-blueprint v0.3.0",
        "demo v1.2.1",
    ]
    assert entries[0].findtext(f"{ATOM}summary") == "### Bug fixes\n\n* a fix"
    # Notes that are empty leave the summary out.
    assert entries[2].find(f"{ATOM}summary") is None
    link = feed.find(f"{ATOM}link[@rel='self']")
    assert link is not None
    assert link.get("href") == dashboard.PUBLISHED + "releases.atom"


def release(number: int) -> dashboard.Release:
    tag = f"v1.0.{number}"
    return dashboard.Release(
        "Dennis-Otto/demo",
        tag,
        f"https://github.com/Dennis-Otto/demo/releases/tag/{tag}",
        dashboard.stamp(NOW - timedelta(hours=number)),
    )


def test_the_feed_holds_the_newest_releases_first() -> None:
    releases = [release(number) for number in (*range(20, 40), *range(20))]

    text = dashboard.feed(releases, "Dennis-Otto", "https://site/dashboard/", NOW)

    feed = ElementTree.fromstring(text)
    assert text.startswith('<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns=')
    entries = feed.findall(f"{ATOM}entry")
    assert [entry.findtext(f"{ATOM}title") for entry in entries] == [
        f"demo v1.0.{number}" for number in range(dashboard.FEED)
    ]
    # What a feed reader needs of the feed and of every entry.
    address = "https://site/dashboard/releases.atom"
    assert feed.findtext(f"{ATOM}id") == address
    assert feed.findtext(f"{ATOM}title") == (
        "The releases of the repositories of Dennis-Otto"
    )
    assert feed.findtext(f"{ATOM}updated") == "2026-10-08T06:05:00Z"
    assert feed.findtext(f"{ATOM}author/{ATOM}name") == "Dennis-Otto"
    links = {item.get("rel"): item.get("href") for item in feed.findall(f"{ATOM}link")}
    assert links == {"self": address, "alternate": "https://site/dashboard/"}
    first = entries[0]
    assert first.findtext(f"{ATOM}id") == (
        "https://github.com/Dennis-Otto/demo/releases/tag/v1.0.0"
    )
    assert first.findtext(f"{ATOM}updated") == "2026-10-08T06:05:00Z"
    assert first.findtext(f"{ATOM}published") == "2026-10-08T06:05:00Z"
    category = first.find(f"{ATOM}category")
    assert category is not None
    assert category.get("term") == "demo"


def test_a_feed_without_releases() -> None:
    feed = ElementTree.fromstring(
        dashboard.feed([], "Dennis-Otto", "https://site/", NOW)
    )

    assert feed.findall(f"{ATOM}entry") == []
    assert feed.findtext(f"{ATOM}updated") == "2026-10-08T06:05:00Z"


def test_the_feed_escapes_every_text() -> None:
    hostile = dashboard.Release(
        "Dennis-Otto/demo",
        'v1 <b>&"</b>',
        'https://github.com/x?a=1&b="2"',
        "2026-10-07T12:00:00Z",
        # Characters that XML 1.0 has no place for: a control character, a lone
        # surrogate and a noncharacter.
        '<script>alert("&")</script>\x01\ud800￿\r\nnext line',
    )

    text = dashboard.feed([hostile], "Dennis-Otto", "https://site/", NOW)

    assert "<script>" not in text
    assert "<b>" not in text
    assert "&lt;script&gt;" in text
    assert "&amp;b=&quot;2&quot;" in text
    (entry,) = ElementTree.fromstring(text).findall(f"{ATOM}entry")
    assert entry.findtext(f"{ATOM}title") == 'demo v1 <b>&"</b>'
    link = entry.find(f"{ATOM}link")
    assert link is not None
    assert link.get("href") == 'https://github.com/x?a=1&b="2"'
    assert entry.findtext(f"{ATOM}summary") == (
        '<script>alert("&")</script>\nnext line'
    )


def test_the_summary_of_a_release_ends_at_a_word() -> None:
    assert dashboard.summary("  short notes \n") == "short notes"
    cut = dashboard.summary("word " * 200)
    assert cut.endswith(" word…")
    assert len(cut) <= dashboard.SUMMARY + 1
    assert dashboard.summary("x" * 600) == "x" * dashboard.SUMMARY + "…"


# The published dashboard, as the job that publishes it asks for it: a fake curl
# answers each address with what its file holds, but the one that ends with BROKEN,
# and the feed with FEED, if set.
CURL = r"""url="${@: -1}"
printf '%s\n' "curl $url" >> "$STUB_CALLS"
if [[ -n "${BROKEN:-}" && "$url" == *"$BROKEN" ]]; then
  echo "curl: (22) The requested URL returned error: 404" >&2
  exit 22
fi
while [[ "$1" != --output ]]; do
  shift
done
case "$url" in
  *.html) printf '<title>Repository dashboard</title>\n' > "$2" ;;
  *history.json) printf '[{"date": "2026-10-08"}]\n' > "$2" ;;
  *repos.json) printf '{"repos": []}\n' > "$2" ;;
  *) printf '%s\n' "${FEED:-<feed xmlns=\"http://www.w3.org/2005/Atom\"/>}" > "$2" ;;
esac
"""
PUBLISHED_DASHBOARD = "https://owner.github.io/repo-blueprint/dashboard"
DASHBOARD_FILES = ("index.html", "history.json", "repos.json", "releases.atom")


@pytest.mark.skipif(BASH is None, reason="the steps run in bash, Git Bash on Windows")
@pytest.mark.parametrize(
    ("broken", "feed", "failed"),
    [
        ("", "", ""),
        ("/repos.json", "", "repos.json"),
        # A page of GitHub Pages in place of the feed is no feed.
        ("", "<html><title>404</title></html>", "releases.atom"),
    ],
)
def test_the_job_that_publishes_asks_for_the_data_of_the_dashboard(
    tmp_path: Path, broken: str, feed: str, failed: str
) -> None:
    result = run_step(
        tmp_path,
        "dashboard.yml",
        "deploy",
        "Ask the published dashboard for its data",
        env={
            "PAGE_URL": "https://owner.github.io/repo-blueprint/",
            "BROKEN": broken,
            "FEED": feed,
        },
        stubs={"curl": CURL},
    )

    assert result.stubbed == [
        f"curl {PUBLISHED_DASHBOARD}/{name}" for name in DASHBOARD_FILES
    ]
    assert result.returncode == (1 if failed else 0), result.stdout + result.stderr
    if failed:
        assert (
            f"::error title=The published dashboard::{PUBLISHED_DASHBOARD}/{failed}"
            " answers without its data"
        ) in result.stdout
    else:
        assert result.summary == "".join(
            f"- {PUBLISHED_DASHBOARD}/{name} answers with its data.\n"
            for name in DASHBOARD_FILES
        )
