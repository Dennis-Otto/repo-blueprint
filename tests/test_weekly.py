"""Tests of weekly.py against a simulated GitHub."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import weekly
from blueprint.github import Api

NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
# The week starts at the minute of its run seven days before, not at midnight: the
# report of last Monday counted the hours of that Monday too.
SINCE = "2026-10-05T06:00:00Z"
CREATED = urllib.parse.quote(f">={SINCE}")


def counted(query: str) -> str:
    return f"search/issues?q={urllib.parse.quote(query)}&per_page=1"


def searched(query: str) -> str:
    return f"search/issues?q={urllib.parse.quote(query)}&per_page=100"


ROUTES: dict[str, tuple[int, Any]] = {
    "users/Dennis-Otto/repos?type=owner&per_page=100": (
        200,
        [{"full_name": "Dennis-Otto/demo"}, {"full_name": "Dennis-Otto/quiet"}],
    ),
    "repos/Dennis-Otto/demo/releases?per_page=30": (
        200,
        [
            {
                "tag_name": "v1.3.0",
                "html_url": "https://release/130",
                "published_at": "2026-10-09T10:00:00Z",
            },
            {
                "tag_name": "v1.3.0-beta.1",
                "html_url": "https://draft",
                "published_at": None,
            },
            {
                "tag_name": "v1.2.2",
                "html_url": "https://release/122",
                "published_at": "2026-09-30T10:00:00Z",
            },
        ],
    ),
    # The search counts every match, the items of a page at most 100.
    counted(f"repo:Dennis-Otto/demo is:pr is:merged merged:>={SINCE}"): (
        200,
        {"total_count": 103, "items": [{"title": "feat: start a game by voice"}]},
    ),
    searched(f"repo:Dennis-Otto/demo is:pr is:merged merged:>={SINCE}"): (
        200,
        {
            "total_count": 103,
            "items": [
                {"title": "feat: start a game by voice"},
                {"title": "chore(deps): update the actions"},
                {"title": "fix(deps): update dependency x to v2"},
            ],
        },
    ),
    counted(f"repo:Dennis-Otto/demo is:issue created:>={SINCE}"): (
        200,
        {"total_count": 2, "items": [{"title": "a"}]},
    ),
    counted(f"repo:Dennis-Otto/demo is:issue closed:>={SINCE}"): (
        200,
        {"total_count": 1, "items": [{"title": "a"}]},
    ),
    "repos/Dennis-Otto/demo/actions/workflows?per_page=100": (
        200,
        {"workflows": [{"path": ".github/workflows/ci-python.yml"}]},
    ),
    f"repos/Dennis-Otto/demo/actions/runs?branch=main&status=failure&created={CREATED}&per_page=1": (
        200,
        {"total_count": 2},
    ),
    f"repos/Dennis-Otto/demo/actions/workflows/ci-python.yml/runs?branch=main&status=success&created={CREATED}&exclude_pull_requests=true&per_page=100": (
        200,
        {
            "workflow_runs": [
                {
                    "run_started_at": "2026-10-06T10:00:00Z",
                    "updated_at": "2026-10-06T10:06:00Z",
                },
                {
                    "run_started_at": "2026-10-07T10:00:00Z",
                    "updated_at": "2026-10-07T10:10:00Z",
                },
                {
                    "run_started_at": "2026-10-08T10:00:00Z",
                    "updated_at": "2026-10-08T10:08:00Z",
                },
                {"run_started_at": None, "updated_at": "2026-10-08T10:08:00Z"},
                # A pull request from the main of a fork runs on a branch of that name.
                {
                    "event": "pull_request",
                    "run_started_at": "2026-10-08T11:00:00Z",
                    "updated_at": "2026-10-08T12:00:00Z",
                },
            ]
        },
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


def test_the_week_of_a_busy_repository() -> None:
    week = weekly.collect(simulated(ROUTES), "Dennis-Otto/demo", NOW.replace(day=5))

    assert week.releases == [("v1.3.0", "https://release/130")]
    assert (week.merged, week.updates) == (103, 2)
    assert (week.opened, week.closed, week.failed) == (2, 1, 2)
    assert week.ci_minutes == 8


def test_the_week_of_a_quiet_repository() -> None:
    week = weekly.collect(simulated(ROUTES), "Dennis-Otto/quiet", NOW.replace(day=5))

    assert week == weekly.Week("Dennis-Otto/quiet")


def test_the_report_shows_every_repository_and_the_releases() -> None:
    since = NOW.replace(day=5)
    api = simulated(ROUTES)
    weeks = [
        weekly.collect(api, repo, since)
        for repo in ("Dennis-Otto/demo", "Dennis-Otto/quiet")
    ]

    report = weekly.render(weeks, "Dennis-Otto", since, NOW)

    assert "from 2026-10-05 to 2026-10-12" in report
    assert (
        "| [demo](https://github.com/Dennis-Otto/demo) | 1 | 103 | 2 | 2 | 1 | 2 | 8 min |"
        in report
    )
    assert (
        "| [quiet](https://github.com/Dennis-Otto/quiet) | 0 | 0 | 0 | 0 | 0 | 0 |  |"
        in report
    )
    assert "| **All** | 1 | 103 | 2 | 2 | 1 | 2 | |" in report
    assert (
        "- [demo](https://github.com/Dennis-Otto/demo) [v1.3.0](https://release/130)"
        in report
    )
    assert "No release this week." not in report
    assert "No release this week." in weekly.render([], "Dennis-Otto", since, NOW)


def test_a_week_of_a_time_zone_starts_at_the_same_moment() -> None:
    since = datetime.fromisoformat("2026-10-05T08:00:00+02:00")

    week = weekly.collect(simulated(ROUTES), "Dennis-Otto/demo", since)

    assert (week.merged, week.opened, week.failed) == (103, 2, 2)


def test_the_command_line_writes_the_report_and_prints_its_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "report.md"

    code = weekly.main(
        ["--owner", "Dennis-Otto", "--out", str(out)], api=simulated(ROUTES), now=NOW
    )

    assert code == 0
    assert capsys.readouterr().out == "The week of 2026-10-05 to 2026-10-12\n"
    assert "[v1.3.0](https://release/130)" in out.read_text(encoding="utf-8")


def test_the_command_line_names_an_error_of_github(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    routes = {
        "users/Dennis-Otto/repos?type=owner&per_page=100": (500, {"message": "Boom"})
    }

    code = weekly.main(
        ["--owner", "Dennis-Otto", "--out", str(tmp_path / "r.md")],
        api=simulated(routes),
        now=NOW,
    )

    assert code == 2
    assert "weekly.py:" in capsys.readouterr().err
