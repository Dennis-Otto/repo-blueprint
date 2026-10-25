# A second app writes the administration, and the blueprint bot widens the allowed actions with it

- Status: accepted, amends [0074](0074-every-pull-request-follows-the-actions-that-its-workflows-run-in-turn.md) and [0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md)
- Date: 2026-10-25

## Context

One GitHub App, the release app, does everything that the token of a job can't: it opens the release and update pull requests, pushes changes of workflows, creates the release tags and, for the settings bot, writes the administration of every repository that it is installed on: rulesets, environments, variables, the website and the actions that may run. Most workflows ask it for a token, so its private key is in the environment `release` of every repository, and a key that leaks can turn off the protection of `main`.

GitHub checks the list of the allowed actions when a workflow starts. When a release of the blueprint adds an action, the update pull request of each repository can't start the jobs that run it until a maintainer runs `settings apply` from its branch ([decision 0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md)). The blueprint bot could widen the list itself before it pushes the update, but that needs *Administration*, which its token lacks on purpose ([decision 0074](0074-every-pull-request-follows-the-actions-that-its-workflows-run-in-turn.md), Option 4, and [#440](https://github.com/Dennis-Otto/repo-blueprint/issues/440)).

## Options

1. Keep the manual step, and the administration with the release app.
2. Give the token of the blueprint bot *Administration* of the release app as well: no new app, but the job that pushes the update would then hold a token that can also change the rulesets, and the release app keeps the administration for good.
3. A second GitHub App of the owner, the settings app, with only the permissions of the settings: the settings bot applies them as it, and the blueprint bot asks it for a token with *Administration* alone, in a step of its own, to widen the list. Optional, so that nothing changes until the owner sets it up.

## Decision

Option 3.

- **The settings app** is a GitHub App of the owner with *Administration*, *Issues*, *Pages* and *Variables* (read and write) and *Actions*, *Contents*, *Environments* and *Secrets* (read), the permissions that `settings apply` needs and no others. The variable `SETTINGS_APP_CLIENT_ID` names it, and its private key is the secret `SETTINGS_APP_PRIVATE_KEY` of the environment `release`, which only `main` may use.
- **The settings bot** takes it once both are set: the step *Check whether the settings app is set up* sees both, the check of the release app is skipped, and `settings apply` runs with a token of the settings app for the repository alone. Its token asks for no permission by name, since the token action has no input for *Variables*; the app itself has only the permissions of the settings, and zizmor accepts it on the line of that step alone. GitHub refusing the token fails the run with what the app needs; nothing falls back on the release app, which may have given up its permissions.
- **The blueprint bot** asks the settings app for a token with *Administration* alone. After `copier update` and before the push, the step *Let the actions of the update start* runs `blueprint.py settings widen` of `main`, copied before the update, with the settings of the update as data: it adds the patterns of `[actions.selected]` that GitHub's list lacks and takes none away, which stops no workflow. The settings bot narrows the list to the settings after the merge. The step that renders the update holds no token, and the commit and the pull request come with the release app, as before.
- **Without the settings app, nothing changes.** The release app applies the settings, and an update that brings a new action waits for `settings apply` from its branch. With only the variable or only the secret, both bots warn in their summary and go on as without it; a refused token of the blueprint bot, or settings with conflicts that don't parse, leave the update as it was.

## Consequences

Once the owner has set up the settings app in every repository, the release app can give up *Administration*, *Pages*, *Variables*, *Environments* and *Secrets*, and a leaked key of it can no longer change a ruleset, an environment or the actions that may run. The update pull request of a release that adds an action starts its checks and merges itself, as every other update does. The owner registers, installs and names one more app, as [Your own account](../own-account.md#8-the-settings-app-optional) shows, and keeps a second private key. The widening only adds patterns that the verified release and the project's own settings list, so a pattern that the release drops stays on GitHub until the settings bot runs after the merge.
