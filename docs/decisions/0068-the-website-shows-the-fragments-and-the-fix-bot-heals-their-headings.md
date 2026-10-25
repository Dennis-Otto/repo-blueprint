# The website shows the fragments, and the fix bot heals their headings

- Status: accepted
- Date: 2026-10-25

## Context

Since [decision 0018](0018-changelog-fragments.md), a pull request describes its change in a fragment of its own in `changelog.d/`, and the release bot moves the fragments into the section of the next release. Two of its consequences were left open:

- **The website showed the changelog without the fragments.** The changelog page of a website includes `CHANGELOG.md` with a line `--8<-- "CHANGELOG.md"`, whose Unreleased section stays empty while pull requests write fragments. Until a release, the website hid every change that `main` already holds.
- **A typo of a heading stopped the release, and only a person fixed it.** The check names a heading that is no kind of change, such as `### Fixes` for `### Fixed`, with the heading that it likely meant, and `scripts/check.sh` checks every fragment that waits on `main` as well. Each such fragment cost a round trip to its author, although the fix is plain.

## Options

1. Leave both as they are: the website catches up with each release, and the author renames the heading.
2. Let the release bot write the fragments under Unreleased of `CHANGELOG.md` after each merge. Every merge would change `CHANGELOG.md` again, and every pull request that waits would conflict with it, the problem that decision 0018 solved.
3. Fold the fragments into the page when the website is built, with the code that the release uses, and let the fix bot rename a heading whose kind of change is certain.

## Decision

Option 3.

- **The website shows the fragments under Unreleased.** The hook of every website replaces a line `--8<--` that includes `CHANGELOG.md`, beside which `changelog.d/` has fragments, with the changelog as the next release will have it: `with_fragments` of `blueprint/changelog.py` joins the entries of the fragments to the text of Unreleased, each kind of change under one heading, as `unreleased_text` groups them for the release. The hook loads that file by its path, beside it in `.github/blueprint/` of a repository made from the blueprint and at the root of the blueprint itself, so it imports nothing else of `blueprint.py`. A part of the changelog, such as `CHANGELOG.md:10:20`, a changelog without fragments, and a hook without `blueprint/changelog.py` beside it leave the line as it is. The page takes the date of the newest of the changelog and its fragments.
- **The fix bot renames a heading that surely means a kind of change.** `blueprint.py fragments --fix` renames `### Fixes` to `### Fixed`, `### bug fixes` to `### Bug fixes` and `## Features`, which would start a section of its own, to `### Features`, and keeps the byte order mark and the line endings of the file. A heading surely means the kind that is closest to it, by the ratio of `difflib`, when that ratio is at least 0.8 and no other kind is as close. The hint of the check names every kind from 0.6 on, but at 0.6 the fix would turn a meaning around: `### Improved` would become `### Removed`, `### Removed features` `### Features` and `### Added and changed` `### Breaking changes`. These stay for their author, as `### Change` does, as close to `Changes` as to `Changed`, and a heading that is close to no kind. The step *Changelog fragments* of `scripts/check.sh` names the command in `autofix`, so the fix bot commits the rename onto a branch of the repository and suggests it on a pull request from a fork, as for every other step.
- **A draft entry of the PR coach is a fragment.** The coach explains the check *changelog* with a new file `changelog.d/<branch without its type>.md` first and Unreleased as the alternative, and the draft entry that the self-healing work of Dennis-Otto/repo-blueprint#429 plans to write from the title will be a new fragment, never a line under Unreleased.

## Consequences

The website shows what `main` brings before its release, in the words and the groups of the release notes, without a commit to `CHANGELOG.md`, so no pull request conflicts with it. A fragment with a heading that the release can't take in heals itself on a branch of the repository, and the release no longer waits for its author. The words of an entry stay its author's: the bot only renames a heading whose kind of change is certain. A fragment that the release would refuse for another reason still shows on the website, as far as it has headings; the check stops it before the merge.
