# The refresh of Composer merges by itself, with versions of any age

- Status: accepted
- Date: 2026-11-17

## Context

The weekly refresh of the lock files of npm and pip-compile merges by itself, because the blueprint keeps it to versions at least a week old and checks their age ([0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md), [0172](0172-a-young-version-of-main-stays-in-the-refresh-and-a-refresh-that-takes-one-back-holds.md)). The refresh of Composer still waited for the maintainer, on the branch `renovate/review-lock-file-maintenance`, as [0012](0012-lock-refresh-waits-for-the-maintainer.md) had let every refresh wait.

For Composer the week can't be kept and can't be checked. Composer has no cooldown, and the `time` of a version in `composer.lock` comes from the package itself, so whoever publishes a version sets it. The blueprint knows no date of Packagist beside it that the publisher couldn't choose. So the review that the refresh waited for had nothing to go by that the checks don't have already, and every week the refresh waited in each repository with PHP: on 2026-11-17 three of them, repo-blueprint#983, paperless-unified-search#475 and paperless-sync#517, the first two with every check green since the day before ([issue 1023](https://github.com/Dennis-Otto/repo-blueprint/issues/1023)).

The owner of the blueprint decided on 2026-11-17 that the refresh of Composer merges by itself as well, once every check passes, as every other dependency update does, whose safety comes from the checks, not from a review ([0150](0150-a-major-update-merges-by-itself-once-every-check-passes.md)).

## Options

1. Keep the wait: the maintainer reviews a diff of versions whose age nobody can tell.
2. Let the refresh of Composer merge by itself once every check passes, with versions of any age, and say so wherever the week is promised.
3. Date the versions of Composer by something else, such as the tag of the repository of each package or the first time that Packagist served the version. The publisher sets the tag too, and the blueprint knows no such date that Packagist offers and the publisher can't influence, so it would pretend that the week holds.

## Decision

Option 2.

- **The rules of Renovate:** a rule for the refresh of the manager `composer` sets `automerge: true` and `additionalBranchPrefix: "composer-"`, after the rule of npm and pip-compile, in `.github/renovate-blueprint.json5` and its template, also for a repository with the Mend Renovate app, as Composer needs no command of the blueprint. Its `minimumReleaseAge` stays `null`, so that no setting pretends a week. Renovate builds the refresh anew only in its window on Mondays (`updateNotScheduled: false`), so that what merges is what the checks saw, and the branch bot keeps it up to date with `main` afterwards.
- **A branch of its own:** the refresh of Composer goes to `renovate/composer-lock-file-maintenance`, not to `renovate/lock-file-maintenance` of npm. Renovate gives a branch the settings of its first update (`generateBranchConfig` in `lib/workers/repository/updates/generate.ts`), and npm gets `--before=` from the `minimumReleaseAge` of that branch, so a refresh of Composer as the first update of a shared branch could take the week of npm away.
- **The check:** the step *Check the age of what the refresh of the lock files brings* of dependency-review runs on that branch too. It reads each version that the refresh adds to a `composer.lock`, names it as a version that nothing dates, in its log and in the summary of the check, and lets it pass; a `composer.lock` whose versions it can't read holds the refresh. It still dates only the versions of PyPI and of npm, and still fails on one of those that is younger than a week, that it can't date, or that takes back a version of `main`.
- **Every other package manager** keeps waiting for the maintainer on its branch `renovate/review-…`, as before.

**The accepted risk:** a version of an indirect dependency of Composer can reach `main` without the week that every other update waits, also one that was published minutes before the refresh, perhaps from a hijacked account, because nothing that its publisher can't set tells how old it is. Only the other checks stand in its way, such as the dependency review of GitHub, OSV-Scanner, Psalm and the tests. The owner accepted that price on 2026-11-17 for every repository that follows the blueprint.

The fix of a vulnerability still comes at once, in a pull request of its own. A refresh whose checks fail stays open and shows the failure ([0150](0150-a-major-update-merges-by-itself-once-every-check-passes.md)).

## Consequences

A repository with a `composer.lock` gets its refresh merged by itself every week, with no review. A refresh of Composer that waits under the old name, on `renovate/review-lock-file-maintenance`, merges once every check passes if its auto-merge is on; otherwise the next run of Renovate after the update finds no update for that branch, closes its pull request with the title ending in `- autoclosed` and deletes the branch, as it does with every branch that no update needs any more, and builds the refresh anew on `renovate/composer-lock-file-maintenance` in its next window on Mondays. Renovate leaves a branch alone that someone else edited, with the title ending in `- abandoned`; the commits of the release app, such as those of the branch bot, count as its own. This replaces what [0012](0012-lock-refresh-waits-for-the-maintainer.md) and [0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md) say about Composer, and amends [0150](0150-a-major-update-merges-by-itself-once-every-check-passes.md), whose one exception is now the refresh of a package manager that the rules don't name.
