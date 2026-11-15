# scripts/check.sh lints the Markdown on your machine, and leaves it to lint in the CI

- Status: accepted
- Date: 2026-11-15

## Context

The check *lint* runs markdownlint-cli2 on `**/*.md`, by the rules of `.markdownlint.jsonc`, with the action of markdownlint-cli2, while `scripts/check.sh` had no such step. A pull request passed every step of `scripts/check.sh` and the hook before a push, and still failed *lint* on its first push: Dennis-Otto/player-switch-for-autodarts#279 did, on a line of a record of a decision that started with `#278).`, which markdownlint reads as a heading without its space (MD018) and which no fix of the bot repairs ([issue 932](https://github.com/Dennis-Otto/repo-blueprint/issues/932)). `AGENTS.md` says that `scripts/check.sh` runs the same checks as the CI. The comment of the Lint workflow gave `npx markdownlint-cli2@0.23.2` for a local run, while the Variants workflow lints the rendered projects with the image of v0.24.0, the version of the action.

## Options

1. A step of `scripts/check.sh` that runs `npx markdownlint-cli2` itself: the version stays a second pin that nothing keeps current, and every job of the CI that runs `scripts/check.sh` downloads it once more, beside the check *lint* of the same pull request.
2. A tool of `blueprint.py`: it would need Python 3.12 as well as Node or Docker, and the step would skip on a machine without Python that has Node.
3. A script of the blueprint, `scripts/markdownlint.sh`, which every repository gets, with the image of markdownlint-cli2 by tag and digest, which Renovate keeps current with that of the Variants workflow, and the version of npx from its tag. It runs with Node 22 or newer through npx, which needs the network only until its cache has the version, or else with Docker, which pulls the image once; without either, it says so and leaves the check to the CI. `--fix` fixes what markdownlint can fix. In the CI it lints nothing, since *lint* lints the same files with the same version in the same pull request and its fix bot fixes them.

## Decision

Option 3. The step *Markdown* of `scripts/check.sh`, after *Pages in one column*, runs `bash scripts/markdownlint.sh`, and its explanation in `.github/checks.toml` gives `bash scripts/markdownlint.sh --fix` as its autofix, which `blueprint.py fix run` runs on your machine, as does the explanation of the check *markdown*. The comment of the Lint workflow names the script, not a version of its own.

## Consequences

A finding of markdownlint fails `scripts/check.sh` and the hook before a push, on any machine with Node 22 or Docker, with the same rules and files as *lint*: about five seconds for two hundred documents on Windows, less on Linux. The image in the script and in the Variants workflow is one dependency for Renovate, which updates both in one pull request, and a test keeps them equal; the action of the Lint workflow is updated by its own pull request, so for the days between the two the versions may differ by a release. The jobs of the CI that run `scripts/check.sh` download nothing more and keep their time, and the check *lint* stays the one that decides in a pull request.
