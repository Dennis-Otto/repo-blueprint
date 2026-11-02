# The fix bot leaves a commit to the run that ends last

- Status: accepted
- Date: 2026-11-02

## Context

The fix bot waits up to a quarter of an hour for the checks of a commit that keep fixes, so that one commit holds them all ([decision 0107](0107-the-fix-bot-reads-every-workflow-of-its-list.md)). A run that took longer was left out: the bot committed what it had. That went wrong in three ways, and most for a project with long end-to-end tests, or on a day when runs wait for a runner.

- **It threw away the run.** The commit cancelled the run after a quarter of an hour, and the checks began again. A fix of Lint and a fix of end-to-end tests of twenty minutes could run those tests three times, for what one commit does in two.
- **It used up the limit.** The bot commits at most twice in a row, so that commands that never agree stop. Two commits of a part of the fixes used up that limit, and a third with a real fix stopped the bot with an error, and left to a person what a command fixes.
- **It closed too early.** On `main`, a job with no fix in its hands closed the pull request of the fixes of `main` while a run that may need them still ran, and said that `main` needs them no more.

[#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429) names two ways out.

## Options

1. Let the job *rerun* skip a run that kept an artifact `fixes-*`. Such a run fails the same way again, so its second attempt only keeps a runner and the bot waiting. This starts no new job, but it removes only one cause: a run that is simply long, or that waits for a runner, still outlasts the wait, with all three problems.
2. Wait longer. Every fix would hold one of the about 20 runners of the account for as long as the longest run of the project, and no limit fits every project and every busy day.
3. After the wait, commit nothing, and leave the commit to the job after the run that ends last. This is one commit, cancels no run and uses up nothing. It has a trap: the job starts only after a run that failed, so a late run that passes would start nothing, and the fix of Lint would wait for the next push. So the job has to start however a run ends, which costs a job for each such run.

## Decision

Option 3, on a branch of the repository.

- **The rule:** `fix collect` says which workflows that it waited for still run after the wait, from the same look at the runs that decides which fixes it downloads. With any of them, `plan` of `blueprint/fixes.py` commits nothing onto a branch and names them in the summary of the job.
- **The job starts however a check ends:** after a run of a check for the head of a pull request from a branch of this repository that passed, was cancelled or ended in any other way, as well as after one that failed. The condition of the job can't know which workflows keep fixes, as a project adds its own, so it leaves out those that never do on a pull request: the same scanners as the flaky-test bot, and Docs. A test keeps that list free of every workflow that the bot waits for, in each kind of project. A commit that a newer push replaced starts no such job, as [decision 0108](0108-the-runs-of-a-replaced-commit-give-their-runner-back.md) wants, and a job of a commit with no fix ends at once, as before.
- **A suggestion on a fork doesn't wait,** because it starts no checks and comes once. A run from a fork that passes starts no job, so nothing would come after it.
- **The pull request of `main` doesn't wait either.** It cancels no run of `main`, the next job brings it up to date with what its run found, and a weekly run that passes starts no job, which [decision 0105](0105-the-fixers-run-on-main-every-week.md) keeps for a quiet week. It only stays open while a run still goes, instead of closing on half of the answer.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-run-that-ends-last-commits.dark.svg">
  <img src="../images/diagrams/the-run-that-ends-last-commits.svg" alt="The run that ends last commits: A check of a commit fails and keeps a fix. The job of the fix bot waits for the other checks of the commit that keep fixes, up to a quarter of an hour. When they have all ended, it makes one commit with every fix. When one still runs, it depends on where the fixes go. A suggestion on a fork and the pull request of main cancel no run, so they take what has ended. On a branch of the repository, the bot commits nothing, as a commit would cancel the run that still goes. The end of that run starts the job again, however it ended, and that job looks again. Once a job has made the commit, any other job of that commit finds a new head and commits nothing.">
</picture>

### Why no fix gets lost

A fix stays in its artifact until a job takes it, and a job that commits nothing changes nothing. So it is enough that a job reads every awaited run as ended, while the commit is still the head:

1. Among the runs of a commit that the bot waits for, one ends last. Its end starts a job, whatever its conclusion, as the job leaves out only workflows that keep nothing.
2. That job starts after that end, so it reads every one of these runs as ended, and takes the fixes of all that failed.
3. GitHub keeps one pending job of a branch and cancels the one before it. The one that stays started after a later end, and sees at least as much.
4. A run that starts again, by the flaky-test bot or the bot for cancelled checks, counts as running until its new attempt ends, which starts a job in turn.

The commit may stop being the head in the meantime. Then the checks of the new head find the same fixes.

### Why none is committed twice

The jobs of a branch run one at a time. `plan` commits only for the head of an open pull request, and the commit names that head in `expectedHeadOid`, so GitHub takes one commit onto it at most. After that, every other job of the same commit finds a new head and does nothing. On the new head, `changeable` drops a fix that the commit has already.

`test_the_job_after_the_run_that_ends_last_commits_every_fix_once` of `tests/test_fixes.py` plays this through in the fake GitHub: for a run that fails, passes, is cancelled or runs out of time, the job after Lint commits nothing, the job after that run makes one commit with every fix, and a further job makes none.

## Consequences

A fix of Lint now comes in one commit with the fix of a run of twenty minutes, and no run is cancelled to make it. A pull request waits that much longer for its first commit of the bot, and the PR coach still names the command in the meantime, for a person in a hurry.

A run of a check of a pull request of this repository starts one more short job, also when it passes, which is three for a project with Lint, its CI and Docker E2E, and each ends after a few calls of the API. That is the price of never losing a fix, in a workflow whose PR coach already starts a job for each of these runs.

The wait stays, so the usual case runs as before: the job that waits sees the end of the last run and commits, and the job of that run then finds a new head. With a job after every run, the wait itself could go and give its runner back; it remains for now as a second chance when GitHub starts no job after a run. A run that kept a fix still runs its failed jobs once more, as option 1 would have stopped; that costs a runner, not a fix.

When the event of a run names no pull request of its branch, the job doesn't start after a run that passed. The bot then commits nothing, as with any doubt: the check stays red with its explanation, and the next push makes the fix again. A workflow that keeps its artifact by a composite action isn't waited for, as [decision 0107](0107-the-fix-bot-reads-every-workflow-of-its-list.md) says, and still costs one more commit.
