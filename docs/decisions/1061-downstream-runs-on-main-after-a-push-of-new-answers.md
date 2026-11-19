# Downstream runs on main after a push of new answers

- Status: accepted
- Date: 2026-11-19
- Amends [0039](0039-try-every-change-on-the-repositories-that-take-the-blueprint.md)

## Context

The Downstream workflow runs "in the pull requests that change what the repositories get from the blueprint, and every week" ([0039](0039-try-every-change-on-the-repositories-that-take-the-blueprint.md)). Its weekly run fails on purpose when the answers in `tests/answers/` differ from those of a repository, and keeps the new answers as `fixes-downstream`; the fix bot brings them to `main` in its pull request of the fixes of `main` ([0105](0105-the-fixers-run-on-main-every-week.md)). A fix of Downstream only ever changes `tests/answers/`, since that is all that `downstream.py --answers` writes.

On 2026-11-18 the weekly run failed on the answers of homedarts-for-autodarts and player-switch-for-autodarts. The fix bot opened #1054 with exactly these two files, and it merged ten minutes later. Its push started the CI and the other checks, but not Downstream, which had no `push` trigger, so the red run stayed the latest of `main`. The next morning the nightly look of the bot-health bot opened #1057 *Downstream fails on main*, 19 hours after the fix had reached `main`, for a failure that was already healed ([issue 1061](https://github.com/Dennis-Otto/repo-blueprint/issues/1061)). Without a start by hand, `main` would have kept the red run and the issue until the next weekly run.

Decision 0105 lets a failure at a commit that `main` has left go only for Lint: "Only Lint counts: the CI runs after a push anyway, and a check that needn't pass in a pull request proves nothing by a merge." Both halves hold for Downstream too: it is no required check, so the merge of #1054 proved nothing, and unlike the CI it didn't run after the push.

## Options

1. A `push` trigger on `main` for `tests/answers/**`. A run of a push already does what the weekly run does: it isn't `pull_request`, so it passes `--drift-fails`; when it fails on the default branch, it keeps `fixes-downstream`; and outside a pull request its concurrency group is the run's own, so no newer push cancels it. *After the checks* already lists Downstream: a push run that fails starts the rerun and the fix bot, one that passes starts neither.
2. A job of *After the checks* that starts the healed workflow by hand after the merge of the fix bot's pull request, in every kind of project. A run that the `GITHUB_TOKEN` starts ends without a `workflow_run`, so neither the fix bot nor the bot-health bot follows it, and the job would take a runner after the end of every push run on `main`. A lot of new code in every repository for a case that only the blueprint has.
3. The nightly look opens no issue when a merged pull request of `bot/self-heal` names the run. That trusts the fix without checking it: a run that failed on a conflict as well as on answers keeps `fixes-downstream` too, and the conflict would stay hidden until the next weekly run.
4. Downstream joins the `workflow_run` list of `bot-health.yml`. On 2026-11-18 its end would have opened the issue before the fix merged, and it would have stayed open just as long.

## Decision

Option 1. Downstream runs on a push to `main` that changes `tests/answers/`, besides its pull requests, its weekly run and a start by hand. The paths of its pull requests, its permissions (`contents: read`), its concurrency and the lists of *After the checks* and of the bot-health bot stay as they are, and `tests/test_template.py` pins the trigger. Downstream exists only in the blueprint, so nothing of this reaches the other repositories.

## Consequences

After the merge of the fix bot's pull request with new answers, Downstream runs on `main` for about two minutes. When the answers hold, `main` turns green, and the nightly look writes "passes" and opens no issue. When they don't, because a repository changed its answers again or a conflict failed the same run, the run of the push fails and is reported as a failure of `main` is today. There is no loop: a run that fails on answers that equal those of `main` makes `fix keep` keep no file, so no `fixes-downstream` and no new pull request follow. A push that changes nothing in `tests/answers/` runs no Downstream, so a quiet week takes no extra runner and the fix bot after the CI waits for no extra run. GitHub's own mail of the failed weekly run still comes, since that run fails on such answers on purpose.
