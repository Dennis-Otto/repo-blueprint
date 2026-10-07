# Repo Blueprint

[![CI](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/ci-python.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/ci-python.yml)
[![Variants](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/variants.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/variants.yml)
[![CodeQL](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/codeql.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/repo-blueprint/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/repo-blueprint)
[![REUSE](https://api.reuse.software/badge/github.com/Dennis-Otto/repo-blueprint)](https://api.reuse.software/info/github.com/Dennis-Otto/repo-blueprint)
[![License: MIT-0](https://img.shields.io/badge/license-MIT--0-blue)](LICENSE)
[![Sponsor](https://img.shields.io/badge/sponsor-%E2%99%A5-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/Dennis-Otto)

A [Copier](https://copier.readthedocs.io/) template for GitHub repositories that look after themselves: tests on every change, a release bot, security checks, an issue assistant and the settings of the repository as code, for seven kinds of projects. A bot brings every repository made from it up to each new release of the blueprint.

<sub>💛 If the blueprint is useful to you, you can [support its development](https://github.com/sponsors/Dennis-Otto). [Deutsche Fassung](README.de.md).</sub>

## What a new repository gets

| Area | What runs | How |
| --- | --- | --- |
| **Checks** | `scripts/check.sh` on every change, the same locally and in the CI: tests with full coverage, types, lint, packaging | the tools of each kind of project, hash-pinned |
| **Lint** | the workflows (actionlint), the license of every file (REUSE), the sign-off of every commit (DCO), the title of every pull request (Conventional Commits) | `lint.yml`, `pull-request-title.yml` |
| **Security** | CodeQL, OpenSSF Scorecard, dependency review, secret scan, SBOM, findings watcher, the security audit of the workflows (zizmor), the network traffic of every job (Harden-Runner) | every action pinned to a commit hash |
| **Releases** | a pull request with the next version, decided from the titles of the merged pull requests (`fix` a patch, `feat` a minor, `!` a major version), and the text of *Unreleased* in the changelog as its notes; merging it publishes the release with its package, SBOM and signed provenance, delivers it, and then verifies it as its users can, also every week | release-please, the release app, immutable releases, `verify-release.yml` |
| **Dependencies** | Dependabot with a week of cooldown; routine updates and releases of dependency updates merge themselves once every check passes | `dependabot.yml`, `dependabot-automerge.yml` |
| **Issues** | a first analysis of every new issue by an AI that only reads, labels, duplicates, reminders, and closing with the release that ships the fix | the [issue assistant](https://github.com/Dennis-Otto/issue-assistant) |
| **Community** | README, contributing guide, code of conduct, security policy, support, governance, issue forms, pull request template, sponsor button, social preview | |
| **Settings** | the settings of the repository as code: merges, rulesets, security, Actions, environments, variables | `.github/repository.toml` and `blueprint.py` |
| **Development** | a dev container for VS Code and GitHub Codespaces with the tools of the checks, and a hook that runs them before every push | `.devcontainer/`, `.githooks/pre-push` |
| **Updates** | every week, the blueprint bot runs `copier update` and opens a pull request | `blueprint-update.yml` |
| **Upstream** | for a Nextcloud app, every week: when Nextcloud has a new major version, a pull request raises `max-version` and merges itself once every check, the end-to-end tests included, passes against it | `upstream.yml` |
| **Branches** | after every change of `main`, the branch bot brings each pull request that waits for auto-merge up to date, so that it merges once its checks pass | `update-branches.yml` |

## Kinds of projects

| Kind | Stack | Checks | Delivery |
| --- | --- | --- | --- |
| Home Assistant integration | Python 3.14, pytest-homeassistant-custom-component | Ruff, mypy, tests, HACS, hassfest | a zip asset for HACS |
| Nextcloud app | PHP 8.2, Composer | php-cs-fixer, Psalm, PHPUnit | signed package to the App Store |
| GitHub Action | Python 3.12 of the runner, composite action | Ruff, mypy, tests, a run of the action | release tags and a moving major tag |
| Python package | Python 3.12, Hatchling | Ruff, mypy, tests, build | PyPI, trusted publishing |
| Node package | Node 24, TypeScript | tsc, node:test with full coverage, pack | npm with provenance |
| Container image | Alpine by digest | Hadolint, build, self-test | GHCR, multi-arch, with SBOM and provenance |
| Repository without a build | | text files, shell scripts | releases only |

Every kind starts with a small working example and its tests: replace it with the real code.

## Start a repository

Copier 9.4 or later, Git, the GitHub CLI and a checkout of the blueprint (for `blueprint.py`):

```sh
copier copy gh:Dennis-Otto/repo-blueprint my-project
cd my-project
git init && git add --all && git commit --signoff --message "chore: start from the blueprint"
gh repo create Dennis-Otto/my-project --public --source . --push
python3 ../repo-blueprint/blueprint.py settings apply
python3 ../repo-blueprint/blueprint.py checklist
```

Copier asks for the name, a one-sentence description, the kind of project, the license (MIT, MIT-0, BSD-3-Clause, Apache-2.0, GPL-3.0-or-later or AGPL-3.0-or-later) and a few details of the kind. `settings apply` sets everything the API can set; `checklist` shows what is left for a person, such as the secrets, and which steps are done.

### Once per repository

- **The release app** opens the release and update pull requests, so that their checks run. Install it on the repository, and set its private key as the secret `RELEASE_AUTOMATION_PRIVATE_KEY` of the environment `release`. The app needs the permissions *Contents*, *Pull requests* and *Workflows* (read and write).
- **The issue assistant** needs `CLAUDE_CODE_OAUTH_TOKEN` in the environment `issue-assistant`.
- **Delivery:** trusted publishing on PyPI or npm, the app certificate of a Nextcloud app, or the HACS submission, as the checklist says.

`checklist` prints the `gh secret set` commands; the value is typed into the prompt of the GitHub CLI and never appears anywhere else.

### An existing repository

An existing repository takes the blueprint on a branch, in one pull request:

1. `copier copy --overwrite --vcs-ref vX.Y.Z gh:Dennis-Otto/repo-blueprint .` with the answers that fit the repository, such as its description, topics and homepage as they are on GitHub, so that `settings apply` changes nothing there. The files of the project (README, changelog, code, tests, manifests, labels, issue forms, icons) stay as they are.
2. Look at the diff of every file of the blueprint and put back what belongs to the project only: sections of SECURITY.md or CONTRIBUTING.md, ecosystems of `dependabot.yml`, hosts of the issue assistant, ignore rules. `copier update` keeps these changes from then on.
3. Write the version of the latest release into `version.txt` and `.release-please-manifest.json`, start `CHANGELOG.md` with `## Unreleased`, and give `.github/labels.toml` the labels of the bots (`autorelease: pending`, `autorelease: tagged`, `merge-conflict`, `maintenance`, `docker`).
4. Put the checks of the project alone, such as its end-to-end tests, into `.github/repository.project.toml` and `scripts/check-project.sh`; remove the workflows, scripts and tests that the blueprint replaces, and delete files of the template that the project doesn't need, such as a sample test.
5. Open the pull request. Once its new checks pass, `blueprint.py settings apply` switches the required checks, the variables and the labels, and the pull request can merge.

## Settings as code

`.github/repository.toml` holds the settings of a repository; `blueprint.py settings check` compares them with GitHub and `settings apply` makes GitHub match:

- **Repository:** squash merges with the title of the pull request, auto-merge, branch updates, deleted branches, signed-off web commits, no wiki or projects.
- **Security:** immutable releases, private vulnerability reporting, Dependabot alerts and security updates, secret scanning with push protection.
- **Actions:** read-only tokens by default, no approvals by workflows, actions pinned to commit hashes, approval for the workflows of every outside contributor.
- **Rulesets:** *Protect main* (pull requests only, squashed, linear history, every required check, no deletion or force push) and *Release tags* (`v*.*.*` never moves).
- **Variables and environments:** `PUBLISH_TO`, the release app, and environments that only `main` may use, with the secrets they need.

`blueprint.py` needs Python 3.12 and the GitHub CLI signed in as an administrator, and nothing else. It never reads or prints the value of a secret. Every repository has a copy in `.github/blueprint.py`, and the settings bot (`settings.yml`) compares its settings with the settings as code every week and after every change of them, so that no repository drifts.

## Updates

The blueprint bot (`blueprint-update.yml`) runs `copier update` every week. Without conflicts its pull request merges itself once every check passes; conflicts stay in it as markers for the maintainer. The repository variable `BLUEPRINT_AUTOMERGE` set to `off` makes every update wait for the maintainer. Run it by hand under *Actions → Blueprint update*, or locally with `copier update`.

The blueprint owns the workflows, `scripts/check.sh` and the community files: their changes arrive with the updates. Files that belong to the project are never overwritten: the README, the changelog, the dependency manifests and lock files (the project's Dependabot keeps them current), the code and the tests, the issue forms, the labels and accepted findings. Checks of a project alone belong in `scripts/check-project.sh`, which `scripts/check.sh` runs last.

## What belongs to a project

The blueprint keeps the shared parts of every repository equal; a project adds its own without forking them:

- **Changes in the blueprint's files survive updates:** `copier update` merges the changes of the blueprint with those of the repository, line by line, and marks a conflict only where both changed the same lines.
- **Settings of the project alone** go into `.github/repository.project.toml`, such as the checks of its end-to-end tests or an environment with its secrets. `blueprint.py` and the settings bot add them to `.github/repository.toml`.
- **Checks of the project alone** go into `scripts/check-project.sh`, which `scripts/check.sh` runs last; **workflows of the project alone** are workflow files of their own.
- **Several copyright holders,** such as the authors of a fork, are the answer `copyright`, separated by semicolons; LICENSE and REUSE.toml name each of them.
- **Files under another license,** such as third-party artwork, get a `.license` file next to them, as REUSE describes.
- **The package of a Nextcloud app** is checked by `scripts/check-package.sh ARCHIVE unsigned|signed` if the project has one: `scripts/check.sh` runs it on the package that krankerl builds, the release on the package before and after signing.
- **The version in other lines of a file of the release,** such as the tag in the URL of a screenshot in `appinfo/info.xml`, follows each release when the line ends with the comment `x-release-please-version`, such as `<!-- x-release-please-version -->`.

## Tools in every repository

- `bash scripts/check.sh`: the checks of the CI, locally.
- `bash scripts/social-preview.sh`: renders `.github/social-preview.html` into the 1280×640 image that GitHub shows for links to the repository; upload it under *Settings → Social preview*.

## Dashboard

[The dashboard](https://dennis-otto.github.io/repo-blueprint/) shows every public repository of the owner at a glance: the release of the blueprint it is on, its latest release and the pull request of the next one, its open pull requests and those in conflict, the last run of its main workflows on `main`, and its OpenSSF Scorecard. The Dashboard workflow builds it with `dashboard.py` every six hours and publishes it on GitHub Pages. It shows only what is public anyway, no finding of code scanning and no alert of Dependabot.

## How the blueprint works

- `copier.yml` holds the questions. `template/` holds the files of a new repository; a file or folder name such as `[% if stack == 'php' %]composer.json[% endif %]` carries its condition, and a name that renders empty is left out. The delimiters `{= =}` and `[% %]` appear in no workflow, script or manifest, so `${{ }}` of GitHub Actions and `[[ ]]` of Bash and TOML stay as they are.
- The workflows in `.github/workflows/` run in this repository and are the templates of the workflows of every new repository: actionlint lints them and Dependabot keeps their actions current here. A line marked *Not in the blueprint itself* switches a job off in this repository and disappears in new ones.
- `stacks/` holds the dependency manifests and lock files of each kind of project, which Dependabot keeps current; a new project starts from them.
- `tests/` checks `blueprint.py` against a simulated GitHub and renders every kind of project; the Variants workflow renders each one and runs its own checks with its real tools.

Contributions are welcome: see [CONTRIBUTING.md](CONTRIBUTING.md). Questions and problems: [SUPPORT.md](SUPPORT.md). Report vulnerabilities privately, as [SECURITY.md](SECURITY.md) describes.

## License

[MIT No Attribution](LICENSE): repositories made from the blueprint owe it nothing, not even a notice. Every file names its license in the machine-readable form of [REUSE](https://reuse.software).
