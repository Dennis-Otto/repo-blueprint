# A new copy becomes its repository on GitHub with one command that it brings

- Status: accepted
- Date: 2026-10-18

## Context

Copier writes the files of a project into a folder and nothing more. The quick start then took six commands: `git init`, the first commit, `gh repo create` with the owner and the name typed in once more, and `settings apply` and `checklist` from a checkout of the blueprint, `../repo-blueprint/blueprint.py`, although every copy brings the same tool as `.github/blueprint.py`. Copier's own message after the copy named `<blueprint>/blueprint.py` and a `gh repo create --source . --push` that fails in a folder without a repository and without a commit. `git init` made the branch that Git's configuration names, `master` on Git for Windows and on every Git without `init.defaultBranch`, while every workflow runs on pushes to `main` and on pull requests to it: in such a repository, none of them ever ran, and nothing said so.

## Options

1. Keep the commands in the README and fix them: `git init --initial-branch=main` and the tool in `.github/`. Still six commands to type in the right order, and the owner and the name twice.
2. Tasks of Copier that run the commands after the copy: Copier runs them only with `--trust`, which lets a template run any code on the machine. The blueprint promises a copy that runs none of its code, as its [security design](../security.md) says.
3. A command of the tool that every copy brings, `blueprint.py create`, that does all of it from the answers of Copier.

## Decision

Option 3.

- **`create`** reads the owner and the name from `.copier-answers.yml`, or from `--repo OWNER/NAME`, and the description from `.github/repository.toml`, whose settings it loads first, so that a configuration that can't be right stops it before anything is made. It runs `git init --initial-branch=main`, `git add --all`, `git commit --signoff`, `gh repo create OWNER/NAME --public` (or `--private`) `--source . --remote origin --push`, then `settings apply` and `checklist`, as the commands of the tool do. `--dry-run` prints the commands and runs none.
- **A folder that Git knows already** is taken as it is, as the quick start of older releases left it: its branch is renamed to `main`, and the first commit is made only when there is none. A folder with uncommitted changes next to its commits is refused, as `create` pushes commits only, and so is a folder that pushes to a remote already, which is no new copy; the refusal names `settings apply` and `checklist` for a repository that is on GitHub.
- **Only a refused part of the settings fails it.** What a person does, such as the secrets and the release app, the checklist names, so a new repository with those steps left still ends with success.
- **`settings check`** reports a default branch other than `main`, with the place where GitHub renames it and the commands for each clone. `settings apply` leaves the renaming to a person, since every clone has to follow it.
- **Copier says it too:** before its questions what the command after the copy needs (Git, Python 3.12, GitHub CLI 2.48, signed in as an administrator of the owner) and that copying needs no `--trust`; after the files, `cd` into the folder and `python3 .github/blueprint.py create`.
- **The quick start** copies with the Copier that the blueprint bot updates with, by `uvx` or `pipx run` with its version pinned, which Renovate moves with the Copier of `stacks/copier/`.

## Consequences

A new user goes from `copier copy` to a configured repository with two commands and needs no checkout of the blueprint; the default branch is always `main`, and a repository where it isn't is named by `settings check` and by the settings bot. `create` needs Python 3.12 and the GitHub CLI as the rest of the tool does, and Git. A private repository on a free plan of GitHub gets no rulesets, which GitHub offers for public repositories only there: `settings apply` reports the refused part, and `create` fails after the repository was made, so that the person sees what is missing.
