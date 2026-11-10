# The secret scan runs gitleaks of its release

- Status: accepted
- Date: 2026-11-10

## Context

[Decision 0133](0133-the-downloads-of-the-workflows-go-through-the-api.md) moved every download of an asset of a release on GitHub that the blueprint's own steps make to the API, after GitHub's downloads without a token timed out for hours on 8 November 2026. It left the actions of others as they were and named what each still downloads: `gitleaks/gitleaks-action` downloads gitleaks from the page of its release without a token, whenever the cache of Actions lacks it, after a new version or once GitHub evicted the cache, which it does after a week without use. Then the check *gitleaks* fails in such an outage. The record left it open whether the secret scan should run gitleaks of its release through `.github/download.sh`, as the link check runs lychee, at the cost of the summary of the findings that the action writes ([#806](https://github.com/Dennis-Otto/repo-blueprint/issues/806)).

A look at the code of the pinned action, v3.0.0, found more:

- It runs gitleaks 8.24.3, the version that it names itself, about a year older than 8.30.1. The workflows can't move it: Renovate sees only the version of the action, and its input for the version of gitleaks, `GITLEAKS_VERSION`, has no line `# renovate:`.
- It checks the download by no checksum.
- Its license is no open-source license but an end-user license agreement of Gitleaks LLC, and it asks every repository of an organization for a license key in the secret `GITLEAKS_LICENSE`, without which the check fails. When it can't ask GitHub whether the owner is an organization, it asks for the key as well. gitleaks itself has the MIT license.
- On a pull request, it scans the commits that the first page of `GET /pulls/{number}/commits` lists, 30 at most, along their first parents: the later commits of a longer pull request, and those of a branch merged into it, stay out of the scan.
- Its comments on a pull request need `pull-requests: write`, which the job doesn't have, so it only logs a warning for each.

## Options

1. **Keep the action**, with an issue upstream for its download. The download stays without a token until the maintainers of the action change it, and the rest stays the same.
2. **gitleaks of its release, as lychee:** `.github/gitleaks.sh` downloads gitleaks through the API with `.github/download.sh`, checked by the sha256 that the blueprint pins, and runs it. The summary of the findings, which the action wrote, comes from the report of gitleaks in JSON.
3. **The image of gitleaks** from `ghcr.io`, which needs no download of a release, but a pull of an image in every run, and a pin of its digest that Renovate moves on its own.

## Decision

Option 2. The secret scan gives up nothing of the action that it used: the summary comes from a few lines of jq, and the rest of the action was its weak points.

- **`.github/gitleaks.sh`** pins the version and sha256 of gitleaks below a line `# renovate:`, like lychee in `.github/lychee.sh`, and `.github/pins.toml` keeps them, so Renovate moves both and `pins.py` writes the sha256. It downloads gitleaks once in a job, with the token of the job, and runs it without that token. gitleaks redacts every secret in its log and its report, as it did in the action.
- **A pull request** scans the commits from its base to its head, `base..head`, every one of them, also after its 30th and those of a branch merged into it. A pull request that changes gitleaks or its rules, in `.github/gitleaks.sh`, `.gitleaks.toml` or `.gitleaksignore`, scans the whole history, so that a new rule or a new version fails the pull request that brings it, such as the update of the blueprint, and not the weekly scan after it. The weekly scan, and one started by hand, scans the whole history of every branch, as the action did.
- **Each finding** becomes an annotation of an error at its line, which a pull request shows at that line of the changed file, with the fingerprint that `.gitleaksignore` takes, and a row of a table in the summary of the check, with links to the line and to the commit. The table leaves out the author's e-mail address, which the action showed. When gitleaks fails itself, its annotation says that this is no finding of a secret.
- **The action leaves the allowed actions** of every repository, and the job keeps `contents: read` alone.

## Consequences

An outage of GitHub's downloads without a token fails no secret scan any more; an outage of the API still does, and the annotation of `.github/download.sh` says so. The secret scan of a repository of an organization needs no license key. gitleaks moves to 8.30.1, whose rules find more than those of 8.24.3: a finding in the history fails the update of the blueprint that brings it, where `.gitleaksignore` takes its fingerprint.

The secret scan no longer keeps the report of the action as an artifact of the run: the summary and the annotations name everything that it held.

Each scan costs the two calls of the API of a download, once in a job.
