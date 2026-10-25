---
description: Every variable and secret that the workflows of Repo Blueprint read or that its settings as code set: what it does, who sets it and which workflows read it.
---

# Variables and secrets

<!-- reference.py writes this page from .github/workflows/ and template/.github/repository.toml.jinja: change them and run python3 reference.py. -->

The workflows read the variables of the repository as `vars.NAME` and its secrets as `secrets.NAME`. The settings as code set most of the variables from the answers of Copier, and the checklist of `python3 .github/blueprint.py checklist` names each secret that is missing, with the command that sets it; the value goes into the prompt of the GitHub CLI and nowhere else. A variable that isn't set reads as empty, and so does a secret, which the workflows check before they use it.

## Variables

- [`BETA_CHANNEL`](#beta_channel): `true` makes every change for users that reaches `main`, a `feat`, `fix` or `perf`, a beta of the next release, such as `1.3.0-beta.2`, which the release publishes as a prerelease for the testers who take prereleases.
- [`BLUEPRINT_AUTOMERGE`](#blueprint_automerge): `off` makes every update of the blueprint wait for the maintainer, where its pull request would merge itself once every check passes; an update with conflicts waits either way.
- [`ISSUE_ASSISTANT_AI`](#issue_assistant_ai): `off` makes the issue assistant label the issues and answer the commands of their comments without an AI engine, which then needs no secret; `on` lets the engine analyze each new issue as well.
- [`MUTATION_PARTS`](#mutation_parts): The number of parts in which the mutation tests run, one job each, in place of the estimate from the number of mutants: more parts for a project whose parts run out of the six hours of a job.
- [`PUBLISH_TO`](#publish_to): Where the release delivers the package: `pypi`, `npm`, `ghcr`, `hacs`, `nextcloud-appstore`, `github-action` or `none`, by the kind of project.
- [`RELEASE_APP`](#release_app): The name of the release app, as its address says: github.com/apps/NAME.
- [`RELEASE_AUTOMATION_APP_ID`](#release_automation_app_id): The App ID of the release app, the number on its settings page.
- [`RELEASE_AUTOMATION_CLIENT_ID`](#release_automation_client_id): The Client ID of the release app, with which each bot asks for a token of the app, together with the private key `RELEASE_AUTOMATION_PRIVATE_KEY`.
- [`SETTINGS_APP_CLIENT_ID`](#settings_app_client_id): The Client ID of the settings app, an optional second GitHub App of the owner with only the permissions that the settings need.
- [`UPSTREAM_AUTOMERGE`](#upstream_automerge): `off` makes the pull request of the upstream bot of a Nextcloud app, which raises `max-version` to a new major version of Nextcloud, wait for the maintainer, where it would merge itself once every check passes.

### `BETA_CHANNEL`

`true` makes every change for users that reaches `main`, a `feat`, `fix` or `perf`, a beta of the next release, such as `1.3.0-beta.2`, which the release publishes as a prerelease for the testers who take prereleases. Without it, or with any other value, no betas are published.

- **Set by:** you, where you want it: in `[variables]` of `.github/repository.project.toml`, which the settings bot applies, or under *Settings → Secrets and variables → Actions → Variables*
- **Read by:** [`release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/release.yml) (Release, every repository)

What the workflows say of it:

- `release.yml`: Where the repository variable `BETA_CHANNEL` is true, every change for users that reaches main, a feat, fix or perf, becomes a beta of the next release, such as 1.3.0-beta.2, for the testers who take prereleases.

### `BLUEPRINT_AUTOMERGE`

`off` makes every update of the blueprint wait for the maintainer, where its pull request would merge itself once every check passes; an update with conflicts waits either way. Set it to `on`, or delete it with `gh variable delete BLUEPRINT_AUTOMERGE`, and the updates merge themselves again: the settings bot never deletes a variable, so removing its line from `.github/repository.project.toml` leaves `off` in place.

- **Set by:** you, where you want it: in `[variables]` of `.github/repository.project.toml`, which the settings bot applies, or under *Settings → Secrets and variables → Actions → Variables*
- **Read by:** [`blueprint-update.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/blueprint-update.yml) (Blueprint update, every repository)

What the workflows say of it:

- `blueprint-update.yml`: The repository variable `BLUEPRINT_AUTOMERGE` set to off makes every update wait.

### `ISSUE_ASSISTANT_AI`

`off` makes the issue assistant label the issues and answer the commands of their comments without an AI engine, which then needs no secret; `on` lets the engine analyze each new issue as well. The reusable workflow of the issue assistant, which `issue-assistant.yml` calls, reads it.

- **Set by:** the settings as code: `.github/repository.toml` sets it, from [`issue_assistant_ai`](questions.md#issue_assistant_ai), and the settings bot applies it; `.github/repository.project.toml` can set another value
- **Read by:** no workflow

### `MUTATION_PARTS`

The number of parts in which the mutation tests run, one job each, in place of the estimate from the number of mutants: more parts for a project whose parts run out of the six hours of a job.

- **Set by:** you, where you want it: in `[variables]` of `.github/repository.project.toml`, which the settings bot applies, or under *Settings → Secrets and variables → Actions → Variables*
- **Read by:** [`mutation.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/mutation.yml) (Mutation, where `stack in ['python', 'home-assistant', 'php']`)

### `PUBLISH_TO`

Where the release delivers the package: `pypi`, `npm`, `ghcr`, `hacs`, `nextcloud-appstore`, `github-action` or `none`, by the kind of project. The build, the release and the check of the latest release follow it.

- **Set by:** the settings as code: `.github/repository.toml` sets it, from [`publish_to`](questions.md#publish_to), and the settings bot applies it; `.github/repository.project.toml` can set another value
- **Read by:** [`build-release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/build-release.yml) (Build the release, every repository); [`release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/release.yml) (Release, every repository); [`verify-release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/verify-release.yml) (Release verification, every repository)

What the workflows say of it:

- `release.yml`: The jobs below attach the package, its SBOMs (SPDX and CycloneDX), the licenses of its third-party components, the advisories that don't affect it (OpenVEX) and its signed provenance, write the notes, make the release public, announce it in the discussions, and then deliver it where the repository variable `PUBLISH_TO` says: pypi, npm, ghcr, hacs, nextcloud-appstore, github-action or none.
- `verify-release.yml`: It checks a release the way its users can: every asset carries the signed provenance of this repository's release workflow, both in GitHub and in the attached bundle; the SBOMs are attached and describe what the release ships, by its name and version; the release is immutable and its commit signed; and where the repository variable `PUBLISH_TO` delivers it, the same release is there.

### `RELEASE_APP`

The name of the release app, as its address says: github.com/apps/NAME. No workflow reads it; the checklist of `blueprint.py` links the installation of the app with it.

- **Set by:** the settings as code: `.github/repository.toml` sets it, from [`release_app`](questions.md#release_app), and the settings bot applies it; `.github/repository.project.toml` can set another value
- **Read by:** no workflow

### `RELEASE_AUTOMATION_APP_ID`

The App ID of the release app, the number on its settings page. No workflow reads it; the settings as code let only this app create release tags, in the ruleset *Release tag creation*.

- **Set by:** the settings as code: `.github/repository.toml` sets it, from [`release_app_id`](questions.md#release_app_id), and the settings bot applies it; `.github/repository.project.toml` can set another value
- **Read by:** no workflow

### `RELEASE_AUTOMATION_CLIENT_ID`

The Client ID of the release app, with which each bot asks for a token of the app, together with the private key `RELEASE_AUTOMATION_PRIVATE_KEY`. Without it, the bots say in their summary what is missing, and the release pull request starts no checks.

- **Set by:** the settings as code: `.github/repository.toml` sets it, from [`release_app_client_id`](questions.md#release_app_client_id), and the settings bot applies it; `.github/repository.project.toml` can set another value
- **Read by:** [`after-checks.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/after-checks.yml) (After the checks, every repository); [`blueprint-update.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/blueprint-update.yml) (Blueprint update, every repository); [`dependabot-automerge.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/dependabot-automerge.yml) (Dependabot maintenance, every repository); [`diagrams.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/diagrams.yml) (Diagrams, every repository); [`docs-pictures.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/docs-pictures.yml) (Docs pictures, the blueprint alone); [`lint.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/lint.yml) (Lint, every repository); [`release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/release.yml) (Release, every repository); [`renovate.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/renovate.yml) (Renovate, where `renovate_runner == 'self'`); [`rollout.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/rollout.yml) (Rollout, the blueprint alone); [`screenshot-bot.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/screenshot-bot.yml) (Screenshots, every repository); [`settings.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/settings.yml) (Settings, every repository); [`sync-issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/sync-issue-assistant.yml) (Issue assistant sync, the blueprint alone); [`update-branches.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/update-branches.yml) (Update branches, every repository); [`upstream.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/upstream.yml) (Upstream, where `project_type == 'nextcloud-app'`)

### `SETTINGS_APP_CLIENT_ID`

The Client ID of the settings app, an optional second GitHub App of the owner with only the permissions that the settings need. With it and the private key `SETTINGS_APP_PRIVATE_KEY`, the settings bot applies the settings as this app, and the blueprint bot lets the actions of an update start before it pushes the update, so that the release app needs no *Administration*. Without them, the release app applies the settings, as before.

- **Set by:** you, where you want it: in `[variables]` of `.github/repository.project.toml`, which the settings bot applies, or under *Settings → Secrets and variables → Actions → Variables*
- **Read by:** [`blueprint-update.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/blueprint-update.yml) (Blueprint update, every repository); [`settings.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/settings.yml) (Settings, every repository)

What the workflows say of it:

- `settings.yml`: Every week, and after each change of the settings as code or of its own code, it brings the settings of the repository on GitHub in line with .github/repository.toml, .github/repository.project.toml and .github/labels.toml, as the settings app, a second GitHub App of the owner that only administers, once the variable `SETTINGS_APP_CLIENT_ID` and the secret SETTINGS\_APP\_PRIVATE\_KEY name it, and as the release app until then, which may write the administration of the repository as well.

### `UPSTREAM_AUTOMERGE`

`off` makes the pull request of the upstream bot of a Nextcloud app, which raises `max-version` to a new major version of Nextcloud, wait for the maintainer, where it would merge itself once every check passes.

- **Set by:** you, where you want it: in `[variables]` of `.github/repository.project.toml`, which the settings bot applies, or under *Settings → Secrets and variables → Actions → Variables*
- **Read by:** [`upstream.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/upstream.yml) (Upstream, where `project_type == 'nextcloud-app'`)

What the workflows say of it:

- `upstream.yml`: It merges itself once they pass, unless the repository variable `UPSTREAM_AUTOMERGE` is off.

## Secrets

- [`ANTHROPIC_API_KEY`](#anthropic_api_key): An API key of Anthropic, which the issue assistant takes in place of `CLAUDE_CODE_OAUTH_TOKEN` to analyze each new issue with Claude, at the prices of Anthropic's API.
- [`APPSTORE_TOKEN`](#appstore_token): The API token of the account of the Nextcloud App Store, with which the release submits the signed package and the workflow *Register app* registers the id of the app.
- [`APP_PRIVATE_KEY`](#app_private_key): The private key of the certificate of a Nextcloud app, with which the release signs the package for the App Store and the workflow *Register app* proves the id of the app.
- [`CLAUDE_CODE_OAUTH_TOKEN`](#claude_code_oauth_token): The token of a Claude subscription, which `claude setup-token` of Claude Code creates, with which the issue assistant analyzes each new issue with Claude.
- [`COPILOT_GITHUB_TOKEN`](#copilot_github_token): A fine-grained token of GitHub with the permission *Copilot Requests* alone and no access to repositories, with which the issue assistant analyzes each new issue with Copilot, once `name` under `[engine]` of `.github/issue-assistant/config.toml` is `copilot`.
- [`GEMINI_API_KEY`](#gemini_api_key): An API key of Google AI Studio, with which the issue assistant analyzes each new issue with Gemini, once `name` under `[engine]` of `.github/issue-assistant/config.toml` is `gemini`; free within the daily limits of the free tier of the Gemini API.
- [`GITHUB_TOKEN`](#github_token): The token that GitHub gives every run of a workflow, for its repository alone and with the permissions that its `permissions:` grant.
- [`OPENAI_API_KEY`](#openai_api_key): An API key of OpenAI, with which the issue assistant analyzes each new issue with Codex, once `name` under `[engine]` of `.github/issue-assistant/config.toml` is `codex`, at the prices of OpenAI's API.
- [`RELEASE_AUTOMATION_PRIVATE_KEY`](#release_automation_private_key): The private key of the release app, the file that its settings page generates.
- [`SETTINGS_APP_PRIVATE_KEY`](#settings_app_private_key): The private key of the settings app, the file that its settings page generates.

### `ANTHROPIC_API_KEY`

An API key of Anthropic, which the issue assistant takes in place of `CLAUDE_CODE_OAUTH_TOKEN` to analyze each new issue with Claude, at the prices of Anthropic's API. Set one of the two; without either, the assistant works without AI, as with `ISSUE_ASSISTANT_AI` set to `off`.

- **Set by:** you, as a secret of the environment `issue-assistant`, which only `main` may use: `gh secret set ANTHROPIC_API_KEY --env issue-assistant`
- **Read by:** [`issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/issue-assistant.yml) (Issue assistant, every repository)

### `APPSTORE_TOKEN`

The API token of the account of the Nextcloud App Store, with which the release submits the signed package and the workflow *Register app* registers the id of the app. Only a Nextcloud app needs it.

- **Set by:** you, as a secret of the environment `release`, which only `main` may use: `gh secret set APPSTORE_TOKEN --env release`, as the checklist shows
- **Read by:** [`register-app.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/register-app.yml) (Register the app, where `project_type == 'nextcloud-app'`); [`release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/release.yml) (Release, every repository)

### `APP_PRIVATE_KEY`

The private key of the certificate of a Nextcloud app, with which the release signs the package for the App Store and the workflow *Register app* proves the id of the app. Only a Nextcloud app needs it.

- **Set by:** you, as a secret of the environment `release`, which only `main` may use: `gh secret set APP_PRIVATE_KEY --env release`, as the checklist shows
- **Read by:** [`build-release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/build-release.yml) (Build the release, every repository); [`register-app.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/register-app.yml) (Register the app, where `project_type == 'nextcloud-app'`)

### `CLAUDE_CODE_OAUTH_TOKEN`

The token of a Claude subscription, which `claude setup-token` of Claude Code creates, with which the issue assistant analyzes each new issue with Claude. The checklist asks for it while the answer `issue_assistant_ai` is on; `ANTHROPIC_API_KEY` works in its place.

- **Set by:** you, as a secret of the environment `issue-assistant`, which only `main` may use: `gh secret set CLAUDE_CODE_OAUTH_TOKEN --env issue-assistant`, as the checklist shows
- **Read by:** [`issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/issue-assistant.yml) (Issue assistant, every repository)

### `COPILOT_GITHUB_TOKEN`

A fine-grained token of GitHub with the permission *Copilot Requests* alone and no access to repositories, with which the issue assistant analyzes each new issue with Copilot, once `name` under `[engine]` of `.github/issue-assistant/config.toml` is `copilot`. It counts the premium requests of the Copilot plan of the token's owner.

- **Set by:** you, as a secret of the environment `issue-assistant`, which only `main` may use: `gh secret set COPILOT_GITHUB_TOKEN --env issue-assistant`
- **Read by:** [`issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/issue-assistant.yml) (Issue assistant, every repository)

### `GEMINI_API_KEY`

An API key of Google AI Studio, with which the issue assistant analyzes each new issue with Gemini, once `name` under `[engine]` of `.github/issue-assistant/config.toml` is `gemini`; free within the daily limits of the free tier of the Gemini API.

- **Set by:** you, as a secret of the environment `issue-assistant`, which only `main` may use: `gh secret set GEMINI_API_KEY --env issue-assistant`
- **Read by:** [`issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/issue-assistant.yml) (Issue assistant, every repository)

### `GITHUB_TOKEN`

The token that GitHub gives every run of a workflow, for its repository alone and with the permissions that its `permissions:` grant. What a workflow does with it starts no other workflow, which is why the bots that open, update or merge pull requests act as the release app.

- **Set by:** GitHub, for every run of a workflow
- **Read by:** [`after-checks.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/after-checks.yml) (After the checks, every repository); [`bot-health.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/bot-health.yml) (Bot health, every repository); [`build-release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/build-release.yml) (Build the release, every repository); [`cleanup.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/cleanup.yml) (Clean-up, every repository); [`dependabot-automerge.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/dependabot-automerge.yml) (Dependabot maintenance, every repository); [`links.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/links.yml) (Links, every repository); [`mutation.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/mutation.yml) (Mutation, where `stack in ['python', 'home-assistant', 'php']`); [`pull-request-title.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/pull-request-title.yml) (Pull request title, every repository); [`release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/release.yml) (Release, every repository); [`renovate.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/renovate.yml) (Renovate, where `renovate_runner == 'self'`); [`secret-scan.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/secret-scan.yml) (Secret scan, every repository); [`welcome.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/welcome.yml) (Welcome, every repository)

What the workflows say of it:

- `release.yml`: A pull request of the release app starts the checks; one of the job's `GITHUB_TOKEN` would start none.

### `OPENAI_API_KEY`

An API key of OpenAI, with which the issue assistant analyzes each new issue with Codex, once `name` under `[engine]` of `.github/issue-assistant/config.toml` is `codex`, at the prices of OpenAI's API.

- **Set by:** you, as a secret of the environment `issue-assistant`, which only `main` may use: `gh secret set OPENAI_API_KEY --env issue-assistant`
- **Read by:** [`issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/issue-assistant.yml) (Issue assistant, every repository)

### `RELEASE_AUTOMATION_PRIVATE_KEY`

The private key of the release app, the file that its settings page generates. With it and `RELEASE_AUTOMATION_CLIENT_ID`, the bots act as the app: they open and merge the release and update pull requests, so that their checks run, create the release tags and apply the settings. The file goes in with `< key.pem` after the command below.

- **Set by:** you, as a secret of the environment `release`, which only `main` may use: `gh secret set RELEASE_AUTOMATION_PRIVATE_KEY --env release`, as the checklist shows
- **Read by:** [`after-checks.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/after-checks.yml) (After the checks, every repository); [`blueprint-update.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/blueprint-update.yml) (Blueprint update, every repository); [`dependabot-automerge.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/dependabot-automerge.yml) (Dependabot maintenance, every repository); [`diagrams.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/diagrams.yml) (Diagrams, every repository); [`docs-pictures.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/docs-pictures.yml) (Docs pictures, the blueprint alone); [`release.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/release.yml) (Release, every repository); [`renovate.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/renovate.yml) (Renovate, where `renovate_runner == 'self'`); [`rollout.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/rollout.yml) (Rollout, the blueprint alone); [`screenshot-bot.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/screenshot-bot.yml) (Screenshots, every repository); [`settings.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/settings.yml) (Settings, every repository); [`sync-issue-assistant.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/sync-issue-assistant.yml) (Issue assistant sync, the blueprint alone); [`update-branches.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/update-branches.yml) (Update branches, every repository); [`upstream.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/upstream.yml) (Upstream, where `project_type == 'nextcloud-app'`)

### `SETTINGS_APP_PRIVATE_KEY`

The private key of the settings app, the file that its settings page generates. With it and `SETTINGS_APP_CLIENT_ID`, the settings bot and the blueprint bot act as the settings app, the only app that writes the administration of the repository. The file goes in with `< key.pem` after the command below.

- **Set by:** you, as a secret of the environment `release`, which only `main` may use: `gh secret set SETTINGS_APP_PRIVATE_KEY --env release`
- **Read by:** [`blueprint-update.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/blueprint-update.yml) (Blueprint update, every repository); [`settings.yml`](https://github.com/Dennis-Otto/repo-blueprint/blob/main/.github/workflows/settings.yml) (Settings, every repository)

What the workflows say of it:

- `settings.yml`: Every week, and after each change of the settings as code or of its own code, it brings the settings of the repository on GitHub in line with .github/repository.toml, .github/repository.project.toml and .github/labels.toml, as the settings app, a second GitHub App of the owner that only administers, once the variable SETTINGS\_APP\_CLIENT\_ID and the secret `SETTINGS_APP_PRIVATE_KEY` name it, and as the release app until then, which may write the administration of the repository as well.
