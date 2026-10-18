# Bots start from events, and their schedules are only a safety net

- Status: accepted
- Date: 2026-10-18

## Context

The release bot (`release.yml`) looked every hour and the branch bot (`update-branches.yml`) every half hour, because a merge that auto-merge does with the token of a workflow starts no workflow: Dependabot's updates of the dev container turned auto-merge on with the `GITHUB_TOKEN` of `dependabot-automerge.yml`, so their merges woke neither bot. Renovate, the release bot and the branch bot already merged as the release app, whose merges start the workflows of the push.

- **GitHub runs schedules as it can.** It started the scheduled runs of this account in bursts every four to seven hours. From 7 to 12 October 2026 it ran the hourly Release of the blueprint 21 times instead of about 117 and the half-hourly Update branches 22 times instead of about 240; in paperless-unified-search, over 70 hours, 13 of 70 and 14 of 140, and in paperless-sync 17 of 98 and 18 of 197. Daily and weekly bots ran six to nine hours late, such as Findings at 07:17 that ran at 13:46, and the Monday jobs of 05:17 to 05:50 that ran from 13:11.
- **The schedules did nothing.** None of 279 scheduled runs of the release bot made a release, yet each started a run of Issue lifecycle and of the bot-health bot after it, and each run of the branch bot one of the bot-health bot: about 100 short runs a day in each repository, each holding one of the account's about 20 runners while the pull requests waited.
- **They would cost a private repository more than it has.** Configured, the schedules of a project came to about 78 runs a day, and with the runs that they start close to 200: about 6,000 jobs a month, each of which GitHub rounds up to a whole minute, against the 2,000 minutes a month of GitHub Free.
- **The comments promised times** that GitHub didn't keep: every hour, every half hour, every two hours. The weekly report started at 06:00, on the full hour, when GitHub has the most schedules to start.

## Options

1. Keep the schedules, and only reword the comments. The runs stay, and so does the cost.
2. Merge Dependabot's updates as the release app, so that every merge into `main` is a push of the release app or of a person and starts the bots at once, and keep the schedules only as a safety net, a few runs a day.
3. As 2, and also let the release bot rebuild its pull request only on the schedule or when started by hand, not after every merge, so that a merge into `main` pushes nothing to the release branch.

## Decision

Option 2.

- **Dependabot as the release app.** `dependabot-automerge.yml` creates a token of the release app, with *Contents* and *Pull requests* write and nothing else, and turns auto-merge on with it: the environment `release`, which holds the private key and which only `main` may use, is open to `pull_request_target`, which runs on `main`, and the job checks out nothing. A repository without the app turns auto-merge on with the job's own token, as before.
- **Schedules as a safety net.** The release bot looks once a day (`25 5 * * *`), for a push that GitHub lost and a tag that a failed run left to sign; the branch bot every six hours (`10 */6 * * *`), for a lost event and a pull request whose fix passed its checks; the weekly report at 05:07 on Mondays. The bot-health bot starts every night a workflow whose schedule GitHub missed by six hours or more. No schedule starts on the full hour.
- **Honest comments.** No comment of a workflow promises a time; they say that GitHub runs schedules as it can, often hours late.
- **The release pull request stays current with every merge,** not only on the schedule as in option 3: `main` takes only a pull request that is up to date with it, so a release pull request that only the schedule rebuilt couldn't merge for hours, and one merged after an update of its branch by hand would release changes that its notes don't list. Since decision 0009, its rebuilds run only the required checks, without the scanners.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-starts-the-bots.dark.svg">
  <img src="../images/diagrams/what-starts-the-bots.svg" alt="What starts the bots: Renovate, the updates of Dependabot, the release bot and the branch bot merge as the release app, and a person as themselves, since a merge with the token of a workflow would start no workflow. So every merge into main is a push, which starts the release bot and the branch bot at once; they keep the release pull request current and bring the next pull request up to date. Only an event that GitHub lost waits for the schedules, a few runs a day, which GitHub runs as it can, often hours late, and every night the bot-health bot starts a workflow whose schedule GitHub missed.">
</picture>

## Consequences

The schedules of a project start 68 to 78 runs a week, about ten a day, instead of about 540, and with the runs that they start about 20 a day instead of close to 200; `tests/test_template.py` keeps every kind of project at twelve scheduled runs a day at most, no schedule on the full hour and no comment that promises a time. A merge of Dependabot starts the release bot and the branch bot at once, as Renovate's does. An event that GitHub loses waits for the next run of the schedule, at most six hours for the branch bot and a day for the release bot, or for the bot-health bot at night, which starts a workflow whose schedule GitHub missed; a person can start either at once in *Actions*. Issue lifecycle still starts after every run of the release bot, now about once a day on the schedule; skipping the scheduled ones there belongs to its template in the issue assistant. Renovate keeps its schedule of every two hours, which GitHub runs a few times a day; decision 0029 sets when its updates come.
