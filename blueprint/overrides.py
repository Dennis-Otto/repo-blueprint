"""The release bot's override of each merged pull request that release-please may
fail to parse: the title of its squash commit and the lines that release-please reads
of its description, which every parser takes.

A squash commit carries the description of its pull request, and release-please
parses the whole message with a strict parser of Conventional Commits. A line of the
description that the parser takes for the start of a footer, such as `**[(Full` of the
release notes that Renovate quotes, or `print("a" % (b, c))` of an advisory, makes it
give up on the commit, title included: the commit is left out of the release, with a
line in the log of a run that passes, and the fix waits for an unrelated release that
doesn't list it. release-please reads the text between BEGIN_COMMIT_OVERRIDE and
END_COMMIT_OVERRIDE in the description of the pull request of a commit instead of
the message. So, before release-please runs, the release bot writes such an override
into each merged pull request since the last release that can change the release: its
title, and the lines `Release-As:` and `BREAKING CHANGE:` of its message, each a line
of its own, in an HTML comment that the page doesn't show.
"""

from __future__ import annotations

import re
import urllib.parse
from collections.abc import Iterator

from blueprint.bot_health import default_branch
from blueprint.github import Api, Json
from blueprint.pr_report import BREAKING, SHOWN, TITLE

START = "BEGIN_COMMIT_OVERRIDE"
END = "END_COMMIT_OVERRIDE"
# The lines of a message that release-please reads besides the title, as the report
# of a pull request reads them in its description.
FOOTER = re.compile(r"^(?:BREAKING[ -]CHANGE: |(?i:release-as): *v?\d).*$", re.M)
# The most commits between two releases that the bot reads, as GitHub's compare does.
PAGE = 100
MOST_COMMITS = 250


def matters(message: str) -> bool:
    """Whether release-please makes something of the commit: a kind of change that
    the notes show, a breaking change or a version of its own."""
    match = TITLE.match(message)
    if match is None:
        return False
    return (
        match["kind"] in SHOWN
        or bool(match["bang"])
        or bool(BREAKING.search(message))
        or bool(FOOTER.search(message))
    )


def override(message: str) -> str:
    """What release-please reads instead of the message: its title, and its lines of
    Release-As and BREAKING CHANGE below it."""
    title = message.split("\n", 1)[0].strip()
    footers = [line.strip() for line in FOOTER.findall(message)]
    return "\n".join([title, "", *footers]) if footers else title


def with_override(body: str, text: str) -> str:
    """The description of the pull request with the override at its end."""
    block = f"<!-- {START}\n{text}\n{END} -->"
    return f"{body.rstrip()}\n\n{block}" if body.strip() else block


def since_last_release(api: Api, repo: str, branch: str) -> Iterator[Json]:
    """The commits of the branch since the latest release, oldest first; the latest
    commits of the branch, before the first release."""
    latest = api.get(f"repos/{repo}/releases/latest")
    if isinstance(latest, dict):
        span = urllib.parse.quote(f"{latest['tag_name']}...{branch}", safe=".")
        read = 0
        for page in range(1, MOST_COMMITS // PAGE + 2):
            compared = api.get(
                f"repos/{repo}/compare/{span}?per_page={PAGE}&page={page}"
            )
            if not isinstance(compared, dict):
                break
            yield from compared["commits"]
            read += len(compared["commits"])
            if not compared["commits"] or read >= compared["total_commits"]:
                return
        if read:
            return
    recent = api.get(f"repos/{repo}/commits?sha={branch}&per_page={PAGE}")
    yield from recent if isinstance(recent, list) else []


def pull_of(api: Api, repo: str, sha: str) -> Json:
    """The pull request whose merge made the commit, as release-please finds it, or
    None for a commit pushed without one."""
    pulls = api.get(f"repos/{repo}/commits/{sha}/pulls") or []
    for pull in pulls:
        if pull.get("merge_commit_sha") == sha and pull.get("merged_at"):
            return pull
    return None


def write_overrides(api: Api, repo: str) -> str:
    """Write the override into each merged pull request since the last release whose
    commit can change the release and has more than release-please reads of it; the
    summary of the run, in Markdown."""
    branch = default_branch(api, repo)
    lines = []
    for commit in since_last_release(api, repo, branch):
        message = str(commit["commit"]["message"]).replace("\r\n", "\n")
        if not matters(message):
            continue
        text = override(message)
        if message.strip() == text:
            continue
        pull = pull_of(api, repo, commit["sha"])
        if pull is None:
            continue
        body = pull.get("body") or ""
        if START in body:
            continue
        api.patch(
            f"repos/{repo}/pulls/{pull['number']}", {"body": with_override(body, text)}
        )
        title = text.split("\n", 1)[0].replace("`", "'")
        lines.append(f"- #{pull['number']}: release-please reads `{title}`")
    if not lines:
        return "No merged pull request since the last release needs an override.\n"
    return (
        "release-please reads the title of these pull requests instead of their"
        " description, which its parser might not take:\n\n" + "\n".join(lines) + "\n"
    )
