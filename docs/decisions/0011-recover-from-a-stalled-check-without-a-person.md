# Recover from a stalled check without a person, once

- Status: accepted
- Date: 2026-10-13

## Context

The checks of a pull request and the release of a merge stalled until somebody looked, although nothing was wrong with the change:

- **A job that runs out of time** ends *cancelled*, not *failed*, with the annotation "The job has exceeded the maximum execution time". The flaky-test bot ran only failed jobs again, and the bot for cancelled checks only runs that a newer run cancelled. A pull request of the blueprint waited 2.5 hours for a person, for one leg of Variants that hung once.
- **A release** that failed at a push of its tag, which GitHub refused for a moment, held v0.10.0 and its rollout for 35 minutes, until someone ran it again. The release workflow takes up a tag that it pushed already, so running it again is safe.
- **The quick checks** grouped their runs by pull request and cancelled the older one. The release bot edits the description of the release pull request after every merge while release-please pushes to it, and GitHub doesn't always create the runs in the order of the commits: a late run for the older commit cancelled the required checks of the head, 7 of 28 runs of the title check on 2026-10-12, and blocked the release pull request for 44 minutes. The bot for cancelled checks repairs such a race, but only after a while.
- **Real failures ran again:** a test that a change broke failed twice for every commit of its pull request, and each second run kept a runner busy for up to 20 minutes, while an account runs about 20 jobs at once.
- **The issue of flaky tests named only the job,** so that a download that failed for a moment read like a flaky test, and finding the test meant reading the log.

## Options

1. Leave it to people: they run again what stalled, and read the logs.
2. Run every failure again, a few times, until it passes.
3. Run again once what can pass without a change, and only that: a first attempt of the tests that failed or ran out of time, unless the same jobs broke for the commit before; a release that a merge started and that failed; and give the quick checks one group of runs for each commit, so that a race can't cancel them at all.

## Decision

Option 3.

- **Once:** the flaky-test bot runs the failed jobs of the first attempt of a test run once more, the jobs that ran out of time included, and the bot for failed releases does the same with a release that a merge started. A second failure stays red: the bot reports a flaky test only when its job passed the second time, and a failure twice in a row is one for a person. The bot for cancelled checks keeps its limit of two runs.
- **No run again of what failed before:** when the same jobs broke for the commit before on the same branch of the same repository, in the last attempt of its run, the failure comes from the change, and the jobs don't run again. A run for the commit before that a newer push cancelled, or that passed, doesn't count.
- **One group for each commit for the quick checks:** the title and the changelog, the dependency review, the secret scan, the area labels and the website take seconds to a minute or two. Their runs for different commits never cancel each other, and a newer run for the same commit, such as one of an edited title, still replaces the older. The checks that take minutes, the tests, Lint, CodeQL and Variants, still cancel the run for an older commit, because their runners are worth more than the race, which the bot for cancelled checks repairs.
- **A report that names the failure:** each job that failed at first comes with a link to its log, the step that broke, the tests that pytest names in the log, and the first error that the job reported. Names and lines of logs, which a pull request writes, stay plain code in the issue.

## Consequences

A pull request or a release that a moment of bad luck stopped goes on by itself within minutes, and the people who would have run it again see it only in the issue of flaky tests, if at all. A broken test costs one run per commit instead of two. An older commit of a pull request finishes its quick checks even after a newer push, a few runner-minutes in all; the release pull request no longer waits for the bot for cancelled checks. A new workflow of quick checks of a pull request groups its runs by commit, and a new workflow of tests joins the bots after the checks, in the blueprint by its name in `after-checks.yml`, in a repository with the answer `test_workflows`.
