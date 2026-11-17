# Only a run that published a release starts its followers

- Status: accepted
- Date: 2026-11-17

## Context

Two bots followed the end of every run of the workflow *Release*: *Issue lifecycle*, which closes the issues that a release fixes with its link, and *Screenshots*, which renders the pictures of the new version. A release that the job *publish the release* makes public with the token of its job starts no workflow by `release: published`, so `workflow_run` was their way to hear of a release. Most runs of Release publish nothing, though: the push of every other merge and the daily run only keep the release pull request current ([issue 1000](https://github.com/Dennis-Otto/repo-blueprint/issues/1000)). In the week from 2026-11-10 to 2026-11-17, 263 of at least 288 runs of Release in the blueprint and the repositories that follow it published nothing, and behind them came about 297 runs of each bot, most with nothing to do, and about 590 runs of the bot-health bot, which watches both: about 1,100 runs a week that only followed a run of Release.

## Options

1. Keep `workflow_run`, and let each bot skip a run of Release that published nothing, as the screenshot bot's plan did: every run still starts a runner, or at least a run, and one of the bot-health bot after it.
2. Let Release start the bots itself, by `workflow_dispatch`, in a job at its end that runs only when the run published a release, the way After the checks starts Update branches only when it has work ([0151](0151-the-bots-after-the-checks-start-the-branch-bot-when-a-check-failed-for-good.md)), and drop `workflow_run` from the bots.

## Decision

Option 2. The job *start the bots after the release* of `release.yml` runs once the run published a release, also one that it finished from a draft that an earlier run left, and only once the whole run passed, the delivery, the verification and the Dependabot alerts included, as the end of a successful run did before. A workflow that the token of a job dispatches does start, so the job needs `actions: write`, `contents: read` and no secret, and reaches only GitHub's API.

- **Issue lifecycle** starts with `dry_run` false after every release that is no prerelease: the issue assistant closes a fixed issue only with a final release, so a beta or another prerelease starts no sweep.
- **Screenshots** starts after every release but a beta of the next one, which no picture shows, and not at all where the repository has no `scripts/screenshots.sh`, whose run would end after its first job; when GitHub can't say whether the script is there, the bot starts and decides itself. `screenshot-bot.yml` drops its `workflow_run`, and its plan serves the pushes to `main` and its week.
- **A call that GitHub fails** three times is a warning, not a failure: the release stays green, so no bot runs it again for that, and the morning sweep of Issue lifecycle and the weekly run of Screenshots stay the safety net.
- **Issue lifecycle keeps its `workflow_run`** for now: `issue-lifecycle.yml` is a template of the issue assistant, which its check compares exactly ([0024](0024-take-over-each-verified-release-of-the-issue-assistant.md)). Once a release of the issue assistant has a key of `config.toml` with which a repository leaves that trigger out (Dennis-Otto/issue-assistant#457), the blueprint sets it, and the issue assistant keeps the trigger for everyone else. Until then a release sweeps the issues twice, which does no harm, as the sweeps wait for each other in the group `issue-lifecycle` without cancelling.
- **After the checks keeps following Release,** whose jobs run a failed release once more, run its cancelled checks again and fix its branch, and the bot-health bot keeps watching it and giving a failed first attempt its second try; this record changes neither.

## Consequences

A run of Release that publishes nothing starts no screenshot bot and no run of the bot-health bot behind it, and, once the key of the issue assistant is set, no sweep of the issues either. A release starts both bots right after its verification, as before; one whose verification or another job failed starts them once a rerun of its failed jobs passes, which keeps what the job of release-please found. A rerun of the whole run finds no release left to make and starts neither bot: Issue lifecycle still follows that run by its `workflow_run`, and the weekly run of Screenshots renders the pictures of the release within a week. A repository without `scripts/screenshots.sh` no longer starts the screenshot bot after a release at all.
