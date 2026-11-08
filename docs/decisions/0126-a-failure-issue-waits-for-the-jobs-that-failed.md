# A failure issue waits for the jobs that failed

- Status: accepted
- Date: 2026-11-08

## Context

The bot-health bot keeps one issue open while a bot fails on the default branch ([decision 0019](0019-a-failing-bot-keeps-one-issue-open.md)), and until now the next run of the workflow that passed closed it, whichever jobs ran in it. Several workflows plan first and then skip their jobs: every push to `main` starts a run of Screenshots in which only *plan the screenshots* runs, and the daily runs of Release and Docs pictures do much the same. Such a run passes without the job that failed. In player-switch-for-autodarts, *Screenshots fails on main* opened and closed six times in three days ([#64](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/64), [#87](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/87), [#88](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/88), [#90](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/90), [#102](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/102), [#105](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/105)). Each time a push that only planned closed it with *Passes again*, while the render stayed broken until [#115](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/115) fixed it. A green run that skipped the broken job hides a broken bot, which is what decision 0019 was made against.

## Options

1. **As before:** any run that passes closes the issue.
2. **The jobs that failed must pass again:** a run that passes closes the issue only when every job that failed in the run of the issue ran in it and passed.
3. **The failure is gone only when the run ran every job:** a run with a skipped job never closes an issue. A workflow that skips a job on purpose in every run, such as a job only for the blueprint itself, would then keep its issue open for good.
4. **Only a run of the same event as the failure** closes it, such as a schedule after a failed schedule. A push that renders the screenshots counts as much as a schedule that does, and a schedule can skip a job too.

## Decision

Option 2. When a run passes and its workflow has an open issue, the bot reads the jobs of the failed run that the state of the issue names, in the attempt that failed. It counts them as the issue lists them: those that failed or ran out of time, or those that GitHub cancelled when only they ended badly. It reads the latest try of each job of the passing run as well, and closes the issue only when each job that failed ran again and passed. A job of a matrix counts by its name before the values, such as `render` for `render (en, 3/4)`, and every leg of that name has to pass, so a matrix that gets other values or other shards still closes the issue. A job outside a matrix counts only by its own name, so a matrix whose name starts the same, such as `e2e (Home Assistant beta)` beside `e2e`, doesn't keep its issue open. A job that was skipped or is missing leaves the issue open. The end of the run then reports, for example, *passes, but without the job `render the screenshots` that failed in #105*, and the daily look shows the same in its summary. The daily look stands in for an end of a run that GitHub lost, which may be that of an earlier run than the latest: when the latest passed without such a job, it reads up to five earlier runs that passed after the failure and closes the issue with the first in which the jobs that failed passed again.

A run older than the failure still doesn't count. A failure that names no failed job, as a run that GitHub couldn't start, closes on the next run that passes, as before. The bot reads the jobs only when an issue is open, so a run that passes with no issue costs no request more.

## Consequences

An issue stays open until the broken job works again, no matter how many runs pass in the meantime without it. A job that someone removed or renamed keeps its issue open: the issue says so, and a person closes it by hand, which resets the state. A run that passes while an issue is open costs two requests more, one for the jobs of each run. The change is in `blueprint/bot_health.py`, which every repository gets with the next release of the blueprint.
