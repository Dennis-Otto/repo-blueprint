# Guide

How to start a repository, the kinds of projects, what every repository gets, and what a person sets up once.

## Start a repository

--8<-- "README.md:quick-start"

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-a-new-repository-starts.dark.svg">
  <img src="images/diagrams/how-a-new-repository-starts.svg" alt="How a new repository starts: copier copy writes the files of the project and runs no code of the blueprint. python3 .github/blueprint.py create, which every copy brings, makes the first commit on the branch main with a sign-off, creates the repository with gh repo create and pushes to it, applies the settings as code and shows the checklist. You take the steps that only a person can take, such as the release app and the secrets, and then the checks and the bots run.">
</picture>

## Kinds of projects

--8<-- "README.md:kinds"

## What a new repository gets

Each of these pages describes a group of what every repository gets: what runs, the files that run it and the details.

- [Checks and the PR coach](features/checks.md): What runs in every pull request and on `main`, how long it takes, and how a check that fails explains itself.
- [Fix bot and self-healing](features/self-healing.md): What a repository fixes by itself: the findings that a command can fix, tests that fail once, checks that stop, releases and bots that fail.
- [Mutation tests, fuzzing and property tests](features/tests.md): The tests beyond the checks of a pull request: whether the tests notice a change of the code, and inputs that nobody wrote down.
- [Releases and security](features/releases.md): How a change becomes a signed release, and the security checks of every repository.
- [Dependencies and updates](features/updates.md): How the dependencies and the files of the blueprint stay current, and which files belong to the project.
- [Bots, their cost and the dashboard](features/bots.md): The bots of issues and pull requests, what starts them and what they cost, and the dashboard of every repository.
- [Website, diagrams and screenshots](features/website.md): The website of the documentation, and the diagrams and screenshots that keep themselves current.
- [Settings as code](features/settings.md): The settings of a repository as a file that a pull request changes.
- [Community and development](features/development.md): The files of the community, the dev container and the rules for coding agents.

## Set up a repository

What a person does once: the release app of the account and its defaults, the secrets and the delivery of each repository, and the way an existing repository takes the blueprint.

### Your own account

The blueprint works for every account and organization on GitHub, and a repository made from it names nothing of the blueprint's owner but the links to the blueprint. Each owner brings two things of their own:

- **A release app,** once for all of their repositories. The bots act as a GitHub App of the owner: its token starts the checks of the release and update pull requests, may change workflows and creates the release tags, which the token of a job can't. Only the owner of an app has its private key, so the blueprint can't lend its own. Copy the blueprint with the question of the release app left empty, and `checklist` starts with a link that registers the app on your account or organization, with its name and permissions filled in and without a webhook; set *Variables* by hand, which the link can't fill in. Create the app, generate a private key on its settings page, and name the app in the answers of the blueprint, with the name in its address and the Client ID and App ID of that page:

  ```sh
  copier update --defaults --vcs-ref=:current: --data release_app=NAME --data release_app_client_id=CLIENT_ID --data release_app_id=APP_ID
  ```

  Commit the update: `.github/repository.toml` names the app, only it may create release tags, and `settings apply` and `checklist` then ask for its private key and its installation on the repository. Until then every bot that acts as the app checks for it first and says in its summary what is missing, the variable or the private key, rather than fail at a token: a bot whose work is what the app does, such as the blueprint bot, the settings bot or Renovate, fails, and one that only helps a pull request along, such as the fix bot or the branch bot, warns and goes on without it.
- **Your defaults,** so that every new repository asks only what is new. Copier's [settings file](https://copier.readthedocs.io/en/stable/settings/) takes the answers that stay the same, on Windows in `%LOCALAPPDATA%\copier\settings.yml` and on macOS in `~/Library/Application Support/copier/settings.yml`:

  ```yaml
  # ~/.config/copier/settings.yml, or the file that COPIER_SETTINGS_PATH names
  defaults:
    owner: octo-org
    author: Octo Org
    release_app: octo-org-release-automation
    release_app_client_id: Iv23liExample
    release_app_id: "123456"
  ```

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-an-owner-gets-a-release-app.dark.svg">
  <img src="images/diagrams/how-an-owner-gets-a-release-app.svg" alt="How an owner gets a release app: You copy the blueprint with the question of the release app left empty. The checklist links the registration of the app on your account or organization, with its name and permissions filled in. You create the app and its private key, and name it with copier update and the name, Client ID and App ID of its settings page. After the commit, settings apply sets the variables and the ruleset of the release tags, and the checklist asks for the private key and the installation on the repository. Then the bots run as your app; until then each bot that acts as it says in its summary what is missing.">
</picture>

