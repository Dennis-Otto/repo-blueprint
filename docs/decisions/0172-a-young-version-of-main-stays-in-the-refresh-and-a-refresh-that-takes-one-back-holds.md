# A young version of main stays in the refresh, and a refresh that takes one back holds

- Status: accepted
- Date: 2026-11-17

## Context

The weekly refresh of the lock files takes only versions at least a week old and keeps what `main` already has ([0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md)). A version on `main` that is younger than that week broke both promises ([issue 1004](https://github.com/Dennis-Otto/repo-blueprint/issues/1004)):

- **pip-compile:** `blueprint.py locks --refresh` gave every package that Renovate's refresh moved a floor at the version of `main`, `<package>>=<version>`, and compiled with `--exclude-newer=` a week before the start of the day. When the version of `main` came out after that cutoff, no version fitted both, uv failed, the command exited with 1, and Renovate kept its own compile with the newest version of every package, which the check dependency-review then held. issue-assistant#445 and homedarts-for-autodarts#754 stayed red that way for a week. `main` gets such versions in the normal course: the fix of a vulnerability, which comes at once; the packages of Playwright, which come without the week since [0168](0168-the-packages-of-playwright-come-without-a-release-age-like-its-images.md); and an update that merges on the day of the refresh.
- **npm:** the refresh resolves each range anew from the versions a week old, and so replaces a version that `main` got within the range shortly before with an older one. The check held such a refresh only while the version of `main` was younger than a week; after that, the same refresh, unchanged, passed, and the PR coach advised to run the check again. repo-pager#234 would have taken wrangler 4.159.0, vite 8.3.7 and a few more back to the versions before them that way. Had one of them been the fix of a vulnerability, the fix would have gone.

## Options

1. Keep the floor and let the refresh fail, as before.
2. Give a young package of `main` `--exclude-newer-package=<package>=<now>` beside its floor: the compile would pass, but take the newest version, younger than the week, which the check would hold in turn.
3. Keep the young version of `main` exactly: `<package>==<version>` as its constraint, and `--exclude-newer-package=` for it, so that uv sees it.
4. For npm, hold a refresh that takes back a version of `main` only while that version is younger than a week, as before.
5. For npm, hold a refresh that replaces a version of `main` with older ones for as long as it does.

## Decision

Options 3 and 5.

- **pip-compile:** the command asks PyPI when each version of `main` that the refresh moved came out, as the check does, in parallel. A version uploaded after the cutoff of the day, or one that PyPI can't date, such as one of an index of its own, stays exactly as it is, by `==` in the file of constraints and `--exclude-newer-package=` for its package; every other package keeps its floor at the version of `main` and the cutoff of the week. No version is both as new as that of `main` and a week old, so the one that stays is the only one that brings nothing younger than what `main` already has. The command then passes, and Renovate takes its compile; the cutoff stays the same for every run of one day, and a file that the week takes back to `main` byte for byte still reaches Renovate through the index.
- **Every refresh:** the step of dependency-review holds a refresh that replaces a version of `main` only with versions of the same package that came out before it, however old the version of `main` is, with the sentence that the refresh holds until Renovate builds it anew. The registries' dates decide what is older, the dates that the check already asks for, with no parser of the versions of npm and PyPI. A refresh that moves a version of `main` up, or brings a version that the check can't date, is judged by the age of what it brings, as before; so is one that only takes out a version of a package beside another version of it that stays. Renovate builds the refresh anew in its window on Mondays (`updateNotScheduled: false`), from the versions a week old by then, which include the version of `main`; until then, the refresh waits.

The fix of a vulnerability still comes at once, in a pull request of its own with `minimumReleaseAge: null`, which neither the command nor the check touches, and stays on `main`. The Mend Renovate app runs no command of the blueprint and behaves as before.

## Consequences

A young version of `main` no longer breaks the refresh of a file of pip-compile: the other packages of the file move to their versions of a week ago, and the young one moves at the next refresh after its week. The command asks PyPI once for each package that the refresh moved; when PyPI can't answer, the refresh keeps the versions of `main` for those packages, which is safe and only slower. A refresh of npm that takes back a version of `main` no longer passes once that version is a week old: it waits for the next Monday, when Renovate builds it anew. This amends the consequences of 0137 ("until the check runs again a week later") and of 0168 ("its check dependency-review then holds the refresh until that Playwright is a week old"): the refresh holds until Renovate builds it anew. The PR coach, `blueprint.py locks --age` and the troubleshooting page no longer advise to run the check again for such a refresh.
