# An acceptance of advisories warns two weeks before it ends

- Status: accepted
- Date: 2026-11-12

## Context

An `osv-scanner.toml` accepts advisories until a date: `effectiveUntil` of an entry of `[[PackageOverrides]]` for every advisory of one version ([decision 0059](0059-accept-a-pinned-version-and-tell-renovate.md)), `ignoreUntil` of one of `[[IgnoredVulns]]` for one advisory. From that day on OSV-Scanner reports the advisories again, on `main`, in every pull request that changes a lock file and in the Home Assistant leg of the Variants workflow, and the job *dependabot alerts* opens their Dependabot alerts again ([decision 0086](0086-accepted-advisories-close-their-dependabot-alerts.md)). The date is meant as the day when a person looks again, but nothing told anyone that it was near: `blueprint.py advisories` only checked that it was there.

`stacks/home-assistant/osv-scanner.toml` accepted the advisories of Pillow 12.3.0, which Home Assistant 2026.10 pins for the tests, until 2026-11-22. On 2026-11-12 the test plugin `pytest-homeassistant-custom-component` that would move it was still not out, so every check with a lock file would have turned red overnight, also the dependency pull requests that merge by themselves, and in every Home Assistant integration made from the blueprint at the same time ([#851](https://github.com/Dennis-Otto/repo-blueprint/issues/851)).

## Options

1. **Leave it to the date:** the red checks are the reminder. They come all at once, block the automatic merges and page for a red `main`.
2. **Fail `scripts/check.sh` before the date:** every pull request, also one that has nothing to do with the advisories, turns red two weeks early.
3. **Warn and keep an issue:** the run of the OSV-Scanner workflow on `main` and its weekly run warn of each acceptance that ends soon and keep one issue that names it, which closes by itself once none does; the checks stay green.

## Decision

Option 3. `blueprint.py advisories --ending` reads every acceptance with a date, of `[[PackageOverrides]]` and of `[[IgnoredVulns]]`, and names each that ends within 14 days, or has ended: two weekly runs, so that the next one still comes before the date. It writes a warning for each in the summary of the run and keeps one issue, *An acceptance of advisories in osv-scanner.toml ends soon*, with the labels `dependencies` and `security`, which names the file, the package, the version, the date and the reason and says what to do: take the update that moves the version and delete the entry, or look at the advisories again and move the date with a reason that still holds. Its text names no day of its own, so it changes only with the acceptances. Once none ends within 14 days, the command closes it.

The command runs as the last step of the job *dependabot alerts*, which runs on `main`, every Monday and by hand, with the token of the job and `issues: write`: it needs no app, so it also runs where the app couldn't close the alerts, and its dry run follows the input `dry_run` of the workflow. `blueprint.py advisories`, the step *Accepted advisories* of `scripts/check.sh`, names such an acceptance too, as a note that fails nothing.

## Consequences

An acceptance that ends no longer turns the checks red unannounced: the maintainer gets an issue two weeks before, with the work it takes. A person who moves a date without looking again is not stopped by it; the reason beside the date says what was looked at. The Pillow of Home Assistant is accepted until 2026-12-20 after a new look at its advisories, so the issue comes on 2026-12-06 at the latest if the test plugin hasn't moved by then.
