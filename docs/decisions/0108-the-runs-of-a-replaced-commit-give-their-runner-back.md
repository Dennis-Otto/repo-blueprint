# The runs of a replaced commit give their runner back, in steps of jobs that run anyway

- Status: accepted
- Date: 2026-11-02

## Context

All the repositories of an owner share the runners of the account, 20 at once on GitHub Free. During the night of 1 November 2026, the queue reached an hour, and a script on a computer cancelled 20 to 140 runs an hour whose commit no pull request had as its head any more.

The concurrency of most checks already cancels the run for the same pull request. That leaves two gaps:

- **The quick checks,** such as *Pull request title*, *Secret scan* and *Dependency review*, keep one group for each commit, because GitHub doesn't always create the runs in the order of the commits and a late run for an older commit would cancel the run for the head.
- **A pull request that merges or closes:** no new run comes, so no group cancels anything.

We measured that day with the runs of all seven repositories, at least 30,898, as GitHub lists 1,000 for each period, and with five runs of each workflow for its jobs and minutes:

| What | Runs that day |
| --- | --- |
| Checks whose commit went while they waited or ran | 1,278 |
| Cancelled at once by a concurrency group | 731 |
| Ran on, and held a place for nothing | 547 |
| Of those, the quick checks | 420 |
| Of those, the tests, such as *Variants* with 16 jobs | 127 |

Cancelling a run isn't free either. Every run that ends starts *After the checks*, whose PR coach, and for a cancelled run also the bot for cancelled checks and the flaky-test bot, each take a runner for about 20 seconds, only to find that the commit is no longer the head. A bot that cancels 500 runs would start over a thousand such jobs, and pay for little.

And a bot of its own costs what it saves: a short job takes 15 to 18 seconds with Harden-Runner, and that day had 467 new commits on pull requests.

## Options

1. **The script on a computer:** it stops when the computer does, and helps only that owner.
2. **A concurrency group for each pull request for the quick checks too:** the race comes back, and a required check stays cancelled.
3. **A workflow of its own, on `pull_request_target` or `workflow_run`:** one more job for every push. On `pull_request_target`, a run that a newer one replaces in its group would also show as a cancelled check on an unrelated pull request.
4. **A step of the labeler's job, which runs on every push:** no runner, but `actions: write` would reach a third-party action.
5. **A step of `signed commits` for a new commit and the branch bot for a merge,** with no job of their own, and no job after the checks for a replaced commit.

## Decision

Option 5, as `blueprint.py stale-runs`, whose rules are in `blueprint/stale_runs.py`.

| Who looks | When | What it would have cancelled that day |
| --- | --- | --- |
| The branch bot alone | a merge, an update, a failed check | 162 of the 547 |
| *signed commits* alone | a new commit on a pull request | 496 of the 547 |
| Both | | 520 of the 547: about 740 jobs, 900 minutes of runners |

The jobs and the minutes are estimates, from the share of its time that each run had left when the bot would have looked.

- **In jobs that run anyway:** *signed commits* runs on every push, also from a fork, is no required check and has no third-party action besides Harden-Runner and the checkout. The step adds a few seconds to it, where a job of its own would have added 467 jobs that day.
- **Only checks:** the list of `workflows:` of `update-branches.yml`, which the blueprint renders for each kind of project. A workflow such as *Issue lifecycle* does something when a pull request closes, and the release runs on a push. The area labels are not in the list either, as they write labels.
- **Only a commit, never a branch:** two forks can have a branch of the same name, which the script mixed up. A commit that any open pull request has as its head stays.
- **Anything unclear leaves the run alone:** a list that GitHub refuses cancels nothing; a second list, for the commit, must agree right before the cancel; a run younger than 20 seconds and a second attempt stay. A run that stays costs a runner, and the next look takes it. A head that goes costs a required check, which only a person starts again, as the bot for cancelled checks takes it for the decision of a person.
- **It fails nothing:** what GitHub refuses is an annotation, in the job of a check and in the branch bot alike. It saves runners and is no check itself.
- **No job after the checks for a replaced commit:** the flaky-test bot, the bot for cancelled checks and the PR coach have a condition that needs no runner: `contains(github.event.workflow_run.pull_requests.*.head.sha, github.event.workflow_run.head_sha)`. GitHub names the open pull requests of the branch of a run from the repository there; a run from a fork names none, so its jobs ask GitHub, as before.

## Consequences

- The job *signed commits* and the branch bot may cancel the runs of their repository, with `actions: write` on the token of the job. The job runs nothing of the pull request.
- The bot waits in the same queue as every job, so on a full account it comes late. Whichever push reaches it first cleans the whole repository.
- Each repository cleans up after itself, and no token reaches another one.
- `python3 .github/blueprint.py stale-runs --dry-run` shows what the bot would cancel, without cancelling it.
- A commit that a person wants tested after a newer push: run it again, since the bot leaves a second attempt alone.
- **A way back:** take the step out of `pull-request-title.yml`, and the call out of `next_branch`. If GitHub stopped naming the pull requests in the event, the condition after the checks would hold back the jobs `rerun`, `cancelled` and `coach` for every pull request of the repository: a failed test on a head would get no second attempt, so the branch bot, which moves its line on for tests only from the second attempt, would wait for its schedule; a check of a head that a late run cancelled would stay cancelled; and the coach would say nothing. Then the condition goes first, out of all three jobs.
