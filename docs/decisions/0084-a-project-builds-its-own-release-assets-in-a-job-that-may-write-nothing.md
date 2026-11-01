# A project builds its own release assets in a job that may write nothing

- Status: accepted
- Date: 2026-10-25

## Context

The build of a release, `build-release.yml`, packages an asset only where `PUBLISH_TO` delivers it: the zip of HACS, the wheel, the npm package and the signed Nextcloud app. Every other project ships only its SBOMs, its notices and the provenance. player-switch-for-autodarts is a browser extension that the Chrome Web Store delivers (`PUBLISH_TO = "none"`): its releases had no zip of the extension, so the package that its users install had no signed provenance, and nobody who installs it by hand could download it ([#470](https://github.com/Dennis-Otto/repo-blueprint/issues/470)). A release is immutable once it is published, so such an asset has to reach the draft inside the build.

## Options

1. A new `PUBLISH_TO` for each kind of package, such as `chrome-web-store`, with its build in the blueprint.
2. A hook of the project, `scripts/release-assets.sh`, that runs in the job that attests and writes the release, as the build of an npm package does.
3. The same hook in a job of its own in `build-release.yml`, with a token that may only read, whose files the job of the release takes as an artifact and attests with the rest.

## Decision

Option 3. A store or a format that one repository needs would make the blueprint grow a build for each, and the hook of option 2 would run the project's code and its npm packages in a job that holds an OIDC token and may write the release and its attestations.

- **The contract.** When a project has `scripts/release-assets.sh`, the job *assets of the project* runs `bash scripts/release-assets.sh FOLDER VERSION` at the commit of the release, after the Node.js of `.nvmrc` and `npm ci --ignore-scripts` where a `package.json` is, without a cache. It writes each asset as a file at the top of `FOLDER`, by a name of letters, digits, `.`, `_`, `+` and `-`; the job fails for no file, a folder, a link or another name.
- **The job.** `permissions: contents: read`, no environment and no secret; Harden-Runner blocks every host but GitHub, Node.js and npm, without `sudo` and Docker. It checks out the commit of the release by its sha, which the job of the release checks the signed tag against before it attests anything, and hands the files on as the artifact `project-assets`, kept for seven days.
- **The release.** The job *release assets* takes the artifact, refuses a name that one of its own assets has, as well as `provenance.*`, `*.intoto.jsonl`, `*.spdx.json`, `*.cdx.json`, `*.openvex.json` and `THIRD_PARTY_NOTICES.md`, which verify-release reads as files of the release itself, and the names that the registry jobs of `release.yml` download by pattern (`*.whl` and `*.tar.gz` for `pypi`, `*.tgz` for `npm`, `*.tar.gz*` for `nextcloud-appstore`, `*.zip` for `chrome-web-store`), attests every asset with the same `attest-build-provenance` step and attaches it to the draft. Where no registry delivers the project, the zips and tarballs of the hook are what the release ships, and its SBOMs describe them as a package. `verify-release.yml` checks the signed provenance of every asset, these too.
- **Projects without the hook** release as before: the new job only checks out and ends.
- `scripts/release-assets.sh` is a file of the project, in `_skip_if_exists`.

## Consequences

A project can attach what no kind of the blueprint builds, attested, to each release. A Chrome extension doesn't need the hook: its kind builds and attests the zip ([decision 0085](0085-a-chrome-extension-reaches-the-store-with-the-zip-that-its-release-attests.md)). Each release runs one more short job. A hook that needs another host fails with the blocked call in the summary of Harden-Runner; that host goes into the job's list, in the blueprint.
