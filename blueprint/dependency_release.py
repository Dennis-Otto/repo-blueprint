"""Whether the open release pull request merges itself in this run of the release
bot: as a release of dependency updates (decision 0087), or as the daily release of a
repository whose variable RELEASE_MERGE is daily (decision 0176).

A release of nothing but dependency updates merges itself once a day, in the run of
the schedule of the release bot or in one started by hand, and at once when an update
fixes a vulnerability; a release with a change of a person waits for the maintainer.
With RELEASE_MERGE daily, every release merges in that daily run, at most one a day,
and at once in a run started by hand or with the fix of a vulnerability.
What counts is what the release is made of: a commit that release-please makes
something of, as `matters()` of the overrides says, is in the release, and it must be
a dependency update without a version of its own. A commit that release-please makes
nothing of, such as `docs: renew the pictures` or `chore: update to the blueprint
v1.2.3`, which the bots merge between the updates almost every day, keeps the release
back only when a person made it: its change reaches every repository with the release,
and the maintainer reviews each change of a person before it does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from blueprint.bot_health import default_branch
from blueprint.github import Api, Json
from blueprint.overrides import FOOTER, matters, since_last_release
from blueprint.pr_report import BREAKING

# The title of an update of Renovate, as the type of its rule of semantic commits
# makes it: fix for what the users run, chore and build for the rest.
DEPENDENCY = re.compile(r"(?:fix|chore|build)\(deps(?:-dev)?\): ")
# Renovate adds it to the title of every update of its vulnerabilityAlerts.
SECURITY = re.compile(r"\[security\]", re.IGNORECASE)
# The event of the run of each merge into the default branch, which leaves a release
# of routine updates to the daily run of the schedule, or to one started by hand.
MERGE = "push"

FIRST = "The first release waits for the maintainer."
HELD = "The release holds more than dependency updates; the maintainer merges it:"
LATER = (
    "The release of dependency updates merges in the daily run of the release bot,"
    " with the updates of the day."
)
NOW = (
    "The release holds nothing but dependency updates and merges once its checks pass."
)

# The value of the variable RELEASE_MERGE with which the release bot merges every
# release once a day; any other value, or none, leaves it to the maintainer.
DAILY = "daily"
# The event of the daily run, which merges the release at most once a day (UTC).
SCHEDULE = "schedule"
# The time of the schedule of release.yml in the blueprint, which a test keeps equal
# to its cron; a repository made from the blueprint runs it some minutes later.
TIME = "02:25 UTC"
# The comment that says in the release pull request when it goes, found by its first
# line, so that each pull request gets it once.
NOTICE = "<!-- The daily release of the release bot -->"

DAILY_NOW = "The daily release: the release merges once its checks pass."
BY_HAND = (
    "A run started by hand, or by the bot-health bot for a daily run that GitHub"
    " missed: the release merges at once, once its checks pass."
)
SECURITY_NOW = (
    "The release holds the fix of a vulnerability and merges at once, once its"
    " checks pass."
)
WAITS = (
    f"The release merges in the daily release of the release bot at {TIME},"
    " once its checks pass."
)
TODAY = (
    "A release went out today already: this one merges in the daily release of"
    f" tomorrow, at {TIME}."
)


@dataclass(frozen=True)
class Verdict:
    """Whether the release pull request merges now, and why, for the log of the run."""

    merge: bool
    text: str


def message_of(commit: Json) -> str:
    """The message of a commit of GitHub's compare, with the line ends of Git."""
    return str(commit["commit"]["message"]).replace("\r\n", "\n")


def by_a_bot(commit: Json) -> bool:
    """Whether a GitHub App made the commit, as GitHub names its author: the squash
    commit of a pull request has the author of the pull request. An author that
    GitHub doesn't know is taken for a person."""
    author = commit.get("author")
    return isinstance(author, dict) and author.get("type") == "Bot"


def holds_back(commit: Json) -> bool:
    """Whether the commit keeps the release from merging itself: a change that
    release-please puts into the release other than a dependency update, a dependency
    update with a version of its own, such as one whose description quotes a line
    `BREAKING CHANGE:` of the release notes, or a change of a person that the release
    brings without a word in its notes."""
    message = message_of(commit)
    if DEPENDENCY.match(message):
        return bool(BREAKING.search(message) or FOOTER.search(message))
    return matters(message) or not by_a_bot(commit)


def decide(commits: list[Json], event: str) -> Verdict:
    """Whether the release with these commits since the last one merges in a run of
    the event."""
    titles = [message_of(commit).split("\n", 1)[0].strip() for commit in commits]
    held = [
        title
        for commit, title in zip(commits, titles, strict=True)
        if holds_back(commit)
    ]
    if held:
        return Verdict(False, "\n".join([HELD, *held]))
    if event == MERGE and not any(SECURITY.search(title) for title in titles):
        return Verdict(False, LATER)
    return Verdict(True, NOW)


def daily(commits: list[Json], event: str, *, today: bool) -> Verdict:
    """Whether the release with these commits since the last one merges in a run of
    the event, where the release bot merges every release once a day: in the daily run
    when no release went out on its day (UTC) yet, and at once in a run started by
    hand or with the fix of a vulnerability, the ways for what can't wait."""
    if any(SECURITY.search(message_of(commit).split("\n", 1)[0]) for commit in commits):
        return Verdict(True, SECURITY_NOW)
    if event == MERGE:
        return Verdict(False, WAITS)
    if event != SCHEDULE:
        return Verdict(True, BY_HAND)
    if today:
        return Verdict(False, TODAY)
    return Verdict(True, DAILY_NOW)


def same_day(published: object, now: datetime) -> bool:
    """Whether a release published at this time of GitHub, such as
    2026-11-17T02:41:07Z, went out on the day (UTC) of now."""
    if not isinstance(published, str) or not published:
        return False
    moment = datetime.fromisoformat(published.replace("Z", "+00:00"))
    return moment.astimezone(UTC).date() == now.astimezone(UTC).date()


def notice() -> str:
    """The comment that says in the release pull request when it goes, and how it
    goes at once."""
    return "\n".join(
        [
            NOTICE,
            f"The release bot merges this pull request in the daily release at {TIME},"
            " once its checks pass; GitHub may start its daily run later. A release"
            " that went out the same day (UTC) moves it to the next one.",
            "",
            "For a fix that can't wait, such as one for the repositories that a"
            " release broke, release at once: start the workflow Release by hand,"
            " under *Actions → Release → Run workflow* or with"
            " `gh workflow run release.yml`, and it merges once its checks pass. A fix"
            " of a vulnerability that Renovate marks with `[security]` goes at once by"
            " itself.",
        ]
    )


def dependency_release(
    api: Api,
    repo: str,
    event: str,
    merge: str = "",
    now: datetime | None = None,
) -> Verdict:
    """Whether the open release pull request merges itself in this run of the release
    bot, by the commits of the default branch since the latest release and by the
    variable RELEASE_MERGE, in merge."""
    latest = api.get(f"repos/{repo}/releases/latest")
    if not isinstance(latest, dict):
        return Verdict(False, FIRST)
    branch = default_branch(api, repo)
    commits = list(since_last_release(api, repo, branch))
    if merge.strip() == DAILY:
        today = same_day(latest.get("published_at"), now or datetime.now(UTC))
        return daily(commits, event, today=today)
    return decide(commits, event)
