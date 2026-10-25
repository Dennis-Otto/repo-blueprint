# Repo Blueprint

[![Documentation](https://img.shields.io/badge/docs-dennis--otto.github.io-526cfe?logo=materialformkdocs&logoColor=white)](https://dennis-otto.github.io/repo-blueprint/)
[![CI](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/ci-python.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/ci-python.yml)
[![Variants](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/variants.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/variants.yml)
[![CodeQL](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/codeql.yml/badge.svg)](https://github.com/Dennis-Otto/repo-blueprint/actions/workflows/codeql.yml)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/repo-blueprint/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/repo-blueprint)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15284/badge)](https://www.bestpractices.dev/projects/15284)
[![REUSE](https://api.reuse.software/badge/github.com/Dennis-Otto/repo-blueprint)](https://api.reuse.software/info/github.com/Dennis-Otto/repo-blueprint)
[![License: MIT-0](https://img.shields.io/badge/license-MIT--0-blue)](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE)
[![Sponsor](https://img.shields.io/badge/sponsor-%E2%99%A5-db61a2?logo=githubsponsors&logoColor=white)](https://github.com/sponsors/Dennis-Otto)

<!-- --8<-- [start:pitch] -->

**GitHub repositories that test, release, secure and update themselves — from one `copier copy`.**

Repo Blueprint is a [Copier](https://copier.readthedocs.io/) template for eight kinds of projects: Home Assistant integrations, Nextcloud apps, GitHub Actions, Python and Node packages, Chrome extensions, container images and repositories without a build. A new repository starts with more than 30 workflows, and a bot brings it up to every new release of the blueprint.

- **Tested on every change.** `scripts/check.sh` runs the same checks on your machine and in the CI, with full coverage of the code. The PR coach explains every check that fails, and the fix bot commits what a command can fix.
- **Released and signed by a bot.** Merging the release pull request publishes the release with its SBOM and the signed provenance of SLSA Build Level 3, and then verifies it as its users can.
- **Secure from the first commit.** CodeQL, OpenSSF Scorecard, a secret scan and an audit of the workflows run from the start, every action is pinned to a commit hash, and about 90 to 100 answers of OpenSSF Best Practices are filled in.
- **Up to date by itself.** Renovate updates the dependencies, the settings bot keeps the settings as code, and the blueprint bot brings every release of the blueprint as a pull request that its checks test before it merges; each public repository [made with the blueprint](#made-with-the-blueprint) takes every release this way.

<!-- --8<-- [end:pitch] -->

The [website of the blueprint](https://dennis-otto.github.io/repo-blueprint/) has the guide and a page for each group of what a new repository gets, in English and German, with [the comparison](https://dennis-otto.github.io/repo-blueprint/compare.html) with other templates, a page for each kind of project, the questions and answers, the troubleshooting, the architecture, the reference of every question, variable and secret, the roadmap, the security design, the automation, the decisions and the dashboard.

<sub>💛 If the blueprint is useful to you, you can [support its development](https://github.com/sponsors/Dennis-Otto). [Deutsche Fassung](https://github.com/Dennis-Otto/repo-blueprint/blob/main/README.de.md).</sub>

## Start a repository

<!-- --8<-- [start:quick-start] -->

Git, Python 3.12 or later, [uv](https://docs.astral.sh/uv/) and GitHub CLI 2.48 or later, signed in as an administrator of the account or organization that will own the repository (`gh auth login`):

```sh
uvx --from copier==9.19.0 copier copy gh:Dennis-Otto/repo-blueprint my-project
cd my-project
python3 .github/blueprint.py create
```

![copier copy in the terminal: Copier clones the blueprint and asks for the name Paperless Sync, the repository, a description, the kind of project, Python package, and the owner Dennis-Otto, takes the defaults for the rest, including the release app, writes the files and names the one command after it; the new repository has its community files, its checks and its workflows, and a dry run of python3 .github/blueprint.py create shows the commands that make it the repository on GitHub](docs/images/copier-copy.gif)

With pipx in place of uv, the first line is `pipx run --spec copier==9.19.0 copier copy gh:Dennis-Otto/repo-blueprint my-project`, and a Copier of your own, Copier 9.8 or later, runs `copier copy gh:Dennis-Otto/repo-blueprint my-project`; on Windows, `py -3` runs Python in place of `python3`. Copying runs no code of the blueprint: the template has no tasks, migrations or Jinja extensions, so Copier needs no `--trust`.

Copier asks for the name, a one-sentence description, the kind of project, the GitHub account or organization that owns it, the license (MIT, MIT-0, BSD-3-Clause, Apache-2.0, GPL-3.0-or-later or AGPL-3.0-or-later), a few details of the kind and the release app of the owner, which may stay empty until the checklist has registered it. The homepage is the website that the Docs workflow publishes on GitHub Pages, unless you name another or none, and the README, the About box, the issue forms, the manifest of an integration and `appinfo/info.xml` of an app link it; each kind starts with topics of its own, such as `home-assistant, hacs` for an integration, which HACS needs to list it. Copier refuses an answer that would break a file: a description or a name with `"""`, `*/`, `]]>` or a backslash, which would end a docstring of Python, a comment of TypeScript or the CDATA of `appinfo/info.xml`, a Nextcloud app id that the App Store doesn't take, and topics that GitHub doesn't.

`create` makes the repository of the copy, with no checkout of the blueprint: every copy brings `blueprint.py` in `.github/`. It takes the owner and the name from the answers of Copier, and its preflight first checks Python, Git, GitHub CLI and its sign-in, the owner and the name; a finding marked with ✘ stops it before anything is made, with the command that fixes it. Then `create` runs `git init --initial-branch=main`, commits the files with a sign-off, creates the repository with `gh repo create` and pushes to it, public unless you add `--private` ([green on GitHub Free too](https://dennis-otto.github.io/repo-blueprint/faq.html#can-a-repository-be-private-and-what-does-it-cost)), then applies the settings as code and prints the checklist: what is left for a person, such as the release app and the secrets, and which steps are done. `--dry-run` prints the preflight and the commands and runs none. A run that stopped midway goes on where it stopped when you run `create` again. A folder that pushes to another repository is no new copy, and `create` refuses it. The [troubleshooting](https://dennis-otto.github.io/repo-blueprint/troubleshooting.html) explains each finding of the preflight. Every workflow runs on `main`, so `settings check` names a repository whose default branch has another name.

<!-- --8<-- [end:quick-start] -->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-new-repository-starts.dark.svg">
  <img src="docs/images/diagrams/how-a-new-repository-starts.svg" alt="How a new repository starts: copier copy writes the files of the project and runs no code of the blueprint. python3 .github/blueprint.py create, which every copy brings, makes the first commit on the branch main with a sign-off, creates the repository with gh repo create and pushes to it, applies the settings as code and shows the checklist. You take the steps that only a person can take, such as the release app and the secrets, and then the checks and the bots run.">
</picture>

## Made with the blueprint

<!-- --8<-- [start:made-with] -->

Six public repositories follow the blueprint, each with code of its own and the checks and bots of the blueprint; every release of the blueprint reaches them as a pull request:

- **[HomeDarts for Autodarts](https://github.com/Dennis-Otto/homedarts-for-autodarts)**, a Home Assistant integration: local real-time board control, games, tournaments and statistics, without a cloud account. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/homedarts-for-autodarts/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/homedarts-for-autodarts)
- **[Player Switch for Autodarts](https://github.com/Dennis-Otto/player-switch-for-autodarts)**, a Chrome extension in TypeScript: a shared Autodarts display where everyone plays under their own account and a tap on a tile switches players, without signing in again. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/player-switch-for-autodarts/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/player-switch-for-autodarts)
- **[Issue assistant](https://github.com/Dennis-Otto/issue-assistant)**, a GitHub Action: a first analysis of every new issue by an AI that only reads, checked by a job without AI before it posts. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/issue-assistant/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/issue-assistant)
- **[Paperless Sync](https://github.com/Dennis-Otto/paperless-sync)**, a Nextcloud app: the documents of Paperless-ngx in Nextcloud Files, by correspondent, type and year. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/paperless-sync/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/paperless-sync)
- **[Paperless Unified Search](https://github.com/Dennis-Otto/paperless-unified-search)**, a Nextcloud app: the full-text search of Paperless-ngx in the unified search of Nextcloud. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/paperless-unified-search/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/paperless-unified-search)
- **[dennis-otto.github.io](https://github.com/Dennis-Otto/dennis-otto.github.io)**, a repository without a build: the website with every project of its owner. [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/Dennis-Otto/dennis-otto.github.io/badge)](https://scorecard.dev/viewer/?uri=github.com/Dennis-Otto/dennis-otto.github.io)

[The dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) shows each of them at a glance: the release of the blueprint it is on, its checks, its releases and its Scorecard.

<!-- --8<-- [end:made-with] -->

## Why Repo Blueprint

<!-- --8<-- [start:why] -->

- **Rather than a template repository of GitHub:** *Use this template* copies the files once, without the settings, and nothing follows them later. The blueprint sets the rulesets, the security and the environments as code, and brings every improvement as a pull request.
- **Rather than Cookiecutter and cruft:** the hooks of a Cookiecutter template run code on your machine, and `cruft update` waits until someone runs it. Copier runs none of the blueprint's code, so it needs no `--trust`; `blueprint.py create`, which you run next, is a file of the copy that you can read first. And the bot of the blueprint updates every repository by itself.
- **Rather than another Copier template,** such as copier-uv or scientific-python/cookie, which serve Python projects well: the blueprint brings one standard to Home Assistant, Nextcloud, GitHub Actions, Node and containers too, with signed releases of SLSA Build Level 3, SBOMs and VEX, and tests each release on every kind and on the real repositories before it rolls out.
- **Rather than projen:** projen writes the files of a project from code that runs at every synthesis, above all for TypeScript, AWS CDK and jsii. The blueprint needs no code of its own in the project: it keeps its own files current and leaves those of the project to you.

[The comparison](https://dennis-otto.github.io/repo-blueprint/compare.html) puts them side by side, also where another tool fits better.

<!-- --8<-- [end:why] -->

## Kinds of projects

<!-- --8<-- [start:kinds] -->

| Kind | Stack | Checks | Delivery |
| --- | --- | --- | --- |
| [Home Assistant integration](https://dennis-otto.github.io/repo-blueprint/kinds/home-assistant.html) | Python 3.14, pytest-homeassistant-custom-component | Ruff, mypy, tests, HACS, hassfest | a zip asset for HACS, verified as HACS installs it |
| [Nextcloud app](https://dennis-otto.github.io/repo-blueprint/kinds/nextcloud-app.html) | PHP 8.2 and newer, the tools on PHP 8.3, Composer | php-cs-fixer, Psalm with its taint analysis, PHP 8.2 for the code and its packages, PHPUnit in random order with full coverage | signed package to the App Store |
| [GitHub Action](https://dennis-otto.github.io/repo-blueprint/kinds/github-action.html) | Python 3.12 of the runner, composite action | Ruff, mypy, tests, a run of the action | release tags and a moving major tag |
| [Python package](https://dennis-otto.github.io/repo-blueprint/kinds/python-package.html) | Python 3.12, Hatchling | Ruff, mypy, tests, build | PyPI, trusted publishing |
| [Node package](https://dennis-otto.github.io/repo-blueprint/kinds/node-package.html) | Node 24, TypeScript | Biome, tsc, node:test with full coverage, pack; npm without install scripts | npm with provenance |
| [Chrome extension](https://dennis-otto.github.io/repo-blueprint/kinds/chrome-extension.html) | Manifest V3, TypeScript | Node's, the manifest, Chrome for Testing | Chrome Web Store, without a stored secret |
| [Container image](https://dennis-otto.github.io/repo-blueprint/kinds/container.html) | Alpine by digest | Hadolint, build, self-test | GHCR, multi-arch, with SBOM and provenance |
| [Repository without a build](https://dennis-otto.github.io/repo-blueprint/kinds/generic.html) | | text files, shell scripts | releases only |

Every kind starts with a small working example and its tests, to replace with the real code, and has a page of its own on the website: what it gets, the checks its pull requests need, its delivery, its checklist and the one line that copies it.

<!-- --8<-- [end:kinds] -->

![Repo Blueprint for GitHub repositories: eight kinds of projects with one standard, and a terminal in which copier copy asks for the kind of project, the checks and bots arrive, blueprint.py settings apply sets the rulesets, environments and labels, and copier update follows every new release](docs/images/social-preview.webp)

## How a repository looks after itself

<!-- --8<-- [start:loop] -->

Every change, yours or a bot's, is a pull request that merges once every check passes, and the release bot makes a signed release of what reaches `main`; three bots keep the repository current on their own. In the pictures, blue is the blueprint and its bots, orange is you and what is yours, and green is what comes out.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/how-a-repository-looks-after-itself.dark.svg">
  <img src="docs/images/diagrams/how-a-repository-looks-after-itself.svg" alt="How a repository looks after itself: copier copy makes a repository from the blueprint. Every change, yours or a bot's, is a pull request that merges once every check passes, and the release bot makes a signed release of what reaches main. Renovate, the blueprint bot and the settings bot keep the repository current on their own.">
</picture>

The website of every repository shows all of it on the page *Automation*, which it writes from the workflows at every build: what each one does and what starts it, which checks a pull request needs, and which workflows hold a secret.

<!-- --8<-- [end:loop] -->

## What a new repository gets

Each group has a page of its own, with what runs, the files that run it and the details.

### [Checks and the PR coach](docs/features/checks.md)

- **Checks:** `scripts/check.sh` runs the tests with full coverage, the types, the lint and the packaging, the same locally and in the CI.
- **Lint:** The workflows, the license of every file, the Markdown, and the spelling and style of the changed documents.
- **Coverage:** The report of a pull request compares the coverage of each file with that of `main`.
- **Fast checks:** A scanner runs only in the pull requests that change what it reads, and the rest of the scans every week.
- <a id="the-pr-coach"></a>**PR coach:** Every check that fails says what it found, why that matters and how to fix it, in one comment that follows every push, also on forks.

### [Fix bot and self-healing](docs/features/self-healing.md)

- **Fix bot:** A check that fails fixes what a command can fix, such as the format of the code, and commits it onto the branch.
- **Flaky tests:** Failed test jobs run once more, and a job that passes then is reported in one issue.
- **Cancelled checks:** A required check that a late run for an older commit cancelled starts again by itself.
- **Failed releases:** The release of a merge that fails for a moment runs its failed jobs once more.
- **Bot health:** A bot that fails on `main` tries once more where that can help, and otherwise keeps one issue per workflow open, unless the workflow keeps its own.

### [Mutation tests, fuzzing and property tests](docs/features/tests.md)

- **Mutation tests:** Every week, thousands of small changes of the code show which of them the tests don't notice.
- **Fuzzing:** A Python package or a GitHub Action fuzzes every target in `fuzz/`, in pull requests and every week.
- **Property tests:** The property tests of Python and Home Assistant projects run every night with new random inputs.

### [Releases and security](docs/features/releases.md)

- **Releases:** A pull request with the next version and its changelog, and signed releases with provenance and SBOMs.
- **Security:** CodeQL, OpenSSF Scorecard, the review of the dependencies and the scanners of each kind of project.
- **App Store:** A Nextcloud app registers its id with its certificate, once, by hand.

### [Dependencies and updates](docs/features/updates.md)

- **Dependencies:** Renovate updates the dependencies a few times a day, as the release app of the owner.
- **Updates:** Right after every release of the blueprint, and every week, the blueprint bot opens a pull request with `copier update`.
- **Upstream:** A Nextcloud app gets a pull request that raises `max-version` once a new major version of Nextcloud passes every check.

### [Bots, their cost and the dashboard](docs/features/bots.md)

- **Issues:** The issue assistant, an AI that only reads, analyses every new issue, labels it and finds duplicates.
- **Welcome:** A person's first pull request gets a comment with what helps it along.
- **Area labels:** Every pull request gets the labels of the areas whose files it changes.
- **Branches:** The branch bot brings the pull requests that wait for auto-merge up to date with `main`, one at a time.
- **Clean-up:** Every week, the merged branches and the caches of closed pull requests go.
- **Dashboard:** One page shows every repository of the owner, the release of the blueprint it is on and the state of its checks.

### [Website, diagrams and screenshots](docs/features/website.md)

- **Website:** The documentation in `docs/` as a website with search and a light and a dark theme, in English and German.
- **Diagrams:** Every diagram is a picture of its Mermaid source, so that the GitHub app shows it too.
- **Screenshots:** A bot renews the pictures of the project, only when their pixels change.

### [Settings as code](docs/features/settings.md)

- **Settings:** Merges, rulesets, security, Actions, environments, variables and labels in `.github/repository.toml`, which the settings bot applies.

### [Community and development](docs/features/development.md)

- **Community:** README, contributing guide, code of conduct, security policy and the security design of the software.
- **Development:** A dev container for VS Code and Codespaces, and a hook that runs the checks before every push.
- **Coding agents:** The rules of the repository for Claude Code, Codex, GitHub Copilot and Cursor, in `AGENTS.md`.
- **Tools:** `scripts/check.sh`, `scripts/diagrams.sh` and `scripts/social-preview.sh`, the same in every repository.

## Set up a repository

What a person does once: the release app of the account and its defaults, the secrets and the delivery of each repository, and the way an existing repository takes the blueprint. [The guide](https://dennis-otto.github.io/repo-blueprint/guide.html#set-up-a-repository) walks through each of them.

## How the blueprint works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/images/diagrams/the-path-of-a-release.dark.svg">
  <img src="docs/images/diagrams/the-path-of-a-release.svg" alt="The path of a release of the blueprint: A pull request merges into main of the blueprint, and the Release workflow keeps the release pull request with the next version. Its merge, by the maintainer or by itself when it holds only updates, publishes the release with a signed tag and verifies it. The Rollout workflow then starts the blueprint bot of every repository that takes the blueprint. Each bot verifies the release, runs copier update and keeps one update pull request as the release app, so that the checks of the repository run. Without conflicts it merges itself once they pass; with conflicts, or with BLUEPRINT_AUTOMERGE set to off, it waits for the maintainer. The dashboard shows the release of the blueprint that each repository is on.">
</picture>

[The architecture](https://dennis-otto.github.io/repo-blueprint/architecture.html) shows how the blueprint is built, from `copier.yml` and `template/` to the workflows that it shares with every repository and the tests that try each change on every kind of project, and the path of a release from a merge to the update of every repository. The reference describes [every question of Copier](https://dennis-otto.github.io/repo-blueprint/reference/questions.html) and [every variable and secret](https://dennis-otto.github.io/repo-blueprint/reference/variables.html), written by `reference.py` from the sources that they describe, so that they can't drift. When something is unclear or doesn't work, see [the questions and answers](https://dennis-otto.github.io/repo-blueprint/faq.html) and [the troubleshooting](https://dennis-otto.github.io/repo-blueprint/troubleshooting.html).

Where the blueprint is heading: [the roadmap](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/roadmap.md). What it protects and trusts: [its security design](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/security.md).

Contributions are welcome: see [CONTRIBUTING.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/CONTRIBUTING.md). Questions and problems: [SUPPORT.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SUPPORT.md). Report vulnerabilities privately, as [SECURITY.md](https://github.com/Dennis-Otto/repo-blueprint/blob/main/SECURITY.md) describes.

## License

[MIT No Attribution](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE): repositories made from the blueprint owe it nothing, not even a notice. Every file names its license in the machine-readable form of [REUSE](https://reuse.software).
