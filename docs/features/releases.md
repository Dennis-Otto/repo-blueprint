# Releases and security

How a change becomes a signed release, and the security checks of every repository.

## Releases

A pull request with the next version, decided from the titles of the merged pull requests (`fix` a patch, `feat` a minor, `!` a major version, or a minor one while the version is below 1.0.0), and the text of the fragments in `changelog.d/` and of *Unreleased* in the changelog as its notes; merging it publishes the release with its package, SBOM and the signed provenance of an isolated build (SLSA Build Level 3), delivers it, and then verifies it as its users can, also every week; a release of nothing but dependency updates merges itself once a day, so that the updates of a day make one release, and at once when it fixes a vulnerability; where the repository variable `BETA_CHANNEL` is true, every change for users also becomes a beta of the next release, a prerelease for testers.

**How:** Release-please, the release app, immutable releases, `verify-release.yml`.

## From a change to a release

The title of a pull request decides the next version, and merging the release pull request does the rest:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/from-a-change-to-a-release.dark.svg">
  <img src="../images/diagrams/from-a-change-to-a-release.svg" alt="From a change to a release: A pull request whose title is fix, feat or feat! merges into main once every check passes. The release bot keeps a release pull request with the next version and the text of the fragments and of Unreleased. Merging it signs its tag first, in the next run of the release bot, then builds the release in isolation once the tag checks out, signs and publishes it, delivers it and verifies it, then and every week. With BETA_CHANNEL, every change for users also becomes a beta.">
</picture>

A pull request describes what it changes for users in a file of its own, a fragment in `changelog.d/`, such as `changelog.d/dark-mode.md`, below the heading of its kind of change, such as `### Features`. A new file conflicts with nothing, so pull requests that run at the same time merge one after another, without a person who merges `main` into each of them, and a release no longer conflicts with the pull requests that wait. The check of the title, *conventional title*, checks each fragment of a pull request as the release takes it in and counts only a new one as its entry, `scripts/check.sh` checks every fragment that waits on `main` as well, and the release bot moves every fragment into the section of the release and deletes it in the same commit. A heading that surely means a kind of change, such as `### Fixes` for `### Fixed` or `## Features` for `### Features`, the fix bot renames on the branch of the pull request and suggests on one from a fork; one as close to one kind as to another, such as `### Change`, stays for its author. Until the release, a page of the website that includes `CHANGELOG.md`, such as the changelog of this one, shows the entries of the fragments under *Unreleased*, grouped as the release groups them. A line under `## Unreleased` in `CHANGELOG.md` still works.

release-please reads the title of each merged pull request, not its whole description. The squash commit carries the description, and a line of it that the strict parser of release-please takes for a footer, such as `**[(Full` of the release notes that Renovate quotes, made it skip the commit in a run that passed, so that a fix waited for another release, which didn't list it. So before release-please runs, the release bot writes the title and the lines `Release-As:` and `BREAKING CHANGE:` of each pull request since the last release that can change it into the end of its description, as an override in an HTML comment that the page doesn't show; an edit that GitHub refuses is a warning, and release-please runs anyway. The release pull request changes only when its notes change; release-please rebuilt it in every run before, and every check of it started again (decision 0060 of the [decisions](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-changelog-without-conflicts.dark.svg">
  <img src="../images/diagrams/the-changelog-without-conflicts.svg" alt="The changelog without conflicts: Two pull requests each add a file of their own to changelog.d, so they merge into main one after the other without a conflict. The release bot writes the section of the next release from the fragments and the text of Unreleased into CHANGELOG.md of the release pull request, and deletes the fragments in the same commit. Merging it makes that section the notes of the release. Until then, the website shows the entries of the fragments under Unreleased, and the fix bot renames a heading of a fragment that surely means a kind of change.">
</picture>

Each release describes what it ships in its SBOMs, as SPDX and as CycloneDX: the package that its users install, or the files of its tag without those that only check, test and document it, under the name of the repository and the version of the release. A scanner of a user reports only the advisories of what the release ships, and applies its OpenVEX document to them (decision 0034 of the [decisions](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)):

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-the-sboms-of-a-release-describe.dark.svg">
  <img src="../images/diagrams/what-the-sboms-of-a-release-describe.svg" alt="What the SBOMs of a release describe: The build unpacks what the release ships into a folder of its own: the zip of HACS, the wheel, the npm package, the zip of the Chrome extension or the signed Nextcloud app, and for an action, an image or a project without a package the files of its tag without those that only check, test and document it. syft, checked by its sha256, lists the components that a package installs, or that the sources declare, under the name of the repository and the version of the release, as SPDX and as CycloneDX. The build and the release verification check that both name the release, and a scanner of a user applies the OpenVEX document of the release to the SPDX SBOM.">
</picture>

A release of paperless-sync, as GitHub shows its assets: the signed app, its signature, its SBOMs as CycloneDX and SPDX, the provenance of its build with its Sigstore bundle, the notices of its dependencies, and the attestation of the release:

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/github-release.dark.png">
  <img src="../images/github-release.png" alt="The assets of release v1.2.0 of paperless-sync on GitHub: paperless-sync.cdx.json, paperless-sync.spdx.json, paperless_sync.tar.gz, paperless_sync.tar.gz.sig, provenance.intoto.jsonl, provenance.sigstore.json and THIRD_PARTY_NOTICES.md, each with its sha256 and size, then the source code as zip and tar.gz and the release attestation">
</picture>

## Security

CodeQL, and for the PHP of a Nextcloud app the taint analysis of Psalm, which knows the controllers, files and HTTP client of Nextcloud and proves with a canary in every run that it still sees, OpenSSF Scorecard, dependency review, secret scan, SBOMs of what a release ships as SPDX and CycloneDX, by its name and version, OpenVEX, release tags signed without a key (gitsign) and checked before every build, findings watcher, the security audit of the workflows (zizmor), every lock file against the OSV database (OSV-Scanner), the network traffic of every job (Harden-Runner), blocked in each job that holds a secret or may write but for the hosts it needs, the answers of OpenSSF Best Practices and of the OSPS Baseline that the blueprint guarantees (`.bestpractices.json`).

**How:** Every action pinned to a commit hash.

## App Store

For a Nextcloud app: the registration of its id with its certificate, once, by hand.

**How:** `register-app.yml`.

## Chrome Web Store

For a Chrome extension: every release goes to the Chrome Web Store as the zip that the release attests, after a check of its provenance, signed in to Google with the OIDC token of GitHub and no stored secret. A daily run delivers a release whose review had to wait, and reports a rejection or a warning of Google with the fix.

**How:** `publish-store.yml`, `scripts/store-status.mjs`, [the page of the kind](../kinds/chrome-extension.md).
