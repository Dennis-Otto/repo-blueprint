# A push to main cancels the checks and scanners of the push before, and nothing that publishes

- Status: accepted
- Date: 2026-10-25

## Context

A push to a pull request cancels the runs of its push before, but a push to `main` didn't: the group of each check was the number of the pull request or, for every other event, the ID of the run, which is new for every run. When the next merge landed while the checks of the one before still ran, both sets ran to their end. Several merges in a row, such as those of the update pull requests of a rollout or of a release and the pull requests that waited for it, kept the runners busy with the state of commits that were already behind, while an account on the free plan runs about 20 jobs at once for all its repositories ([issue 242](https://github.com/Dennis-Otto/repo-blueprint/issues/242), from finding PS-CI-07 of paperless-sync).

The runs of `main` aren't only a check, though. Before any of them may cancel another, what reads them has to keep working:

- **The coverage of a pull request** in the report of the PR coach is compared with the newest run of the tests of `main` that passed (`--status success`), which a cancelled run never is: a cancelled run leaves the run before it as the base.
- **The fix bot of `main`** starts after a run of the tests or of Lint on `main` that passed or failed, never after one that was cancelled; the run of the newer commit starts it with the same files and more.
- **The flaky-test bot** leaves alone a run that a newer run cancelled ("higher priority waiting request"), and so does its issue of flaky tests. The bot-health bot looks only at runs that passed or failed.
- **The alerts of code scanning** of a pull request are compared with the analysis of its base on `main`. `main` requires every pull request to be up to date before it merges, so the base of a merge is always the newest commit of `main`, whose analysis a newer push can't cancel: only the newest push to `main` is left. An analysis of a commit that a newer one replaced only tells what the newer analysis tells as well.
- **A late run.** GitHub doesn't always create the runs in the order of the commits, so a late run for the commit before can cancel the run for the head of `main`. Then the head would have no coverage, no analysis and no fixes until the next push. The bot for cancelled checks repaired that race only for the head of a pull request.

## Options

1. Leave every run of `main` to its end, as before.
2. One group for all runs on `main` of each workflow that cancels the run in progress, schedules and runs by hand included.
3. Decide for each workflow that a push to `main` starts: the checks and the scanners cancel the run of the push before, as in a pull request; whatever publishes, commits or changes GitHub ends what it started; a run on a schedule or by hand keeps a group of its own. The bot for cancelled checks starts the run for the head of `main` again when a late run cancelled it.

## Decision

Option 3. Option 2 would let a push cancel the full run of a schedule, such as the weekly run of CodeQL or the nightly end-to-end tests of a project, and the release in the middle of its tag.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-a-newer-push-to-main-cancels.dark.svg">
  <img src="../images/diagrams/what-a-newer-push-to-main-cancels.svg" alt="What a newer push to main cancels: A merge pushes to main while the runs of the push before may still go. The tests, CodeQL and the scanners of the push before only tell what the run of the newer commit tells as well, so the newer push cancels them, as a newer push to a pull request does. When a late run for an older commit cancelled the run for the head of main instead, the bot for cancelled checks starts it again. The website, the release and the bots that commit or change GitHub end the run that they started, and only the newest run that waits comes next. No push cancels a run on a schedule or by hand.">
</picture>

| A push to `main` starts | A newer push | Why |
| --- | --- | --- |
| The CI of every kind of project, the Action test, CodeQL, Links, OSV-Scanner, Workflow security | cancels the run of the push before | Their runs of `main` only tell the state of `main`, which the run of the newer commit tells as well. |
| Docs, Release, Labels, Diagrams | waits: the run that started ends, and only the newest of those that wait runs next | They publish the website, make the release, change the labels or commit; a deployment or a tag stopped halfway helps nobody. |
| Settings, Dashboard, Newest Python | cancels the run in progress, as before | The newest run does all the work of an older one. |
| Findings, Renovate, OpenSSF Scorecard, Screenshots, Update branches | runs, as before | A push of a few files starts them, their jobs wait for each other on their own, or, for Scorecard, one short job publishes its results. |

- **The group:** `${{ github.workflow }}-${{ github.event.pull_request.number || (github.event_name == 'push' && github.ref) || github.run_id }}`, which cancels when the event is `pull_request` or `push`. A run on a schedule or by hand has the ID of its run as its group, as before, so that no push cancels it and it cancels no push.
- **The bot for cancelled checks** now also looks at a run of a push to `main` of this repository that was cancelled: when its commit is still the head of `main`, `git/ref/heads/main`, a late run for an older commit cancelled it, and no newer run of its workflow for the same commit exists, the bot starts it again, at most twice. A run whose commit a newer push replaced stays cancelled. For this the bot reads the head of `main`, with `contents: read`.
- **The tests:** `tests/test_template.py` names the side of every workflow that a push to `main` starts, in the blueprint and in every kind of project, and fails for a new one until it takes a side, and for a group that doesn't match its side. The step of the bot runs in a test for a push to `main` as it does for a pull request.

## Consequences

A merge that follows another frees the runners of the checks of the commit before within seconds, and the runs that matter, those of the newest commit and of the pull requests, start sooner. The run of a commit that a newer merge replaced shows as cancelled in the list of the runs of `main`, and its commit has no checks of its own; the newer commit has them all. A workflow of a project's own, such as Docker E2E, keeps its own group: the bot for cancelled checks starts its run for the head of `main` again too when a late run cancelled it, and a project gives it the group of this record when it wants the same.
