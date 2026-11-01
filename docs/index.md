---
hide:
  - navigation
  - toc
---

# Repo Blueprint

--8<-- "README.md:pitch"

[Start a repository](#start-a-repository){ .md-button .md-button--primary }
[Compare](compare.md){ .md-button }
[Read the guide](guide.md){ .md-button }

![The social preview of the blueprint: eight kinds of projects with one standard, and a terminal in which copier copy asks for the kind of project, the checks and bots arrive, blueprint.py settings apply sets the rulesets, environments and labels, and copier update follows every new release](images/social-preview.webp)

## How a repository looks after itself

--8<-- "README.md:loop"

## What a new repository gets

<div class="grid cards" markdown>

- :material-check-all:{ .lg .middle } **Checks**

    ---

    `scripts/check.sh` on every change, the same locally and in the CI: tests with full coverage, on every core in Python projects, types, lint and packaging. The workflows, the license of every file, the Markdown, the sign-off of every commit, the signature of every commit where the rules require one and the title of every pull request are checked as well. A passing error of a download fails no run: every download tries again.

- :material-lightbulb-on-outline:{ .lg .middle } **PR coach**

    ---

    Every check that fails says what it found, why that matters and how to fix it, with the commands to run: in the check, and in one comment on the pull request that follows every push, also on a pull request from a fork. What a command can fix, the pull request fixes by itself: the fix bot commits it, suggests it on a fork, and keeps `main` fixed.

- :material-shield-lock-outline:{ .lg .middle } **Security**

    ---

    CodeQL, the taint analysis of Psalm for the PHP of a Nextcloud app, OpenSSF Scorecard, dependency review, a secret scan, SBOMs of what each release ships, the security audit of the workflows, every lock file against the OSV database and the answers of OpenSSF Best Practices that the blueprint guarantees. Every action is pinned to a commit hash.

- :material-rocket-launch-outline:{ .lg .middle } **Releases**

    ---

    A pull request with the next version, from the titles of the merged pull requests, and the changelog as its notes. Merging it publishes the release with its package, SBOM and signed provenance (SLSA Build Level 3, Level 2 for a container image), and verifies it as its users can.

- :material-package-up:{ .lg .middle } **Dependencies**

    ---

    Renovate, which the blueprint runs a few times a day: actions, dependencies and images a week after their release, on Mondays, and at once an update that fixes a vulnerability or the new commit of a branch that an action follows. Routine updates merge themselves once every check passes; the weekly refresh of every lock file waits for the maintainer as a pull request. Renovate keeps no issue open.

- :material-robot-outline:{ .lg .middle } **Issues**

    ---

    The [issue assistant](https://github.com/Dennis-Otto/issue-assistant): a first analysis of every new issue by an AI that only reads, labels, duplicates, reminders, and closing with the release that ships the fix. Each new release of the assistant reaches every repository by itself, once a bot has verified that its release workflow made it. A bot that fails on `main` opens one issue of its own, which closes once the bot passes again.

- :material-web:{ .lg .middle } **Website**

    ---

    The documentation in `docs/` as a website with search and a light and a dark theme, in English and German. Every pull request builds it strictly and checks every link and anchor of the built pages, every change of `main` publishes it on GitHub Pages and signs it.

- :material-sitemap-outline:{ .lg .middle } **Diagrams**

    ---

    Every diagram as a picture that every reader sees, also in the GitHub app and the stores, drawn from its Mermaid source; the website shows the same pictures, so a page with a diagram stays light. The bots fix them by themselves: in a pull request, on `main` and after an update of the renderer.

- :material-camera-outline:{ .lg .middle } **Screenshots**

    ---

    The pictures of the project renew themselves: after a change of what they show, after every release and every week, the screenshot bot runs `scripts/screenshots.sh` and keeps one pull request with the pictures whose pixels changed, which merges itself. A new repository photographs its website and, by its kind, its integration or its app from the start.

- :material-cog-outline:{ .lg .middle } **Settings as code**

    ---

    Merges, rulesets, security, Actions, environments, variables, labels and GitHub Pages in `.github/repository.toml`. The settings bot applies them after every change and every week.

- :material-update:{ .lg .middle } **Updates**

    ---

    After every release and every week, the blueprint bot verifies the release, which must be immutable and signed by the release workflow of the blueprint, then runs `copier update` and keeps one pull request current. Without conflicts, it merges itself once every check passes; the files of the project and your commits on its branch are never overwritten.

- :material-account-group-outline:{ .lg .middle } **Community**

    ---

    README, contributing guide, code of conduct, security policy and security design, governance, issue forms, records of the decisions, and discussions with an announcement of every release.

- :material-head-cog-outline:{ .lg .middle } **Coding agents**

    ---

    `AGENTS.md` gives Claude Code, Codex, GitHub Copilot and Cursor the commands, the rules of pull requests and the changelog, and which files belong to the project and which to the blueprint. The notes of the project join it from `.github/agents.project.md`.

</div>

The [guide](guide.md#what-a-new-repository-gets) lists every area, with the PR coach, the coverage of every pull request, mutation tests, flaky tests, cancelled checks, failed releases, the clean-up and the dev container as well.

## Kinds of projects

<div class="grid cards" markdown>

- :material-home-assistant:{ .lg .middle } **Home Assistant integration**

    ---

    Ruff, mypy, tests, HACS and hassfest; a zip asset for HACS.

    [:octicons-arrow-right-24: Home Assistant integration](kinds/home-assistant.md)

- :simple-nextcloud:{ .lg .middle } **Nextcloud app**

    ---

    php-cs-fixer, Psalm with its taint analysis and PHPUnit in random order with every line covered, the tools on PHP 8.3 and the code on PHP 8.2 as well; a signed package for the App Store.

    [:octicons-arrow-right-24: Nextcloud app](kinds/nextcloud-app.md)

- :simple-githubactions:{ .lg .middle } **GitHub Action**

    ---

    A composite action with Ruff, mypy, tests and a run of the action; release tags and a moving major tag.

    [:octicons-arrow-right-24: GitHub Action](kinds/github-action.md)

- :material-language-python:{ .lg .middle } **Python package**

    ---

    Ruff, mypy, tests and a build with Hatchling; PyPI with trusted publishing.

    [:octicons-arrow-right-24: Python package](kinds/python-package.md)

- :material-nodejs:{ .lg .middle } **Node package**

    ---

    TypeScript, Biome, tsc and node:test with full coverage; npm with provenance.

    [:octicons-arrow-right-24: Node package](kinds/node-package.md)

- :material-google-chrome:{ .lg .middle } **Chrome extension**

    ---

    Manifest V3 in TypeScript, the manifest checked against the store and loaded in Chrome for Testing; every release to the Chrome Web Store, without a stored secret.

    [:octicons-arrow-right-24: Chrome extension](kinds/chrome-extension.md)

- :material-docker:{ .lg .middle } **Container image**

    ---

    Alpine by digest, Hadolint, a build and a self-test; GHCR, multi-arch, with SBOM and provenance.

    [:octicons-arrow-right-24: Container image](kinds/container.md)

- :material-file-document-multiple-outline:{ .lg .middle } **Repository without a build**

    ---

    The text files and shell scripts are checked, and the releases come without a package.

    [:octicons-arrow-right-24: Repository without a build](kinds/generic.md)

</div>

Every kind starts with a small working example and its tests, to be replaced with the real code. The [guide](guide.md#kinds-of-projects) names the stack of each kind.

## Start a repository

--8<-- "README.md:quick-start"

The guide describes how [your own account](guide.md#your-own-account) gets its release app and keeps its answers, and the page [Your own account](own-account.md) walks through a repository of your own step by step, with Renovate in the repository or as the Mend app and the issue assistant with or without AI; the guide also says what each repository needs [once](guide.md#once-per-repository), and how [an existing repository](guide.md#an-existing-repository) takes the blueprint.

## Made with the blueprint

--8<-- "README.md:made-with"

## Why Repo Blueprint

--8<-- "README.md:why"

## Learn more

<div class="grid cards" markdown>

- :material-book-open-variant:{ .lg .middle } **Guide**

    ---

    Everything a new repository gets, the settings as code, the updates and what belongs to a project.

    [:octicons-arrow-right-24: Read the guide](guide.md)

- :material-compare-horizontal:{ .lg .middle } **Comparison**

    ---

    The blueprint beside GitHub template repositories, Cookiecutter with cruft, other Copier templates and projen, also where they fit better.

    [:octicons-arrow-right-24: Comparison](compare.md)

- :material-map-marker-path:{ .lg .middle } **Roadmap**

    ---

    Where the blueprint is heading in the next twelve months, and what it will not do.

    [:octicons-arrow-right-24: Roadmap](roadmap.md)

- :material-shield-search:{ .lg .middle } **Security design**

    ---

    What the blueprint protects, what it trusts, the threats with their countermeasures, and the risks that remain.

    [:octicons-arrow-right-24: Security design](security.md)

- :material-scale-balance:{ .lg .middle } **Decisions**

    ---

    The decisions that shape the blueprint, each with its reasons.

    [:octicons-arrow-right-24: Decisions](decisions/README.md)

- :material-history:{ .lg .middle } **Releases and changelog**

    ---

    Every release with its notes on GitHub, and the changes of each version.

    [:octicons-arrow-right-24: Releases](https://github.com/Dennis-Otto/repo-blueprint/releases) · [Changelog](changelog.md)

- :material-view-dashboard-outline:{ .lg .middle } **Dashboard**

    ---

    Every public repository of the owner at a glance: the release of the blueprint it is on, its releases, pull requests, runs, website, Scorecard and health, with the same data as JSON and a feed of every release.

    [:octicons-arrow-right-24: Dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) · [JSON](https://dennis-otto.github.io/repo-blueprint/dashboard/repos.json) · [Feed](https://dennis-otto.github.io/repo-blueprint/dashboard/releases.atom)

</div>
