#!/usr/bin/env python3
"""The dashboard of the public repositories of an owner.

    python3 dashboard.py --owner Dennis-Otto --out site/index.html

For every public repository that is no fork and not archived, it shows the release of
the blueprint it is on and the pull request that updates it, its latest release and the
pull request of the next one, its open pull requests and those that conflict, the last
run of its main workflows on main, and its OpenSSF Scorecard. It shows nothing that
isn't public anyway: no finding of code scanning and no alert of Dependabot. The
Dashboard workflow publishes it on GitHub Pages.
https://github.com/Dennis-Otto/repo-blueprint
"""

from __future__ import annotations

import argparse
import base64
import html
import http.client
import io
import json
import re
import statistics
import subprocess
import sys
import urllib.error
import urllib.parse
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
# The file of the CI: ci.yml in a repository made from the blueprint, and in the
# blueprint, which has a CI for each stack, that of its own code, in Python.
CI_FILES = ("ci.yml", "ci-python.yml")
# The workflows whose last run on main the dashboard shows, by file; that of the CI is
# the first of CI_FILES that a repository has.
WORKFLOWS = {
    "CI": CI_FILES[0],
    "CodeQL": "codeql.yml",
    "Release": "release.yml",
    "Verification": "verify-release.yml",
    "Settings": "settings.yml",
    "Findings": "findings.yml",
    "Links": "links.yml",
    "Mutation": "mutation.yml",
    "Renovate": "renovate.yml",
}
SYMBOLS = {
    "success": ("✔", "ok", "passed"),
    "failure": ("✘", "bad", "failed"),
    "running": ("●", "wait", "running"),
    "none": (DASH, "none", "no run"),
    "absent": (DASH, "none", "not set up"),
}
# The runs of main that the state of a workflow looks through for one that ran.
RECENT = 10
# The runs of main that the last run of a workflow looks through: a busy hour of pull
# requests leaves more than ten skipped runs of Findings in a row, and it is still
# one request.
LAST_RUNS = 50
# The conclusions of a run or a job that passed.
PASSED = ("success", "neutral")
# The branch of the pull request of the blueprint bot.
UPDATE_BRANCH = "blueprint/update"
# The seconds that a request to a website may take, such as one to the Scorecard.
TIMEOUT = 30

Opener = Callable[..., Any]


@dataclass
class Run:
    """The state of the last run of a workflow or a job, and when it started."""

    state: str
    url: str = ""
    started: str = ""


@dataclass
class Update:
    """The open pull request of the blueprint bot: the release it updates to and the
    state of its checks."""

    target: str
    number: int
    url: str
    state: str


@dataclass
class Row:
    """What the dashboard shows of one repository."""

    repo: str
    kind: str = ""
    blueprint: str = ""
    update: Update | None = None
    release: str = ""
    released: str = ""
    next_release: str = ""
    next_url: str = ""
    pulls: int = 0
    conflicts: int = 0
    ci: str = CI_FILES[0]
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


def workflow_files(api: Api, repo: str) -> set[str]:
    """The files of the workflows that repo has, by name, without deleted ones."""
    return {
        str(item.get("path", "")).rsplit("/", 1)[-1]
        for item in api.get_all(f"repos/{repo}/actions/workflows")
        if item.get("state") != "deleted"
    }


def ci_workflow(files: set[str]) -> str:
    """The file of the CI among the files of the workflows of a repository."""
    return next((name for name in CI_FILES if name in files), CI_FILES[0])


def state_of(item: dict[str, Any]) -> str:
    """The state of a run or a job: running until it completed, then passed or
    failed."""
    if item.get("status") != "completed":
        return "running"
    return "success" if item.get("conclusion") in PASSED else "failure"


def last_run(api: Api, repo: str, workflow: str) -> Run:
    """The last run of workflow for main. A run that GitHub skipped says nothing about
    main, such as one of Findings that the CodeQL of a pull request started, and
    neither does a pull request from the main of a fork, whose branch has that name
    too."""
    runs = api.get(
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        f"?branch=main&per_page={LAST_RUNS}&exclude_pull_requests=true"
    )
    for run in (runs or {}).get("workflow_runs") or []:
        skipped = run.get("conclusion") == "skipped"
        if skipped or str(run.get("event", "")).startswith("pull_request"):
            continue
        return Run(state_of(run), run.get("html_url", ""), run.get("created_at") or "")
    return Run("none")