Two more answers decide what runs for you, and the page [Your own account](https://dennis-otto.github.io/repo-blueprint/own-account.html) walks through every step:

- **Renovate,** by the answer `renovate_runner`. The blueprint's owner keeps `hub`, the Renovate workflow of the blueprint, which runs it for each of the owner's repositories. Every other owner gets `self`: `.github/workflows/renovate.yml`, the same workflow with the same Renovate, pinned by its digest, which runs it every two hours as the release app, with a token for that repository alone, and names the bot user of the app as the author of its commits. In a pull request that changes the rules or a lock file, its check *renovate rules* shows whether Renovate accepts the rules and reads every file, and explains a failure through the PR coach, as every other check does. With `mend`, the owner installs the [Mend Renovate app](https://github.com/apps/renovate) instead, which comes at every push and needs no workflow. Every way reads the same rules, and `checklist` ticks Renovate off once it has opened a pull request.
- **The AI of the issue assistant,** by the answer `issue_assistant_ai`: without it, the variable `ISSUE_ASSISTANT_AI` is `off`, the environment `issue-assistant` asks for no secret, and `SUPPORT.md` says that no AI reads the issues; labels, reminders, closing and the commands of the maintainer go on, and the checklist passes without a token of Claude.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/who-runs-renovate.dark.svg">
  <img src="images/diagrams/who-runs-renovate.svg" alt="Who runs Renovate: The answer renovate_runner decides who runs Renovate for a repository. The blueprint's owner keeps the hub, the Renovate workflow of the blueprint, which runs it for each of the owner's repositories on which the release app is installed. Every other owner gets a Renovate workflow in the repository itself, which runs it every two hours as the release app, for that repository alone, with the same Renovate and the same rules; or installs the Mend Renovate app, which needs no workflow and comes at every push. Each way reads the rules of .github/renovate.json5 and opens the updates as pull requests, whose checks decide whether they merge.">
</picture>

### Once per repository

- **The release app** of the owner opens the release and update pull requests, so that their checks run. Register it once for the account, as [your own account](#your-own-account) shows, install it on the repository, and set its private key as the secret `RELEASE_AUTOMATION_PRIVATE_KEY` of the environment `release`. The app needs the permissions *Actions*, *Administration*, *Checks*, *Commit statuses*, *Contents*, *Issues*, *Pages*, *Pull requests*, *Variables* and *Workflows* (read and write), and *Dependabot alerts*, *Environments* and *Secrets* (read): with them the settings bot applies the settings as code, Renovate updates the dependencies, and the rollout of the blueprint starts the blueprint bot of every repository after a release. Renovate gets a token without *Administration*, and the settings bot one with only *Administration*, *Issues*, *Pages* and *Variables* (read and write) and *Actions*, *Contents* and *Environments* (read), which can neither push a commit nor change a workflow; GitHub refuses that token to an app that lacks one of them, and the summary of the run says which permissions to grant (decision 0075 of the [decisions](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)). The release workflow creates every release tag with the app, and the ruleset *Release tag creation* lets nobody else create one; the variables `RELEASE_APP`, `RELEASE_AUTOMATION_CLIENT_ID` and `RELEASE_AUTOMATION_APP_ID` in `.github/repository.toml` name the app, from the answers `release_app`, `release_app_client_id` and `release_app_id`, and a project with another app than its answers name sets them in `.github/repository.project.toml`.
- **The issue assistant** needs `CLAUDE_CODE_OAUTH_TOKEN` in the environment `issue-assistant`, unless the answer `issue_assistant_ai` switched its AI off.
- **Delivery:** trusted publishing on PyPI or npm, the app certificate of a Nextcloud app, or the HACS submission, as the checklist says.
- **OpenSSF Best Practices:** add the project on [bestpractices.dev](https://www.bestpractices.dev/en/projects/new) with the URL of the repository. It proposes the answers of `.bestpractices.json`, about 90 to 100 of the badge and of the OSPS Baseline that the blueprint guarantees for the kind of project, each with the file that shows it; *Save (and continue) 🤖* takes them in on each level, also after an update of the file. Answer the rest, what only your software and your people can say, and add both badges to the README, as the checklist shows.

`checklist` prints the `gh secret set` commands; the value is typed into the prompt of the GitHub CLI and never appears anywhere else.

### An existing repository

An existing repository takes the blueprint on a branch, in one pull request:

1. `copier copy --overwrite --vcs-ref vX.Y.Z --data sample_code=false gh:Dennis-Otto/repo-blueprint .` with the answers that fit the repository, without the sample code and tests of a new one, such as its description, topics and homepage as they are on GitHub, so that `settings apply` changes nothing there. The files of the project (README, changelog, code, tests, manifests, labels, issue forms, icons) stay as they are.
2. Look at the diff of every file of the blueprint and put back what belongs to the project only: sections of SECURITY.md or CONTRIBUTING.md, rules of Renovate (in `.github/renovate.json5`), hosts of the issue assistant, ignore rules. `copier update` keeps these changes from then on.
3. Write the version of the latest release into `version.txt` and `.release-please-manifest.json`, start `CHANGELOG.md` with `## Unreleased`, and give `.github/labels.toml` the labels of the bots (`autorelease: pending`, `autorelease: tagged`, `merge-conflict`, `maintenance`, `bot-failure`, `docker`).
4. Put the checks of the project alone, such as its end-to-end tests, into `.github/repository.project.toml` and `scripts/check-project.sh`, with the patterns of the actions that its own workflows run, which `blueprint.py settings check` names; remove the workflows, scripts and tests that the blueprint replaces, and delete files of the template that the project doesn't need, such as a sample test. A repository without `docs/` has no website until it writes `docs/index.md`; `mkdocs.yml` shows how German pages join it.
5. Open the pull request. Once its new checks pass, `blueprint.py settings apply` switches the required checks, the variables and the labels, and the pull request can merge.

The configuration of the checks belongs to the blueprint and looks for the code where a new project of the same kind has it. Every file it names comes with the blueprint, also without the sample code:

| Kind | Code | Tests | From the blueprint |
| --- | --- | --- | --- |
| Nextcloud app | `lib/` | PHPUnit tests in `tests/Unit/` | `psalm.xml` and `phpunit.xml`, with the `tests/bootstrap.php` and `tests/stubs/` that they load |
| Node package | `src/`, built into `dist/` | `test/`, typechecked by `tsconfig.json`; the `npm test` of a new project runs `test/**/*.test.ts` | `tsconfig.json` and `tsconfig.build.json`, which need `typescript` and `@types/node` in the `package.json` of the project, and `biome.jsonc`, whose step *Lint and format* runs once `@biomejs/biome` is there too |

The other kinds set these places in files of their own, such as `pyproject.toml`. What lies in `tests/` belongs to the project: the copy and every update add only the files that are missing there, so an app with its own bootstrap keeps it.
