#!/usr/bin/env python3
"""The dashboard of the public repositories of an owner.

    python3 dashboard.py --owner Dennis-Otto --out site/index.html

For every public repository that is no fork and not archived, it shows the release of the blueprint it is
on, its latest release and the pull request of the next one, its open pull requests
and those that conflict, the last run of its main workflows on main, and its OpenSSF
Scorecard. It shows nothing that isn't public anyway: no finding of code scanning and
no alert of Dependabot. The Dashboard workflow publishes it on GitHub Pages.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
import statistics
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from blueprint.github import Api, GitHubError

BLUEPRINT = "Dennis-Otto/repo-blueprint"
SCORECARD_API = "https://api.scorecard.dev/projects/github.com/"
# What a cell without a value shows.
DASH = "\u2013"
# The workflows whose last run on main the dashboard shows, by file.
WORKFLOWS = {
    "CI": "ci.yml",
    "CodeQL": "codeql.yml",
    "Release": "release.yml",
    "Verification": "verify-release.yml",
    "Settings": "settings.yml",
    "Findings": "findings.yml",
    "Links": "links.yml",
}
SYMBOLS = {
    "success": ("✔", "ok", "passed"),
    "failure": ("✘", "bad", "failed"),
    "running": ("●", "wait", "running"),
    "none": (DASH, "none", "no run"),
}

Opener = Callable[[str], Any]


@dataclass
class Run:
    state: str
    url: str = ""


@dataclass
class Row:
    """What the dashboard shows of one repository."""

    repo: str
    kind: str = ""
    blueprint: str = ""
    release: str = ""
    released: str = ""
    next_release: str = ""
    next_url: str = ""
    pulls: int = 0
    conflicts: int = 0
    runs: dict[str, Run] = field(default_factory=dict)
    scorecard: float | None = None
    health: Health = field(default_factory=lambda: Health())


def answers(api: Api, repo: str) -> dict[str, str]:
    """The release of the blueprint and the kind of project, from .copier-answers.yml."""
    content = api.get(f"repos/{repo}/contents/.copier-answers.yml")
    if not isinstance(content, dict):
        return {}
    text = base64.b64decode(content.get("content", "")).decode("utf-8", "replace")
    return dict(re.findall(r"^(_commit|project_type): *(\S+)", text, re.MULTILINE))


def last_run(api: Api, repo: str, workflow: str) -> Run:
    runs = api.get(
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        "?branch=main&per_page=1&exclude_pull_requests=true"
    )
    found = (runs or {}).get("workflow_runs") or []
    if not found:
        return Run("none")
    run = found[0]
    if run.get("status") != "completed":
        return Run("running", run.get("html_url", ""))
    good = run.get("conclusion") in ("success", "skipped", "neutral")
    return Run("success" if good else "failure", run.get("html_url", ""))


def scorecard(repo: str, opener: Opener) -> float | None:
    try:
        with opener(SCORECARD_API + repo) as response:
            score = json.load(response).get("score")
    except (urllib.error.URLError, ValueError, OSError):
        return None
    return float(score) if isinstance(score, int | float) else None


def collect(api: Api, repo: str, opener: Opener) -> Row:
    row = Row(repo)
    found = answers(api, repo)
    row.kind = found.get("project_type", "")
    row.blueprint = found.get("_commit", "")
    latest = api.get(f"repos/{repo}/releases/latest")
    if isinstance(latest, dict):
        row.release = latest.get("tag_name", "")
        row.released = (latest.get("published_at") or "")[:10]
    for pull in api.get(f"repos/{repo}/pulls?state=open&per_page=100") or []:
        labels = {label["name"] for label in pull.get("labels", [])}
        if "autorelease: pending" in labels:
            row.next_release = pull["title"].removeprefix("chore: release ")
            row.next_url = pull["html_url"]
            continue
        row.pulls += 1
        row.conflicts += "merge-conflict" in labels
    row.runs = {name: last_run(api, repo, file) for name, file in WORKFLOWS.items()}
    row.scorecard = scorecard(repo, opener)
    return row


def repositories(api: Api, owner: str) -> list[str]:
    """The public repositories of the owner, without archived ones and forks."""
    found = api.get(f"users/{owner}/repos?type=owner&per_page=100") or []
    return sorted(
        repo["full_name"]
        for repo in found
        if not repo.get("archived") and not repo.get("fork") and not repo.get("private")
    )


# ------------------------------------------------------------------------- health

# How far back the release cadence and the answers to issues look.
WINDOW = timedelta(days=90)
# The issues whose first answer the dashboard reads, the newest first.
ISSUES = 30
# The entries of the history: one a day.
HISTORY = 120
TREND = ("coverage", "mutation", "releases", "answer_hours", "ci_minutes")

Downloader = Callable[[str], bytes]


def gh_download(path: str) -> bytes:
    """The bytes at path of GitHub's API, such as the zip of an artifact."""
    return subprocess.run(  # pragma: no cover - the tests simulate gh
        ["gh", "api", path], capture_output=True, check=True
    ).stdout


