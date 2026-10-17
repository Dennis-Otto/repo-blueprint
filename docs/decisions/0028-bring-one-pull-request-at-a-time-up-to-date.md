# Bring one pull request at a time up to date, in the order of its auto-merge

- Status: accepted
- Date: 2026-10-17

## Context

The rules of `main` take a pull request only when it is up to date with `main` (strict required checks), and auto-merge doesn't update a branch by itself. The branch bot, `update-branches.yml`, brought every pull request that waited for auto-merge up to date after each push to `main`:

- **Quadratic checks.** Only one of n waiting pull requests can merge next, and its merge leaves the others behind again, so every other run of their checks was thrown away: about n²/2 runs of every check for n pull requests. A run is about 36 jobs in the blueprint and 20 minutes of end-to-end tests in ha-autodarts, and the account runs about 20 jobs at once. In paperless-sync, four waiting pull requests on 2026-10-08 had critical paths of 1364 to 2539 seconds, mostly waiting for runners.
- **Late.** The workflow started on a push to `main`, by hand and every half hour. GitHub ran the schedule as it could: 22 runs from 2026-10-07 instead of about 240, and 18 of 197 in paperless-sync. A pull request whose auto-merge was turned on while it was behind waited for the next merge or a rare scheduled run, 5.4 hours on average in paperless-sync.
- **One error stopped all.** The loop ran under `bash -e`, so a failed request for one pull request stopped the updates of all after it, and a failed `gh pr update-branch`, for whatever reason, was reported as a merge conflict, with the label and the comment, also for a pull request that had none.

## Options

1. Keep updating every waiting pull request, and only start the bot sooner. The checks stay quadratic.
2. A merge queue of GitHub. It isn't available for repositories of a personal account.
3. A line, as Kodiak and Bulldozer keep it: the pull requests that wait for auto-merge in the order in which it was turned on, of which only the first one that can merge is brought up to date; the bot starts again when that one merges, when its required check fails, and when auto-merge is turned on or off.

## Decision

Option 3, with the logic in `blueprint.py next-branch` (`blueprint/branches.py`), which every repository gets as `.github/blueprint.py`.

- **The line.** The open pull requests into the default branch that wait for auto-merge, from this repository and not from the release bot, sorted by the time at which their auto-merge was turned on. A required check is one that the rules of the branch require; without such rules every check counts. Of the runs of a check, the latest decides, so a run that an edit started again replaces the cancelled one.
- **In flight.** When one of them is up to date and a required check of it runs, none of which failed, or none of its checks has started yet, as right after the bot updated it, the bot updates nothing: that one merges next, and its merge starts the next run.
- **Otherwise the next one.** The bot skips each pull request whose required check failed, which waits for a fix, and each one that is up to date and whose checks ended, which something else holds up, such as a conversation to resolve, and merges `main` into the first other one that is behind, with `expected_head_sha` so that a push since the list isn't merged over.
- **Conflicts.** A pull request that GitHub lists as conflicting gets the label `merge-conflict` and one comment, as before, and the line moves on; Renovate builds such a branch of its own anew. The label goes once GitHub lists it as mergeable. When an update of one whose state GitHub didn't know yet fails and GitHub then finds the conflict, it is a conflict as well.
- **Errors.** Any other request that GitHub refuses is a warning about that pull request and never a conflict, and the bot goes on with the next one; the run then fails, so that the bot-health bot keeps an issue open about it.
- **Events.** A push to `main`; `pull_request_target` with `auto_merge_enabled` and `auto_merge_disabled`; `workflow_run` of the workflows of the checks, which the job acts on only for a failure of a pull request of this repository; the schedule as a safety net; and a start by hand. The job checks out only the default branch, without the token, and runs nothing of a pull request, so zizmor's `dangerous-triggers` accepts it in `.github/zizmor.yml`. Its group of concurrency is on the job, so that a run whose job skips, as after checks that passed, cancels no run that updates.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-line-of-the-branch-bot.dark.svg">
  <img src="../images/diagrams/the-line-of-the-branch-bot.svg" alt="The line of the branch bot: A merge into main, auto-merge turned on or off, or a required check of a pull request that fails starts the branch bot. It takes the pull requests that wait for auto-merge in the order in which it was turned on. One that conflicts with main gets the label merge-conflict and one comment. While the checks of one that is up to date run, the others wait in line. Otherwise one whose required check failed waits for a fix, and the bot brings the first other one that is behind up to date, as the release app. Its checks run, and once they pass it merges, which starts the bot again for the next one.">
</picture>

## Consequences

With n waiting pull requests, the checks run about n times instead of about n²/2 times, and they still merge one after the other without a person. Each pull request had to run its checks again after the merge before it anyway, so the line delays a merge only when the pull request before it fails, by one run of the checks; with fewer jobs at once, every job gets its runner sooner. Turning auto-merge on brings a pull request that is first in the line up to date within about a minute.

A pull request that the line skipped for a failed check takes its place again in the next run of the bot after its fix; a run that only passing checks would start isn't worth a runner after every check of every pull request, so until the next merge, auto-merge turned on or a failed check, the schedule is what starts it. The same holds for a pull request at the front whose checks passed but that something else holds up. Every failed check of a pull request of the repository starts a short run of the bot, and each run of the bot one of the bot-health bot. The tests in `tests/test_branches.py` simulate GitHub for the line, the conflicts and the errors, and `tests/test_template.py` keeps the events, the group on the job, the checkout of the default branch and the list of the workflows of the checks equal to that of the bots after the checks, in every kind of project.
