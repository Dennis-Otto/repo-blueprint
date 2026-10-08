# Generate the repositories with Copier and keep them current with a bot

- Status: accepted
- Date: 2026-10-07

## Context

Several repositories of one owner need the same checks, release bot, security workflows and community files. Copied by hand, they drift apart: a fix reaches one repository and not the others.

## Options

1. A GitHub template repository: it copies once and never updates.
2. Reusable workflows in one repository: they share the workflows, but not the community files, the settings or `scripts/check.sh`.
3. A Copier template, whose updates a bot of every repository applies with a three-way merge.

## Decision

Option 3. Copier keeps what a project changed in a file of the blueprint, and `_skip_if_exists` leaves the files of the project alone. The blueprint bot of each repository runs `copier update` every week, on Tuesday morning, and on demand, and opens a pull request with the latest release that merges itself once every check passes. Once a week is enough: the releases of a week arrive as one pull request instead of one each, and a release that can't wait is brought in by running the bot by hand.

## Consequences

Every change for the repositories is a change of the template, released and rolled out like a dependency: within a week of its release, every repository has its pull request. A project change of a file of the blueprint survives updates, but the blueprint owns the file. An adopted repository answers `sample_code` with no.
