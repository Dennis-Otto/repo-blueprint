# The bots after the checks start the branch bot when a check failed for good

- Status: accepted
- Date: 2026-11-13

## Context

A required check of a pull request that fails for good moves the line of the branch bot on to the next pull request ([0099](0099-the-branch-bot-takes-forks-into-its-line-and-approves-only-its-own-heads.md)). `.github/workflows/update-branches.yml` started for it on `workflow_run`, at the end of each of the 16 workflows of the checks, and decided only in the `if` of its job whether a run had work, after GitHub had created the run. The bots after the checks start on the same list. And Bot health watches Update branches, so that each of its runs started a run of Bot health as well, which skipped too when the run of Update branches had skipped.

The 800 latest runs of the blueprint spanned only 33 hours, from 2026-11-10 to 2026-11-11, and 507 of them came from those three workflows, 341 of them without a job that ran: 117 of the 124 runs of Update branches skipped, and 179 of the 260 runs of Bot health ([issue 819](https://github.com/Dennis-Otto/repo-blueprint/issues/819)). A skipped run costs no minutes, but the list of the runs and every listing of the API was mostly noise: a failed run of a check was hard to find, and the dashboard, the weekly report and the nightly look of Bot health paged through three times as many runs.

## Options

1. Keep `workflow_run` and take Update branches out of the list of Bot health, which leaves its failures to the nightly look: half of the runs that skip stay.
2. A filter `branches:` under `workflow_run` of Update branches: a run that `workflow_run` started counts as one of the default branch, and a run of a pull request has its own branch, so the filter can't keep the failures of pull requests and drop the rest.
3. Take `workflow_run` out of Update branches, and let the bots after the checks, which run after each of these ends anyway, start it with `workflow_dispatch` when a check failed for good.

## Decision

Option 3. A job `branches` of `.github/workflows/after-checks.yml` has the condition that the job of Update branches had for the event `workflow_run`: a run of a pull request, from a branch of the repository or, on `pull_request`, from a fork, that failed, ran out of time or that GitHub couldn't start, at its second attempt for the tests, which the flaky-test bot runs once more, and at once for the other checks. It starts `update-branches.yml` with the token of the job, which may start a workflow by `workflow_dispatch`, and passes the run and its attempt as the inputs `after` and `attempt`, so that the bot first asks whether GitHub started that run, as [0136](0136-an-outage-of-github-starts-no-bot-failure.md) wants. The job holds the one right `actions: write` and blocks every host but GitHub's API. The bot that cancels the runs of a replaced commit reads the workflows of the checks from the list of the bots after the checks now, without the release ([0108](0108-the-runs-of-a-replaced-commit-give-their-runner-back.md)).

Bot health keeps watching Update branches: every run of it now has work, after a merge, a change of auto-merge, a check that failed for good, the schedule or a person. The filter `branches:` that the issue proposes for the workflows that Bot health watches on the default branch alone can't come in the same workflow: the bots of events that it watches, such as Area labels and Welcome, run on `pull_request_target` with the branch of the pull request, and the job `stopped` still needs those runs ([0141](0141-the-bot-health-bot-runs-every-bot-again-that-harden-runner-stopped.md)), while one `workflow_run` has one filter for all of its workflows.

## Consequences

- A check of a pull request that ends adds no run of Update branches and no run of Bot health behind it to the list of the runs, only a job of the bots after the checks when it failed for good. In the window of the issue, about 120 runs of Update branches and as many of Bot health less.
- The bot moves its line on a few seconds later, after the job that starts it.
- A person can start the bot by hand as before, also with the run of a check that failed, in the inputs of the dispatch.
- Every repository made from the blueprint gets the change with its next update, as both workflows are files of the blueprint.
