# The release pull request is rebuilt once before it merges

- Status: accepted
- Date: 2026-11-17
- Amends [0003](0003-curated-changelog.md) and [0033](0033-schedules-are-only-a-safety-net.md)

## Context

After every merge into `main`, the release bot rebuilt the open release pull request on the current `main`, also when the merge was a `docs`, `chore`, `ci` or `test` change ([issue 1001](https://github.com/Dennis-Otto/repo-blueprint/issues/1001)). Such a change appears in no release notes and changes no version, so the rebuilt pull request released the same thing as before. Yet each rebuild pushed two new heads, the commit of release-please and the bot's commit *chore: write the changelog of …*, and each head ran every required check again, with After the checks and Bot health behind them. release-please rebuilds its pull request by itself only when the description that it builds changes ([0060](0060-release-please-reads-the-title-of-each-merged-pull-request.md)); the step *Have the release pull request rebuilt on the current main* wrote a marker into the description of every release pull request that was behind `main`, in every run.

In the week from 2026-11-10 to 2026-11-17, in the blueprint and the repositories that follow it, 46 such merges landed while a release pull request was open. Of the 25 release pull requests that merged, only 13 would have needed a rebuild at the moment they were about to merge: about 33 rebuilds, with about 750 runs on release pull requests and about 850 runs of the bots behind them, changed nothing that was released. Every update to a new release of the blueprint is a `chore` merge, and every new set of pictures a `docs` merge.

Decision 0003 said that the release bot rebuilds its pull request on every merge, and decision 0033 kept it so, against rebuilding only on the schedule, for two reasons: `main` takes only a pull request that is up to date, so a release pull request rebuilt only by the daily schedule couldn't merge for hours; and a release pull request updated by hand would release changes that its notes don't list.

## Options

1. Keep the rebuild after every merge.
2. Rebuild only in the daily run and by hand: the first reason of 0033 against it holds, a release pull request that is behind couldn't merge for hours.
3. Leave out release-please's update of its pull request on a push: the number of a beta would come from a stale version, the title would stay stale, and the release of a fix of a vulnerability ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)) would wait for the next day.
4. Push each rebuild once, with the token of the job, or with the label that leaves out the changelog: the settings forbid workflows to create pull requests, so the token of the job can't open the release pull request, and without the commit of the release app no check starts on it.
5. Rebuild the release pull request for a merge that changes nothing that it releases only when it is about to merge: when auto-merge is on for it, in the daily run and by hand, and have the branch bot start the release bot when auto-merge is turned on for it while it is behind.

## Decision

Option 5.

- **The marker is written** only when the release pull request is behind `main` and auto-merge is on for it, or when the run of Release is the daily one or one started by hand. release-please still runs on every push, so a merge that changes the notes, a `feat`, a `fix` or a `perf`, still rebuilds it at once, which also moves the version that the number of a beta comes from.
- **Turning auto-merge on rebuilds it within minutes.** The branch bot gets the event already, and starts the workflow of a bot that builds its own branch ([0118](0118-a-bot-whose-pull-request-conflicts-builds-it-anew-at-once.md)). For the release pull request, which takes no place in its line, it starts `release.yml` with the token of its job when the pull request is behind `main`, unless a run of Release that was created since auto-merge was turned on hasn't ended yet, as the one of a merge, which rebuilds it anyway. An older run may have passed the marker before auto-merge was on, so it doesn't count. The branch bot never updates the branch of the release pull request, and outside of a job it names the workflow to start.
- **A release of dependency updates still merges by itself** ([0087](0087-a-release-of-dependency-updates-merges-once-a-day.md)): the daily run writes the marker before release-please runs, and the push of a fix of a vulnerability changes the notes, so the run that turns auto-merge on for it has rebuilt it before; the event of that auto-merge finds it up to date.

What stays as it was:

- `main` takes a release pull request only when it is up to date and every required check has passed on that head.
- The changelog of the release pull request takes in the fragments and the text of Unreleased of `main` in every run, also while the pull request is behind.
- The summary of the branch bot shows a release pull request that is behind as one that waits for its rebuild, with the run that rebuilds it, and nothing reports it as stuck: the report of a pull request and the dashboard don't read whether a pull request is behind.
- A person who presses *Update branch* on the release pull request can only bring in changes that no notes list, since every change that notes list rebuilds it at once.
- Each rebuild is still two pushes, each with its own checks, as option 4 showed no way to make it one.

## Consequences

A release pull request is rebuilt once before it merges, instead of after every merge of a day; a merge of `docs`, `chore`, `ci` or `test` starts no check of it. A release pull request that is behind `main` when auto-merge is turned on merges one round of checks later, about 15 to 25 minutes. With the daily release of the blueprint ([issue 990](https://github.com/Dennis-Otto/repo-blueprint/issues/990)), its release pull request waits most of a day, and this rebuilds it once, before its merge. Turning auto-merge on for another pull request while the release pull request is behind with auto-merge on and its rebuild has just ended can start one more run of Release, which finds it up to date and pushes nothing.
