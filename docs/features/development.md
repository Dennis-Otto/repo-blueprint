# Community and development

The files of the community, the dev container and the rules for coding agents.

## Community

README, contributing guide with the coding standards and the rule that every change brings its tests, code of conduct, security policy with how to verify a release and an assurance case, the security design of the software (`docs/security.md`), support, governance with the roles and the continuity of the project, issue forms, pull request template, records of the decisions that shape the project (`docs/decisions/`), discussions with forms for questions and ideas and an announcement of every release, sponsor button, social preview.

**How:** .

## Development

A dev container for VS Code and GitHub Codespaces with the tools of the checks and of the website, and a hook that runs them before every push, on Linux, macOS and Windows: `scripts/check.sh` fails when Git would skip it.

**How:** `.devcontainer/`, `.githooks/pre-push`.

## Coding agents

The rules of the repository for Claude Code, Codex, GitHub Copilot and Cursor: the commands of the checks and tests of its kind, the titles of pull requests and the versions they make, the changelog, the sign-off and the signature, and which files belong to the project and which to the blueprint, a list that a test of the blueprint keeps equal to the files an update never overwrites; the notes of the project join them from a file of its own.

**How:** `AGENTS.md`, `CLAUDE.md`, `.github/agents.project.md`.

## Tools in every repository

- `bash scripts/check.sh`: the checks of the CI, locally.
- `bash scripts/diagrams.sh`: draws every diagram of `docs/diagrams/` that a page shows as its pictures in `docs/images/diagrams/`, with Docker, and leaves the other sources alone; `--extract` first turns every `mermaid` block of the Markdown into a source and its picture and writes the `alt` of each picture from its source, and `--check` checks without Docker what `scripts/check.sh` checks.
- `bash scripts/social-preview.sh`: renders `.github/social-preview.html` into the 1280×640 image that GitHub shows for links to the repository; upload it under *Settings → Social preview*.
