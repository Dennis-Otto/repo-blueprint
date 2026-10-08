---
hide:
  - navigation
  - toc
---

# Repo Blueprint

A [Copier](https://copier.readthedocs.io/) template for GitHub repositories that look after themselves: tests on every change, a release bot, security checks, an issue assistant and the settings of the repository as code, for seven kinds of projects, kept current by a bot with every new release of the blueprint.

[Start a repository](#start-a-repository){ .md-button .md-button--primary }
[Read the guide](guide.md){ .md-button }

![The social preview of the blueprint: seven kinds of projects with one standard, and a terminal in which copier copy asks for the kind of project, the checks and bots arrive, blueprint.py settings apply sets the rulesets, environments and labels, and copier update follows every new release](https://raw.githubusercontent.com/Dennis-Otto/repo-blueprint/main/.github/social-preview.png)

## How a repository looks after itself

--8<-- "README.md:loop"

## What a new repository gets

<div class="grid cards" markdown>

- :material-check-all:{ .lg .middle } **Checks**

    ---

    `scripts/check.sh` on every change, the same locally and in the CI: tests with full coverage, types, lint and packaging. The workflows, the license of every file, the Markdown, the sign-off of every commit and the title of every pull request are checked as well.

- :material-shield-lock-outline:{ .lg .middle } **Security**

    ---

    CodeQL, OpenSSF Scorecard, dependency review, a secret scan, SBOMs, the security audit of the workflows and every lock file against the OSV database. Every action is pinned to a commit hash.

- :material-rocket-launch-outline:{ .lg .middle } **Releases**

    ---

    A pull request with the next version, from the titles of the merged pull requests, and the changelog as its notes. Merging it publishes the release with its package, SBOM and signed provenance (SLSA Build Level 3), and verifies it as its users can.

- :material-package-up:{ .lg .middle } **Dependencies**

    ---

    Renovate, which the blueprint runs every two hours: actions, dependencies and images a week after their release, and an update that fixes a vulnerability at once. Routine updates merge themselves once every check passes.

- :material-robot-outline:{ .lg .middle } **Issues**

    ---

    The [issue assistant](https://github.com/Dennis-Otto/issue-assistant): a first analysis of every new issue by an AI that only reads, labels, duplicates, reminders, and closing with the release that ships the fix.

- :material-web:{ .lg .middle } **Website**

    ---

    The documentation in `docs/` as a website with search and a light and a dark theme, in English and German. Every pull request builds it strictly, every change of `main` publishes it on GitHub Pages.

- :material-cog-outline:{ .lg .middle } **Settings as code**

    ---

    Merges, rulesets, security, Actions, environments, variables, labels and GitHub Pages in `.github/repository.toml`. The settings bot applies them after every change and every week.

- :material-update:{ .lg .middle } **Updates**

    ---

    Every week the blueprint bot runs `copier update` and opens a pull request. Without conflicts, it merges itself once every check passes; the files of the project are never overwritten.

- :material-account-group-outline:{ .lg .middle } **Community**

    ---

    README, contributing guide, code of conduct, security policy and security design, governance, issue forms, records of the decisions, and discussions with an announcement of every release.

</div>

The [guide](guide.md#what-a-new-repository-gets) lists every area, with the coverage of every pull request, mutation tests, flaky tests, the clean-up and the dev container as well.

## Kinds of projects

<div class="grid cards" markdown>

- :material-home-assistant:{ .lg .middle } **Home Assistant integration**

    ---

    Ruff, mypy, tests, HACS and hassfest; a zip asset for HACS.

- :simple-nextcloud:{ .lg .middle } **Nextcloud app**

    ---

    php-cs-fixer, Psalm with its taint analysis and PHPUnit with every line covered; a signed package for the App Store.

- :simple-githubactions:{ .lg .middle } **GitHub Action**

    ---

    A composite action with Ruff, mypy, tests and a run of the action; release tags and a moving major tag.

- :material-language-python:{ .lg .middle } **Python package**

    ---

    Ruff, mypy, tests and a build with Hatchling; PyPI with trusted publishing.

- :material-nodejs:{ .lg .middle } **Node package**

    ---

    TypeScript, tsc and node:test with full coverage; npm with provenance.

- :material-docker:{ .lg .middle } **Container image**

    ---

    Alpine by digest, Hadolint, a build and a self-test; GHCR, multi-arch, with SBOM and provenance.

</div>

A repository without a build checks its text files and shell scripts and makes releases only. Every kind starts with a small working example and its tests, to be replaced with the real code. The [guide](guide.md#kinds-of-projects) names the stack of each kind.

## Start a repository

--8<-- "README.md:quick-start"

The guide describes what each repository needs [once](guide.md#once-per-repository), such as the release app, and how [an existing repository](guide.md#an-existing-repository) takes the blueprint.

## Learn more

<div class="grid cards" markdown>

- :material-book-open-variant:{ .lg .middle } **Guide**

    ---

    Everything a new repository gets, the settings as code, the updates and what belongs to a project.

    [:octicons-arrow-right-24: Read the guide](guide.md)

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

    Every public repository of the owner at a glance: the release of the blueprint it is on, its releases, pull requests, runs, Scorecard and health.

    [:octicons-arrow-right-24: Dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/)

</div>
