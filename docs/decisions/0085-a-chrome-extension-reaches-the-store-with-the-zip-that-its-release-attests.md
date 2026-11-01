# A Chrome extension reaches the store with the zip that its release attests

- Status: accepted
- Date: 2026-10-25

## Context

The blueprint had seven kinds of projects, and none for a browser extension. [Player Switch for Autodarts](https://github.com/Dennis-Otto/player-switch-for-autodarts) is a Chrome extension made as a Node package: it built everything a Chrome extension needs as files of its own, a workflow that delivers each release to the Chrome Web Store, the checks of its manifest and a test in Chrome. Its release had no zip with a provenance, though. The package that its users install was built a second time, in the workflow of the store, outside the isolated build of the release, and nothing tied it to the signed tag.

The Chrome Web Store differs from the registries of the other kinds in four ways:

- Google reviews every version before its users get it, which takes from hours to days, and takes no new version while a review is pending.
- The API makes no item: the first version is uploaded by hand.
- The listing and the privacy practices, with a justification of each permission, are filled in by hand in the Developer Dashboard, and the API can't set them; a version that asks for a permission that the dashboard doesn't justify is refused with `INVALID_ITEM_METADATA`.
- There is no trusted publishing of GitHub: the API takes an access token of Google, either from the refresh token of a developer account, a long-lived secret, or from a service account.

## Options

1. Leave it to each extension: every project writes its own delivery again, as Player Switch did, and none of them gets a provenance of the release.
2. A kind that delivers from the release workflow, as npm does: the release would wait days for the review, and fail for a pending one that isn't its fault.
3. A kind `chrome-extension`, on the stack of Node, whose isolated build zips and attests the extension like every other package, and a workflow of its own, *Chrome Web Store*, that delivers exactly that zip after each release and looks after the store every day.

## Decision

Option 3.

- **The kind** `chrome-extension` takes the tools of Node: the same `check (node)`, Biome, tsc and node:test with every line covered. Its build compiles `src/` into `extension/lib/`, and its `package.json` is private. The release bot writes the version of each release into `extension/manifest.json` as well. `extension/` and `store/` belong to the project.
- **The checks** of `scripts/check.sh` add the step *Extension*: `scripts/check-manifest.mjs` fails on what the store would refuse or hold up, before a release finds it. That covers a manifest other than V3, a version other than that of the release, a key or an update URL, a name or a description over the limits of the store, a permission or host without its reason in `store/permissions.json` or its justification in the listing of a language, and a language without its listing. `scripts/package-extension.sh` then builds the zip, the same for the same commit. The CI loads the extension into Chrome for Testing and fails when its service worker doesn't start.
- **The release** zips the extension from the signed tag in `build-release.yml`, attests it with the other assets, and `verify-release.yml` checks that it holds the manifest of its version. A beta gets the numbers of its version in the manifest and the whole version as `version_name`, since a manifest takes only numbers.
- **The delivery** is `publish-store.yml`, after every run of the Release workflow and every day. Its job *the state of the store* asks the store and decides with `scripts/store-status.mjs`. A pending review waits for a later day; a rejection, a warning, a review of more than seven days and a higher version in the store fail the run, with the reason and the fix. The job *the package of the release* takes the zip of the release only with a valid provenance of the isolated build. The job that uploads runs no code of the repository and reaches only Google. A refusal with `INVALID_ITEM_METADATA` names what the version asks for and which languages it speaks, so the maintainer knows what to justify in the dashboard.
- **The sign-in** needs no stored secret: once the variables `CWS_WORKLOAD_IDENTITY_PROVIDER` and `CWS_SERVICE_ACCOUNT` are set, the OIDC token of GitHub becomes an access token of a service account for 20 minutes, through Workload Identity Federation, under a condition that admits only this repository, `main` and this workflow. The refresh token of the secrets of the environment `chrome-web-store` stays as the way until then, and a run warns while one is left. The settings as code keep the environment to `main`.
- **What only a person can do,** the first upload, the listing and the set-up of the sign-in, is in `docs/releases.md` of the project and in two steps of the checklist, which are done once their variables are set.

## Consequences

Every Chrome extension of the blueprint ships the zip that its release attests, and its users get exactly that package. Its maintainer stores no secret of the store, and nothing expires. The review of the store no longer touches the release; the daily run reports how it goes, and the bot-health sweep keeps an issue open while a run fails. Edge installs from the Chrome Web Store as well; addons.mozilla.org and the Edge Add-ons store are left to a project of its own. A project that was a Node package, such as Player Switch, takes the kind with `copier update --data project_type=chrome-extension`, keeping its own `extension/`, `store/` and `docs/releases.md`.
