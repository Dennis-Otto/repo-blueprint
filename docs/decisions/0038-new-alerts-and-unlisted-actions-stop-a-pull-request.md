# New alerts of code scanning and unlisted actions stop a pull request, and secret scanning looks for generic secrets

- Status: accepted, amended by [0055](0055-what-github-does-not-do-for-a-repository-fails-no-settings-run.md), with which a switch that GitHub doesn't offer or keeps off fails no run, by [0064](0064-an-image-of-docker-runs-with-docker-run.md), with which `settings check` names every step that runs an image with `docker://`, and by [0073](0073-zizmor-analyzes-every-pull-request-and-each-new-alert-stops-the-merge.md), with which zizmor analyzes every pull request and each new alert of it stops the merge
- Date: 2026-10-18

## Context

Three gaps let a pull request bring a problem to `main` that its checks had seen or could have stopped:

- **The required check `codeql` asserts only that the analysis ran,** not that it found nothing. A pull request that added a high alert of CodeQL merged, and the alert showed only afterwards, when the Findings workflow turned `main` red, after the change had run with the secrets of `main` and, in the blueprint, after a release could have brought it to every repository.
- **Any action pinned to a commit could run.** The settings required the pin, but any owner's action was allowed, so a workflow that a pull request, an update of Renovate or a token that leaked changed could start an action that no one had chosen, also inside a large update.
- **Secret scanning looked only for the secrets of its partners,** such as tokens of GitHub or of a cloud. A private key, a connection string or a password that no provider issued went unseen, and the settings as code couldn't switch on the scan of generic patterns.

## Options

1. Keep the Findings workflow as the only gate, after the merge.
2. A rule *code scanning* in the ruleset *Protect main*, the list of the allowed actions in the settings as code, and the generic patterns of secret scanning.
3. As 2, with zizmor and OSV-Scanner in the rule of code scanning too.

## Decision

Option 2.

- **A new alert stops the merge.** *Protect main* has a rule `code_scanning` with CodeQL, from `code_scanning_tools` in `[branch]` of `.github/repository.toml`: a security alert of high or critical severity, or an error, that the pull request adds stops its merge. GitHub compares the analysis of the pull request with that of `main`, so an alert that `main` has already stops nothing. A required tool whose analysis is missing stops the merge as well, so only CodeQL, which analyzes every pull request, is in the rule; zizmor and OSV-Scanner run only on the pull requests that change what they read (decision 0009) and stay behind Findings, and the dependency review already stops a new vulnerable dependency. A project adds a tool or changes the thresholds of one in `.github/repository.project.toml`, where an entry of a tool replaces that of the blueprint; the alerts that its `main` has already, such as those that Findings still reports, stop none of its pull requests.
- **Only listed actions run.** `allowed_actions = "selected"` with `[actions.selected]`: the actions of GitHub (`actions/*`, `github/*`), no other verified creator, and a pattern `owner/repo@*` (with its path, for a reusable workflow or an action in a folder) for each action that a workflow names and each one that these run in turn, such as `oven-sh/setup-bun` of the action of Claude Code. A test renders every kind of project and fails while a workflow names an action that the list lacks, or the list names one that no workflow runs. `blueprint.py settings check` reads the workflows and actions of the repository, follows each composite action and reusable workflow at the commit of its pin, and names every action that the list lacks with the file or the action that runs it; while one does, `settings apply` only adds to the allowed actions on GitHub, also the patterns of a newer release, and never removes one, so that no workflow stops. A project lists its own in `.github/repository.project.toml`, whose list joins that of the blueprint.
- **Generic secrets as well.** `secret_scanning_non_provider_patterns = true` in `[security]`. A switch that GitHub doesn't offer for a repository, which its answer then leaves out, is named with the line that turns it off in `.github/repository.project.toml`, and is never sent, so that the other switches still come on. Validity checks have no switch for a repository in the API, only in the security configurations of an organization, which a repository of a user has none of; they stay out of the settings as code.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-a-pull-request-passes-before-it-merges.dark.svg">
  <img src="../images/diagrams/what-a-pull-request-passes-before-it-merges.svg" alt="What a pull request passes before it merges: A pull request changes code or a workflow. Each workflow starts only when every action that it runs, and every action that these run in turn, is one of GitHub or matches a pattern of the list in the settings as code; a workflow that names another fails to start. The required checks then pass, and CodeQL and zizmor upload their analyses of the pull request. GitHub compares each with that of main: a new alert of CodeQL of high or critical severity, or a new error, stops the merge, and so does every new alert of zizmor; an alert that main has already doesn't. Otherwise the pull request merges.">
</picture>

## Consequences

A pull request that adds a high alert of CodeQL shows the alert at its lines and waits until it is fixed, or until a maintainer dismisses it with the reason; Findings stays the backstop for the tools that aren't in the rule. A new action needs its pattern in the same pull request, and because GitHub checks the list when a workflow starts, its jobs start only once the list is on GitHub: a maintainer runs `python3 .github/blueprint.py settings apply` from the branch, as for a renamed required check, and runs the checks again. A release of the blueprint that adds an action brings its pattern with the update, and the update pull request of each repository waits for the same step, until the update widens the list itself ([#275](https://github.com/Dennis-Otto/repo-blueprint/issues/275)). The images of Docker that a step names with `docker://` match no pattern; they stay pinned by their digest. `settings check` asks GitHub for the file of each action that a workflow runs, about 40 requests for a repository of the blueprint. GitHub names the switch of the generic patterns for the repositories of the blueprint, which are public repositories of a user; should it refuse to turn it on all the same, the run of the settings bot fails and names the refusal, and the line in `[security]` goes back to `false` with a note here.
