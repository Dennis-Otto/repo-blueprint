# The sync bot looks for a release of the issue assistant every hour

- Status: accepted
- Date: 2026-11-08

## Context

The sync bot of the blueprint takes over each verified release of the issue assistant ([0024](0024-take-over-each-verified-release-of-the-issue-assistant.md)), and every repository gets it with the next release of the blueprint. The bot looked once a day, at 05:20 UTC. A release that came after that look waited for the next morning, and GitHub starts schedules late at busy times: on 8 November 2026 it started the morning run at 11:59 UTC. The issue assistant 1.10.3, released at 13:50 UTC with the fix of the check *Findings*, which mailed the maintainer three times in a minute, would have waited until the next morning. Then the release of the blueprint would have waited another day: the bot's pull request opens just after the daily run of the release bot at 05:25 UTC, the run that merges a release of nothing but dependency updates ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)). The pins were moved by hand instead (#724).

Bots start from events, and their schedules are only a safety net ([0033](0033-schedules-are-only-a-safety-net.md)): GitHub runs schedules as it can, in bursts every four to seven hours, and from 7 to 12 October 2026 it ran the hourly schedule of the release bot 21 times instead of about 117. But no event of the blueprint tells the sync bot of a release of another repository, so here only a schedule can look.

Renovate doesn't cause the delay. The rules of every repository leave `Dennis-Otto/issue-assistant` to the sync bot, because a pin that moved without the templates of its release fails the check `issue-assistant`, and so the week of waiting of Renovate ([0005](0005-renovate-instead-of-dependabot.md)) doesn't apply to it. No other dependency of the blueprint comes from its maintainer.

## Options

1. A rule of Renovate without the week of waiting for the maintainer's own releases: it would change nothing, since Renovate leaves the issue assistant alone, and must, for the reason above.
2. The release workflow of the issue assistant starts the sync bot of the blueprint: within minutes, but only through a step in the release workflow of every repository, made for one of them, and a token of the release app of the issue assistant that can start workflows in the blueprint.
3. The sync bot looks on an hourly schedule: a release reaches the blueprint within a few hours, as GitHub runs the schedule, in place of up to a day, with no new token and no new permission. A look that finds the latest release in the blueprint and no branch of the bot has nothing to do, and ends after its first job.

## Decision

Option 3. The Issue assistant sync runs at 20 minutes past every hour (`20 * * * *`), away from the full hour at which GitHub starts the most schedules late. Its first job finds the latest published release with the token of the job, which may only read. When every pin already names that release, the job also asks whether the branch `bot/issue-assistant` exists. Without that branch, no pull request is left to close, so the job of the pull request doesn't run, and with it neither the environment `release` nor a token of the release app. Otherwise that job runs as before, also when GitHub doesn't answer the question. A release still has to pass every check of 0024 before it is taken over.

## Consequences

A release of the issue assistant reaches the blueprint at the next scheduled run that GitHub starts, within a few hours as it runs schedules, plus the checks of its pull request, in place of up to a day. The release of the blueprint is still bundled: a release of nothing but dependency updates merges itself in the daily run of the release bot ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)), or at once when the maintainer starts the Release workflow by hand, and the Rollout then brings it to every repository within minutes. Whether a release that brings only a new version of the issue assistant should merge at once, as one with the fix of a vulnerability does, is left to the maintainer.

The schedule asks for 24 runs a day, and GitHub starts fewer; most of them are one job of a few seconds, and each also starts a short job of the bot-health bot, so about 48 short jobs a day in the blueprint. The bot-health bot gives a failed run a second try before it opens an issue ([0019](0019-a-failing-bot-keeps-one-issue-open.md)), so a moment in which GitHub doesn't answer opens no issue. A failure that lasts, such as an outage of the attestations or of Sigstore, keeps that one issue open, but GitHub mails each failed scheduled run to whoever last changed the schedule, now up to once an hour. An issue of a failure of the job of the pull request closes only when that job runs again and passes ([0126](0126-a-failure-issue-waits-for-the-jobs-that-failed.md)): an idle scheduled look skips it, so the issue stays open until the next release of the issue assistant, or until the maintainer starts the workflow by hand, which always runs that job.
