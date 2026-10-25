# The settings bot asks for only what it needs, and environments bind administrators

- Status: accepted
- Date: 2026-10-25

## Context

The bots act as one release app of the owner ([decision 0049](0049-every-owner-brings-their-own-release-app.md)), whose private key is in the environment `release` of every repository. Each bot asks for a token with the permissions of its job, but the settings bot asked for none, and a token without permissions gets every permission of the installation: *Contents* and *Workflows* (read and write) too, although `settings apply` never pushes a commit. Its reason was that the token action has no input for *Variables*, and `.github/zizmor.yml` accepted the finding of zizmor's audit `github-app` for it. Every environment of the settings also kept GitHub's default `can_admins_bypass`, which lets an administrator of the repository force a deployment past the rules of the environment, such as the rule that only `main` may use `release` and its private key ([#442](https://github.com/Dennis-Otto/repo-blueprint/issues/442)).

## Options

1. Keep the token with every permission, and accept the finding.
2. Read the variables from `${{ vars }}` in the job, which needs no permission, and ask for a token with every permission only when a variable differs.
3. Ask for the permissions that `settings apply` needs, *Variables* through the variable `INPUT_PERMISSION-ACTIONS-VARIABLES` of the step, which the token action reads as it reads its inputs.
4. A second GitHub App for the settings, with *Administration*, *Variables*, *Environments* and *Pages*, whose private key only the blueprint holds, and a settings bot that runs from the blueprint for every repository, as Renovate does; the release app then loses *Administration* and *Secrets*.

## Decision

Option 3 now. Option 4 needs the owner to create the second app and stays the next step.

- **The token of the settings bot** asks for these permissions, for the repository of the run alone:

  | Permission | Access | What `settings apply` does with it |
  | --- | --- | --- |
  | *Administration* | read and write | The repository, its security, the permissions of Actions, the rulesets, the environments and the branches that may use them |
  | *Variables* | read and write | The variables of the repository |
  | *Issues* | read and write | The labels |
  | *Pages* | read and write | The website, which GitHub writes with *Administration* as well |
  | *Actions* | read | The environments and the branches that may use them |
  | *Contents* | read | The files of the community standards |
  | *Environments* | read | The names of the secrets of the environments |

  It can't push a commit, change a workflow or open a pull request.
- **Variables by its name in the token API.** GitHub calls the permission `actions_variables` in the permissions of an installation, but its OpenAPI description, from which the token action makes its inputs, lacks it. The pinned version of the action takes every `INPUT_PERMISSION-*` of its environment, the way the runner passes an input, so the step sets that variable; an input under `with:` that the action doesn't name would make the runner warn in every run.
- **A refused token explains itself.** GitHub refuses the whole token when the app lacks one of its permissions, as an app registered before the bot asked for it does. The step *Explain a refused token* names the permissions in the summary of the run, and where to grant and accept them; nothing falls back to a token with more permissions.
- **Tests keep it so.** A test fails on a token of the release app, in any workflow of the blueprint or of a kind of project, that asks for no permission; another keeps the token of the settings bot equal to the table above and to the permissions that each part of the settings writes with.
- **No administrator past the rules of an environment.** `settings check` reports `environment <name>.can_admins_bypass` for an environment of the settings that lets administrators bypass its rules, and `settings apply` turns it off in the same write that sets the branches. The environment `github-pages`, which GitHub makes for the website and the settings don't name, keeps GitHub's default.
- **The hint names the right permission.** When GitHub refuses a part, the run names the permissions that GitHub writes it with: *Administration* for the environments, *Administration* and *Pages* for the website.

## Consequences

A token of the settings bot that leaked while `settings apply` runs can't change the code or the workflows of the repository, and zizmor accepts no exception for it any longer. It can still change the settings, and the private key of the release app can still give any job of `release` a token with *Administration*: the second app of option 4 takes that out of every repository but the blueprint.

A release app that lacks one of the seven permissions now fails the settings bot at its token, not at a single part; the summary of the run and the troubleshooting guide say which permissions to grant. An app registered with the link of the checklist has them all once *Variables* is set by hand, as the checklist says.

An administrator can no longer approve a deployment past the rules of `release` or `issue-assistant`; a job that needs their secrets runs on `main`.

What remains for later: the second app of option 4, which the owner creates, and a token of Renovate for each repository, from a matrix over the repositories of the app with at most two at once, so that a package manager that runs code of one repository's dependencies can't push to the others.
