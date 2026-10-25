# create checks what it needs first and goes on where it stopped

- Status: accepted
- Date: 2026-10-25

## Context

`blueprint.py create` is the first command that a new user runs ([decision 0050](0050-a-new-copy-becomes-its-repository-with-one-command.md)). It checked nothing before its first step: `git init` ran, and only then did `git commit --signoff` fail without `user.name` and `user.email`. A GitHub CLI that was missing or too old, a sign-in that was missing, a token without the scope `workflow`, which GitHub needs for a push of `.github/workflows/`, an account that may not create repositories of the owner, and a name that was taken all failed midway with the raw message of gh. Once `gh repo create` had added `origin`, a push or settings that failed left a folder that `create` refused the next time, as one that "pushes to origin already", so the user finished by hand ([issue 453](https://github.com/Dennis-Otto/repo-blueprint/issues/453)).

## Options

1. Better messages for each failure as it happens. The folder would still be half made, and the user would learn of the next problem only after fixing the first.
2. A preflight before the first step, which only asks, and a `create` that goes on from the first step that is left in a folder that it made.
3. A `create` that undoes what it made when a step fails, such as deleting the repository on GitHub. Deleting needs the scope `delete_repo`, which `gh auth login` doesn't grant, and undoing a push or settings that GitHub accepted in part loses work.

## Decision

Option 2.

- **The preflight** asks for Python 3.12 or later, Git, the identity of the first commit through `git var GIT_AUTHOR_IDENT` and `GIT_COMMITTER_IDENT` (which take the variables such as `GIT_AUTHOR_EMAIL` into account, as the commit does) when a commit is to be made, GitHub CLI 2.48 or later, the sign-in and its scopes with `gh api --include user`, the owner with `gh api users/OWNER` and, for an organization, the role with `gh api user/memberships/orgs/OWNER`, and the name with `gh api repos/OWNER/NAME`. The scopes are `repo` and `workflow`, and `read:org` for an organization, which `write:org` and `admin:org` include; `workflow` only where gh's git protocol is HTTPS, as an SSH key pushes workflows without it. A Python before 3.11, which can't import the package, is named by `blueprint.py` itself before the import.
- **A finding is ✔, ✘ or ·.** A ✘ stops `create` before anything is made and names what fixes it, a command where one does, such as `gh auth refresh --hostname github.com --scopes workflow`; every ✘ shows at once, not only the first. A · is what the preflight can't tell, such as a fine-grained token, which names no scopes, a member of an organization who isn't an owner, which works where the organization lets its members create repositories, or an answer that GitHub didn't give: it stops nothing, as the step itself still says what went wrong.
- **`--dry-run`** shows the preflight with the commands, and **`blueprint.py doctor`** runs the preflight alone, with the exit code 1 when a finding would stop `create`.
- **Going on:** a folder whose `origin` pushes to the repository of the answers, in any form of address of GitHub, and that GitHub has, is one that `create` made. `create` then pushes `main` when GitHub has no branch `main` yet, with gh's credential helper as `gh repo create --push` does, so that it needs no `gh auth setup-git`, and the command line applies the settings and shows the checklist, which change only what differs. A folder whose `origin` pushes to another repository, or that has remotes but no `origin`, is still refused, and an `origin` whose repository GitHub doesn't have is a ✘ that names `git remote remove origin`.

## Consequences

A new user learns everything that would stop `create` at once, before anything is made, and a run that stopped midway ends with the same command that started it. The preflight costs a few requests to GitHub and calls of git and gh, about a second, and changes nothing. `create` doesn't undo a repository that it made; the troubleshooting names `git remote add origin` for a repository that a run made before gh could add `origin`, so that the next run goes on with it.
