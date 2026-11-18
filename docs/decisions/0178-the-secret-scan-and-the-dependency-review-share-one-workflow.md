# The secret scan and the dependency review share one workflow, outside Lint

- Status: accepted, amended by [1046](1046-a-bot-notices-a-stale-entry-on-bestpractices-dev.md): the answers of `.bestpractices.json` link to the new file, and the entry on bestpractices.dev takes the new link only through the links of the weekly bot
- Date: 2026-11-17

## Context

*Secret scan* and *Dependency review* were two workflows of one job each, *gitleaks* and *dependency-review*, and both started on every push to a pull request, for the same commit as *Lint*. Each run that ends, also a cancelled one, starts a run of *After the checks*, whose ten jobs report ten check runs, most of them skipped. From 10 to 17 November 2026, in the blueprint and the seven repositories that follow it ([issue 1002](https://github.com/Dennis-Otto/repo-blueprint/issues/1002)):

| Workflow | Runs on `pull_request` | On a commit that Lint also checked | Failed |
| --- | --- | --- | --- |
| Secret scan | 584 | 584 | 0 |
| Dependency review | 585 | 585 | 7 |

*After the checks* ran 8,462 times that week, about 1,170 of them after a run of these two workflows. The two have the same trigger and the same concurrency: one group for each commit of a pull request, as the quick checks keep it ([0014](0014-recover-from-a-stalled-check-without-a-person.md), [0108](0108-the-runs-of-a-replaced-commit-give-their-runner-back.md)), so that a late run for an older commit can't cancel a required check of the head. The rulesets require the checks by the names of the jobs, not of the workflows. [0027](0027-few-jobs-that-each-run-several-checks.md) joined short checks into few jobs; it joined no workflows.

## Options

1. **Keep two workflows:** one run of a workflow and one run of *After the checks* more for every push.
2. **Move both jobs into Lint:** one run fewer still, but Lint keeps one group for each pull request and cancels the run before, which brings back the race of a late run for an older commit for two required checks.
3. **One workflow, *Quick checks*, with the two jobs as they are,** one group for each commit, and the jobs under their names.

## Decision

Option 3: `.github/workflows/quick-checks.yml`, in the blueprint and through the template in every repository.

- **The jobs keep their names,** *gitleaks* and *dependency-review*, so no ruleset changes, and a pull request opened before the update gets both checks from whichever workflow files its run takes.
- **The concurrency stays one group for each commit,** `quick-checks-<pull request>-<head>`.
- **The weekly scan of the whole history stays:** the schedule runs *gitleaks* only; *dependency-review* has nothing to compare there and skips.
- **Started by hand,** *gitleaks* scans the whole history, and *dependency-review* compares a base and a head commit when both are given and skips otherwise. The inputs are optional, because Bot health starts a schedule that GitHub missed by hand without inputs, and GitHub refuses a start without a required one; a test holds that no workflow with a schedule needs an input that Bot health leaves out.
- **The bots after the checks** follow the new name in every list of `after-checks.yml`: the trigger, the restart bots, the flaky-test report, the branch bot, the bot for checks that Harden-Runner stopped, the fix bot and the coach. The bot for replaced commits reads the same list. The PR coach still explains each job by its own name from `.github/checks.toml`.

## Consequences

Every push to a pull request starts one workflow run and one run of *After the checks* fewer, with its ten check runs: about 585 runs, 585 runs of *After the checks* and 5,850 check runs fewer in a week like that one. The number of jobs and the minutes of the runners stay the same. A failure of either job fails the one run, which starts the branch bot and the PR coach as before; the run of the other job goes on, as the jobs don't depend on each other. An update removes `secret-scan.yml` and `dependency-review.yml` from a repository and adds `quick-checks.yml`, as the Variants check for an update from the latest release; the answers of `.bestpractices.json` link to the new file.
