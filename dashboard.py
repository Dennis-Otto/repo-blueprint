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
import json
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from blueprint import Api, GitHubError

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


# --------------------------------------------------------------------------- page

STYLE = """
:root { color-scheme: light dark; --bg: #ffffff; --fg: #1f2328; --muted: #59636e;
  --line: #d1d9e0; --ok: #1a7f37; --bad: #cf222e; --wait: #9a6700; --head: #f6f8fa; }
@media (prefers-color-scheme: dark) { :root { --bg: #0d1117; --fg: #e6edf3;
  --muted: #9198a1; --line: #3d444d; --ok: #3fb950; --bad: #f85149; --wait: #d29922;
  --head: #151b23; } }
body { margin: 0; padding: 24px 16px; background: var(--bg); color: var(--fg);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1200px; margin: 0 auto; }
h1 { font-size: 24px; margin: 0 0 4px; }
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


def render(rows: list[Row], owner: str, latest: str, now: datetime) -> str:
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
        + "\n</tbody>\n</table></div>\n</main>\n</body>\n</html>\n"
    )


def main(
    argv: Sequence[str] | None = None,
    api: Api | None = None,
    opener: Opener = urllib.request.urlopen,
    now: datetime | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        prog="dashboard.py", description=__doc__.split("\n\n")[0]
    )
    parser.add_argument(
        "--owner", required=True, help="the account of the repositories"
    )
    parser.add_argument("--out", type=Path, required=True, help="the page to write")
    arguments = parser.parse_args(argv)
    api = api or Api()
    try:
        latest = (api.get(f"repos/{BLUEPRINT}/releases/latest") or {}).get(
            "tag_name", ""
        )
        rows = [
            collect(api, repo, opener) for repo in repositories(api, arguments.owner)
        ]
    except GitHubError as error:
        print(f"dashboard.py: {error}", file=sys.stderr)
        return 2
    arguments.out.parent.mkdir(parents=True, exist_ok=True)
    arguments.out.write_text(
        render(rows, arguments.owner, latest, now or datetime.now(UTC)),
        encoding="utf-8",
    )
    print(f"Wrote the dashboard of {len(rows)} repositories to {arguments.out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
