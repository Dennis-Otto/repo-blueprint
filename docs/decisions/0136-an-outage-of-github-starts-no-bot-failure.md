# An outage of GitHub starts no failure of a bot

- Status: accepted, amends [0036](0036-a-request-to-github-tries-once-more-and-a-refused-write-fails.md) and follows up [0133](0133-the-downloads-of-the-workflows-go-through-the-api.md) and [0134](0134-a-job-stops-when-harden-runner-doesnt-block.md)
- Date: 2026-11-09

## Context

On 9 November 2026, from 18:09 to 18:14 UTC, GitHub Actions ended the runs of every repository that follows the blueprint before their first job, with the annotation *Internal server error*, while githubstatus.com still said that all was well. The bots that start on the end of another run, `workflow_run`, started on each of those runs, and GitHub ended most of them the same way. Each failed run mailed the maintainer: over a hundred mails in five minutes, such as *Run failed: Findings* over *All jobs were successful*, and *Run failed: Bot health* over *No jobs were run*.

The runs of those minutes, read back from the API of the eight repositories, show what failed and how. Of 121 failed runs, in four of them, 116 were runs of bots: 46 of *Bot health*, 38 of *After the checks*, 18 of *Update branches*, 10 of *Findings* and 4 of *Issue lifecycle*; the other five were checks of pull requests. Every one of them failed in one of three ways:

- **No job at all,** as [run 42672089408](https://github.com/Dennis-Otto/repo-blueprint/actions/runs/42672089408) of *Bot health*: 83 runs.
- **A job that never started,** without a step, a runner or an annotation, as [run 42672085130](https://github.com/Dennis-Otto/repo-blueprint/actions/runs/42672085130) of *Bot health*: 15 runs.
- **Only jobs that passed or skipped,** as [run 42671585557](https://github.com/Dennis-Otto/issue-assistant/actions/runs/42671585557) of *Findings*, whose other job GitHub never created: 23 runs.

No bot failed in a step. The bots added to it all the same: the bot-health bot opened four issues, [#778](https://github.com/Dennis-Otto/repo-blueprint/issues/778) to [#781](https://github.com/Dennis-Otto/repo-blueprint/issues/781), for runs of *Findings*, *Dashboard*, *Screenshots* and *OpenSSF Scorecard* that GitHub hadn't started, each saying *The run names no failed job*. The flaky-test bot, the bot for failed releases and the bot for stopped checks would have run such a run again while GitHub failed, which only fails again and mails again, and the branch bot moved its line on after a check that never ran. Every bot that asks GitHub's API failed when GitHub answered with an error of its own for longer than its one more try of [decision 0036](0036-a-request-to-github-tries-once-more-and-a-refused-write-fails.md), five seconds later, and a 500 got no try at all.

The orchestrator of the night run stopped the mails by turning off *Bot health*, *After the checks*, *Findings* and *Update branches* in all eight repositories until the outage was over.

## Options

1. **Leave it:** an outage of GitHub is rare, and a person turns the bots off. Every outage mails again, and four issues stay open about nothing.
2. **A condition of each bot on the event:** `github.event.workflow_run` names the conclusion and the attempt of the run, but not its jobs, so no condition can tell a run that GitHub couldn't start from one that failed in a step.
3. **A step of each bot asks for the jobs of the run,** and the bot does nothing for a run that GitHub couldn't start; every call of GitHub's API tries again after an error of GitHub, and a bot that GitHub keeps failing ends with a notice instead of a failure.
4. **One more job before every bot** that asks for the jobs, which the others need: a runner more for every end of every run, which in an outage fails like the others.

## Decision

Option 3: a bot looks at what failed, and an error of GitHub is no failure of a bot.

- **A run that GitHub couldn't start** is a failed run, at the attempt that ended, whose jobs that failed have no step and no annotation, or that has no failed job at all. A job whose condition or matrix GitHub couldn't evaluate has no step either, but an annotation that says why: that is a failure of the workflow, and a person must fix it. A run that ended as `startup_failure`, such as one of a workflow file that GitHub can't read, stays a failure that the bot-health bot reports at once. `blueprint/outage.py` holds the test, `never_started()`.
- **The bot-health bot** reports nothing and runs nothing again at the end of such a run, at any attempt, with a notice. Its daily look runs the latest run of a workflow again once, as a whole, when GitHub couldn't start it, among the four starts a day of the look; when GitHub couldn't start that second attempt either, the look reports it like any failure.
- **After the checks** runs no such run again: the flaky-test bot finds no job that failed in a step and ends with a notice, and the bot for failed releases asks for the jobs of the release first and leaves one alone that GitHub couldn't start, as the scheduled run of the release takes it up. Each of them, and the bot for stopped checks, still runs a run again only at its first attempt, and none of the workflows that *After the checks* follows is a bot that starts on the end of a run, which a test keeps so.
- **The branch bot** leaves its line as it is after a check that GitHub couldn't start: *Update branches* names the run and its attempt with `next-branch --after RUN --attempt N`.
- **Every call of GitHub's API** in `blueprint.py` tries again after a 5xx, the *Internal server error* of the outage too, and after a call without an answer, three more times, 10, 20 and 40 seconds apart, as the flaky-test bot of [decision 0133](0133-the-downloads-of-the-workflows-go-through-the-api.md) does, within the two minutes of waits of a run of 0036; a call that stalls ends after 90 seconds as one without an answer, and those 90 seconds count against the two minutes as a wait does, so a second stall ends it; and `gh pr list` and the queries of GraphQL try again as well. A POST still tries no second time after an error of GitHub, which may have done it. A rate limit still waits once.
- **A bot that GitHub keeps failing ends with a notice,** *GitHub is unavailable*, and passes: `bot-health`, `next-branch` and `coach report`, and the steps of the flaky-test bot, the bot for failed releases and the bot for stopped checks, whose function `tried` leaves a mark when it gives up on an error of GitHub, which their trap at the end turns into the notice. The branch bot makes an error of GitHub with one pull request a notice too. Its next event, schedule or daily look does what it couldn't. A refusal, such as a 403, still fails the bot, and a check, such as that of the signatures of a pull request, still fails when GitHub fails: it must not pass unseen.
- **Tests keep it so:** the three shapes of the runs of 9 November in the tests of the bot-health bot and of the steps of the flaky-test bot and of the bot for failed releases, the API's tries after a 500, a 503 and a call without an answer, and a bot's notice after GitHub kept failing.

## Consequences

An outage of GitHub no longer adds a failure, an issue or a run of its own to the runs that GitHub itself fails: a bot that GitHub starts in an outage passes, with a notice that says that a person has nothing to do. The runs that GitHub couldn't start at all still fail and mail, since a workflow can't keep GitHub from creating a run for its event, and no condition can tell that GitHub never ran the run it follows; they mail once each, not once more for every bot on top.

A required check of a pull request that GitHub couldn't start stays failed until the pull request's next push or someone runs it again, as the flaky-test bot no longer runs it again while GitHub fails; the PR coach shows it as failed. A bot that keeps failing for another reason still fails, opens its issue or warns, as before.

A call that GitHub fails now waits up to 70 seconds before the bot gives up, where it waited five; the budget of a run's waits stays at two minutes, so a bot in an outage still ends long before its time limit.

The jobs of *After the checks* that act on pull requests, the PR coach's own calls in bash, the fix bot, the bot of the title and the entry and the diagram bot, and the token of the release app that *Update branches* creates before its bot, don't wait out an outage yet; nor does the reusable *Findings* of the issue assistant. They follow in their own pull requests.
