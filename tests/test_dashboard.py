"""Tests of dashboard.py against a simulated GitHub."""

from __future__ import annotations

import base64
import dataclasses
import io
import json
import subprocess
import urllib.error
import zipfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import dashboard
from blueprint.github import Api

NOW = datetime(2026, 10, 8, 6, 5, tzinfo=UTC)


def content(text: str) -> dict[str, str]:
    return {"content": base64.b64encode(text.encode()).decode()}


def runs(status: str, conclusion: str | None = None) -> dict[str, Any]:
    run = {"status": status, "conclusion": conclusion, "html_url": "https://run"}
    return {"workflow_runs": [run]}


ROUTES: dict[str, tuple[int, Any]] = {
    "repos/Dennis-Otto/repo-blueprint/releases/latest": (200, {"tag_name": "v0.3.0"}),
    "users/Dennis-Otto/repos?type=owner&per_page=100": (
        200,
        [
            {"full_name": "Dennis-Otto/demo"},
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
    "repos/Dennis-Otto/demo/actions/workflows/ci.yml/runs"
    "?branch=main&per_page=1&exclude_pull_requests=true": (
        200,
        runs("completed", "success"),
    ),
    "repos/Dennis-Otto/demo/actions/workflows/codeql.yml/runs"
    "?branch=main&per_page=1&exclude_pull_requests=true": (
        200,
        runs("completed", "failure"),
    ),
    "repos/Dennis-Otto/demo/actions/workflows/release.yml/runs"
    "?branch=main&per_page=1&exclude_pull_requests=true": (200, runs("in_progress")),
    "repos/Dennis-Otto/demo/actions/workflows/links.yml/runs"
    "?branch=main&per_page=1&exclude_pull_requests=true": (200, {"workflow_runs": []}),
}


def simulated(routes: dict[str, tuple[int, Any]]) -> Api:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        status, data = routes.get(arguments[4], (404, {"message": "Not Found"}))
        answer = f"HTTP/2.0 {status} X\n\n{json.dumps(data)}"
        return subprocess.CompletedProcess(arguments, 0, answer, "")

    return Api(runner)


def opener(url: str) -> io.BytesIO:
    if url.endswith("/demo"):
        return io.BytesIO(json.dumps({"score": 7.6}).encode())
    if url.endswith("/behind"):
        return io.BytesIO(json.dumps({"score": "unknown"}).encode())
    raise urllib.error.URLError("offline")


def test_a_repository_on_the_blueprint() -> None:
    row = dashboard.collect(simulated(ROUTES), "Dennis-Otto/demo", opener)

    assert (row.kind, row.blueprint) == ("github-action", "v0.3.0")
    assert (row.release, row.released) == ("v1.2.2", "2026-10-07")
    assert (row.next_release, row.next_url) == ("1.3.0", "https://pull/5")
    assert (row.pulls, row.conflicts) == (2, 1)
    assert row.runs["CI"] == dashboard.Run("success", "https://run")
    assert row.runs["CodeQL"].state == "failure"
    assert row.runs["Release"].state == "running"
    assert row.runs["Links"].state == "none"
    assert row.runs["Settings"].state == "none"
    assert row.scorecard == 7.6


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


def test_the_repositories_are_the_public_ones_of_the_owner() -> None:
    assert dashboard.repositories(simulated(ROUTES), "Dennis-Otto") == [
        "Dennis-Otto/behind",
        "Dennis-Otto/demo",
        "Dennis-Otto/plain",
        "Dennis-Otto/repo-blueprint",
    ]


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
    assert ">7.6</a>" in page
    # The head and a row for each repository, in the table of the state and of health.
    assert page.count("<tr>") == 10


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
        "?branch=main&status=success&per_page=1&exclude_pull_requests=true"
    )


HEALTH: dict[str, tuple[int, Any]] = {
    successful("ci.yml"): (200, {"workflow_runs": [{"id": 11}]}),
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
    successful("mutation.yml"): (200, {"workflow_runs": [{"id": 22}]}),
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
                "user": {"login": "reporter"},
            },
            {
                "number": 7,
                "created_at": "2026-10-02T00:00:00Z",
                "user": {"login": "reporter"},
            },
            {
                "number": 6,
                "created_at": "2026-05-01T00:00:00Z",
                "user": {"login": "reporter"},
            },
        ],
    ),
    "repos/Dennis-Otto/demo/issues/8/comments?per_page=30": (
        200,
        [
            {"user": {"login": "reporter"}, "created_at": "2026-10-01T01:00:00Z"},
            {"user": {"login": "maintainer"}, "created_at": "2026-10-01T04:00:00Z"},
        ],
    ),
    "repos/Dennis-Otto/demo/issues/7/comments?per_page=30": (200, []),
    "repos/Dennis-Otto/demo/actions/workflows/ci.yml/runs"
    "?branch=main&status=success&per_page=10&exclude_pull_requests=true": (
        200,
        {
            "workflow_runs": [
                {
                    "run_started_at": "2026-10-06T10:00:00Z",
                    "updated_at": "2026-10-06T10:04:00Z",
                },
                {"run_started_at": None, "updated_at": "2026-10-06T10:04:00Z"},
            ]
        },
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


def test_a_repository_without_reports_has_no_health_values() -> None:
    health = dashboard.health(simulated({}), downloader, "Dennis-Otto/demo", NOW)

    assert health == dashboard.Health()


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        (
            {"build/infection-summary.log": "Mutation Score Indicator (MSI): 81.5%\n"},
            81.5,
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


def test_the_history_comes_from_the_published_dashboard() -> None:
    def published(url: str) -> io.BytesIO:
        if url == "https://site/history.json":
            return io.BytesIO(json.dumps([{"date": "2026-10-01"}, "noise"]).encode())
        if url == "https://site/object.json":
            return io.BytesIO(b'{"date": "2026-10-01"}')
        raise urllib.error.URLError("offline")

    assert dashboard.load_history("https://site/history.json", published) == [
        {"date": "2026-10-01"}
    ]
    assert dashboard.load_history("https://site/object.json", published) == []
    assert dashboard.load_history("https://site/gone.json", published) == []
    assert dashboard.load_history("", published) == []


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


@pytest.mark.parametrize(
    ("hours", "text"),
    [(None, dashboard.DASH), (0.2, "< 1 h"), (5.4, "5 h"), (72.0, "3 d")],
)
def test_the_time_to_a_first_answer(hours: float | None, text: str) -> None:
    assert dashboard.shown("answer_hours", hours) == text


def test_the_dashboard_writes_its_history(tmp_path: Path) -> None:
    out = tmp_path / "site" / "index.html"

    def published(url: str) -> io.BytesIO:
        if url == "https://site/history.json":
            return io.BytesIO(
                json.dumps([{"date": "2026-10-01", "repos": {}}]).encode()
            )
        return opener(url)

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
    assert [entry["date"] for entry in history] == ["2026-10-01", "2026-10-08"]
    assert "Dennis-Otto/demo" in history[-1]["repos"]


def test_a_run_without_the_artifact() -> None:
    files = dashboard.artifact(
        simulated(HEALTH), downloader, "Dennis-Otto/demo", "ci.yml", "absent"
    )

    assert files == {}
