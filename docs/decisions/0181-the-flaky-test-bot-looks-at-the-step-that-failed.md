# The flaky-test bot looks at the step that failed, not only at the workflow

- Status: accepted, amends [0014](0014-recover-from-a-stalled-check-without-a-person.md)
- Date: 2026-11-18

## Context

When a run of the tests fails for the first time, the flaky-test bot in *After the checks* runs its failed jobs once more ([0014](0014-recover-from-a-stalled-check-without-a-person.md)): what can pass without a change, and only that. It decided by the workflow alone, and so it ran a job again that failed in a step of `scripts/check.sh` that can't pass without a change, such as *Files of the project*, *Text files* or *Psalm*. From 10 to 17 November 2026, in the blueprint and the repositories that follow it ([issue 1005](https://github.com/Dennis-Otto/repo-blueprint/issues/1005)):

- 27 runs were second tries of the flaky-test bot that failed again, each in the same step as at first, apart from one job that Harden-Runner had stopped the first time.
- 11 of them failed in a step that has nothing random in it: *Files of the project* 6 times, all on `blueprint/update`, *Psalm* 4 times and *Text files* once. Each kept a runner busy for 1 to 7 minutes more, started one more run of *After the checks*, and held back the branch bot, which moved its line on only after the second attempt ([0151](0151-the-bots-after-the-checks-start-the-branch-bot-when-a-check-failed-for-good.md)): up to 34 minutes later. On `blueprint/update`, the fix bot commits the fix of *Files of the project* within minutes, so the second try of the old commit can't help either.
- The other 16 failed in tests, the demo, the visual check, the end-to-end tests, a check of a project of its own or outside `scripts/check.sh`. They need their second try.

`scripts/check.sh` writes the step that stopped it as the title of the annotation of the PR coach, `PR coach: <step> (scripts/check.sh)`, which the API of the check runs gives for every job.

## Options

1. **A list of steps in the workflow:** a second list beside the explanations, which no check keeps in step with `scripts/check.sh`.
2. **Every leg of a matrix failed in the same step, so it is real:** turns the bot off for a workflow of one job, such as *CI (php)*, and refuses the second try that an outage of a registry needs, which fails every leg in the same step.
3. **A field of each step in the catalog of the PR coach,** which the step *Explanations of the checks* already holds to `scripts/check.sh`.

## Decision

Option 3.

- **`rerun`:** each `[step."NAME"]` of `.github/checks.toml` says whether it can pass when it runs again without a change: `true` for one that downloads, starts a browser or runs tests, such as *Composer* (Packagist, curl error 28), *Lock files match their sources*, which compiles the lock files with uv, *Markdown*, *Website* or every step of the tests; `false` for one that only reads the files of the commit, such as *Text files*, *Files of the project*, *Ruff*, *Mypy*, *Psalm*, *Lock files* or *Changelog fragments*. A step that several kinds of projects share takes `true` when one of them downloads, as *Package* does for a Nextcloud app.
- **The blueprint's steps must say it:** `blueprint.py coach verify`, and so the step *Explanations of the checks*, fails for a step of `.github/checks.toml` without `rerun`, so a new step can't slip past the bot. A step of `.github/checks.project.toml` may leave it out, and then runs again: no repository fails its checks after the update, and its explanation, which wins over the blueprint's, decides for its step.
- **From the default branch:** the job checks out `.github` and `blueprint` of the default branch, never the code of the run, and `blueprint.py coach final-steps` names the steps with `false`. When the checkout or the catalog fails, every failed job runs once more, as before.
- **Every failed job in such a step:** the bot leaves the run alone only when each job that broke failed in a step with `false`, by the title of its annotation. As soon as one failed in a test, a download, a step without such an annotation, ran out of time or was stopped by Harden-Runner ([0134](0134-a-job-stops-when-harden-runner-doesnt-block.md), [0141](0141-the-bot-health-bot-runs-every-bot-again-that-harden-runner-stopped.md)), every failed job runs once more. The summary of the job names each job and its step.
- **The line moves on at once:** a failure that the bot doesn't run again, by its step or because the same jobs broke for the commit before, failed for good: for a pull request, the bot starts the branch bot with the run, as the job *branches* does after a second attempt, which never comes now. Not for a check of a fork that runs on `pull_request_target`, which the job *branches* leaves out as well.

## Consequences

A test run that failed in a step that can't pass without a change ends at once: no runner, no run of *After the checks* and no wait of the branch bot for a second try that would fail the same way; about 11 runs a week like that one. A flaky test, an outage of a registry, a job that ran out of time and one that Harden-Runner stopped still get their second try, and a flaky test still lands in the issue of flaky tests. The job of the bot checks out the default branch, which takes a few seconds and the host `github.com`. A step whose `rerun` is wrong in the blueprint either runs again in vain, as before, or keeps a failure that a second try would have fixed; a person runs that job again under **Actions**, and the field changes in the blueprint.
