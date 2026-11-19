# The blueprint releases at most once a day

- Status: accepted, amended by [1055](1055-github-starts-the-daily-release-hours-after-its-schedule.md), with which the texts say that GitHub starts the daily run hours after its cron
- Date: 2026-11-17
- Amends [0087](0087-a-release-of-dependency-updates-merges-once-a-day.md) and [0033](0033-schedules-are-only-a-safety-net.md)

## Context

Every release of the blueprint starts the Rollout: each repository that follows it gets an update pull request, runs all its checks on it, merges it and rebuilds its own release pull request after the merge. From 2026-11-10 to 2026-11-16 the blueprint released eleven times, which made 76 update pull requests in seven repositories ([issue 990](https://github.com/Dennis-Otto/repo-blueprint/issues/990)). Most of these releases followed each other within hours, several of them for one dependency update each. One release a day would have brought the same changes to every repository with less than half of the update pull requests, and with as many runs of Actions fewer.

The release bot merged a release by itself only when it held nothing but dependency updates, once a day, or at once with the fix of a vulnerability ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)). Every other release pull request was merged by a person, or by an agent of a run, whenever it was green: so the blueprint released as often as someone merged it. The maintainer decided on 2026-11-17 that the blueprint releases at most once a day.

## Options

1. Keep it to the people who merge: nothing holds a release back, and the habit of merging when green stays.
2. A required check that fails on the release pull request outside a window of the day: a person sees a red pull request for most of the day, and the check runs again for nothing.
3. A variable that has the release bot merge every release in its daily run, when its checks pass, at most one a day, with one clear way to release at once, and a comment in the release pull request that says when it goes.

## Decision

Option 3.

- **The setting** is the repository variable `RELEASE_MERGE` of `[variables]`. `daily`, as `.github/repository.toml` of the blueprint sets it: the release bot merges every release. `maintainer`, the default that the template writes for a new repository, or any other value: as before, the maintainer merges, and only a release of dependency updates merges itself ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)). A project chooses the daily release in `.github/repository.project.toml`, which the update of the blueprint never overwrites.
- **The daily run** of the schedule of `release.yml` sets the auto-merge of the release pull request, after the release bot has rebuilt it on the current `main` ([0175](0175-the-release-pull-request-is-rebuilt-once-before-it-merges.md)), so it merges once its checks pass; a pull request whose checks have all passed already merges at once. A daily run on a day (UTC) on which a release went out already leaves it to the next day, so that the bot never makes a second release on one day. The first release still waits for the maintainer.
- **At once** goes what can't wait: a run of `release.yml` started by hand (*Actions → Release → Run workflow*, or `gh workflow run release.yml`) merges the release once its checks pass, for a fix of the repositories that a release broke, or any fix that can't wait for the night. A fix of a vulnerability that Renovate marks with `[security]` merges in the run of its own merge, as before. Only a run that a person starts goes at once: a run that a bot starts by hand, such as the bot-health bot for a daily run that GitHub missed or for one that failed, or the branch bot to rebuild the release pull request, keeps to the day as the daily run does, by the actor that GitHub names for the run (`GITHUB_TRIGGERING_ACTOR`, which ends in `[bot]`), so that no bot makes a second release on a day.
- **The push of every other merge** only keeps the release pull request current and says why it waits, in the log and the summary of the run.
- **The pull request says when it goes:** with `daily`, the release bot comments once in each release pull request when it merges and how to release at once. The comment comes from the token of the job, whose events start no workflow; one of the release app would start every workflow that listens to comments.
- **The time** is 02:25 UTC, 03:25 in Berlin in winter and 04:25 in summer, for the blueprint, and a few minutes later for each repository that follows it ([0083](0083-every-repository-runs-its-schedules-at-times-of-its-own.md)). The release merges about a quarter of an hour later, and the Rollout then brings it to the repositories one after the other, each with all its checks: in the night of Europe, where the maintainer and the people who use these repositories are, nobody waits for these runs, and they take no runner from a person's pull request. It comes after the daily look of the bot-health bot at 01:47 and before the weekly jobs of the repositories, such as the checks of every kind, CodeQL, the SBOM, the Scorecard, OSV-Scanner and the links, which start from 03:20 on, so that the checks of the update pull requests don't wait behind them and the scans don't wait behind the Rollout. It is no full hour, at which GitHub starts the most schedules ([0033](0033-schedules-are-only-a-safety-net.md)). The schedule was at 05:25 UTC before, among the weekly scans.

What stays as it was:

- A release of dependency updates in a repository with `maintainer` merges itself once a day, and at once with the fix of a vulnerability ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)).
- `main` takes the release pull request only when it is up to date and every required check has passed on that head; the release bot never merges past a failed check.
- The release pull request is rebuilt only once before it merges ([0175](0175-the-release-pull-request-is-rebuilt-once-before-it-merges.md)): the daily run and the run by hand rebuild it, and so does every merge while auto-merge is on for it.
- The Rollout rolls out every release that a run of Release published ([0173](0173-only-a-run-that-published-a-release-starts-its-followers.md)): it needs no change, since fewer releases mean fewer runs of it.

## Consequences

The blueprint makes at most one release a day by its bot, and with it at most one update pull request a day in each repository that follows it, instead of one for each release. A change reaches the other repositories up to a day later, unless someone starts the release by hand. A release pull request whose checks fail in the daily run keeps its auto-merge and merges once a fix makes them pass, the same day; the next daily run waits for the day after. A person can still merge the release pull request by hand; the comment says that the bot does it. GitHub may start the daily run late, sometimes by hours, and the release goes later with it.
