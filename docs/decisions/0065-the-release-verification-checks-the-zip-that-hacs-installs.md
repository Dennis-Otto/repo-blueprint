# The release verification checks the zip that HACS installs, and a beta has its own version in it

- Status: accepted
- Date: 2026-10-25

## Context

`verify-release.yml` checks a release as its users can, after every release and every week: the signed tag, the immutable release, the provenance and the SBOMs of every asset, and, by the repository variable `PUBLISH_TO`, that PyPI, npm, GHCR, the Nextcloud App Store or the major tag of an action delivers it. It had no case for `hacs` ([#259](https://github.com/Dennis-Otto/repo-blueprint/issues/259)). HACS installs the asset that `filename` of `hacs.json` names, when `zip_release` is true, unpacks it into `custom_components/<domain>/` and reads the version of its `manifest.json`. A zip with the integration one folder too deep, a name other than the one that `hacs.json` gives, or a `manifest.json` of another domain or version passed every check, and would have broken the installation or the update of every user.

The beta channel (`BETA_CHANNEL`) tags the commit of `main`, whose `manifest.json` still has the version of the last release, since release-please writes the version of a release only into its release pull request. So the zip of the beta 2.1.0-beta.1 of HomeDarts for Autodarts had the version 2.0.1, which Home Assistant showed to its testers, and which a check of the version would have failed.

## Options

1. Check the zip of a release, and leave the version out for a beta: the testers keep seeing the version of the last release, and a beta whose zip is wrong in another way goes unnoticed only in part.
2. Write the version of the beta into its `manifest.json` on `main` before the tag: a commit of the release app for every beta, which runs every check again and brings a version into `main` that no release has.
3. Give the zip of a beta the version of the beta, in the build, and check the same for every release.

## Decision

Option 3. The step *Package the integration for HACS* of `build-release.yml` zips the folder of the integration at the tag with `git archive`, as before. Where its `manifest.json` has another version than the release, as for a beta, it writes the version of the release into a copy of the file, puts it in a tree of its own beside the tag's, with a separate index of Git, and zips that tree; the files of the zip are otherwise those of the tag, and a release, whose version release-please wrote, zips the folder of its tag as it is. The provenance and the SBOMs describe that zip, since they are made after it. Before the zip is attested and attached, and so before the release is immutable, the step checks that its root has a `manifest.json` of the domain of the folder and of the version of the release, and fails the build otherwise, as the step of the SBOMs repeats the check of `verify-release.yml`. It writes the stamped `manifest.json` without the carriage returns that `jq` of a Windows runner adds, so the zip has the line endings of the tag on every runner.

`verify-release.yml` has a case `hacs`, which checks, each with a line of its own in the summary, that `hacs.json` at the tag names a zip with `zip_release` and `filename`, that the release has that zip, that its `manifest.json` lies at the root of the zip with the domain of the folder in `custom_components/` at the tag and the version of the release, and that HACS offers the release as it should: a version with a `-` as a prerelease only, any other one as the latest release, or behind a newer release when an older one is checked by hand.

## Consequences

A zip whose `manifest.json` is missing at its root or has another domain or version fails the build, before there is a release to fix. Anything else wrong in the zip or the release fails the verification after the release, which GitHub reports to the maintainer, before most users update. A release made before this decision verifies as long as its zip was right; the weekly run checks the latest release, never a beta, so the betas made before with the version of the last release aren't checked again. `tests/test_template.py` runs both steps, with a stand-in for gh, git and curl: every check of the case `hacs` with a zip that passes and with each kind of wrong zip or release, and the zip of a release and of a beta. A project whose `hacs.json` has no `zip_release` lets HACS install the files of the tag rather than the asset with the provenance, and fails the verification: the blueprint's `hacs.json` has it.
