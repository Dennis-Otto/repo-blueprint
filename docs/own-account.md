---
description: Use Repo Blueprint for your own GitHub account or organization, with your own release app, Renovate in your own repositories or as the Mend app, and the issue assistant with or without AI.
---

# Your own account

The blueprint works for every account and organization on GitHub. A repository made from it names nothing of the blueprint's owner but the links to the blueprint and its tools, and every bot runs as an app of yours. This page walks through a new repository of your own, from the copy to a checklist without a cross.

## What you bring, and what is optional

- **A release app,** once for all of your repositories, which the bots act as: its token starts the checks of the release and update pull requests, may change workflows and creates the release tags, which the token of a job can't. Only the owner of an app has its private key, so the blueprint can't lend its own.
- **Renovate,** which keeps the dependencies current: in a workflow of each repository, as your release app, or as the Mend Renovate app, which you install. The Renovate workflow of the blueprint runs only for the repositories of the blueprint's owner.
- **The AI of the issue assistant** is optional. Without it, the issue assistant still labels new issues, reminds and closes, and carries out the commands of the maintainer, and no secret is needed.
- **The settings app** is optional: a second app with only the permissions of the settings, which then applies them in place of the release app, so that the release app needs no *Administration*. [Step 8](#8-the-settings-app-optional) sets it up.
- **The Rollout** is optional: the blueprint bot of each repository runs every week and brings the latest release of the blueprint on its own. The Rollout of the blueprint only starts the bots of its owner's repositories right after a release.

## 1. Copy the blueprint

You need Git, Python 3.12 or later, [uv](https://docs.astral.sh/uv/) and GitHub CLI 2.48 or later, signed in as an administrator of your account or organization (`gh auth login`), and no checkout of the blueprint.

```sh
uvx --from copier==9.19.1 copier copy gh:Dennis-Otto/repo-blueprint my-project
```

[The guide](https://dennis-otto.github.io/repo-blueprint/guide.html#start-a-repository) also shows this command with pipx and with a Copier of your own; the other `uvx` commands on this page change in the same way.

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

Every copy brings the tool of the blueprint in `.github/`, so this and each later command run in the folder of the copy; on Windows, `py -3` runs Python in place of `python3`:

```sh
cd my-project
python3 .github/blueprint.py create
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-a-new-repository-starts.dark.svg">
  <img src="images/diagrams/how-a-new-repository-starts.svg" alt="How a new repository starts: copier copy writes the files of the project and runs no code of the blueprint. python3 .github/blueprint.py create, which every copy brings, makes the first commit on the branch main with a sign-off, creates the repository with gh repo create and pushes to it, applies the settings as code and shows the checklist. You take the steps that only a person can take, such as the release app and the secrets, and then the checks and the bots run.">
</picture>

`create` takes the owner and the name from your answers. It first checks what it needs, and a finding marked with ✘ stops it before anything is made, with the command that fixes it, as [the troubleshooting](troubleshooting.md#create-stops-at-its-preflight) explains. Then it makes the first commit with a sign-off on the branch `main`, on which every workflow runs, creates the repository and pushes to it, public unless you add `--private`, applies the settings as code and prints the checklist. `--dry-run` prints the preflight and the commands and runs none, and a run that stopped midway goes on where it stopped when you run `create` again.

## 3. Register the release app

One command registers the app on your account or organization, with its name and all of its permissions filled in and without a webhook, sets its private key and opens the pull request that names it:

```sh
python3 .github/blueprint.py app register
```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-the-release-app-is-registered.dark.svg">
  <img src="images/diagrams/how-the-release-app-is-registered.svg" alt="How the release app is registered: python3 .github/blueprint.py app register first checks what it needs, and nothing happens while something would stop it. A form on a free port of 127.0.0.1 sends the manifest of the app to GitHub, and you press Create GitHub App on the page of GitHub. GitHub comes back to that port with a code and the state of the form; a wrong state is refused, and the wait goes on. gh trades the code for the App ID, the Client ID and the private key. gh secret set takes the key on its stdin, so no file holds it, and Copier names the app in a pull request. You install the app and merge the pull request, and the checklist ticks the app off.">
</picture>

Like `create`, it first checks what it needs, and a finding marked with ✘ stops it before anything is made. Then it opens a page in your browser, which sends the [manifest of the app](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest) to GitHub. Be signed in to GitHub there as the owner of the repository, or as an owner of its organization, and press *Create GitHub App*. GitHub then hands over the name, the Client ID and the App ID of the app, so nothing is copied by hand, and its private key, this once:

- **The private key** goes on the stdin of GitHub CLI, into the secret `RELEASE_AUTOMATION_PRIVATE_KEY` of the environment `release`. No file holds it, nothing prints it, and no download is left behind.
- **The answers of the blueprint** name the app on a branch of its own, in a pull request, because `create` has protected `main` already. `--no-update` prints these commands instead of running them.

Two things are left for you, and the command prints the link of the first:

1. **Install the app** on the repository, at `https://github.com/apps/NAME/installations/new`.
2. **Merge the pull request** once its checks are green, on its page or with `gh pr merge --squash`.

The checklist sees the installation by the check suite that GitHub opens for an installed app at each push, so it ticks the app off after the merge when you install first, and after the next push otherwise.

The browser has to run on the same machine, since only this machine reaches the page. On another machine, `--no-browser` prints the address of the page: forward its port, such as with `ssh -L`, and open it there. An organization that GitHub doesn't name as the owner takes `--org ORG`. [The troubleshooting](troubleshooting.md#app-register-doesnt-go-on) shows what to do when the command waits or stops.

**A further repository** takes the same app, so register it once. Keep the three lines that the command printed in [the settings file of Copier](guide.md#your-own-account), and each new copy names the app. Each repository still needs the private key: on the settings page of the app, on the tab *Credentials*, under *Key pairs*, press *New key*; your browser saves it as a file, which you give to the command of the copy and then delete:

```sh
python3 .github/blueprint.py app connect --key-file private-key.pem
```

The same command takes an app that you registered by hand, with the permissions that [the guide](guide.md#once-per-repository) lists, or an existing copy that doesn't name the app yet: add `--name NAME --client-id CLIENT_ID --app-id APP_ID` from its settings page. They can't come from GitHub, which shows a private app to no token of GitHub CLI. The command checks them as the questions of Copier do, and it names the app in a pull request like `app register`.

Until the app is named and has its private key, each bot that acts as it says in its summary what is missing, rather than fail at its token: one whose work is what the app does fails, and one that only helps a pull request along warns, as [Troubleshooting](troubleshooting.md#a-bot-says-that-it-needs-the-release-app) shows. An app that is not installed on the repository still fails at its token.

## 4. Apply the settings

`create` applied the settings before the app had a name. Once the pull request has merged, apply them again:

```sh
git switch main
git pull
python3 .github/blueprint.py settings apply
```

It sets everything that the API can set: the rulesets, the variables that name the app, the environments, the security features and the actions that may run. A private repository works too, with `--private` for `create`: what GitHub doesn't offer it on its plan, such as code scanning or the rulesets on GitHub Free, the settings name as a notice and leave to the workflows, by the variables `CODE_SCANNING` and `DEPENDENCY_REVIEW`. The [FAQ](faq.md#can-a-repository-be-private-and-what-does-it-cost) shows what works on which plan.

## 5. Renovate

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/who-runs-renovate.dark.svg">
  <img src="images/diagrams/who-runs-renovate.svg" alt="Who runs Renovate: The answer renovate_runner decides who runs Renovate for a repository. The blueprint's owner keeps the hub, the Renovate workflow of the blueprint, which runs it for each of the owner's repositories on which the release app is installed. Every other owner gets a Renovate workflow in the repository itself, which runs it every two hours as the release app, for that repository alone, with the same Renovate and the same rules; or installs the Mend Renovate app, which needs no workflow and comes at every push. Each way reads the rules of .github/renovate.json5 and opens the updates as pull requests, whose checks decide whether they merge.">
</picture>

Every way reads the same rules, those of the blueprint in `.github/renovate-blueprint.json5` and yours in `.github/renovate.json5`, and keeps no issue open: what waits for you is a pull request. The checklist ticks Renovate off once it has opened a pull request.

- **`self`, a workflow of the repository:** `.github/workflows/renovate.yml` runs Renovate every two hours as your release app, with a token for this repository alone and without *Administration*. It is the workflow of the blueprint's own hub, with the same Renovate pinned by its digest, which every update of the blueprint moves on, and `.github/renovate-global.json5` holds the settings of the bot: commits through the API, which GitHub signs, and no scripts of the package managers. The bot user of your app is its author, which the workflow asks GitHub for. Its first run starts by itself; *Actions → Renovate → Run workflow* starts one at once. A run without the release app says in its summary what is missing, and a pull request that changes the rules or a lock file shows whether Renovate still accepts and reads them; the PR coach explains a failure of this check, *renovate rules*, also on a pull request from a fork, as [the troubleshooting](troubleshooting.md#the-check-renovate-rules-fails) does.
- **`mend`, the Mend Renovate app:** install the [Mend Renovate app](https://github.com/apps/renovate) on the repository. It reads the same rules, comes at every push rather than on a schedule, and needs no workflow and no token of yours. The branch bot and the fix bot update its branches as your release app, so add the bot user of the app to `gitIgnoredAuthors` in `.github/renovate.json5`, or Renovate takes the branches for edited and stops rebasing them; the checklist prints the line with the number of your app's bot user.

To change the answer later, run `uvx --from copier==9.19.1 copier update --defaults --vcs-ref=:current: --data renovate_runner=mend` on a branch and merge the update in a pull request, as in [step 3](#3-register-the-release-app).

## 6. The issue assistant

With `issue_assistant_ai`, the issue assistant analyzes each new issue with Claude, and the checklist asks for its token, as the secret `CLAUDE_CODE_OAUTH_TOKEN` of the environment `issue-assistant`. Without it, `.github/repository.toml` sets the variable `ISSUE_ASSISTANT_AI` to `off`, the environment asks for no secret, and `SUPPORT.md` tells reporters that no AI reads their issues; labels, reminders, closing and the commands of the maintainer work as before. `uvx --from copier==9.19.1 copier update --defaults --vcs-ref=:current: --data issue_assistant_ai=true`, on a branch as in [step 3](#3-register-the-release-app), turns the AI on later.

## 7. The checklist

```sh
python3 .github/blueprint.py checklist
```

It shows what is left for a person and which steps are done: the release app, the settings, the secrets, the installation, Renovate, the community profile, the social preview and the badges. A private repository also gets the step *GitHub Code Security on*, neutral without it, since the plan of its owner may not offer it. Once every step has its tick, the repository looks after itself.

## 8. The settings app (optional)

The release app can do everything that the bots need, the administration of each repository included: its rulesets, environments, variables and the actions that may run. A second app, the **settings app**, can take the administration over, so that the release app, which most workflows use, can give it up: a stolen key of the release app then can't change a ruleset or let a new action run.

- **The settings bot** applies the settings as the settings app, every week and after each change of them.
- **The OSV-Scanner workflow** closes the Dependabot alerts of the advisories that an `osv-scanner.toml` accepts, with the reason and the end of the acceptance, and opens again each one that it closed once the acceptance is gone: the token of a workflow can't read the Dependabot alerts.
- **The blueprint bot** lets the actions of a new release of the blueprint start before it pushes the update: it adds the patterns of the release's `[actions.selected]` to the list of the allowed actions on GitHub, and takes none away, so the checks of the update's pull request start without a `settings apply` from its branch. The settings bot narrows the list to the settings after the merge.
- **The release app** then needs no *Administration*, *Pages*, *Variables*, *Environments* and *Secrets* any more.

Without the settings app, everything works as before: the release app applies the settings and closes the accepted Dependabot alerts, and an update that brings a new action waits for `settings apply` from its branch. With only the variable or only the secret set, both bots warn and go on with the release app.

1. **Register the app** on your account, with its permissions filled in and without a webhook, at [this link](https://github.com/settings/apps/new?description=Applies+the+settings+as+code+of+the+repositories+made+from+Repo+Blueprint.&public=false&webhook_active=false&administration=write&issues=write&pages=write&vulnerability_alerts=write&actions=read&contents=read&environments=read), or for an organization at the same address under `https://github.com/organizations/ORG/settings/apps/new`. Name it, such as `octo-org-settings`, and give it these repository permissions, and no others:

    | Permission | Access | What for |
    | --- | --- | --- |
    | Administration | Read and write | rulesets, the switches of security, the actions that may run, environments |
    | Issues | Read and write | the labels |
    | Pages | Read and write | the website's settings |
    | Dependabot alerts | Read and write | the Dependabot alerts of the advisories that an `osv-scanner.toml` accepts, which the OSV-Scanner workflow closes and opens again |
    | Variables | Read and write | the variables of `[variables]`; set it by hand, the link can't |
    | Actions | Read-only | the settings of the workflows |
    | Contents | Read-only | the files of the community profile |
    | Environments | Read-only | the environments, their branch rules and the names of their secrets, never their values |
    | Metadata | Read-only | which GitHub asks for itself |

    Leave *Where can this GitHub App be installed?* at *Only on this account*, and create the app.

2. **Note its Client ID** on the settings page of the app, and on its tab *Credentials*, under *Key pairs*, press *New key*; your browser saves the key as a file, such as `octo-org-settings.2026-10-25.private-key.pem`, which the commands below call `settings-private-key.pem`.
3. **Install the app** on every repository made from the blueprint, the same ones as the release app: *Install App* on the settings page of the app, then *Only select repositories*.
4. **Name it in each repository,** with its Client ID as a variable and its key as a secret of the environment `release`, which only `main` may use. The GitHub CLI reads the file and shows the key nowhere; delete the file afterwards. In Git Bash or another POSIX shell:

    ```sh
    for repo in octo-org/my-project octo-org/another; do
      gh variable set SETTINGS_APP_CLIENT_ID --repo "$repo" --body CLIENT_ID
      gh secret set SETTINGS_APP_PRIVATE_KEY --env release --repo "$repo" < settings-private-key.pem
    done
    ```

    In PowerShell, which has neither this `for` nor a `<` that reads a file:

    ```powershell
    foreach ($repo in 'octo-org/my-project', 'octo-org/another') {
      gh variable set SETTINGS_APP_CLIENT_ID --repo $repo --body CLIENT_ID
      Get-Content -Raw settings-private-key.pem | gh secret set SETTINGS_APP_PRIVATE_KEY --env release --repo $repo
    }
    ```

    The variable can also live in the settings as code, as `SETTINGS_APP_CLIENT_ID = "CLIENT_ID"` under `[variables]` of `.github/repository.project.toml`, which the settings bot applies with the release app first.

5. **Check it:** *Actions → Settings → Run workflow*. The run takes the step *Create a token of the settings app* and skips *Check that the release app is set up*. When GitHub refuses the token, of an app that is not installed on the repository or lacks a permission, the summary of the run says so, and no setting changes.
6. **An app registered before the OSV-Scanner workflow closed the Dependabot alerts** lacks their permission, and the job *dependabot alerts* of that workflow fails, or, in a repository of an owner other than the blueprint's, leaves a notice: on the settings page of the app that the summary of the run names, the settings app or, without it, the release app, under *Permissions & events* → *Repository permissions*, set *Dependabot alerts* to *Read and write* and press *Save changes*. GitHub then asks to accept the new permission on the installation: *Settings → Applications → Installed GitHub Apps*, *Configure* next to the app, *Review request*, *Accept new permissions*. Then run *Actions → OSV-Scanner → Run workflow*, with *dry_run* first to see what it would close.
7. **Take the permissions from the release app** once the settings bot has run as the settings app in every repository: on the settings page of the release app, under *Permissions & events*, set *Administration*, *Pages*, *Variables*, *Environments* and *Secrets* to *No access*, and *Dependabot alerts* to *Read-only*. Its other permissions stay, for the release bot, Renovate, the blueprint bot and the others.

`gh variable delete SETTINGS_APP_CLIENT_ID` hands the settings back to the release app, which needs its permissions again then.
