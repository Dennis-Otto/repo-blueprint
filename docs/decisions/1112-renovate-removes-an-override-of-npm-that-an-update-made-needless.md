# Renovate removes an override of npm that an update made needless

- Status: accepted
- Date: 2026-11-23

## Context

An entry of `overrides` in `package.json` raises a package that a dependency asks for in a version with a vulnerability. homedarts-for-autodarts raises minimatch that way, because ESLint asked for minimatch `^10` and the fix of GHSA-g3hv-75wg-m249 is only in minimatch 11, and a test of the project fails once every package that needs minimatch takes the major version of the override itself, so that the override leaves with the update that makes it needless. That update came with Renovate's homedarts-for-autodarts#783, which moves ESLint to 10.15.0, which asks for `^11.0.5`: its check failed, and the pull request waited for a person ([#1112](https://github.com/Dennis-Otto/repo-blueprint/issues/1112)). paperless-sync has the same override in `scripts/eslint/package.json`, without such a test, and player-switch-for-autodarts a nested one below `addons-linter`.

No bot could repair it. On a pull request of a bot, `for_unread()` of `blueprint/fixes.py` leaves a fix of `package.json` and `package-lock.json` to a person, since both are in `WORKFLOW_FILES` of `blueprint/branches.py` ([decision 0142](0142-the-fix-bot-commits-nothing-that-runs-with-rights-where-nobody-reads-its-commit.md)), and Renovate runs only the commands that `allowedCommands` of `.github/renovate-global.json5` allows, the refresh of the lock files of pip-compile ([decision 0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md)) and the blueprint's own `pins.py`.

## Options

1. **A test that only warns, or an override that stays for good:** the override holds the package back from the updates of the tools that ask for it, and nobody notices.
2. **An `autofix` of the project for the fix bot:** the bot rightly leaves `package.json` to a person on a pull request of a bot; loosening that rule weakens a control.
3. **Turning off Renovate's update of the override, or `ignoreDeps`:** the override stays old for good.
4. **A script of one project in `allowedCommands`:** it runs in Renovate's checkout with the token, so it belongs in `blueprint.py`, reviewed once here and the same for every repository.
5. **A command of `blueprint.py` that Renovate runs after every update of npm, which removes an override only where npm doesn't need it, and the one more entry of `allowedCommands` that allows it.**

## Decision

Option 5:

- **The command:** `python3 .github/blueprint.py npm-overrides --fix` (in the blueprint `python3 blueprint.py npm-overrides --fix`) looks at every `package.json` that git keeps, in any folder and not only those that the update changed, that has `overrides` and a `package-lock.json` beside it. For each entry that names a version or a range, also one nested below the package that asks for it, it takes the entry out, with what that leaves empty, and runs `npm install --package-lock-only --ignore-scripts --no-audit --no-fund` in that folder, so that npm writes the lock file itself and runs no code of a package. An entry that names no version, such as `$eslint` or `npm:other@1`, stays without npm.
- **When a removal stays:** only when every copy of the package in the new lock file is at or above the floor of the override, the lowest version that it allows, such as 11.0.3 for `^11.0.3`, unless the old lock file held a copy at the same path below the floor too, outside the reach of the override, as minimatch 3.1.5 below multimatch in player-switch-for-autodarts; and only when the new lock file brings no version of any package that the old one lacked, since Renovate gives npm `--before=` only on its own call, and a version younger than a week must not come into an update that merges by itself. Otherwise the command puts `package.json` and `package-lock.json` back byte for byte, also when npm fails.
- **What it says:** each override that it removed and each one that it kept, with what npm takes without it; and a note `//` beside `overrides`, which may speak of the override that left, which it leaves as it is. Without `--fix` it names the overrides that npm no longer needs and fails, and changes nothing.
- **Renovate:** a rule of `.github/renovate-blueprint.json5` runs the command after every update of npm, in `executionMode: "branch"`, with `fileFilters` `**/package.json` and `**/package-lock.json`, and `installTools: { node: {}, python: {} }`: the image of Renovate 44.249.1 has `/usr/bin/node` without npm and a Python 3.12, and `install-tool` gives it the Node with npm and the Python of Containerbase, as `binarySource: "install"` lets it. Renovate runs each distinct task of the updates of a branch once, so a branch of the refresh of the lock files that holds npm and pip-compile runs `locks --refresh` and this command both. The Mend Renovate app runs no command of the blueprint, so there the rule is left out.
- **The settings of the bot** allow `^python3 (?:\.github/)?blueprint\.py npm-overrides --fix$` besides the two commands of before, with its reason; it sits outside the lines of `pins.py`, which the settings of a repository that runs Renovate itself leave out, so that such a repository allows it too.

## Consequences

- An update of Renovate that makes an override needless removes it in its own commit, turns green and merges by itself; one that still needs it leaves both files as they were.
- The allowed command takes effect in every repository of the owner as soon as it merges, since they all run on the Renovate of the blueprint; the rule reaches a repository with the release and the blueprint bot's pull request there. Renovate then builds a branch such as homedarts-for-autodarts#783 anew, as it is behind `main`, and commits `package.json` without the override.
- Every update of npm takes a little longer, as Renovate installs Node and Python and npm writes the lock file once for each override; a repository without an override runs no npm.
- The command reads only the lock file that npm writes: a removal that npm resolves the same way but that a test of the project still refuses stays a failure for a person, and so does a stale note `//`, which the command only names.
