# Every owner chooses who runs Renovate, and whether an AI reads the issues

- Status: accepted, amended by [0057](0057-renovate-keeps-no-dependency-dashboard.md), with which the checklist ticks Renovate off by its pull requests, and by [0094](0094-each-run-of-renovate-has-a-token-for-its-repository-alone.md), with which the hub runs Renovate once for each repository, with a token for it alone
- Date: 2026-10-18

## Context

Renovate ran only from the blueprint's own repository: its Renovate workflow found every repository of the blueprint's owner on which the owner's release app is installed, and nothing rendered a Renovate workflow into a repository. A repository of any other owner, which [decision 0049](0049-every-owner-brings-their-own-release-app.md) made possible, got the rules of Renovate but never an update, although the README promised Renovate for every repository. The settings of the bot, `.github/renovate-global.json5`, named the owner's account, its app and the number of the app's bot user. And `.github/repository.toml` always asked for `CLAUDE_CODE_OAUTH_TOKEN`, the secret of the AI of the issue assistant, so the checklist of an owner without Claude never passed, although the issue assistant works without its AI.

## Options

1. Let every owner run a copy of the blueprint's hub: a fork of the blueprint for every owner, only to run one workflow.
2. A Renovate workflow of the template that each repository runs for itself, written apart from the hub: two workflows that drift apart, with pins that Renovate keeps current only in one of them.
3. The hub's workflow for one repository: the template takes the blueprint's own workflow and changes only what makes it the hub, and an owner may choose the Mend Renovate app instead; the AI of the issue assistant becomes an answer.

## Decision

Option 3.

- **The answer `renovate_runner`:** `hub` keeps the Renovate workflow of the blueprint, and only the blueprint's owner may answer it, and that owner nothing else, because the hub already runs for each of the owner's repositories; it is that owner's default, so every repository of the Rollout stays as it is. `self`, the default of every other owner, renders `.github/workflows/renovate.yml` and `.github/renovate-global.json5`. `mend` renders neither, and the owner installs the Mend Renovate app.
- **One workflow:** the hub names who and where in the workflow, not in the settings of the bot: the bot user of the release app and its author come from the slug of the app's token, and the hub finds the repositories of its owner by `RENOVATE_AUTODISCOVER_FILTER`. The template takes this workflow and changes three places, which a test lists line by line: the job runs without the name of the blueprint, the token is for the repository alone, and `RENOVATE_REPOSITORIES` names the repository in place of every repository of the owner. So both run the same Renovate, pinned by its digest, which Renovate in the blueprint keeps current and every update of the blueprint brings on. The settings of the bot are the hub's, without the one command of the blueprint's own `pins.py`. Before the token, the workflow says what is missing when the repository names no release app or has no private key.
- **The checklist:** Renovate is done once its issue *Dependency dashboard* is open; until then, the checklist says how it comes to run for the answer of the repository, and for the Mend Renovate app the rule `gitIgnoredAuthors` with the bot user of the release app, so that Renovate doesn't take the commits of the branch bot and the fix bot for those of someone else.
- **The answer `issue_assistant_ai`:** without it, `.github/repository.toml` sets `ISSUE_ASSISTANT_AI` to `off` (and to `on` with it, so that a later answer switches it back), the environment `issue-assistant`, still for `main` alone, asks for no secret, `SUPPORT.md` says that no AI reads the issues, and the issue assistant's check asks no file to name an engine.

## Consequences

Any owner's repository gets its updates: from a workflow of its own, every two hours, or from the Mend Renovate app, which comes at every push. The bot-health bot watches the workflow, and its issue of Renovate's problems works there as in the blueprint. An owner without Claude gets a checklist that can pass and a `SUPPORT.md` that is true. The settings of the bot no longer name the hub's owner; only the guard of its job does, so a fork that changes that one line runs its hub as its own app. The repositories of the blueprint's owner render as before: their next update stores the answers `hub` and yes.
