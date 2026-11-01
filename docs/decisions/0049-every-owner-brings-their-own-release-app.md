# Every owner brings their own release app, and only the blueprint's owner gets its defaults

- Status: accepted, amended by [0093](0093-the-release-app-comes-from-a-manifest-and-its-key-touches-no-disk.md), with which one command registers the app in place of the link of the checklist
- Date: 2026-10-18

## Context

The blueprint is published as a free template for anyone, but every repository made from it was wired to its owner: `.github/repository.toml` named the Client ID and the App ID of the owner's release app, the checklist sent every user to install that app, and Copier proposed the owner's account and name, which went into the license and the governance. The release app is what the bots act as: its token starts the checks of the release and update pull requests, may change workflows and creates the release tags. Only the owner of an app has its private key, so in a repository of anyone else the release, settings, update and branch bots could never get a token, and the ruleset *Release tag creation* let only the owner's app create a release tag there. A render with another owner still held both identifiers of the app.

## Options

1. Keep the owner's app as the default for everyone, and let another owner override it in `.github/repository.project.toml`, as before: the default never works for anyone else, and the override is a step that nothing asks for.
2. One app that serves every owner, a public app of the blueprint that anyone installs: its private key would have to be shared with every repository, or the blueprint would have to run every bot for everyone.
3. Questions of Copier for the release app of the owner, which only the blueprint's owner gets as defaults, and a checklist that registers an app for everyone else.

## Decision

Option 3.

- **The questions:** `owner` has no default and must be a name that GitHub takes. `author` defaults to the owner. `release_app` asks for the name in the address of the app, and `release_app_client_id` and `release_app_id`, which only a named app asks for, for its Client ID and App ID. The constant `blueprint_owner` of `copier.yml`, which is never asked and never stored, holds the account, the name and the app of the blueprint's owner: an owner who is that account gets them as defaults, every other owner none. A fork of the blueprint names its own owner there.
- **The settings:** `.github/repository.toml` names the app in `RELEASE_APP`, `RELEASE_AUTOMATION_CLIENT_ID` and `RELEASE_AUTOMATION_APP_ID`. Without an app it names none: no ruleset lets an app create the release tags, and the environment `release` asks for no private key.
- **The checklist:** without an app, it starts with a link that registers one on the owner's account or organization, with its name, its permissions and no webhook filled in by the parameters of the address that GitHub documents, and names the one permission, *Variables*, that the link can't fill in. Then the `copier update` that names it. A test keeps the permissions of the link equal to every permission that a workflow asks the token of the app for, and to those that the README names. With an app, the checklist links its installation.
- **The bots without an app:** the blueprint bot fails with what is missing in its summary, the variable or the private key, rather than at the token; the release bot warns that no release can be published.
- **Defaults of an owner:** Copier's settings file keeps the answers that stay the same for every repository of an owner, which the README shows; the tests render with a settings file of their own, so that those of a machine change no test.

## Consequences

Any account or organization can take the blueprint, and nothing of a repository made from it names the blueprint's owner but the links to the blueprint and its tools; a test renders every kind for another owner and looks for the owner's name, account and app. The repositories of the blueprint's owner render as before: their next update stores the three answers of the app with the values that they had, and adds `RELEASE_APP`, which the settings bot sets. `copier copy --defaults` now needs the owner, by `--data owner=…` or in the settings file. Renovate, which runs from the blueprint's own repository for the repositories of its owner, still serves only them.