@dataclass
class Health:
    """How well the tests and the bots of one repository do."""

    coverage: float | None = None
    mutation: float | None = None
    releases: int = 0
    answer_hours: float | None = None
    ci_minutes: float | None = None


def when(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def artifact(
    api: Api, download: Downloader, repo: str, workflow: str, name: str
) -> dict[str, bytes]:
    """The files of the artifact name of the last successful run of workflow on main."""
    runs = api.get(
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        "?branch=main&status=success&per_page=1&exclude_pull_requests=true"
    )
    found = (runs or {}).get("workflow_runs") or []
    if not found:
        return {}
    listed = api.get(f"repos/{repo}/actions/runs/{found[0]['id']}/artifacts") or {}
    for item in listed.get("artifacts", []):
        if item.get("name") == name and not item.get("expired"):
            data = download(f"repos/{repo}/actions/artifacts/{item['id']}/zip")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return {entry: archive.read(entry) for entry in archive.namelist()}
    return {}


def coverage(files: dict[str, bytes]) -> float | None:
    for name, data in files.items():
        if name.endswith(".xml"):
            rate = ElementTree.fromstring(data).get("line-rate")
            return None if rate is None else 100 * float(rate)
    return None


def mutation(files: dict[str, bytes]) -> float | None:
    for name, data in files.items():
        text = data.decode("utf-8", "replace")
        if name.endswith("results.txt"):
            killed = len(re.findall(r": killed$", text, re.MULTILINE))
            survived = len(re.findall(r": survived$", text, re.MULTILINE))
            if killed + survived:
                return 100 * killed / (killed + survived)
        found = re.search(r"Mutation Score Indicator \(MSI\): (\d+(?:\.\d+)?)%", text)
        if found:
            return float(found[1])
    return None


def answer_hours(api: Api, repo: str, since: datetime) -> float | None:
    """The median hours from a new issue to its first answer by someone else."""
    stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = api.get(f"repos/{repo}/issues?state=all&since={stamp}&per_page=100") or []
    hours = []
    for issue in [item for item in issues if "pull_request" not in item][:ISSUES]:
        if when(issue["created_at"]) < since:
            continue
        reporter = issue["user"]["login"]
        comments = (
            api.get(f"repos/{repo}/issues/{issue['number']}/comments?per_page=30") or []
        )
        for comment in comments:
            if comment["user"]["login"] != reporter:
                answered = when(comment["created_at"]) - when(issue["created_at"])
                hours.append(answered.total_seconds() / 3600)
                break
    return statistics.median(hours) if hours else None


def ci_minutes(api: Api, repo: str) -> float | None:
    runs = api.get(
        f"repos/{repo}/actions/workflows/{WORKFLOWS['CI']}/runs"
        "?branch=main&status=success&per_page=10&exclude_pull_requests=true"
    )
    minutes = [
        (when(run["updated_at"]) - when(run["run_started_at"])).total_seconds() / 60
        for run in (runs or {}).get("workflow_runs", [])
        if run.get("run_started_at") and run.get("updated_at")
    ]
    return statistics.median(minutes) if minutes else None


def health(api: Api, download: Downloader, repo: str, now: datetime) -> Health:
    since = now - WINDOW
    releases = api.get(f"repos/{repo}/releases?per_page=100") or []
    return Health(
        coverage=coverage(artifact(api, download, repo, WORKFLOWS["CI"], "coverage")),
        mutation=mutation(artifact(api, download, repo, "mutation.yml", "mutation")),
        releases=sum(
            1
            for release in releases
            if release.get("published_at")
            and not release.get("prerelease")
            and when(release["published_at"]) >= since
        ),
        answer_hours=answer_hours(api, repo, since),
        ci_minutes=ci_minutes(api, repo),
    )


def load_history(url: str, opener: Opener) -> list[dict[str, Any]]:
    """The history that the published dashboard holds, or none."""
    if not url:
        return []
    try:
        with opener(url) as response:
            found = json.load(response)
    except (urllib.error.URLError, ValueError, OSError):
        return []
    return (
        [entry for entry in found if isinstance(entry, dict)]
        if isinstance(found, list)
        else []
    )


def add_to_history(
    history: list[dict[str, Any]], rows: list[Row], now: datetime
) -> list[dict[str, Any]]:
    """The history with today's values, one entry a day, the last HISTORY days."""
    today = now.strftime("%Y-%m-%d")
    entry = {
        "date": today,
        "repos": {row.repo: asdict(row.health) for row in rows},
    }
    kept = [item for item in history if item.get("date") != today]
    return [*kept, entry][-HISTORY:]


def week_before(history: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """The values of the entry of a week ago, or of the oldest one after it."""
    target = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    older = [item for item in history if str(item.get("date", "")) <= target]
    return dict((older[-1] if older else {}).get("repos") or {})


# --------------------------------------------------------------------------- page

STYLE = """
:root { color-scheme: light dark; --bg: #ffffff; --fg: #1f2328; --muted: #59636e;
  --line: #d1d9e0; --ok: #1a7f37; --bad: #cf222e; --wait: #9a6700; --head: #f6f8fa; }
@media (prefers-color-scheme: dark) { :root { --bg: #0d1117; --fg: #e6edf3;
  --muted: #9198a1; --line: #3d444d; --ok: #3fb950; --bad: #f85149; --wait: #d29922;
  --head: #151b23; } }
body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1400px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 18px; margin: 32px 0 4px; }
p { color: var(--muted); margin: 0 0 20px; }
.table { overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; }
table { border-collapse: collapse; width: 100%; min-width: 900px; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--line); text-align: left;
  white-space: nowrap; }
th { background: var(--head); font-weight: 600; font-size: 13px; }
tr:last-child td { border-bottom: 0; }
td.state { text-align: center; }
a { color: inherit; }
.ok { color: var(--ok); } .bad { color: var(--bad); font-weight: 600; }
.wait { color: var(--wait); } .none, .muted { color: var(--muted); }
"""


def cell(text: str, url: str = "", css: str = "", title: str = "") -> str:
    content = html.escape(text)
    if url:
        content = f'<a href="{html.escape(url)}">{content}</a>'
    attributes = f' class="{css}"' if css else ""
    attributes += f' title="{html.escape(title)}"' if title else ""
    return f"<td{attributes}>{content}</td>"


# Whether a higher value of a measure is better (1) or worse (-1).
BETTER = {
    "coverage": 1,
    "mutation": 1,
    "releases": 1,
    "answer_hours": -1,
    "ci_minutes": -1,
}


def shown(key: str, value: float | None) -> str:
    if value is None:
        return DASH
    if key in ("coverage", "mutation"):
        return f"{value:.1f} %"
    if key == "releases":
        return f"{value:.0f}"
    if key == "ci_minutes":
        return f"{value:.0f} min"
    if value < 1:
        return "< 1 h"
    return f"{value:.0f} h" if value < 48 else f"{value / 24:.0f} d"


def health_cell(key: str, value: float | None, before: dict[str, Any]) -> str:
    """The value with an arrow when it moved since a week ago, green when better."""
    old = before.get(key)
    text = shown(key, value)
    if value is None or not isinstance(old, int | float) or value == old:
        return cell(text, css="" if value is not None else "muted")
    arrow = "↑" if value > old else "↓"
    better = (value - old) * BETTER[key] > 0
    return cell(
        f"{text} {arrow}",
        css="ok" if better else "bad",
        title=f"a week ago {shown(key, old)}",
    )


def health_table(rows: list[Row], previous: dict[str, Any]) -> str:
    heads = [
        "Repository",
        "Coverage",
        "Mutants caught",
        "Releases in 90 days",
        "First answer to an issue",
        "CI on main",
    ]
    lines = []
    for row in rows:
        before = previous.get(row.repo, {})
        values = asdict(row.health)
        cells = [cell(row.repo.split("/", 1)[1], f"https://github.com/{row.repo}")]
        cells += [health_cell(key, values[key], before) for key in TREND]
        lines.append("<tr>" + "".join(cells) + "</tr>")
    header = "".join(f"<th>{html.escape(head)}</th>" for head in heads)
    return (
        "<h2>Health</h2>\n"
        "<p>The line coverage and the share of mutants that the tests catch, from the "
        "reports of the last runs on main; the stable releases and the median time to "
        "the first answer to a new issue over 90 days; the median time of the CI on "
        "main. An arrow shows a change since a week ago.</p>\n"
        f'<div class="table"><table>\n<thead><tr>{header}</tr></thead>\n<tbody>\n'
        + "\n".join(lines)
        + "\n</tbody>\n</table></div>\n"
    )


def render(
    rows: list[Row],
    owner: str,
    latest: str,
    now: datetime,
    previous: dict[str, Any] | None = None,
) -> str:
    heads = [
        "Repository",
        "Kind",
        "Blueprint",
        "Release",
        "Next release",
        "Pull requests",
        *WORKFLOWS,
        "Scorecard",
    ]
    lines = []
    for row in rows:
        github = f"https://github.com/{row.repo}"
        cells = [
            cell(row.repo.split("/", 1)[1], github),
            cell(row.kind or DASH, css="muted"),
        ]
        if row.repo == BLUEPRINT:
            cells.append(cell("the blueprint", css="ok"))
        elif not row.blueprint:
            cells.append(cell("not on it", css="wait"))
        elif row.blueprint == latest:
            cells.append(cell(f"✔ {row.blueprint}", css="ok"))
        else:
            cells.append(cell(f"{row.blueprint} → {latest}", css="wait"))
        if row.release:
            release_url = f"{github}/releases/tag/{row.release}"
            cells.append(cell(f"{row.release} · {row.released}", release_url))
        else:
            cells.append(cell(DASH, css="muted"))
        cells.append(
            cell(
                row.next_release or DASH, row.next_url, "" if row.next_url else "muted"
            )
        )
        pulls = f"{row.pulls}" + (
            f", {row.conflicts} in conflict" if row.conflicts else ""
        )
        cells.append(cell(pulls, f"{github}/pulls", "bad" if row.conflicts else ""))
        for name in WORKFLOWS:
            run = row.runs.get(name, Run("none"))
            symbol, css, words = SYMBOLS[run.state]
            cells.append(cell(symbol, run.url, f"state {css}", f"{name}: {words}"))
        score = DASH if row.scorecard is None else f"{row.scorecard:.1f}"
        scorecard_url = f"https://scorecard.dev/viewer/?uri=github.com/{row.repo}"
        cells.append(
            cell(score, scorecard_url, "" if row.scorecard is not None else "muted")
        )
        lines.append("<tr>" + "".join(cells) + "</tr>")
    header = "".join(f"<th>{html.escape(head)}</th>" for head in heads)
    stamp = now.strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Repository dashboard</title>\n"
        f"<style>{STYLE}</style>\n</head>\n<body>\n<main>\n"
        "<h1>Repository dashboard</h1>\n"
        f"<p>The public repositories of {html.escape(owner)} and the bots of the "
        f'<a href="https://github.com/{BLUEPRINT}">repo blueprint</a>, '
        f"as of {stamp}. The blueprint's latest release is {html.escape(latest or DASH)}.</p>\n"
        f'<div class="table"><table>\n<thead><tr>{header}</tr></thead>\n<tbody>\n'
        + "\n".join(lines)
        + "\n</tbody>\n</table></div>\n"
        + health_table(rows, previous or {})
        + "</main>\n</body>\n</html>\n"
    )


def main(
    argv: Sequence[str] | None = None,
    api: Api | None = None,
    opener: Opener = urllib.request.urlopen,
    now: datetime | None = None,
    download: Downloader = gh_download,
) -> int:
    parser = argparse.ArgumentParser(
        prog="dashboard.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--owner", required=True, help="the account of the repositories"
    )
    parser.add_argument("--out", type=Path, required=True, help="the page to write")
    parser.add_argument(
        "--history",
        default="",
        help="the address of the history.json of the published dashboard, if any",
    )
    arguments = parser.parse_args(argv)
    api = api or Api()
    now = now or datetime.now(UTC)
    try:
        latest = (api.get(f"repos/{BLUEPRINT}/releases/latest") or {}).get(
            "tag_name", ""
        )
        rows = [
            collect(api, repo, opener) for repo in repositories(api, arguments.owner)
        ]
        for row in rows:
            row.health = health(api, download, row.repo, now)
    except GitHubError as error:
        print(f"dashboard.py: {error}", file=sys.stderr)
        return 2
    history = load_history(arguments.history, opener)
    previous = week_before(history, now)
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        render(rows, arguments.owner, latest, now, previous), encoding="utf-8"
    )
    arguments.out.with_name("history.json").write_text(
        json.dumps(add_to_history(history, rows, now), indent=1) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote the dashboard of {len(rows)} repositories to {arguments.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
