# One report on each pull request, which says what it makes

- Status: accepted
- Date: 2026-10-18

## Context

The PR coach ([decision 0022](0022-every-check-explains-its-failure.md)) keeps one comment on a pull request whose checks failed, with the fix of each check. What the pull request itself makes showed nowhere:

- **The version.** Whether a merge makes a minor or a patch release, or none, follows from the title and from the release-please files of `main`, and a contributor learned it from the release pull request after the merge. A `!`, a `BREAKING CHANGE:` line or a `Release-As:` line of the description, which the squash commit carries, changes it.
- **The entry of the changelog.** The fragment in `changelog.d/` or the lines under `## Unreleased` reach the notes of the release as they are, and a reviewer saw them only in the diff.
- **A second comment for the coverage.** The coverage bot kept a comment of its own on every pull request that ran the tests: 34 on the last 40 pull requests of paperless-unified-search, 30 of which only said that no file changes its coverage. A pull request with a failure had two comments of bots.
- **The website.** The check *docs* built the website of every pull request and threw it away, so a pull request of the documentation was reviewed as Markdown.

Rust's triagebot, the changesets bot and the bots of Next.js and Home Assistant keep one comment for all of this.

## Options

1. A comment for each: the coverage bot as it was, and new ones for the release and the website. Every pull request gets more comments, and each its own notifications.
2. Sections that each workflow writes into the comment of the coach. The coach rewrites the whole comment after every workflow, and GitHub has no way to write a comment only if nobody changed it since, so a section could get lost between two writers.
3. The coach builds the whole report itself, in every run: the parts of the pull request after the sections of the checks that failed.

## Decision

Option 3. `blueprint.py coach report` (`blueprint/coach.py`) takes the parts of `blueprint/pr_report.py`:

- **Release:** the part of the version that the type of the title raises as release-please counts it, with the kinds of change that `release-please-config.json` shows in its notes, `bump-minor-pre-major` and `bump-patch-for-minor-pre-major`, against the version of `.release-please-manifest.json` of the default branch and the version of the open release pull request, a branch of the repository named `release-please--…`. A `Release-As:` line wins. Below it, the lines that the pull request adds to a fragment of `changelog.d/` or to `CHANGELOG.md`, from the files of the API, as code, wrapped for reading.
- **Coverage:** the job of the coach fetches the coverage report of the newest finished run of a workflow `CI (…)` for the head, and that of the newest run of the same workflow on `main`, in every run: a run of the coach that waits is replaced by a newer one, so the run after the tests may never come. The job `coverage comment` is gone; the report deletes the old comment of the coverage bot once it carries the table.
- **Website:** the check *docs* keeps the website of a pull request as the artifact `website` for 7 days; the report links it when the pull request changes the website, with the address of each changed page of `docs/` from `site_url` of `mkdocs.yml`.
- **When:** a pull request of a person gets the report when a check failed or when a part is news: a release, an entry of the changelog, a file whose coverage changes, or a change of the website. A pull request of a bot gets no parts and the report only for a check that failed, as before. The job fetches the coverage in every run, also one a bot started, because the bots (update branches, the fix bot, the diagram bot) push to pull requests of people too.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-report-of-a-pull-request.dark.svg">
  <img src="../images/diagrams/the-report-of-a-pull-request.svg" alt="The report of a pull request: A push to a pull request of a person runs the checks, which keep the coverage of the tests and the website that they built as artifacts. After the checks, the PR coach reads the check runs, the title and description, the files, the coverage reports of the pull request and of main and the artifact website from the API, with the release-please files and mkdocs.yml of main, and runs no code of the pull request. It keeps one comment: the checks that failed, the next version with the entry of the changelog, the coverage file by file, and the website with the pages that change. A pull request whose checks pass gets it only when it has something of this to say.">
</picture>

## Consequences

A pull request has at most one comment of the bots, which says before the merge what the merge releases and how the notes read. Pull requests that change nothing of this, most of those of Renovate and the bots, get no comment at all, where they had the coverage comment. The parts follow the coach: they run no code of the pull request, show its text only as code and link only to GitHub and to the website of the repository.

A run of the coach for a pull request of a person asks the API a few more times: for the files of the pull request, the open pull requests once it releases something, the artifacts once it changes the website, and the runs of its commit with two downloads once the tests ended. The coach runs after every workflow of the checks, so this counts against the 1,000 requests an hour that the token of a repository has; most runs of the coach come before the tests end, when the coverage costs one request.

The project workflows of a repository, such as the visual tests of ha-autodarts, still keep comments of their own; a part that a workflow of the project hands to the coach would need the coach to collect it in every run, which is left for later ([#249](https://github.com/Dennis-Otto/repo-blueprint/issues/249)). The release-please files and `mkdocs.yml` are those of the default branch, so a pull request that changes them shows what the default branch would make of it.
