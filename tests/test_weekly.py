"""Tests of weekly.py against a simulated GitHub."""

from __future__ import annotations

import json
import subprocess
import urllib.parse
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import weekly
from blueprint.github import Api

NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)
SINCE = datetime(2026, 10, 5, tzinfo=UTC)
UNTIL = datetime(2026, 10, 12, tzinfo=UTC)
# The week is the calendar week in UTC, whatever hour its run starts at. Once it
# started at the minute of the run seven days before: the late starts of GitHub
# counted some hours twice and others never. A start at midnight with no end counted
# the hours of Monday before the run twice; the end at Monday 00:00 counts them once,
# in the next report. A range of the search takes both of its ends.
WINDOW = "2026-10-05T00:00:00Z..2026-10-11T23:59:59Z"
CREATED = urllib.parse.quote(WINDOW)


def counted(query: str) -> str:
    return f"search/issues?q={urllib.parse.quote(query)}&per_page=1"


def searched(query: str) -> str:
    return f"search/issues?q={urllib.parse.quote(query)}&per_page=100"


ROUTES: dict[str, tuple[int, Any]] = {
    "users/Dennis-Otto/repos?type=owner&per_page=100": (
        200,
        [{"full_name": "Dennis-Otto/demo"}, {"full_name": "Dennis-Otto/quiet"}],
    ),
    "repos/Dennis-Otto/demo/releases?per_page=100&page=1": (
        200,
        [
            # Published at the end of the week, it belongs to the next one.
            {
                "tag_name": "v1.4.0",
                "html_url": "https://release/140",
                "published_at": "2026-10-12T00:00:00Z",
            },
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
            # Published at the start of the week, it belongs to it.
            {
                "tag_name": "v1.2.3",
                "html_url": "https://release/123",
                "published_at": "2026-10-05T00:00:00Z",
            },
            {
                "tag_name": "v1.2.2",
                "html_url": "https://release/122",
                "published_at": "2026-09-30T10:00:00Z",
            },
        ],
    ),
    # The search counts every match, the items of a page at most 100.
    counted(f"repo:Dennis-Otto/demo is:pr is:merged merged:{WINDOW}"): (
        200,
        {"total_count": 103, "items": [{"title": "feat: start a game by voice"}]},
    ),
    searched(f"repo:Dennis-Otto/demo is:pr is:merged merged:{WINDOW}"): (
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
    counted(f"repo:Dennis-Otto/demo is:issue created:{WINDOW}"): (
        200,
        {"total_count": 2, "items": [{"title": "a"}]},
    ),
    counted(f"repo:Dennis-Otto/demo is:issue closed:{WINDOW}"): (
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


@pytest.mark.parametrize(
    "now",
    [
        # GitHub starts the schedule hours late, at a different hour each week.
        datetime(2026, 10, 12, 13, 34, tzinfo=UTC),
        # A start by hand later in the week.
        datetime(2026, 10, 14, 9, 0, tzinfo=UTC),
        datetime(2026, 10, 18, 23, 59, 59, tzinfo=UTC),
        # At exactly Monday 00:00, the week that just ended.
        datetime(2026, 10, 12, tzinfo=UTC),
        # 01:30 in Berlin is still Sunday in UTC.
        datetime.fromisoformat("2026-10-19T01:30:00+02:00"),
    ],
)
def test_the_week_is_the_last_full_calendar_week_in_utc(now: datetime) -> None:
    assert weekly.week_before(now) == (SINCE, UNTIL)


def test_two_reports_in_a_row_meet_exactly() -> None:
    # The starts of the step that wrote the reports of 2026-10-12 and 2026-10-19.
    first = weekly.week_before(datetime(2026, 10, 12, 14, 48, 14, tzinfo=UTC))
    second = weekly.week_before(datetime(2026, 10, 19, 10, 50, 57, tzinfo=UTC))

    assert first == (SINCE, UNTIL)
    assert second == (UNTIL, UNTIL + timedelta(days=7))


def test_the_week_of_a_busy_repository() -> None:
    week = weekly.collect(simulated(ROUTES), "Dennis-Otto/demo", SINCE, UNTIL)

    assert week.releases == [
        ("v1.3.0", "https://release/130"),
        ("v1.2.3", "https://release/123"),
    ]
    assert (week.merged, week.updates) == (103, 2)
    assert (week.opened, week.closed, week.failed) == (2, 1, 2)
    assert week.ci_minutes == 8


def test_the_week_of_a_quiet_repository() -> None:
    week = weekly.collect(simulated(ROUTES), "Dennis-Otto/quiet", SINCE, UNTIL)

    assert week == weekly.Week("Dennis-Otto/quiet")


def test_a_week_with_more_releases_than_a_page_reads_the_next_page() -> None:
    # The run may come days after the end of the week, with many releases since.
    def release(number: int, published: str) -> dict[str, str]:
        return {
            "tag_name": f"v1.{number}.0",
            "html_url": f"https://release/{number}",
            "published_at": published,
        }

    first = [release(number, "2026-10-14T10:00:00Z") for number in range(160, 120, -1)]
    first += [release(number, "2026-10-09T10:00:00Z") for number in range(120, 60, -1)]
    routes = {
        "repos/Dennis-Otto/busy/releases?per_page=100&page=1": (200, first),
        "repos/Dennis-Otto/busy/releases?per_page=100&page=2": (
            200,
            [
                release(60, "2026-10-06T10:00:00Z"),
                *(
                    release(number, "2026-10-04T23:59:59Z")
                    for number in range(59, -40, -1)
                ),
            ],
        ),
        # A page that reaches before since is the last one that it reads.
        "repos/Dennis-Otto/busy/releases?per_page=100&page=3": (
            200,
            [release(-40, "2026-10-06T10:00:00Z")],
        ),
    }

    week = weekly.collect(simulated(routes), "Dennis-Otto/busy", SINCE, UNTIL)

    assert [tag for tag, _ in week.releases] == [
        f"v1.{number}.0" for number in range(120, 59, -1)
    ]


def test_the_report_shows_every_repository_and_the_releases() -> None:
    api = simulated(ROUTES)
    weeks = [
        weekly.collect(api, repo, SINCE, UNTIL)
        for repo in ("Dennis-Otto/demo", "Dennis-Otto/quiet")
    ]

    report = weekly.render(weeks, "Dennis-Otto", SINCE, UNTIL)

    assert report.startswith(
        "What the public repositories of Dennis-Otto released, merged and fixed in the"
        " week from Monday 2026-10-05, 00:00 UTC, to Monday 2026-10-12, 00:00 UTC,"
        " from public data alone.\n"
    )
    assert (
        "| [demo](https://github.com/Dennis-Otto/demo) | 2 | 103 | 2 | 2 | 1 | 2 | 8 min |"
        in report
    )
    assert (
        "| [quiet](https://github.com/Dennis-Otto/quiet) | 0 | 0 | 0 | 0 | 0 | 0 |  |"
        in report
    )
    assert "| **All** | 2 | 103 | 2 | 2 | 1 | 2 | |" in report
    assert (
        "- [demo](https://github.com/Dennis-Otto/demo) [v1.3.0](https://release/130)"
        in report
    )
    assert "No release this week." not in report
    assert "No release this week." in weekly.render([], "Dennis-Otto", SINCE, UNTIL)


def test_a_week_of_a_time_zone_starts_at_the_same_moment() -> None:
    since = datetime.fromisoformat("2026-10-05T02:00:00+02:00")
    until = datetime.fromisoformat("2026-10-12T02:00:00+02:00")

    week = weekly.collect(simulated(ROUTES), "Dennis-Otto/demo", since, until)

    assert (week.merged, week.opened, week.failed) == (103, 2, 2)
    assert len(week.releases) == 2


@pytest.mark.parametrize(
    "now", [NOW, datetime(2026, 10, 14, 9, 0, tzinfo=UTC)], ids=["Monday", "Wednesday"]
)
def test_the_command_line_writes_the_report_and_prints_its_title(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], now: datetime
) -> None:
    out = tmp_path / "report.md"

    code = weekly.main(
        ["--owner", "Dennis-Otto", "--out", str(out)], api=simulated(ROUTES), now=now
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
