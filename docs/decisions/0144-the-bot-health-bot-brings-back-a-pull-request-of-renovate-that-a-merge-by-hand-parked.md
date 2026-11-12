# The bot-health bot brings back a pull request of Renovate that a merge by hand parked

- Status: accepted, follows up [0104](0104-renovate-takes-the-commits-of-the-release-app-for-its-own.md) and [0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md)
- Date: 2026-11-12

## Context

Renovate rebuilds, rebases and merges its branch only while it takes every commit on it for its own or for that of an author that it ignores, such as the release app of the bots ([decision 0104](0104-renovate-takes-the-commits-of-the-release-app-for-its-own.md)). A merge of `main` with *Update branch* or `gh pr update-branch` is a commit of the person who starts it. After one, Renovate says in its comment *Edited/Blocked Notification* that it won't rebase the pull request, and leaves the branch alone for good, until a person ticks the box for a rebase in the description of the pull request.

On 9 November 2026 that parked the refresh of the lock files in [#744, #745 and #746](https://github.com/Dennis-Otto/repo-blueprint/issues/817): each carried two or three merges of `main` by a person, so Renovate built none of them anew under the rules of [decision 0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md), none had auto-merge, and the next Monday's refresh didn't replace them either. The indirect dependencies of nine stacks stood still, and nothing said so: the bot-health bot looked at the runs of `main` only, and the branch bot at the pull requests that wait for auto-merge.

## Options

1. **The branch bot,** which runs after every merge into `main`. It takes only the pull requests that wait for auto-merge into its line, and a parked pull request of Renovate has none.
2. **Report every parked pull request in an issue.** A person then ticks a box that a bot can tick as well, for each merge by hand.
3. **Tick the box of every parked pull request.** The new branch drops every commit that isn't Renovate's, also a fix that a person pushed onto an update, such as one that makes a new major version pass.
4. **The nightly look of the bot-health bot ticks the box where the new branch drops nothing that it doesn't make again, and reports the rest in one issue.**

## Decision

Option 4. Every night, the look takes each open pull request of Renovate of the repository itself, by its branch `renovate/…`, never one of a fork, and its commits:

- **Parked** is a pull request with a commit of a person, by an account that isn't Renovate's and isn't a bot, or by an address that GitHub links to no account, or with Renovate's own comment *Edited/Blocked Notification* after its last commit, for a bot that Renovate doesn't ignore. A comment before the last commit is left over from before Renovate built the branch anew, and a quote of it by someone else doesn't count.
- **The box is ticked** where every commit of a person is a merge, which has two parents: Renovate builds the branch anew from `main`, which has everything that the merges brought, and the bots commit their fixes onto it again. The look edits the description of the pull request with the `GITHUB_TOKEN` of its job, for which the job *sweep* of `bot-health.yml` now has `pull-requests: write`.
- **One issue,** *Renovate leaves pull requests alone*, with the labels `bot-failure`, `maintenance` and `dependencies`, lists a pull request with a change of a person, which a new branch would drop and which only that person can move elsewhere, one whose box has been ticked for a day without a new branch, as Renovate runs every two hours, and one without the box. It updates without a notification and closes once Renovate takes every one up again or they are closed.

## Consequences

- A merge of `main` by hand into a branch of Renovate parks it for a night at most, and a refresh of the lock files that a release before this one left parked, as #744, #745 and #746, gets back onto its automatic path by itself once the repository takes this release.
- The job *sweep* writes to pull requests. It changes only a box in the description of a pull request of Renovate, which asks Renovate for what it would do on its own without the merge.
- A fix that a person pushes onto a branch of Renovate keeps an issue open until it moves to a pull request of its own; the issue says so, and the troubleshooting guide says to leave a branch of Renovate to Renovate and the branch bot rather than *Update branch*.
