# The fixers run on main every week

- Status: accepted
- Date: 2026-11-02

## Context

The fix bot ([decision 0023](0023-pull-requests-fix-themselves.md)) fixes what a command can fix when a check fails: on the head of a pull request, or on `main` after a push. What no commit changes never reaches it. A new rule of HACS, or of a tool that no lock file pins, such as one that the runner brings, then waits on `main`, and it fails the next pull request of a person, who has nothing to do with it. On a repository where little happens, that can be months later.

Lint runs only in pull requests, because a pull request reaches `main` only when it passes, so `main` had no run of it at all. A week of `main` that needs nothing should cost next to nothing. [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429) tracks this as one of the fixers that needed a design of their own.

## Options

1. A new workflow *Self-heal* that only runs the commands of `autofix`. It needs the tools of each kind of project, a copy of what each `ci-*.yml` sets up, and with no finding to start from it would commit what no check asked for.
2. The CI alone, on a schedule. Lint, whose fix is markdownlint's, would stay blind.
3. A schedule on Lint and on the CI of each kind, which keep their fixes as on a push, and which the fix bot takes as it does those of a push.

## Decision

Option 3. Each week the checks themselves run on `main`, and only a check that fails runs its fixers, as everywhere else, so the bot never commits what no check found.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-fixers-run-on-main-every-week.dark.svg">
  <img src="../images/diagrams/the-fixers-run-on-main-every-week.svg" alt="The fixers run on main every week: Each week, Lint and the CI run on main by their schedule, or by hand where bot health starts a schedule that GitHub missed. When every check passes, the week was quiet, with no job of the fix bot, no pull request and no issue. When a check fails and a command fixes what it found, the fix bot keeps one pull request from bot/self-heal, which merges itself, so that main is healed before the next pull request. When no command fixes it, bot health keeps one issue open until a run passes.">
</picture>

- **One time:** Lint and the CI of every kind share the time that the CI of Home Assistant already had, moved into the slot of each repository as every schedule is ([decision 0083](0083-every-repository-runs-its-schedules-at-times-of-its-own.md)), so that one commit of the bot holds what both fix.
- **By hand counts as well:** bot health starts a schedule that GitHub missed by hand, so `workflow_dispatch` on the default branch does what `schedule` does, and the bot reads the runs of a commit of `main` of every event: a check that its schedule ran and one that bot health started end in one pull request, and the newest run of a check decides. A run by hand on another branch fixes nothing, and doesn't count among the runs of `main` at its commit.
- **A quiet week:** a weekly run that passes starts no job of the fix bot, whereas a push always does, because only a push can leave a pull request of the fixes behind. So a quiet week takes one run of Lint, about a minute, and one of the CI, a few minutes, and writes nothing anywhere. The job `diagrams` of Lint stays out of the weekly run, with its large image, since the Diagrams workflow looks after the pictures of `main`.
- **One pull request, one commit:** each check that fails starts the bot, and the later run finds what the first one made. `fix main` leaves a pull request alone that already is the one commit these fixes make of this commit of `main`: a new commit would only start its checks again, and those of a stuck one anew each week.
- **Bot health:** the nightly look opens one issue for a weekly run that failed at the head of `main`, as for any other workflow; the schedule runs a few hours after the look, which gives the pull request of the bot most of a day to merge first. But Lint doesn't run after the merge that fixes it, and its red run would stay the latest for a week. A failure at the head gets its second try from the nightly look, because nothing else starts one for Lint, so a failed pull of an image doesn't stay for a week and a real finding is reported the next night. And a failure of Lint at a commit that `main` has left says nothing any more, because a pull request reached `main` only by passing Lint. The nightly look opens no issue for it, and when one is open, it starts Lint by hand, so that a run that passes closes it. Only Lint counts: the CI runs after a push anyway, and a check that needn't pass in a pull request proves nothing by a merge.

## Consequences

Drift repairs itself within a week and through the pull request that `main` already had for its fixes, with the same limits: only text files that the commit has, outside the workflows, and at most two commits of the bot in a row. A flaky test can't open a pull request, because the flaky-test bot runs the job again and the newest run decides. A fix that the commands can't finish fails in the checks of its pull request, which stays open, and bot health says that the check still fails.

A repository in a busy week runs its CI once more than it needs to, since the runs of its pushes told the same. To skip that run, the job would have to ask GitHub first, which costs as much as it saves in most repositories, so it stays simple.

The way back is one line in each workflow: take out the schedule, and everything else stands idle.
