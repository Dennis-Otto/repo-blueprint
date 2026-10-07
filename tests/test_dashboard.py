"""Tests of dashboard.py against a simulated GitHub."""

from __future__ import annotations

import base64
import io
import json
import subprocess
import urllib.error
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import blueprint
import dashboard

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


def simulated(routes: dict[str, tuple[int, Any]]) -> blueprint.Api:
    def runner(
        arguments: Sequence[str], body: str | None
    ) -> subprocess.CompletedProcess[str]:
        status, data = routes.get(arguments[4], (404, {"message": "Not Found"}))
        answer = f"HTTP/2.0 {status} X\n\n{json.dumps(data)}"
        return subprocess.CompletedProcess(arguments, 0, answer, "")

    return blueprint.Api(runner)


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
    # The head and a row for each repository.
    assert page.count("<tr>") == 5


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
