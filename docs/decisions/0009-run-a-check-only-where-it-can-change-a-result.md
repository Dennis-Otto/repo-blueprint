# Run a check only where it can change a result

- Status: accepted
- Date: 2026-10-13

## Context

A GitHub account on the free plan runs about 20 jobs at once, across all its repositories. In the blueprint, a pull request started 35 to 38 jobs, and 72 % of the median time until its checks finished was spent waiting for a runner. Much of that work could not change a result:

- **The release pull request** is rebuilt by the release bot after every merge, and each rebuild ran all 37 jobs, among them the 14 legs of the Variants workflow. On 2026-10-12, 11 of 23 pushes to pull requests were such rebuilds, although they change only `CHANGELOG.md`, `version.txt` and `.release-please-manifest.json`, which no kind of project renders.
- **A merge into main** started 36 or 37 jobs. The rules of `main` take only squash merges of pull requests that are up to date, so the tree of the merge is the tree that the pull request was checked with; about 21 of these jobs checked it again, at the moment the branch bot and the Rollout needed runners. In paperless-unified-search, a merge ran 23 to 28 jobs the same way.
- **The scanners** ran in every pull request: SBOM, fuzzing, zizmor and OSV-Scanner, whatever the pull request changed, and the link check for every entry in the changelog.

## Options

1. Keep every check on every event, and wait.
2. Run fewer kinds of checks.
3. Keep every check, and run each one only where it can change a result: required checks in every pull request, a scanner where its files change, on `main` what keeps a baseline or publishes, and every week what depends on tools and sites that move on their own.

## Decision

Option 3.

- **Pull requests** run the required checks. A required check never sits behind a path filter, because a workflow that its filter leaves out reports no check, and a missing required check blocks the merge for good; `test_a_required_check_never_waits_for_a_path_filter` keeps that. The scanners have path filters: zizmor for the workflows, actions and the settings of Dependabot, OSV-Scanner for the lock files, fuzzing for the Python code, its targets and tools, and the link check for the documents but the changelog alone. The SBOM no longer runs in pull requests; the dependency review checks what a pull request brings in.
- **The release pull request**, the branch `release-please--…` of this repository, skips Variants, the scanners and the hints at the prose with a condition of the job. A branch of a fork that is named like it still runs them. In the blueprint, the required check `variants` stands for all variants and updates, because a matrix that its condition skips reports none of its legs; it passes when every leg passed or none ran, like the job `codeql` for its languages.
- **`main`** runs after a merge only what keeps a baseline or acts on it: the tests, whose coverage the coverage bot compares with, CodeQL, zizmor and OSV-Scanner, whose analyses code scanning compares pull requests with, Scorecard, the website, the release and the branch bot. Variants, Lint, the secret scan, the SBOM and the fuzzing don't run there.
- **Every week** brings what moves without a change: Variants, the fuzzing for a quarter of an hour, the secret scan over the whole history, which also keeps its badge current, the SBOM, and the scanners in full.
- **The newest Python** checks `main` after every change and every week, in its own workflow `newest-python.yml`, no longer in every pull request: a new Python breaks every pull request alike, and no pull request waits for this check. A failure there no longer turns the CI of `main` red, whose coverage the coverage bot needs as its baseline.
- **The website of the blueprint** is published by its Dashboard workflow. The Docs workflow only builds it on `main` wherever another workflow publishes GitHub Pages; every other repository keeps publishing from Docs.

## Consequences

A merge into `main` of the blueprint starts 11 to 14 jobs instead of 36, and a rebuild of the release pull request 17 instead of 37, with no Variants leg; the 17 are the required checks and the jobs of the bots around the pull request. A repository made from the blueprint starts 3 to 6 fewer jobs per pull request and 6 to 7 fewer per merge.

Nothing that a merge brings goes unchecked, since it brings only what its pull request ran with. A commit pushed to `main` directly, which its rules allow nobody, would meet Gitleaks only in the weekly run; GitHub's push protection guards it at once. The required checks of the blueprint change from the 14 legs of Variants to `variants`: the settings bot applies the change after the merge, and a pull request whose checks ran before it gets the new check when the branch bot brings it up to date. A new check comes with its place in this scheme: required and without a path filter, or a scanner with the paths it reads.
