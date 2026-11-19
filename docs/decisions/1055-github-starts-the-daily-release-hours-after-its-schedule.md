# GitHub starts the daily release hours after its schedule, and the texts say so

- Status: accepted
- Date: 2026-11-19
- Amends [0180](0180-the-blueprint-releases-at-most-once-a-day.md)

## Context

The blueprint releases at most once a day, in the daily run of `release.yml`, whose cron is `25 2 * * *` ([0180](0180-the-blueprint-releases-at-most-once-a-day.md)). Every repository made from the blueprint runs it at a minute of its own ([0083](0083-every-repository-runs-its-schedules-at-times-of-its-own.md)), such as 02:06 in paperless-sync and 02:57 in paperless-unified-search, and reads that time from its own `release.yml` for the texts of its release bot. These texts said that the release goes "at 02:25 UTC", and the comment above `schedule:` in `release.yml`, which reaches every repository unchanged, that it runs "in the night of Europe". The automation page of every website said that GitHub starts a scheduled run "often some minutes late". GitHub doesn't keep these times ([issue 1055](https://github.com/Dennis-Otto/repo-blueprint/issues/1055)).

What the maintainer measured over the ten repositories of the account, in UTC:

- Since 2026-11-05, 947 of 950 times of the daily and weekly crons got a run, a median of 7.8 h after the cron and at worst about 10 h (10.3 h). The three without a run each fell on a day on which that cron changed.
- `release.yml`, in the eight repositories that have it: every time of the cron in force got a run, 108 of 108, a median of 7.8 h late and at worst 9.3 h. The blueprint's scheduled runs of 2026-11-13 to 2026-11-17 came at 13:17, 12:22, 12:52, 13:52 and 14:45, for a cron of 05:25, and that of 2026-11-18 at 10:19, for the cron of 02:25.
- The hours pass before GitHub creates the run: a run starts when it is created, and its jobs waited a median of 0 minutes for a runner. The delay was 4.5 to 5 h in September and has been 7.5 to 9 h since 2026-11-02, and it hardly follows the account's own load. A start by `workflow_dispatch` begins at once.
- The order of the crons held on 2026-11-17: the eight scheduled runs of Release came from 14:16 to 14:56, in the order of the minutes of their crons. Nothing promises that it holds.
- GitHub's documentation of the `schedule` event (*Events that trigger workflows*) says that it "can be delayed during periods of high loads of GitHub Actions workflow runs", that the start of every hour is such a time, and that some queued jobs may be dropped then. The cause of the delays of these weeks is on GitHub's side and unknown.

On 2026-11-18 the maintainer started Release by hand at 01:40. That run merged the release pull request, and the run of its push put out v1.22.0 at 01:55. At 09:11 the bot-health bot started Release, because the scheduled run had not come ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)), and at 10:19, 7.9 h after its cron, the scheduled run came. Both held the next release pull request, because a release had gone out that UTC day: the day rule of 0180 did what it should. Their logs said that it merges "tomorrow, at 02:25 UTC", which in truth meant tomorrow, some time in the morning or around midday UTC.

## Options

1. Keep the schedule and make the texts true: they name the time of the cron as the earliest one, say that GitHub starts the run later, at present usually hours later, and say that a release by hand counts for the day.
2. An earlier cron: on 2026-11-18 the cron of 02:25 gave a run at 10:19, so an earlier one moves the release to no particular time either.
3. The Worker of the pager starts the release of every repository by `repository_dispatch` or `workflow_dispatch` at a fixed time: new parts in the release path of every repository, and the limits of the Worker's free plan.
4. The Worker starts only the blueprint's release, which starts those of the others: one run on which all of them depend.
5. A start with a personal token: GitHub names a person as its actor, so the run skips the day rule and releases at once on any day.
6. A day rule of "since the last time of the cron" instead of "the same UTC day": on 2026-11-18 it would have made two releases and two Rollouts, against the aim of 0180.
7. A question to GitHub Support: no promise of an answer or of a change, and the texts stay untrue meanwhile.

## Decision

Option 1: the maintainer decided on 2026-11-19 to keep GitHub's schedule, with no clock outside GitHub, no earlier cron and no question to GitHub Support. Decision 0180 stays in force; only its texts change. No measured number becomes a promise outside this record.

- **The log, the summary and the comment of the release pull request** (`blueprint/dependency_release.py`, with the time of each repository's own cron) say that GitHub starts the daily run from that time on, at present usually hours later. The hedge is one constant, `LATER_ON`, so the three texts can't drift apart. The log of a run that holds the release for the next day says that a run of Release that a person starts by hand releases at once, and the comment says that a release that went out earlier the same UTC day, such as one started by hand, moves the bot's release to the daily run of the next day. The first line of the comment stays, since the step finds the comment by it: an open release pull request keeps its old comment, and the next one gets the new words.
- **The comment above `schedule:` in `release.yml`** names no clock time, no night and no Rollout, which a repository made from the blueprint doesn't have: the cron sets the earliest time of the daily run, and GitHub starts it when it can, at present usually hours later. The test of [0033](0033-schedules-are-only-a-safety-net.md), which looked only for rates such as "hourly", now also refuses a clock time and "in the night" in the comments of the workflows of the blueprint and of every kind of project.
- **The automation page** of every website says that GitHub starts a scheduled run "at present usually hours late", in English and in German. The times of its table stay the times of the crons.
- **The pages and notes of the blueprint** (the pages of releases and updates, the diagram of when the release pull request merges, CONTRIBUTING.md, the notes for agents, the comment of `RELEASE_MERGE`) say the same.

## Consequences

The texts promise no time that GitHub doesn't keep, and every repository still names the time of its own cron, as the earliest one. The release and the Rollout come at present hours after the cron, later in the day; when GitHub's run comes six hours or more after it, the bot-health bot starts Release first, and that start can be the release of the day. Should GitHub start the schedules on time again, the texts stay true. The index of the records still says "in its daily run at 02:25 UTC" in the row of 0180, since no pull request edits the index ([1033](1033-a-new-record-takes-the-number-of-its-pull-request.md)).