def verification(api: Api, repo: str, tag: str, standalone: Run) -> Run:
    """The newer of the last run of the release verification itself, which checks the
    latest release every week, and the verification of the release tag in the run of
    the Release workflow that made it, which calls it as a reusable workflow: GitHub
    lists that run under the Release workflow alone, as its job "verify / verify the
    release". Only the push that merged the release pull request made the release:
    the scheduled runs of Release on that commit skip the verification."""
    quoted = urllib.parse.quote(tag, safe="")
    commit = api.get(f"repos/{repo}/commits/{quoted}") if tag else None
    sha = (commit or {}).get("sha", "")
    runs = (
        api.get(
            f"repos/{repo}/actions/workflows/release.yml/runs"
            f"?head_sha={sha}&event=push&per_page=1"
        )
        if sha
        else None
    )
    for run in (runs or {}).get("workflow_runs") or []:
        jobs = api.get(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=100")
        for job in (jobs or {}).get("jobs") or []:
            named = str(job.get("name", "")).startswith("verify / ")
            if named and job.get("conclusion") != "skipped":
                verified = Run(
                    state_of(job), job.get("html_url", ""), job.get("started_at") or ""
                )
                return max(standalone, verified, key=lambda found: found.started)
    return standalone


def checks(api: Api, repo: str, sha: str) -> str:
    """The state of the checks of a commit: failed when one failed, passed when every
    one passed or was skipped, running otherwise."""
    found = api.get_all(f"repos/{repo}/commits/{sha}/check-runs") if sha else []
    good = (*PASSED, "skipped")
    if any(
        item.get("status") == "completed" and item.get("conclusion") not in good
        for item in found
    ):
        return "failure"
    if found and all(item.get("status") == "completed" for item in found):
        return "success"
    return "running"


def update(api: Api, repo: str, pull: dict[str, Any]) -> Update:
    """The pull request of the blueprint bot, such as "chore: update to the blueprint
    v0.10.1": the release it updates to and the state of its checks."""
    found = re.search(r"(v\d+\.\d+\.\d+\S*)\s*$", str(pull.get("title", "")))
    sha = str((pull.get("head") or {}).get("sha", ""))
    return Update(
        found[1] if found else "",
        int(pull.get("number", 0)),
        str(pull.get("html_url", "")),
        checks(api, repo, sha),
    )


def scorecard(repo: str, opener: Opener) -> float | None:
    try:
        with opener(SCORECARD_API + repo, timeout=TIMEOUT) as response:
            score = json.load(response).get("score")
    except (OSError, ValueError, http.client.HTTPException):
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
    for pull in api.get_all(f"repos/{repo}/pulls?state=open&per_page=100"):
        labels = {label["name"] for label in pull.get("labels", [])}
        if "autorelease: pending" in labels:
            row.next_release = pull["title"].removeprefix("chore: release ")
            row.next_url = pull["html_url"]
            continue
        row.pulls += 1
        row.conflicts += "merge-conflict" in labels
        if (pull.get("head") or {}).get("ref") == UPDATE_BRANCH:
            row.update = update(api, repo, pull)
    files = workflow_files(api, repo)
    row.ci = ci_workflow(files)
    row.runs = {
        name: last_run(api, repo, file) if file in files else Run("absent")
        for name, file in {**WORKFLOWS, "CI": row.ci}.items()
    }
    row.runs["Verification"] = verification(
        api, repo, row.release, row.runs["Verification"]
    )
    row.scorecard = scorecard(repo, opener)
    return row


def repositories(api: Api, owner: str) -> list[str]:
    """The public repositories of the owner, without archived ones and forks."""
    found = api.get_all(f"users/{owner}/repos?type=owner&per_page=100")
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
# The seconds that the download of an artifact may take.
DOWNLOAD_TIMEOUT = 120
# What a report that can't be read raises: gh failing to download it, a zip or an XML
# file that is none, a rate that is no number.
UNREADABLE = (
    subprocess.SubprocessError,
    zipfile.BadZipFile,
    ElementTree.ParseError,
    ValueError,
)

Downloader = Callable[[str], bytes]


class HistoryError(Exception):
    """The history of the published dashboard can't be read."""


def gh_download(path: str) -> bytes:
    """The bytes at path of GitHub's API, such as the zip of an artifact."""
    return subprocess.run(  # pragma: no cover - the tests simulate gh
        ["gh", "api", path], capture_output=True, check=True, timeout=DOWNLOAD_TIMEOUT
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


def main_runs(api: Api, repo: str, workflow: str) -> list[dict[str, Any]]:
    """The last successful runs of workflow for main itself, newest first. A pull
    request from the main of a fork runs on a branch of that name too, with its own
    changes, even to the workflow."""
    runs = api.get(
        f"repos/{repo}/actions/workflows/{workflow}/runs"
        f"?branch=main&status=success&per_page={RECENT}&exclude_pull_requests=true"
    )
    return [
        run
        for run in (runs or {}).get("workflow_runs") or []
        if not str(run.get("event", "")).startswith("pull_request")
    ]


def artifact(
    api: Api, download: Downloader, repo: str, workflow: str, name: str
) -> dict[str, bytes]:
    """The files of the artifact name of the last successful run of workflow on main."""
    found = main_runs(api, repo, workflow)
    if not found:
        return {}
    listed = api.get(f"repos/{repo}/actions/runs/{found[0]['id']}/artifacts") or {}
    for item in listed.get("artifacts", []):
        if item.get("name") == name and not item.get("expired"):
            data = download(f"repos/{repo}/actions/artifacts/{item['id']}/zip")
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                return {entry: archive.read(entry) for entry in archive.namelist()}
    return {}


def report(
    read: Callable[[dict[str, bytes]], float | None],
    api: Api,
    download: Downloader,
    repo: str,
    workflow: str,
    name: str,
) -> float | None:
    """The value that read finds in the artifact name of the last successful run of
    workflow, or None, with a warning, when it can't be read: a broken report leaves
    out its own value, not the page."""
    try:
        return read(artifact(api, download, repo, workflow, name))
    except UNREADABLE as error:
        print(
            f"dashboard.py: the {name} report of {repo} is unreadable: {error}",
            file=sys.stderr,
        )
        return None


def coverage(files: dict[str, bytes]) -> float | None:
    for name, data in files.items():
        if name.endswith(".xml"):
            rate = ElementTree.fromstring(data).get("line-rate")
            return None if rate is None else 100 * float(rate)
    return None


def mutation(files: dict[str, bytes]) -> float | None:
    """The share of the mutants of the code that the tests run which a test caught:
    of mutmut the killed among the killed and survived, of Infection the Covered Code
    MSI, or the MSI of an older artifact that has no other."""
    for name, data in files.items():
        text = data.decode("utf-8", "replace")
        if name.endswith("results.txt"):
            killed = len(re.findall(r": killed$", text, re.MULTILINE))
            survived = len(re.findall(r": survived$", text, re.MULTILINE))
            if killed + survived:
                return 100 * killed / (killed + survived)
        found = re.search(r"Covered Code MSI: (\d+(?:\.\d+)?)%", text) or re.search(
            r"Mutation Score Indicator \(MSI\): (\d+(?:\.\d+)?)%", text
        )
        if found:
            return float(found[1])
    return None


def bot(user: dict[str, Any]) -> bool:
    """Whether a user of GitHub is a bot, such as the issue assistant or an app."""
    return user.get("type") == "Bot" or str(user.get("login", "")).endswith("[bot]")


def answer_hours(api: Api, repo: str, since: datetime) -> float | None:
    """The median hours from a new issue to its first answer by a person other than
    its reporter. The answer of a bot, such as the issue assistant, comes within
    minutes and tells nothing about the maintainers, and an issue that a bot opened,
    such as the report of a failed run, waits for no answer."""
    stamp = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    issues = api.get(f"repos/{repo}/issues?state=all&since={stamp}&per_page=100") or []
    asked = [
        item for item in issues if "pull_request" not in item and not bot(item["user"])
    ]
    hours = []
    for issue in asked[:ISSUES]:
        if when(issue["created_at"]) < since:
            continue
        reporter = issue["user"]["login"]
        comments = (
            api.get(f"repos/{repo}/issues/{issue['number']}/comments?per_page=30") or []
        )
        for comment in comments:
            if comment["user"]["login"] != reporter and not bot(comment["user"]):
                answered = when(comment["created_at"]) - when(issue["created_at"])
                hours.append(answered.total_seconds() / 3600)
                break
    return statistics.median(hours) if hours else None


def median_minutes(runs: list[dict[str, Any]]) -> float | None:
    """The median minutes from the start of each run to its end."""
    minutes = [
        (when(run["updated_at"]) - when(run["run_started_at"])).total_seconds() / 60
        for run in runs
        if run.get("run_started_at") and run.get("updated_at")
    ]
    return statistics.median(minutes) if minutes else None


def health(
    api: Api, download: Downloader, repo: str, now: datetime, ci: str = CI_FILES[0]
) -> Health:
    """The health of repo, whose CI is the workflow ci."""
    since = now - WINDOW
    releases = api.get(f"repos/{repo}/releases?per_page=100") or []
    return Health(
        coverage=report(coverage, api, download, repo, ci, "coverage"),
        mutation=report(mutation, api, download, repo, "mutation.yml", "mutation"),
        releases=sum(
            1
            for release in releases
            if release.get("published_at")
            and not release.get("prerelease")
            and when(release["published_at"]) >= since
        ),
        answer_hours=answer_hours(api, repo, since),
        ci_minutes=median_minutes(main_runs(api, repo, ci)),
    )


def load_history(url: str, opener: Opener) -> list[dict[str, Any]]:
    """The history that the published dashboard holds: none when nothing is published
    there yet. Any other failure raises HistoryError: the page would otherwise publish
    a history of today alone, and the trends of up to HISTORY days would be gone."""
    if not url:
        return []
    try:
        with opener(url, timeout=TIMEOUT) as response:
            found = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return []
        raise HistoryError(f"the history at {url} can't be read: {error}") from error
    except (OSError, ValueError, http.client.HTTPException) as error:
        raise HistoryError(f"the history at {url} can't be read: {error}") from error
    if not isinstance(found, list):
        raise HistoryError(f"the history at {url} holds no list of days")
    return [
        entry
        for entry in found
        if isinstance(entry, dict)
        and isinstance(entry.get("date"), str)
        and isinstance(entry.get("repos", {}), dict)
    ]


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
    """The values of the newest entry from a week ago or before, or none when the
    history is younger than a week."""
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
# The workflow whose runs a value of the health comes from.
SOURCES = {"coverage": "CI", "mutation": "Mutation", "ci_minutes": "CI"}


def shown(key: str, value: float | None) -> str:
    if value is None:
        return DASH
    if key in ("coverage", "mutation"):
        return f"{value:.1f} %"
    if key == "releases":
        return f"{value:.0f}"
    if key == "ci_minutes":
        return "< 1 min" if value < 1 else f"{value:.0f} min"
    if value < 1:
        return "< 1 h"
    return f"{value:.0f} h" if value < 48 else f"{value / 24:.0f} d"


def health_cell(
    key: str, value: float | None, before: dict[str, Any], run: Run | None = None
) -> str:
    """The value with an arrow when it moved since a week ago, green when better. No
    value, where the last run of its workflow failed, shows that run."""
    if value is None and run is not None and run.state == "failure":
        return cell("✘ failed", run.url, "bad", f"{SOURCES[key]}: the last run failed")
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
        "First answer by a person",
        "CI on main",
    ]
    lines = []
    for row in rows:
        before = previous.get(row.repo, {})
        values = asdict(row.health)
        cells = [cell(row.repo.split("/", 1)[1], f"https://github.com/{row.repo}")]
        cells += [
            health_cell(key, values[key], before, row.runs.get(SOURCES.get(key, "")))
            for key in TREND
        ]
        lines.append("<tr>" + "".join(cells) + "</tr>")
    header = "".join(f"<th>{html.escape(head)}</th>" for head in heads)
    return (
        "<h2>Health</h2>\n"
        "<p>The line coverage and the share of mutants that the tests catch, from the "
        "reports of the last successful runs on main, or ✘ where none has one and the "
        "last run failed; the stable releases and the median time to the first answer "
        "by a person, not a bot, to a new issue over 90 days; the median time of the "
        "CI on main. An arrow shows a change since a week ago.</p>\n"
        f'<div class="table"><table>\n<thead><tr>{header}</tr></thead>\n<tbody>\n'
        + "\n".join(lines)
        + "\n</tbody>\n</table></div>\n"
    )


def blueprint_cell(row: Row, latest: str) -> str:
    """The release of the blueprint that row is on, and the update to a newer one: a
    pull request of the blueprint bot in the colour of its checks."""
    if row.repo == BLUEPRINT:
        return cell("the blueprint", css="ok")
    if not row.blueprint:
        return cell("not on it", css="wait")
    if row.blueprint == latest:
        return cell(f"✔ {row.blueprint}", css="ok")
    if row.update:
        _, css, words = SYMBOLS[row.update.state]
        return cell(
            f"{row.blueprint} → {row.update.target or latest} · #{row.update.number}",
            row.update.url,
            css,
            f"the update of the blueprint: checks {words}",
        )
    return cell(f"{row.blueprint} → {latest}", css="wait")


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
            blueprint_cell(row, latest),
        ]
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
        # First: a history that can't be read stops the page before its requests.
        history = load_history(arguments.history, opener)
        latest = (api.get(f"repos/{BLUEPRINT}/releases/latest") or {}).get(
            "tag_name", ""
        )
        rows = [
            collect(api, repo, opener) for repo in repositories(api, arguments.owner)
        ]
        for row in rows:
            row.health = health(api, download, row.repo, now, row.ci)
    except (GitHubError, HistoryError) as error:
        print(f"dashboard.py: {error}", file=sys.stderr)
        return 2
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
