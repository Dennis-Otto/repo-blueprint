# A lock file and a version fix themselves only where their tool refuses them

- Status: accepted
- Date: 2026-10-25

## Context

The fix bot ([decision 0023](0023-pull-requests-fix-themselves.md)) commits what the commands of `autofix` in `.github/checks.toml` change when a check fails. A check of `scripts/check.sh` runs the commands of every one of its steps, not only of the step that failed, on the head of the pull request and with the tools of the check. Four checks had no fix yet ([#225](https://github.com/Dennis-Otto/repo-blueprint/issues/225)): the version of the release bot, which the step Version compares with `.release-please-manifest.json`, the lock files of Composer and of npm, and the licenses of REUSE.

A lock file depends on the version of the tool that writes it: Composer writes its own `plugin-api-version`, and another npm can add or drop fields. Renovate writes the lock files of its pull requests with its own versions. `composer update --lock`, which the explanation of the step Composer named, only writes the hash of `composer.json` into the lock file: a package that `composer.json` adds stays missing, and `composer install` still stops.

## Options

1. Lock again whenever a check fails. Every failed check of a Nextcloud app or a Node package would commit a lock file of another Composer or npm, a change that has nothing to do with what failed.
2. Lock again only where the tool itself refuses the lock file, and then with the least change. `composer validate` without `--strict` fails only for a broken `composer.json` or a lock file out of date, and `npm ci --dry-run` fails only for a lock file that `npm ci` refuses, without changing anything, not even `node_modules`. `composer update --minimal-changes --no-install` keeps every other package at its version and adds and drops what `composer.json` asks for, and `npm install --package-lock-only` does the same for npm.
3. As 2, and REUSE fixes itself with `reuse annotate` for a file without a header.

## Decision

Option 2.

- **The version:** `python3 .github/blueprint.py fix version` takes the files from `release-please-config.json`, those of its release type and its `extra-files`, and writes the version of the manifest at the place where the step Version reads it, the first match of its pattern, without changing any other byte of the file. A file without a version at that place stays for a person. A test renders every kind of project and checks that the fix writes exactly the files that the step checks, and that the step passes after it.
- **Composer:** the autofix of the step Composer runs `composer update --minimal-changes --no-install --no-scripts --no-plugins --no-interaction` once `composer validate --no-check-publish` fails, without the scripts and plugins of the packages, as Renovate locks them.
- **npm:** a new step, Package lock, the first one of a Node package, runs `npm ci --dry-run`, so that `scripts/check.sh` finds such a lock file on your machine as well. Its autofix runs `npm install --package-lock-only --ignore-scripts` once the dry run fails. In the CI, the `npm ci` of the workflow stops before `scripts/check.sh`, and the fix of the check runs all the same.
- **REUSE:** no command. `REUSE.toml` gives every file the license of the project with `path = "**"`, so the tool finds only a header of a file's own that names a license whose text `LICENSES/` lacks or one that is no identifier of SPDX, or a text in `LICENSES/` that no file names. Its fix adds a file to `LICENSES/` or deletes one, which the bot never does, and the license of a file is the decision of a person.
- **Prettier and ESLint,** which #225 named for Node, are Biome in the blueprint ([decision 0043](0043-a-node-package-lints-with-biome-and-installs-without-scripts.md)), whose `biome check --write` already fixes the format and the safe rules.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-lock-file-and-a-version-fix-themselves.dark.svg">
  <img src="../images/diagrams/how-a-lock-file-and-a-version-fix-themselves.svg" alt="How a lock file and a version fix themselves: A pull request changes composer.json, package.json or a version by hand, and a check fails. The job of the check runs the autofix of every step. Where Composer or npm refuses the lock file, composer validate or the dry run of npm ci fails, and the lock file is locked again with the least change, every other package at its version; a lock file that the tool takes stays as Renovate wrote it. Where a file has another version than the manifest of the release bot, fix version writes the version of the manifest back at the place of the step Version, and nothing else of the file. The fix bot commits what changed, and the checks pass.">
</picture>

## Consequences

A pull request that changes `composer.json` or `package.json` by hand, or a version, passes after one commit of the bot. Every other lock file stays as Renovate wrote it. The lock file that the bot writes comes from the Composer or the npm of the CI, which can differ from that of Renovate; Renovate writes it its own way again with its next update. A check that fails for another reason runs the dry run of npm or the validation of Composer once more, a second or two.

The manifest decides: a pull request that changes `.release-please-manifest.json` by hand gets the version of every file changed to match. Only the release bot changes the manifest, in its own pull request, which writes every file at once and so never needs the fix. The cost: a manifest changed by hand passes after the fix instead of failing for a person to look; a fix that leaves the files alone when the pull request changed the manifest, from the manifest of the base, follows in [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429).

The other points of #225 need designs of their own and follow in [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429): a check of the lock files of pip-compile, which nothing checks yet, the draft of an entry of the changelog, a new file that the bot never commits, the title that the PR coach suggests, a `/fix` of a maintainer on a fork, a weekly run of the fixers on `main`, the fixes of the workflows of a project of its own, runs that end after the bot, and `gitIgnoredAuthors` for Renovate.
