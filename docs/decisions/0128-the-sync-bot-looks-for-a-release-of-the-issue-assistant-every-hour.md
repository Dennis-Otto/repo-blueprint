# The sync bot looks for a release of the issue assistant every hour

- Status: accepted
- Date: 2026-11-08

## Context

The sync bot of the blueprint takes over each verified release of the issue assistant ([0024](0024-take-over-each-verified-release-of-the-issue-assistant.md)), and every repository gets it with the next release of the blueprint. The bot looked once a day, at 05:20 UTC. A release that came after that look waited for the next morning, and GitHub starts schedules late at busy times: on 8 November 2026 it started the morning run at 11:59 UTC. The issue assistant 1.10.3, released at 13:50 UTC with the fix of the check *Findings*, which mailed the maintainer three times in a minute, would have waited until the next morning. Then the release of the blueprint would have waited another day: the bot's pull request opens just after the daily run of the release bot at 05:25 UTC, the run that merges a release of nothing but dependency updates ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)). The pins were moved by hand instead (#724).

Renovate doesn't cause the delay. The rules of every repository leave `Dennis-Otto/issue-assistant` to the sync bot, because a pin that moved without the templates of its release fails the check `issue-assistant`, and so the week of waiting of Renovate ([0005](0005-renovate-instead-of-dependabot.md)) doesn't apply to it. No other dependency of the blueprint comes from its maintainer.

## Options

1. A rule of Renovate without the week of waiting for the maintainer's own releases: it would change nothing, since Renovate leaves the issue assistant alone, and must, for the reason above.
2. The release workflow of the issue assistant starts the sync bot of the blueprint: at once, but only through a step in the release workflow of every repository, made for one of them, and a token of the release app of the issue assistant that can start workflows in the blueprint.
3. The sync bot looks every hour: a release reaches the blueprint within the hour, with no new token and no new permission. A look that finds the latest release in the blueprint and no branch of the bot has nothing to do, and ends after its first job.

## Decision

Option 3. The Issue assistant sync runs at 20 minutes past every hour (`20 * * * *`), away from the full hour at which GitHub starts the most schedules late. Its first job finds the latest published release with the token of the job, which may only read. When every pin already names that release, the job also asks whether the branch `bot/issue-assistant` exists. Without that branch, no pull request is left to close, so the job of the pull request doesn't run, and with it neither the environment `release` nor a token of the release app. Otherwise that job runs as before, also when GitHub doesn't answer the question. A release still has to pass every check of 0024 before it is taken over.

## Consequences

A release of the issue assistant reaches the blueprint about an hour after it is published, plus the checks of its pull request, in place of up to a day. The release of the blueprint is still bundled: a release of nothing but dependency updates merges itself in the daily run of the release bot ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)), or at once when the maintainer starts the Release workflow by hand, and the Rollout then brings it to every repository within minutes. Whether a release that brings only a new version of the issue assistant should merge at once, as one with the fix of a vulnerability does, is left to the maintainer.

The bot runs 24 times a day, most of these runs one job of a few seconds. The bot-health bot gives a failed run a second try before it opens an issue ([0019](0019-a-failing-bot-keeps-one-issue-open.md)), so a moment in which GitHub doesn't answer opens no issue, and the next run that passes closes it.
