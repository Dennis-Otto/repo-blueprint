# An existing repository adopts the blueprint by command

- Status: accepted, follows up [0078](0078-create-checks-what-it-needs-first-and-goes-on-where-it-stopped.md) and [0154](0154-a-classic-branch-protection-is-named-never-removed.md)
- Date: 2026-11-14

## Context

A new copy becomes a repository with `blueprint.py create`, whose preflight checks first what it needs (decision 0078). The other journey of the guide, *An existing repository*, had no command: after `copier copy`, its step 3 asked a person to write the version of the latest release into `version.txt` and `.release-please-manifest.json`, to start `CHANGELOG.md` with `## Unreleased` and to give `.github/labels.toml` the labels of the bots by hand, and step 4 to remove the workflows that the blueprint replaces, without a list of them ([#836](https://github.com/Dennis-Otto/repo-blueprint/issues/836)). A label that is missing lets a bot fail later, and a wrong manifest lets release-please propose the wrong version. Decision 0154 made `settings check` name a classic branch protection, the first part of the issue.

Three questions decide the shape of the command:

- `.github/labels.toml` belongs to the project, and a copied repository has no template to read the labels of the bots from.
- Each kind of release keeps its version in another place: `version.txt` for the kind `simple`, `pyproject.toml` or `package.json` for a Python or Node package.
- The preflight of `create` checks that the name is still free, which a repository that exists never is.

## Options

1. **Keep the steps by hand** in the guide, with a list of the labels and the workflows.
2. **A migration of `migrate --fix`** that adds the labels in every repository on each update.
3. **A command `blueprint.py adopt`** that a person runs once, after `copier copy`, with a preflight of its own.

## Decision

Option 3. `adopt` writes only what is missing, so a second run writes nothing:

- **The version** comes from the tag of the latest release on GitHub, its end such as `1.2.3` of `v1.2.3`, or from `--version X.Y.Z` for a repository whose releases GitHub doesn't have; one without a release stays at `0.0.0`, and its first release is `0.1.0`. release-please reads the version from `.release-please-manifest.json` for every kind of release, so `adopt` writes it there, and into `version.txt` only for the kind `simple` that `release-please-config.json` names, the only kind that has that file. The manifest of a Python or Node package belongs to the project, and release-please writes the next version into it with the release.
- **The changelog** gets `## Unreleased` above the section of its first release.
- **The labels of the bots** are a list in `blueprint/adopt.py`, which every repository gets, and a test keeps it equal to `template/.github/labels.toml.jinja`: those of the group `release`, `maintenance` and `no-bot-fixes`. `adopt` adds those that the file lacks, in a section of its own at its end, and leaves a label of the project with the same name, in any case, as it is.
- **The preflight** asks Python, Git, where origin pushes to, the GitHub CLI, the repository on GitHub and its latest release, and writes nothing while a finding is marked with ✘, as that of `create` does.
- **The workflows** of `.github/workflows/` that `.github/blueprint/owned.txt` doesn't list are named for the maintainer to keep or remove; `adopt` removes none, since only the maintainer knows which of them the blueprint replaces.

A migration (option 2) was not chosen: a repository that the blueprint made has the labels from its first copy, and adding them on every update would bring back a label that a project removed on purpose.

## Consequences

- Step 3 of *An existing repository* is one command, and step 4 starts from its list of the workflows.
- A new label of the bots in the template needs the same label in `LABELS` of `blueprint/adopt.py`, or the test fails.
- `adopt` changes nothing on GitHub: the labels reach GitHub with `settings apply` after the merge, as before, and a classic branch protection stays what `settings apply` names (decision 0154).
