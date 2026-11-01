# Accepted advisories close their Dependabot alerts, and open them again when the acceptance ends

- Status: accepted, amends [0059](0059-accept-a-pinned-version-and-tell-renovate.md) and [0077](0077-a-second-app-writes-the-administration.md)
- Date: 2026-10-25

## Context

An `osv-scanner.toml` accepts the advisories of a version that another package pins, with a reason and a date when a person looks again ([decision 0059](0059-accept-a-pinned-version-and-tell-renovate.md)). OSV-Scanner reads it, and Renovate the rules that `blueprint.py advisories` writes from it, but Dependabot reads neither: repo-blueprint and homedarts-for-autodarts each kept 41 Dependabot alerts open for the Pillow 12.3.0 that Home Assistant pins for the tests of an integration, and a new alert that matters would hide among them. Dennis wants them closed by themselves, "fix first, explain second".

GitHub's token of a workflow can't read or write the Dependabot alerts; only a token of a person or of an app with the permission *Dependabot alerts* can.

## Options

1. Dismiss the alerts by hand, with a comment each: 41 clicks per repository, again for each new advisory, and nothing opens them again when the acceptance ends.
2. Dependabot's own rules (`ignore` in `dependabot.yml`, or auto-triage rules): they hide a package or an advisory for good, without the reason and the end that the acceptance has, and the blueprint keeps Dependabot to the Features of the dev container.
3. A job that dismisses each alert that an acceptance covers, with its reason and its end, and opens again each alert that it dismissed once the acceptance is gone, as an app of the owner.

## Decision

Option 3.

- **The command** `blueprint.py advisories --dependabot` lists the open and the dismissed alerts. It dismisses each open alert that an acceptance which hasn't ended covers, as `tolerable_risk`, with a comment that starts with `Accepted in`, then names the file, the end and the reason, in GitHub's 280 characters. An entry of `[[PackageOverrides]]` covers every advisory of its version of the package in the lock files of its folder, and only while the lock file pins that version; one of `[[IgnoredVulns]]` with `ignoreUntil` and `reason` covers its advisory, by its GHSA or CVE id or an alias, in every package there. It opens again every alert whose comment starts with `Accepted in` once no acceptance covers it: the date has passed, the entry is gone, or an update moved the version. `--dry-run` only says what it would do. The log names each alert by its number and link alone.
- **The job** *dependabot alerts* of the OSV-Scanner workflow runs it on `main`, every week and by hand, with a token of the settings app once the variable `SETTINGS_APP_CLIENT_ID` and the secret `SETTINGS_APP_PRIVATE_KEY` name it, and of the release app until then, for this repository alone and with *Dependabot alerts* (read and write) alone. The settings app gains that permission: closing an alert is an administration of the repository, which the settings app took over in [decision 0077](0077-a-second-app-writes-the-administration.md).
- **A refused token** fails the job in the repositories of the blueprint's owner, whose apps have the permission, and the PR coach explains the check *dependabot alerts*. In a repository of another owner it leaves a notice until the owner grants the permission, and without either app the alerts stay as they are, with a warning that names what is missing, as every bot of the release app gives.

## Consequences

The Dependabot alerts of every repository show what nobody accepted, and an acceptance that ends brings its alerts back, as OSV-Scanner brings its findings back. The owner grants *Dependabot alerts* (read and write) to the settings app, or to the release app without one, and accepts the new permission on its installation, as [Your own account](../own-account.md), step 6 of the settings app, shows; until then the job fails in the owner's repositories. An alert closes within a week of a new advisory, or with the next push to `main`, and its comment keeps the end of the acceptance that closed it, until the acceptance ends and the alert opens again.
