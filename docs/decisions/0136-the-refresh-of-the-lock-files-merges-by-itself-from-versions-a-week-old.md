# The weekly refresh of the lock files merges by itself, from versions a week old

- Status: accepted
- Date: 2026-11-09

## Context

Since [0012](0012-lock-refresh-waits-for-the-maintainer.md), the weekly refresh of the lock files waits for the maintainer, because it brought the newest version of every indirect dependency, also one published minutes before, without the week that every other update of Renovate waits after its release. In practice nobody reviewed the refreshes: in every repository of the owner they piled up as open pull requests, such as `chore(deps): lock file maintenance` and `chore(deps): refresh pip-compile outputs` of homedarts, 18 hours old with every check green, and so the indirect dependencies didn't move at all. On 9 November 2026 the owner decided that the refresh merges by itself, but only from versions at least a week old, once every check passes ([#783](https://github.com/Dennis-Otto/repo-blueprint/issues/783)).

0012 rejected a cooldown of the package managers because Renovate sets their environment, such as `UV_EXCLUDE_NEWER`, for the whole repository and not for a rule, so that the fix of a vulnerability, which comes at once, would wait a week as well. That holds for `env`, but there are two other ways that reach the refresh alone:

- **npm:** Renovate 44 gives `npm install` the option `--before=` a week ago whenever the `minimumReleaseAge` of the branch is set, also in a refresh (`lib/modules/manager/npm/post-update/npm.ts`). A rule of the refresh sets it; the fix of a vulnerability keeps `minimumReleaseAge: null` of `vulnerabilityAlerts` and gets no `--before=`. When `package.json` asks for a version younger than the week, such as the fix of a vulnerability of the last days, npm can't keep to it, and Renovate tries again without `--before=` and says so in a warning.
- **pip-compile:** Renovate compiles a lock file again with the command in its header and passes it nothing of the age. A rule of the refresh can run a command after it (`postUpgradeTasks`), in the checkout of the branch, where `git diff HEAD` names the lock files that the refresh compiled anew.
- **Composer** has no cooldown, and the `time` of `composer.lock` comes from the package, which its author can set. No other package manager of the blueprint has a refresh.

Renovate's own check of the age doesn't fit the refresh: it has no release date, so with `minimumReleaseAge` set, the status `renovate/stability-days` would stay pending for ever.

## Options

1. Keep 0012: the refresh waits for a review that doesn't come.
2. Let the refresh merge by itself as it is, with the newest versions.
3. Keep the refresh to versions a week old where the package manager can, let it merge by itself there, and check the age of what it brings in a required check, so that a version that comes younger anyway holds it.
4. A cooldown for the whole repository, in `.npmrc` and `uv.toml`, which would hold back the fix of a vulnerability for a week.

## Decision

Option 3.

- **The rules of Renovate:** every refresh waits for the maintainer, as before, with `minimumReleaseAge: null`, `updateNotScheduled: false` and `additionalBranchPrefix: "review-"`, so that its branch, such as `renovate/review-lock-file-maintenance`, stays apart. The refresh of npm and pip-compile gets `minimumReleaseAge: "7 days"`, `statusCheckWhen: { minimumReleaseAge: "never" }`, so that Renovate's age check keeps no status that waits for ever, `automerge: true` and its usual branch: `renovate/lock-file-maintenance` for npm and `renovate/pip-compile-refresh` for pip-compile, or `renovate/lock-file-maintenance-` and the name of a group. Renovate still builds a refresh anew only in its window on Mondays, so that what merges is what the checks saw; the branch bot keeps it up to date with `main` afterwards, as it does with every pull request that waits for auto-merge.
- **pip-compile:** a rule of the refresh runs `python3 .github/blueprint.py locks --refresh` after Renovate (in the blueprint `python3 blueprint.py locks --refresh`), with Python and uv that Renovate installs for it. It compiles each lock file that the refresh changed again with uv, onto a copy of the refresh, from uploads before `--exclude-newer=`, a week before the start of the day in UTC, so that the runs of one day agree. A package that the refresh pins as `main` does keeps its pin, by `--exclude-newer-package=` for it, also a young one such as the fix of a vulnerability that came at once; a package that the refresh moved takes no version below that of `main`, by a constraint, so that no fix goes back. When uv finds no version both that new and a week old, the command fails, and the refresh keeps the newest versions, which the check below holds. The settings of the bot allow the command, `^python3 (?:\.github/)?blueprint\.py locks --refresh$`, besides `pins.py`; a repository whose own workflow runs Renovate allows it too. uv compiles there as Renovate itself compiles the lock file a moment before, in the same checkout.
- **The Mend Renovate app** runs no command of the blueprint, so there the refresh of pip-compile keeps waiting for the maintainer; npm merges by itself as everywhere.
- **The check:** in a pull request of the same repository from one of the branches that merge by themselves, the step *Check the age of what the refresh of the lock files brings* of the required check dependency-review compares the lock files of the merge with those of its base, asks PyPI and the registry of npm when each version that it adds came out, and fails on one younger than a week, on one that it can't date, such as one by an address of its own, and on a changed file that is no lock file of pip-compile or npm. The registries set those dates, and no author can choose them. The PR coach explains it as the part *age of the refresh*. Nothing fixes it but time: the check passes when it runs again once each version is a week old, or the next refresh brings other versions; a lock file of another package manager gets a rule that lets its refresh wait.

The fix of a vulnerability comes at once, as before: neither `minimumReleaseAge` of the refresh nor its command nor its check applies to it, and the command keeps the young pin of such a fix that `main` has.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-the-weekly-refresh-of-the-lock-files-merges.dark.svg">
  <img src="../images/diagrams/how-the-weekly-refresh-of-the-lock-files-merges.svg" alt="How the weekly refresh of the lock files merges: On Mondays Renovate refreshes the lock files of every package manager. npm takes only versions released at least a week before. After Renovate, blueprint.py compiles the lock files of pip-compile again from uploads at least a week old, and keeps what main pins, such as the fix of a vulnerability. The check dependency-review asks PyPI and the registry of npm when each version that the refresh adds came out. Once every one is at least a week old and every check passes, the refresh merges on its own; a younger one holds it, and the check names it. The refresh of Composer and of any other package manager, which can't keep to that age, waits for the maintainer on a branch of its own.">
</picture>

## Consequences

The indirect dependencies move every week again, a week behind their newest versions, without a review. A refresh that brings a younger version all the same waits with a failed check that names each one, until the check runs again a week later or the next refresh replaces it. A repository that runs the Mend Renovate app, or has a lock file of Composer, keeps reviewing those refreshes. A project with a lock file of another package manager adds a rule that lets its refresh wait, as the check says. This supersedes the part of [0012](0012-lock-refresh-waits-for-the-maintainer.md) that let every refresh wait; its two checks that keep every lock file readable stay.
