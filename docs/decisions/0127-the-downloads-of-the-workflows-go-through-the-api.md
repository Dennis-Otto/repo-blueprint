# The downloads of the workflows go through the API

- Status: accepted
- Date: 2026-11-08

## Context

On 8 November 2026, GitHub declared the incident *Increase in timeouts for some unauthenticated users* at 10:36 UTC; the checks failed from about 08:47 UTC on. For hours, a download from the page of a release on github.com, without a token, timed out or answered 504, while the API, with a token, kept working. The checks of every repository made from the blueprint failed on pull requests and on `main`, and GitHub mailed every failed run to the maintainer:

- `lycheeverse/lychee-action` downloads lychee with an unauthenticated `curl -sfLO` from the page of its release, which failed with exit code 22: the step *Check the links and anchors of the website* of the check *docs*, and the Links workflow. The action has no way to skip its download.
- The init of `github/codeql-action` failed with `Unable to download and extract CodeQL CLI: Unexpected HTTP response: 504`. The runner had CodeQL 2.27.3 in its tool cache, the version that the pinned action brings (`src/defaults.json`), but GitHub's feature flags asked for 2.27.4, so the action deleted 2.27.3 and downloaded 2.27.4 from github.com, three times without success.
- The other tools that the workflows download, gitsign, krankerl, Infection and syft, came from the pages of their releases with curl as well, which tried again, but without a token.
- The flaky-test bot of *After the checks* failed on a call that GitHub refused because the run was already running again, and a 5xx of the API would have failed it the same way.

## Options

1. **Retries alone:** longer retries of curl. They don't help in an outage that lasts hours.
2. **Through the API with the token of the job:** `gh release download` asks the API for the asset, which redirects to `release-assets.githubusercontent.com`, as the authenticated downloads that kept working did.
3. **A cache of the tools:** the Actions cache serves the tools from Azure. Its first download still needs GitHub, and the cache of a repository holds a few hundred MB more.

## Decision

Option 2, for every download of an asset of a release on GitHub that the workflows and the scripts of the template make.

- **`.github/download.sh`** downloads an asset of a release through the API with the token in `GH_TOKEN`, tries again after an error of the network or of GitHub, five times in all, 10, 20, 40 and 80 seconds apart, and stops at once when the release or the asset doesn't exist or the token is refused. It checks the download by the sha256 that the caller pins, or without one by the digest that GitHub keeps of the asset, and refuses an asset without one. When GitHub keeps failing, its annotation says that it is an outage of GitHub and not a problem of the change, with the link to githubstatus.com.
- **lychee** comes from `.github/lychee.sh`, which pins its version and sha256 below a line `# renovate:`, like the other tools of `.github/pins.toml`, downloads it once in a job and runs it as the action did: the report in Markdown in the log, the summary and the output file, the exit code in the output `exit_code`, a failure on a broken link or on no link at all, and the token of the job for the links to GitHub. The check *docs* and the Links workflow keep every argument and the cache of the answers of the sites. The action leaves the allowed actions.
- **CodeQL** analyzes with `tools: linked`, the version that the pinned action brings, which Renovate moves with the action and which the runners usually have in their tool cache. A step before the init looks for it there; when the runner lacks it, `.github/download.sh` downloads the bundle of that version through the API, checked by GitHub's digest, and the action takes it from that file. The analysis no longer follows the feature flags of GitHub ahead of a release of the action, which also keeps the alerts from moving with a version that no pull request brought.
- **gitsign, krankerl, Infection and syft** come through the API as well: krankerl and Infection with `.github/download.sh`, syft and krankerl of a release with `.github/download.sh` of the commit that runs the workflow, before the checkout and in a step of its own, so that no step that builds the project has the token of the job, and gitsign of `.github/sign-tag.sh` and of the verification of a release with `gh release download` of their own, as they don't depend on the checkout.
- **The flaky-test bot** asks GitHub again after a 5xx or a timeout, four times in all, 10, 20 and 40 seconds apart, fails at once on a refusal, and leaves a run alone that runs again already.

## Consequences

An outage of GitHub's downloads without a token fails no check; an outage of the API still does, and the annotation of `.github/download.sh` says so. Each download costs two calls of the API, which count against the limit of the token of the job.

The jobs that block hosts with Harden-Runner already allow `api.github.com` and `release-assets.githubusercontent.com`; the other jobs only record their traffic.

CodeQL takes a new version a few days later than GitHub's feature flags would, with the next release of the action that Renovate brings.

The downloads of the published website of GitHub Pages, of `raw.githubusercontent.com` and of other hosts stay with curl, which tries again: they need no token, or aren't GitHub's.

A test fails on a curl or wget of the page of a release on github.com, and on the action of lychee, in the workflows and scripts of every kind of project.
