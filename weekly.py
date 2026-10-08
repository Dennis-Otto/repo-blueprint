#!/usr/bin/env python3
"""The weekly report of the public repositories of an owner.

    python3 weekly.py --owner Dennis-Otto --out report.md

For the seven days before now, it shows for every public repository that is no fork
and not archived what it released, how many pull requests it merged and how many of
them were updates of dependencies, how many issues were opened and closed, how many
runs failed on main and the median time of its CI. It prints the title of the report
and writes its text. It reports nothing that isn't public anyway: no finding of code
scanning and no alert of Dependabot. The Weekly report workflow posts it in the
discussions of the blueprint.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from blueprint import Api, GitHubError
from dashboard import WORKFLOWS, repositories

# The titles of updates of dependencies, as Renovate and Dependabot write them.
UPDATE = re.compile(r"^(?:fix|chore|build)\(deps(?:-dev)?\): ")


@dataclass
class Week:
    """What one repository did in the week."""

    repo: str
    releases: list[tuple[str, str]] = field(default_factory=list)
    merged: int = 0
    updates: int = 0
    opened: int = 0
    closed: int = 0
    failed: int = 0
    ci_minutes: float | None = None


def search(api: Api, query: str) -> list[dict[str, str]]:
    found = api.get(f"search/issues?q={urllib.parse.quote(query)}&per_page=100") or {}
    items: list[dict[str, str]] = found.get("items", [])
    return items


def when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def collect(api: Api, repo: str, since: datetime) -> Week:
    week = Week(repo)
    day = since.strftime("%Y-%m-%d")
    for release in api.get(f"repos/{repo}/releases?per_page=30") or []:
        published = release.get("published_at")
        if published and when(published) >= since:
            week.releases.append((release["tag_name"], release["html_url"]))
    merged = search(api, f"repo:{repo} is:pr is:merged merged:>={day}")
    week.merged = len(merged)
    week.updates = sum(1 for pull in merged if UPDATE.match(pull["title"]))
    week.opened = len(search(api, f"repo:{repo} is:issue created:>={day}"))
    week.closed = len(search(api, f"repo:{repo} is:issue closed:>={day}"))
    created = urllib.parse.quote(f">={day}")
    failed = api.get(
        f"repos/{repo}/actions/runs?branch=main&status=failure&created={created}&per_page=1"
    )
    week.failed = (failed or {}).get("total_count", 0)
    runs = api.get(
        f"repos/{repo}/actions/workflows/{WORKFLOWS['CI']}/runs"
        f"?branch=main&status=success&created={created}&per_page=100"
    )
    minutes = [
        (when(run["updated_at"]) - when(run["run_started_at"])).total_seconds() / 60
        for run in (runs or {}).get("workflow_runs", [])
        if run.get("run_started_at") and run.get("updated_at")
    ]
    week.ci_minutes = statistics.median(minutes) if minutes else None
    return week


def render(weeks: list[Week], owner: str, since: datetime, now: datetime) -> str:
    def name(repo: str) -> str:
        return f"[{repo.split('/', 1)[1]}](https://github.com/{repo})"

    lines = [
        f"What the public repositories of {owner} released, merged and fixed from "
        f"{since:%Y-%m-%d} to {now:%Y-%m-%d}, from public data alone.",
        "",
        "| Repository | Releases | Pull requests merged | Updates among them "
        "| Issues opened | Issues closed | Failed runs on main | CI, median |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for week in weeks:
        ci = "" if week.ci_minutes is None else f"{week.ci_minutes:.0f} min"
        lines.append(
            f"| {name(week.repo)} | {len(week.releases)} | {week.merged} "
            f"| {week.updates} | {week.opened} | {week.closed} | {week.failed} | {ci} |"
        )
    totals = [
        sum(len(week.releases) for week in weeks),
        sum(week.merged for week in weeks),
        sum(week.updates for week in weeks),
        sum(week.opened for week in weeks),
        sum(week.closed for week in weeks),
        sum(week.failed for week in weeks),
    ]
    lines.append("| **All** | " + " | ".join(str(total) for total in totals) + " | |")
    lines += ["", "### Releases", ""]
    releases = [
        f"- {name(week.repo)} [{tag}]({url})"
        for week in weeks
        for tag, url in week.releases
    ]
    lines += releases or ["No release this week."]
    lines += [
        "",
        "<sub>The Weekly report workflow of the blueprint writes this every Monday; "
        "the [dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) "
        "shows the current state.</sub>",
    ]
    return "\n".join([*lines, ""])


def main(
    argv: Sequence[str] | None = None,
    api: Api | None = None,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="weekly.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--owner", required=True, help="the account of the repositories"
    )
    parser.add_argument("--out", type=Path, required=True, help="the report to write")
    parser.add_argument("--days", type=int, default=7, help="the length of the week")
    arguments = parser.parse_args(argv)
    api = api or Api()
    now = now or datetime.now(UTC)
    since = now - timedelta(days=arguments.days)
    try:
        weeks = [
            collect(api, repo, since) for repo in repositories(api, arguments.owner)
        ]
    except GitHubError as error:
        print(f"weekly.py: {error}", file=sys.stderr)
        return 2
    arguments.out.write_text(
        render(weeks, arguments.owner, since, now), encoding="utf-8"
    )
    print(f"The week of {since:%Y-%m-%d} to {now:%Y-%m-%d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
