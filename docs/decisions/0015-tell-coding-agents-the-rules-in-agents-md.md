# Tell coding agents the rules in AGENTS.md, with the files of a project kept equal to copier.yml

- Status: accepted
- Date: 2026-10-13

## Context

Coding agents write a large share of the pull requests of the repositories made from the blueprint. The rules they need are in the long prose of CONTRIBUTING.md, or nowhere: the commands of the checks of each kind of project, the titles of pull requests and the versions they make, the entry under Unreleased, the sign-off, and above all which files belong to the project and which to the blueprint. An agent that fixes a workflow or `scripts/check.sh` in one repository makes a change that conflicts with the next update and that the other repositories never get. Which files belong to a project is in `_skip_if_exists` of `copier.yml`, which an agent in a repository made from the blueprint doesn't see.

`AGENTS.md` at the root of a repository is the file that Codex, GitHub Copilot, Cursor and other agents read on their own. Claude Code reads `CLAUDE.md`, which can import other files with lines such as `@AGENTS.md`.

## Options

1. Leave the rules in CONTRIBUTING.md. Nothing to keep current, but agents read it seldom and in parts, and it doesn't list the files of a project.
2. An `AGENTS.md` that belongs to the project, written once by the template. Each project could change it, but an update would never bring a new rule, and the list of the files of a project would drift from `copier.yml` with every new entry.
3. An `AGENTS.md` that belongs to the blueprint and is rendered for each kind of project, with the list of the files of a project, which a test keeps equal to `_skip_if_exists`; the notes of each project in `.github/agents.project.md`, which belongs to the project; and a `CLAUDE.md` of the blueprint that imports both.

## Decision

Option 3. `template/AGENTS.md.jinja` names the commands of the kind of project, the rules of pull requests, commits and the changelog, what never to do to get a check green, and the files of the project, grouped by what they are; `test_every_project_tells_coding_agents_its_rules` fails as soon as that list and `_skip_if_exists` differ, so a new entry goes into both. Copier can't read its own `copier.yml` from a template, because the delimiters in its `_envops` would end the include, so the list is written out once more and the test guards it. `AGENTS.md` ends with a pointer to `.github/agents.project.md`, which `_skip_if_exists` lists: the update adds it once, rendered with where the parts of the kind of project are, and then leaves it to the project. `CLAUDE.md` imports `AGENTS.md` and the notes, and asks for new notes in `.github/agents.project.md`, where Claude Code would otherwise add them to `CLAUDE.md`, a file of the blueprint. The blueprint has a pair of its own: its `AGENTS.md` says what reaches the other repositories, its `CLAUDE.md` is the one of every repository, and its `.github/agents.project.md` explains the template.

## Consequences

Every agent in every repository gets the same rules, and a new rule reaches all of them with the next release. The rules exist twice, for people in CONTRIBUTING.md and for agents in `AGENTS.md`; a change of a rule changes both. A repository that already has an `AGENTS.md` or a `CLAUDE.md` gets the blueprint's in its update pull request, with conflict markers, and moves its own notes into `.github/agents.project.md`.
