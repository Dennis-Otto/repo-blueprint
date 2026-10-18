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
import sys
import urllib.parse
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from blueprint.github import Api, GitHubError
from dashboard import ci_workflow, median_minutes, repositories, workflow_files

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


def count(api: Api, query: str) -> int:
    """How many issues and pull requests the search finds: its total, not the items
    of a page, which are 100 at most."""
    found = api.get(f"search/issues?q={urllib.parse.quote(query)}&per_page=1") or {}
    return int(found.get("total_count", 0))


def search(api: Api, query: str) -> list[dict[str, str]]:
    """The issues and pull requests that the search finds, from all its pages."""
    return api.get_all(f"search/issues?q={urllib.parse.quote(query)}&per_page=100")


def when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def collect(api: Api, repo: str, since: datetime) -> Week:
    """The week of repo from since to now. Every search starts at the moment since,
    not at the start of its day, so that one report counts no hour of the last."""
    week = Week(repo)
    stamp = since.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    for release in api.get(f"repos/{repo}/releases?per_page=30") or []:
        published = release.get("published_at")
        if published and when(published) >= since:
            week.releases.append((release["tag_name"], release["html_url"]))
    merged = f"repo:{repo} is:pr is:merged merged:>={stamp}"
    week.merged = count(api, merged)
    week.updates = sum(1 for pull in search(api, merged) if UPDATE.match(pull["title"]))
    week.opened = count(api, f"repo:{repo} is:issue created:>={stamp}")
    week.closed = count(api, f"repo:{repo} is:issue closed:>={stamp}")
    created = urllib.parse.quote(f">={stamp}")
    failed = api.get(
        f"repos/{repo}/actions/runs?branch=main&status=failure&created={created}&per_page=1"
    )
    week.failed = (failed or {}).get("total_count", 0)
    ci = ci_workflow(workflow_files(api, repo))
    runs = api.get_all(
        f"repos/{repo}/actions/workflows/{ci}/runs?branch=main&status=success"
        f"&created={created}&exclude_pull_requests=true&per_page=100"
    )
    # A pull request from the main of a fork runs on a branch of that name too.
    week.ci_minutes = median_minutes(
        [
            run
            for run in runs
            if not str(run.get("event", "")).startswith("pull_request")
        ]
    )
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
