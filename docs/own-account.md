---
description: Use Repo Blueprint for your own GitHub account or organization, with your own release app, Renovate in your own repositories or as the Mend app, and the issue assistant with or without AI.
---

# Your own account

The blueprint works for every account and organization on GitHub. A repository made from it names nothing of the blueprint's owner but the links to the blueprint and its tools, and every bot runs as an app of yours. This page walks through a new repository of your own, from the copy to a checklist without a cross.

## What you bring, and what is optional

- **A release app,** once for all of your repositories, which the bots act as: its token starts the checks of the release and update pull requests, may change workflows and creates the release tags, which the token of a job can't. Only the owner of an app has its private key, so the blueprint can't lend its own.
- **Renovate,** which keeps the dependencies current: in a workflow of each repository, as your release app, or as the Mend Renovate app, which you install. The Renovate workflow of the blueprint runs only for the repositories of the blueprint's owner.
- **The AI of the issue assistant** is optional. Without it, the issue assistant still labels new issues, reminds and closes, and carries out the commands of the maintainer, and no secret is needed.
- **The Rollout** is optional: the blueprint bot of each repository runs every week and brings the latest release of the blueprint on its own. The Rollout of the blueprint only starts the bots of its owner's repositories right after a release.

## 1. Copy the blueprint

```sh
copier copy gh:Dennis-Otto/repo-blueprint my-project
```

Copier asks for your account or organization, `owner`, and takes it as the maintainer. Leave the question of the release app empty, and answer two more:

- **`renovate_runner`**, who runs Renovate: `self`, a workflow in the repository, the default for every owner but the blueprint's; or `mend`, the Mend Renovate app. The repositories of the blueprint's owner keep the blueprint's workflow, `hub`, which already runs for each of them.
- **`issue_assistant_ai`**, whether an AI engine, Claude, analyzes each new issue; *no* switches it off.

Keep the answers that stay the same for every repository in Copier's settings file, as [the guide shows](guide.md#your-own-account):

```yaml
# ~/.config/copier/settings.yml
defaults:
  owner: octo-org
  author: Octo Org
  renovate_runner: self
  issue_assistant_ai: false
```

## 2. Create the repository

```sh
cd my-project
git init && git add --all && git commit --signoff --message "chore: start from the blueprint"
gh repo create octo-org/my-project --public --source . --push
python3 ../repo-blueprint/blueprint.py checklist
```

## 3. Register the release app

The checklist starts with a link that registers the app on your account or organization, with its name and permissions filled in and without a webhook; set *Variables* by hand, which the link can't fill in. Create the app, generate a private key on its settings page, and name the app in the answers of the blueprint, with the name in its address and the Client ID and App ID of that page:

```sh
copier update --defaults --vcs-ref=:current: --data release_app=NAME --data release_app_client_id=CLIENT_ID --data release_app_id=APP_ID
git commit --all --signoff --message "chore: name the release app"
git push
```

Install the app on the repository, at `https://github.com/apps/NAME/installations/new`, and set its private key from the file that GitHub gave you; the GitHub CLI reads it and shows it nowhere:

```sh
gh secret set RELEASE_AUTOMATION_PRIVATE_KEY --env release --repo octo-org/my-project < private-key.pem
```

## 4. Apply the settings

```sh
python3 ../repo-blueprint/blueprint.py settings apply
```

It sets everything that the API can set: the rulesets, the variables that name the app, the environments, the security features and the actions that may run.

## 5. Renovate

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/who-runs-renovate.dark.svg">
  <img src="images/diagrams/who-runs-renovate.svg" alt="Who runs Renovate: The answer renovate_runner decides who runs Renovate for a repository. The blueprint's owner keeps the hub, the Renovate workflow of the blueprint, which runs it for each of the owner's repositories on which the release app is installed. Every other owner gets a Renovate workflow in the repository itself, which runs it every two hours as the release app, for that repository alone, with the same Renovate and the same rules; or installs the Mend Renovate app, which needs no workflow and comes at every push. Each way reads the rules of .github/renovate.json5 and opens the updates as pull requests, whose checks decide whether they merge.">
</picture>

Every way reads the same rules, those of the blueprint in `.github/renovate-blueprint.json5` and yours in `.github/renovate.json5`, and keeps no issue open: what waits for you is a pull request. The checklist ticks Renovate off once it has opened a pull request.

- **`self`, a workflow of the repository:** `.github/workflows/renovate.yml` runs Renovate every two hours as your release app, with a token for this repository alone and without *Administration*. It is the workflow of the blueprint's own hub, with the same Renovate pinned by its digest, which every update of the blueprint moves on, and `.github/renovate-global.json5` holds the settings of the bot: commits through the API, which GitHub signs, and no scripts of the package managers. The bot user of your app is its author, which the workflow asks GitHub for. Its first run starts by itself; *Actions → Renovate → Run workflow* starts one at once. A run without the release app says in its summary what is missing, and a pull request that changes the rules or a lock file shows whether Renovate still accepts and reads them; the PR coach explains a failure of this check, *renovate rules*, also on a pull request from a fork, as [the troubleshooting](troubleshooting.md#the-check-renovate-rules-fails) does.
- **`mend`, the Mend Renovate app:** install the [Mend Renovate app](https://github.com/apps/renovate) on the repository. It reads the same rules, comes at every push rather than on a schedule, and needs no workflow and no token of yours. The branch bot and the fix bot update its branches as your release app, so add the bot user of the app to `gitIgnoredAuthors` in `.github/renovate.json5`, or Renovate takes the branches for edited and stops rebasing them; the checklist prints the line with the number of your app's bot user.

To change the answer later, run `copier update --defaults --vcs-ref=:current: --data renovate_runner=mend` and commit the update.

## 6. The issue assistant

With `issue_assistant_ai`, the issue assistant analyzes each new issue with Claude, and the checklist asks for its token, as the secret `CLAUDE_CODE_OAUTH_TOKEN` of the environment `issue-assistant`. Without it, `.github/repository.toml` sets the variable `ISSUE_ASSISTANT_AI` to `off`, the environment asks for no secret, and `SUPPORT.md` tells reporters that no AI reads their issues; labels, reminders, closing and the commands of the maintainer work as before. `copier update --defaults --vcs-ref=:current: --data issue_assistant_ai=true` turns the AI on later.

## 7. The checklist

```sh
python3 ../repo-blueprint/blueprint.py checklist
```

It shows what is left for a person and which steps are done: the release app, the settings, the secrets, the installation, Renovate, the community profile, the social preview and the badges. Once every step has its tick, the repository looks after itself.
