# A major update merges by itself once every check passes

- Status: accepted
- Date: 2026-11-13

## Context

The pull requests of Renovate and of Dependabot merge by themselves once every required check passes: the checks are the gate, not a review. A major update was the exception. The first rule of `.github/renovate-blueprint.json5` turned auto-merge on for the update types `minor`, `patch`, `digest`, `pin` and `pinDigest` alone, and the merge bot of Dependabot in `.github/workflows/dependabot-automerge.yml` for `version-update:semver-patch` and `version-update:semver-minor` alone, so a major update, and one of Dependabot whose metadata names no type, waited for the maintainer, as [0057](0057-renovate-keeps-no-dependency-dashboard.md) and the picture of [0012](0012-lock-refresh-waits-for-the-maintainer.md) said. The update of `vimeo/psalm` to version 7 waited that way from 2026-11-09 in three repositories, with every check green ([issue 838](https://github.com/Dennis-Otto/repo-blueprint/issues/838)). The owner of the blueprint wants nothing to wait for him that the checks can decide.

## Options

1. Keep the wait: a person reads the notes of every new major version first.
2. Let a major update merge by itself once every required check passes, as every other update does, after the same week of waiting.
3. Let a major update merge by itself only for the tools of the tests, and keep the wait for what the users run.

## Decision

Option 2. The first rule of the Renovate rules merges every update type, `major` included, and the merge bot of Dependabot turns auto-merge on for every update of Dependabot, whatever its metadata names. A major update still waits its week after its release, as [0005](0005-renovate-instead-of-dependabot.md) wants against a version published from a hijacked account, and it merges only once every required check passes: one whose checks fail stays open and shows the failure, which is the signal that it needs work, and the PR coach explains each check that failed.

The refresh of the lock files of a package manager that can't keep to versions a week old, such as Composer, stays the one exception and waits for the maintainer on its branch `renovate/review-…` ([0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md)): it brings versions younger than a week, which a major update doesn't, so its reason is the age of the versions, not their kind. Rules of a project that hold a dependency back, such as a major version of Nextcloud beyond the `max-version` of an app, stay: they keep the update from coming at all.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/which-updates-of-renovate-merge-on-their-own.dark.svg">
  <img src="../images/diagrams/which-updates-of-renovate-merge-on-their-own.svg" alt="Which updates of Renovate merge on their own: Every update, a major one too, waits a week after its release and then merges on its own once every check passes. An update that fixes a vulnerability comes at once and merges on its own. The weekly refresh of the lock files of npm and pip-compile keeps to versions a week old and merges on its own as well. The refresh of a package manager that can't keep to that age, such as Composer, brings the newest version of every indirect dependency, without a week of waiting, so it waits for the maintainer.">
</picture>

## Consequences

- A major update that passes every check reaches `main` without a person, and the release bot sums it up in the next release. A breaking change that no check covers reaches the users as well: the tests of a repository are its gate, and a gap in them shows as a bug after the release instead of as a pull request that waits.
- A major update whose checks fail stays open with the failure, as the update of psalm 7 would, until a person or an agent fixes the code on its branch.
- The repositories get the rules with the next release of the blueprint; a major update that is open already merges at the next run of Renovate or of the branch bot once its checks pass.
