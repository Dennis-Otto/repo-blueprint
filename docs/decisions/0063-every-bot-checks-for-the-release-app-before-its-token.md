# Every bot checks for the release app before its token, and fails without it only when its work is the app's

- Status: accepted
- Date: 2026-10-24

## Context

Since every owner brings a release app of their own ([0049](0049-every-owner-brings-their-own-release-app.md)), a repository may have no app yet, or name one whose private key isn't set yet. The blueprint bot and Renovate checked for both before their token and named what was missing; the release bot warned when the variable was empty. Every other bot that acts as the app asked for its token without a check ([issue 308](https://github.com/Dennis-Otto/repo-blueprint/issues/308)): the settings bot every week and after each change of the settings, the upstream bot of a Nextcloud app, the picture bot and the Rollout failed at the token, with an error of `actions/create-github-app-token` that names its missing input, not the app, the key or the checklist. The fix bot, the branch bot, the diagram, screenshot and sync bots and the merge of Dependabot's updates skipped the token without a client ID, some of them with a warning, but failed at it as well when only the private key was missing.

## Options

1. A composite action that checks the app, in `.github/actions/`. A local action needs the checkout of the repository before it, and several jobs ask for the token first, to check out with it or to check out nothing at all; an action of the blueprint's own repository would tie every repository to it by a pin.
2. A condition on each token, `vars.RELEASE_AUTOMATION_CLIENT_ID != ''`, as some bots had. An expression can't tell whether a secret of an environment is set before the job runs in it, and a token step that is skipped explains nothing.
3. A step before every token of the release app, *Check that the release app is set up*, with the same script in every workflow and what differs, the bot, what it needs the app for, what happens without it and whether its run fails, in its variables; the token runs only once the check found both.

## Decision

Option 3.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-check-of-the-release-app.dark.svg">
  <img src="../images/diagrams/the-check-of-the-release-app.svg" alt="The check of the release app: Before a bot asks for a token of the release app, it checks that the repository names the app in the variable RELEASE_AUTOMATION_CLIENT_ID and has its private key in the environment release. With both, it asks for the token and does its work. Without one, it says in an annotation and in its summary which one is missing and that the checklist sets it up. A bot whose work is what the app does, such as the blueprint bot, the settings bot or Renovate, then fails; one that only helps a pull request along, such as the fix bot or the branch bot, warns and goes on without the token.">
</picture>

- **The check:** it reads the variable `RELEASE_AUTOMATION_CLIENT_ID` and whether the secret `RELEASE_AUTOMATION_PRIVATE_KEY` of the environment `release` is set, never its value. With both, it writes `ready=true` for the token. Without one, it writes an annotation and a summary that name which one is missing, what the bot needs the app for, what happened instead, and that `python3 .github/blueprint.py checklist` sets the app up.
- **Who fails:** a bot whose work is what the app does fails, so that the bot-health bot keeps its issue open: the blueprint bot, the settings bot, the upstream bot, Renovate in a workflow of the repository and the Rollout. A bot that only helps a pull request along warns and goes on, with the token of the job where one can do its work: the fix bot, the branch bot, the diagram, screenshot, picture and sync bots, the merge of Dependabot's updates and the release bot, whose release pull request still comes.
- **The tests:** a test finds every token of an app in the workflows of the blueprint and of every kind of project, and fails unless the check comes before it in its job, with the same script, and unless every later step of a bot that goes on uses the token only once there is one. Another runs the check of each bot without the app.

## Consequences

A repository without its app, or without its private key, sees in the run of each bot what to set up, and a scheduled bot no longer fails with an error that hides the cause. A token that fails for another reason, such as an app that isn't installed on the repository, still fails its step, as before. Each new bot that acts as the app takes the check with it, or the test fails; the same script in 15 jobs is the price of a check that runs before any checkout, and the test keeps the copies equal.
