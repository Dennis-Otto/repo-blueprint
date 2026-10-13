# Each pull request writes its entry of the changelog into a file of its own

- Status: accepted
- Date: 2026-10-13

## Context

[Decision 0003](0003-curated-changelog.md) lets every pull request describe its change under `## Unreleased` in `CHANGELOG.md`, and the release bot moves that text into the section of the next release. All these pull requests edit the same lines:

- **Every merge conflicts with the pull requests that wait.** All 12 pull requests that the branch bot ever labeled `merge-conflict` in the blueprint (#29, #43, #46, #47, #48, #52, #55, #57, #58, #63, #78, #104) edited `CHANGELOG.md` right after a commit on `main` that did too, such as the merge of a release, which empties Unreleased. Their auto-merge stopped until a person or an agent merged `main` by hand, and each merge started every check again. With several pull requests at the same time, this was the limit of how fast changes reached `main`.
- **A merge of `main` can put an entry into the wrong section.** The entry of #172 landed in the section of 0.10.2 after a merge of `main` 27 seconds after that release (#183), so 0.10.3 would have shipped without it, and the check passed, because it only asked whether a pull request changes `CHANGELOG.md`.

## Options

1. Keep Unreleased, and let a bot resolve the conflicts. A bot that merges text has to guess where an entry belongs, as Git did in #183.
2. Let the release bot write the notes from the titles of the pull requests alone. Titles are written for developers, the reason for decision 0003.
3. A fragment: each pull request adds a file of its own to `changelog.d/`, such as `changelog.d/dark-mode.md`, with its entries below the headings of their kinds of change. A new file conflicts with nothing. The release bot moves the fragments into the section of the release and deletes them in the same commit of the release pull request, as towncrier, scriv and changesets do.

## Decision

Option 3, next to Unreleased, which keeps working.

- **The check *changelog*** accepts `CHANGELOG.md` or an added fragment in every `feat`, `fix` or `perf` pull request. Since the release reads every fragment, it checks the fragments of every pull request, whatever its type or author, also those of a `docs:` pull request or of a bot. It checks each fragment with `blueprint.py` and `CHANGELOG.md` of the default branch, which read the fragment as text, so that nothing of the pull request runs: a name that the release reads differently, a fragment without an entry, text outside a heading, a heading that would start a section of its own, and a heading that is no kind of change, with the heading that it likely meant. A problem is an annotation at the fragment.
- **The kinds of change** are those of the blueprint (`Breaking changes`, `Features`, `Changes`, `Bug fixes`, `Performance`), those of Keep a Changelog (`Added`, `Changed`, `Deprecated`, `Removed`, `Fixed`, `Security`), and every other heading that `CHANGELOG.md` has already, so that a project keeps its own words, such as `### New`, and a typo such as `### Fixes` fails before the merge.
- **The release** takes in Unreleased first, as it is, and then the fragments: each kind of change below one heading, the kinds that only the fragments bring in the order above, and the entries of each kind by the names of the fragments. The commit that writes `CHANGELOG.md` into the release pull request deletes the fragments that it took in, as far as the branch has them, so that each entry reaches one release once. A prerelease leaves them to the release that follows it, and the notes of a beta show them. A fragment that the release can't take in stops the release bot with the name of the fragment, instead of a release without it.
- **The template** gives every repository `changelog.d/`, and CONTRIBUTING.md shows the format. `CHANGELOG.md` stays the project's own.
- **The bots** write fragments too: the upstream bot of a Nextcloud app writes `changelog.d/nextcloud-<version>.md`, so that its pull request doesn't conflict with a release either.
- **The link check** of a pull request leaves out the fragments, as it leaves out `CHANGELOG.md`; the weekly run checks the links of both.

## Consequences

Pull requests with fragments merge one after another without a conflict, and a release no longer conflicts with the pull requests that wait for it. The section that an entry lands in follows from the release that takes the fragment in, not from where Git merges a line. A pull request with fragments starts one more step in the check *changelog*, a sparse checkout of the default branch, which takes seconds. The website shows the text of Unreleased, but not the fragments, until a release takes them in. A heading with one close kind of change, such as `### Fixes`, is named with its fix in the annotation; once the checks fix their own findings, the check will rename it on the branch of the pull request, and suggest it on a fork.
