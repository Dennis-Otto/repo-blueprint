---
description: "What to do when something in a repository of Repo Blueprint doesn't work: a create that stops at its preflight or midway, an update that conflicts, a required check that never reports, settings apply without administrator rights, a settings bot whose token the release app refuses, a switch of the security that GitHub keeps off, a release pull request without checks, Renovate that opens no updates, and OSV-Scanner that reports a version that another package pins."
---

# Troubleshooting

Most problems explain themselves where they happen: a check that fails says in its summary and in the report of the PR coach what it found and how to fix it, a bot says in the summary of its run what is missing, and the bot-health bot keeps one issue open for each bot that fails on `main`. This page covers what needs a person beyond that. The common questions are on the page [Questions and answers](faq.md).

## create stops at its preflight

**What you see:** `python3 .github/blueprint.py create` shows *The preflight of OWNER/NAME* with a line marked ✘ and the command that fixes it below, and ends with *the preflight found 1 problem that would stop create, which made nothing*.

**Why:** before its first step, `create` checks what its steps need, so that a missing tool or right can't leave a repository that is half made. The preflight only asks git and gh, and `create` makes nothing while a finding is marked with ✘. A finding marked with · is one that GitHub didn't answer or that the preflight can't tell, and it stops nothing. `python3 .github/blueprint.py doctor` runs the preflight alone, and `create --dry-run` shows it with the commands.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/how-create-checks-first-and-goes-on-where-it-stopped.dark.svg">
  <img src="images/diagrams/how-create-checks-first-and-goes-on-where-it-stopped.svg" alt="How create checks first and goes on where it stopped: python3 .github/blueprint.py create starts with its preflight, which only asks: Python, Git and the identity of the first commit, the GitHub CLI and its sign-in with the scopes repo and workflow, the owner and the name. A finding marked with ✘ stops it before anything is made and names the command that fixes it; python3 .github/blueprint.py doctor shows the same alone. A new copy then gets git init, its first commit and gh repo create with the push. A folder whose origin pushes to the repository on GitHub already, from a run that stopped midway, gets only the push when GitHub has no branch main yet. Both end with settings apply and the checklist.">
</picture>

**What to do:** run the command below the finding, then `create` again.

- **Python before 3.12:** the tools of the new repository, such as its lock files, need Python 3.12 or later. Install it from [python.org](https://www.python.org/downloads/); on Windows, `py -3` runs it.
- **Git is not installed:** install it from [git-scm.com](https://git-scm.com/downloads).
- **Git has no name or no email address to commit with:** `git config --global user.name "Your Name"` and `git config --global user.email "you@example.com"`. The sign-off of the first commit names them.
- **GitHub CLI before 2.48, or none:** install or update it as [its installation](https://github.com/cli/cli#installation) says.
- **gh is not signed in to github.com:** `gh auth login --hostname github.com --scopes workflow`. With a token in the variable `GH_TOKEN`, gh uses that one: give it the scopes, or remove the variable.
- **Without the scopes that create needs:** `gh auth refresh --hostname github.com --scopes workflow,read:org`, with the scopes that the finding names. `repo` creates the repository and pushes, `workflow` pushes the files in `.github/workflows/` over HTTPS, which GitHub refuses without it (with `ssh` as gh's git protocol the key pushes them, and the preflight doesn't ask for `workflow`), and `read:org` shows whether you own the organization. A fine-grained token names no scopes, so the preflight can't tell (·): it has to create repositories of the owner, with *Administration*, *Contents* and *Workflows* (read and write).
- **GitHub has no account or organization of that name:** the owner of the answers is misspelled. Name the repository with `python3 .github/blueprint.py --repo OWNER/NAME create`.
- **An account of its own, while gh is signed in as another:** only that account creates its repositories. `gh auth switch --user OWNER` switches to it when gh knows it, `gh auth login` signs it in.
- **No member of the organization, or invited:** an owner of the organization adds you, or you accept the invitation at `https://github.com/orgs/OWNER/invitation`.
- **A member of the organization, not an owner (·):** `gh repo create` works where the organization lets its members create repositories, and you then administer the repository that you made, which `settings apply` needs. Otherwise an owner runs `create`.
- **The name is taken:** choose another with `--repo OWNER/NAME`. When it is the repository that an earlier run of `create` made, connect the folder to it with `git remote add origin https://github.com/OWNER/NAME.git` and run `create` again, which goes on from there.
- **origin pushes to a repository that GitHub doesn't have:** it was deleted, or the address is wrong. `git remote remove origin`, then `create` again.

## create stopped midway

**What you see:** `create` stopped after `gh repo create`, at the push or at `settings apply`, such as on a connection that dropped, and the folder pushes to `origin` now.

**Why:** `gh repo create` makes the repository on GitHub and adds `origin` before it pushes, so a push or settings that failed leave a repository that is there.

**What to do:** run `python3 .github/blueprint.py create` again. When `origin` pushes to the repository of the answers, and GitHub has it, `create` goes on from the first step that is left: the push of `main` when GitHub has no branch `main` yet, signed in by gh as `gh repo create --push` is, then `settings apply` and the checklist, which change only what differs. A folder that pushes to another repository is no new copy, and `create` refuses it.

## An update of the blueprint conflicts

**What you see:** the pull request of the blueprint bot, from the branch `blueprint/update`, has the label `merge-conflict` and its auto-merge is off. Its description has a checklist of the files to resolve.

**Why:** the repository changed lines of a file of the blueprint that the new release changes too. `copier update` merges both line by line and leaves conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`) where it can't.

**What to do:** resolve the markers on the branch of the pull request and push:

```sh
git fetch origin && git switch blueprint/update
# Edit each file of the checklist: keep what the repository needs of both sides.
bash scripts/check.sh   # fails on a conflict marker that is left
git commit -s -am "Resolve the conflicts of the blueprint update"
git push
```

Once you commit to its branch, the bot leaves the branch to you: when a newer release is out, it says so in one comment, and after you merge or close the pull request, its next run brings the rest. To start over, or to see the conflicts on your machine first, run the update with the same Copier as the bot, whose version and hashes `.github/copier-requirements.txt` pins. Put its virtual environment outside the checkout, and start from a current `main` on a branch of your own: Copier stops with *Destination repository is dirty* while the working tree holds a change or a file that Git doesn't ignore, and on `blueprint/update` the answers already name the new release.

```sh
python3 -m venv ~/.venvs/copier
~/.venvs/copier/bin/pip install --require-hashes -r .github/copier-requirements.txt
git switch main && git pull
git status --short   # must print nothing: commit or stash what it lists
git switch -c blueprint/local
~/.venvs/copier/bin/copier update --defaults --conflict inline
```

On Windows, create the environment with `py -3 -m venv %USERPROFILE%\.venvs\copier` and run its programs from `%USERPROFILE%\.venvs\copier\Scripts\` in place of `~/.venvs/copier/bin/`.

`--defaults` takes the answers of `.copier-answers.yml`, and `--conflict inline` writes the markers into the files, as the bot does, rather than files of rejected changes beside them. A change that a project keeps in a file of the blueprint conflicts again with each update that touches the same lines; move it into a file of the project where one exists, as the [questions and answers](faq.md#which-files-may-a-project-change) show.

## A required check never reports

**What you see:** a pull request waits for a check with *Expected — Waiting for status to be reported*, and no run of it starts or finishes.

**Why, and what to do:**

- **An update renamed a required check.** The ruleset *Protect main* still asks for the old name, which no workflow reports any more. Check out the branch of the pull request and run `python3 .github/blueprint.py settings apply` there right before you merge it, so that the ruleset asks for the new names; the settings bot applies the same after the merge.
- **The workflow didn't start.** Its run under *Actions* shows a *startup failure* when it uses an action that the list of the allowed actions lacks. The check *lint* of the pull request names each one already, and so does `python3 .github/blueprint.py settings check`; add its pattern to `[actions.selected]` of `.github/repository.project.toml` for a workflow of the project, and apply the settings. A step with `uses: docker://…` fails the same way, as GitHub counts the image as an action that no pattern allows: run it in a `run:` step with the `docker run --rm` that the check names instead.
- **The pull request comes from a token that starts no workflow,** such as the token of a job: see [The release pull request has no checks](#the-release-pull-request-has-no-checks).
- **The pull request comes from the fork of an outside contributor:** its workflows wait for a maintainer, who starts them with *Approve and run* on the pull request. The branch bot starts them itself only for a head that it made on top of commits that a maintainer approved; the summary of its run under *Actions*, in the workflow *Update branches*, says what such a pull request waits for.
- **A check of the project alone** that `.github/repository.project.toml` requires runs in a workflow with a path filter, so a pull request that changes other files never starts it. A required check runs in every pull request: remove the filter, or let the job decide inside its steps what to skip, so that it still reports success.

## Applying the settings without administrator rights

**What you see:** `python3 .github/blueprint.py settings apply` ends with lines such as *the rulesets could not be applied: … the token may lack the permission Administration (read and write)*.

**Why:** most of the settings as code, such as the rulesets, the security and the permissions of Actions, need an administrator of the repository. `blueprint.py` uses the account that `gh auth login` signed in, and applies every part that GitHub accepts; it names each part that GitHub refused with the permission that it needs.

**What to do:**

- **Let the settings bot apply them:** it runs as the release app, which has the permission *Administration*, after every change of the settings as code on `main`, every week and on demand under *Actions → Settings → Run workflow*. Change `.github/repository.project.toml` in a pull request, and the settings follow its merge.
- **Ask an administrator** to run `settings apply` once, for a new repository whose release app is not set up yet.
- **See what differs** with `python3 .github/blueprint.py settings check`, which changes nothing; some parts, such as who may bypass a ruleset, show only to an administrator.

## The settings bot fails at its token

**What you see:** the Settings workflow fails at the step *Create a token of the release app*, and its summary says *The release app refused the token of the settings bot*.

**Why:** the settings bot asks the release app for a token with only the permissions that `settings apply` needs: *Administration*, *Issues*, *Pages* and *Variables* (read and write), and *Actions*, *Contents* and *Environments* (read). GitHub refuses the whole token when the app lacks one of them, as an app does that was registered before the bot asked for it, or without *Variables*, which the link of the checklist can't fill in. No setting has changed.

**What to do:**

- **Grant the missing permissions** on the settings page of the app, under *Permissions & events*; the log of the step names what GitHub answered.
- **Accept them on the installation:** GitHub asks the owner of each installation to accept new permissions, under *Settings → Applications → Installed GitHub Apps*.
- **Run the workflow again** under *Actions → Settings → Run workflow*.

## The settings name a switch that GitHub doesn't do

**What you see:** the summary of the Settings workflow, or `python3 .github/blueprint.py settings apply`, ends with *GitHub doesn't do this for the repository, which fails nothing*, and below it a switch such as `security.secret_scanning_non_provider_patterns` with the line that stops asking for it.

**Why:** GitHub offers some switches of the security only with some plans, such as the generic patterns of secret scanning, which find private keys, connection strings and passwords that no provider issued. On a repository of a user GitHub accepts their write and keeps them off, or leaves them out of its answer. The settings bot asks again in every run, so that a repository whose plan gains the switch gets it, and names what GitHub kept as it was without failing the run ([decision 0055](decisions/0055-what-github-does-not-do-for-a-repository-fails-no-settings-run.md)).

**What to do:**

- **Nothing,** if the repository should get the switch once its plan has it: the notice stays in the summary of every run and fails nothing.
- **Stop asking for it** with the line that the notice names, such as `secret_scanning_non_provider_patterns = false` under `[security]` in `.github/repository.project.toml`, in a pull request; the notice ends with its merge.
- **Expect `settings check` to name it as a difference:** it writes nothing, and only a write shows what GitHub keeps.

## The release pull request has no checks

**What you see:** the pull request `chore: release x.y.z` shows no checks, and the summary of the Release workflow says that the repository names no release app.

**Why:** without the release app, release-please keeps the release pull request with the token of the job, which starts no workflow, and only the release app may create and sign a release tag, so no release can be published.

**What to do:**

1. Run `python3 .github/blueprint.py app register`, as the page [Your own account](own-account.md#3-register-the-release-app) shows. It registers the release app, sets its private key and opens the pull request that names it, or `app connect --key-file FILE` does so for an app that exists; the variable [`RELEASE_AUTOMATION_CLIENT_ID`](reference/variables.md#release_automation_client_id) then names it, and the secret [`RELEASE_AUTOMATION_PRIVATE_KEY`](reference/variables.md#release_automation_private_key) of the environment `release` holds the key.
2. Install the app on the repository, and merge the pull request.
3. Start the Release workflow under *Actions → Release → Run workflow*, or merge the next pull request. It updates the release pull request as the app, and its checks start.

When the token of the app fails, as for an app that isn't installed on the repository or a key that doesn't belong to it, the step that asks for the token fails, and the bot-health bot keeps an issue open until a run passes. A pull request whose checks didn't start for another reason starts them when a person closes and reopens it.

## app register doesn't go on

**What you see:** `python3 .github/blueprint.py app register` waits at *confirm the page at*, or ends with *GitHub didn't come back*, *The page was cancelled* or *Refused an answer whose state doesn't belong to this run*.

**Why:** the command waits for GitHub to come back to a server on a free port of `127.0.0.1`, which only this machine reaches, and for ten minutes at most. It sets nothing before that. GitHub sends the browser back only after you press *Create GitHub App*, and the form carries a random state, so an answer without it is refused and the wait goes on.

**What to do:**

- **The page didn't open:** open the address that the command printed, in a browser on the same machine. For a browser on another machine, run with `--no-browser` and forward the port.
- **GitHub shows a form without the name and the permissions:** the manifest may not have survived a sign-in on the way. Sign in to GitHub first, then run the command again.
- **The name is taken:** change it on the page of GitHub; the command takes the name that GitHub made.
- **It says that GitHub made the app on another account:** the browser was signed in as someone other than the owner, and a private app installs only on the account that owns it. Delete that app at the address that the command names, sign in as the owner, and run it again.
- **GitHub refused the private key:** the app exists and no file holds its key. Make a new key on the settings page of the app and run the `app connect` command that the error shows.
- **A step of the pull request failed:** the private key is set, and the error lists the commands that are left, starting with the one that failed. Fix its cause and run them.

## A bot says that it needs the release app

**What you see:** a run of a bot, such as Settings, the blueprint bot, the branch bot or the fix bot, shows the annotation *This repository names no release app in the variable RELEASE_AUTOMATION_CLIENT_ID* or *has no private key of its release app*, and its summary starts with *… needs the release app of the owner*.

**Why:** every bot that acts as the release app checks for the app before it asks for its token, in its step *Check that the release app is set up*, and names what is missing rather than fail at the token with an error that says nothing of the cause. A bot whose work is what the app does fails: the blueprint bot, the settings bot, the upstream bot of a Nextcloud app, Renovate in a workflow of the repository and the Rollout. A bot that only helps a pull request along warns and goes on without the token: the fix bot, the branch bot, the diagram and screenshot bots, the merge of Dependabot's updates and the release bot.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="images/diagrams/the-check-of-the-release-app.dark.svg">
  <img src="images/diagrams/the-check-of-the-release-app.svg" alt="The check of the release app: Before a bot asks for a token of the release app, it checks that the repository names the app in the variable RELEASE_AUTOMATION_CLIENT_ID and has its private key in the environment release. With both, it asks for the token and does its work. Without one, it says in an annotation and in its summary which one is missing and that the checklist sets it up. A bot whose work is what the app does, such as the blueprint bot, the settings bot or Renovate, then fails; one that only helps a pull request along, such as the fix bot or the branch bot, warns and goes on without the token.">
</picture>

**What to do:** run `python3 .github/blueprint.py app register`, as the page [Your own account](own-account.md#3-register-the-release-app) shows, or `app connect --key-file FILE` for an app that exists. It sets the secret [`RELEASE_AUTOMATION_PRIVATE_KEY`](reference/variables.md#release_automation_private_key) of the environment `release` and opens the pull request that names the app in the variable [`RELEASE_AUTOMATION_CLIENT_ID`](reference/variables.md#release_automation_client_id). Install the app on the repository and merge the pull request; `python3 .github/blueprint.py checklist` shows what is left. The next run of each bot does its work.

## Renovate opens no updates

**What you see:** no pull request of Renovate, and the checklist doesn't tick Renovate off.

**Why, and what to do:** first, the rules may hold an update back: it comes a week after its release, on a Monday, unless it fixes a vulnerability, and Renovate keeps no issue that lists what waits ([decision 0057](decisions/0057-renovate-keeps-no-dependency-dashboard.md)). Otherwise it depends on who runs Renovate, by the answer [`renovate_runner`](reference/questions.md#renovate_runner):

- **`self`, a workflow of the repository:** `.github/workflows/renovate.yml` runs as the release app; a run without the app says in its summary what is missing. *Actions → Renovate → Run workflow* starts one at once, and a pull request that changes the rules or a lock file shows whether Renovate still accepts and reads them.
- **`mend`, the Mend Renovate app:** install the [Mend Renovate app](https://github.com/apps/renovate) on the repository; it comes at every push.
- **`hub`, the Renovate workflow of the blueprint,** for the repositories of the blueprint's owner: the release app must be installed on the repository, which needs a `.github/renovate.json5`.

Where a Renovate workflow runs, the bot-health bot keeps one issue open with the warnings and errors of Renovate.

## OSV-Scanner reports a version that another package pins

**What you see:** the check *osv-scanner* fails, and code scanning has open alerts of OSV-Scanner for a lock file whose dependency no update can move, so that the Findings workflow fails on `main` too. Renovate opens no pull request for them, and the issue *Renovate logs problems* lists `Detected empty commit - aborting git push` for a branch such as `renovate/pypi-pillow-vulnerability`. Home Assistant, for example, pins the Pillow and the uv that the tests of an integration install.

**Why:** the package that pins the version, such as the test plugin of Home Assistant, holds it until its next release, so the lock file stays as it is: Renovate's fix of the vulnerability is an empty commit, in every run.

**What to do:** accept every advisory of that version in the `osv-scanner.toml` beside the lock file, with the reason and the date when a person looks again, as an entry of `[[PackageOverrides]]`; OSV-Scanner reads the file in the folder of each lock file. A new Home Assistant integration has the entries for its test tools already.

```toml
[[PackageOverrides]]
name = "pillow"
version = "12.3.0"
ecosystem = "PyPI"
vulnerability.ignore = true
effectiveUntil = 2026-11-22
reason = "Home Assistant pins Pillow 12.3.0 for the tests; its next release moves it."
```

Then let `blueprint.py` write the rule of Renovate for it, and commit both files:

```sh
python3 .github/blueprint.py advisories --fix
```

`.github/renovate-accepted.json5` then has a rule for each such version, which `.github/renovate-blueprint.json5` extends: Renovate makes no update of that version in the lock files of that folder, which only the package that pins it moves. The step *Accepted advisories* of `scripts/check.sh` fails while the rules and the `osv-scanner.toml` files disagree, and when OSV-Scanner couldn't use a file: it ignores a whole file with a key that it doesn't know. After `effectiveUntil`, OSV-Scanner reports the advisories again; once the package that pins the version moves it, delete the entry. An advisory that doesn't affect the project, of a version that an update could move, goes into `[[IgnoredVulns]]` alone, with its `id` and reason, and the OpenVEX document of each release states those of the `osv-scanner.toml` in the root ([decision 0059](decisions/0059-accept-a-pinned-version-and-tell-renovate.md)).

Dependabot doesn't read `osv-scanner.toml` either. After the merge, the job *dependabot alerts* of the OSV-Scanner workflow closes each Dependabot alert that an entry covers, as a tolerable risk with a comment that starts with *Accepted in* and names the file, the end and the reason; an entry of `[[IgnoredVulns]]` closes the alerts of its advisory once it has `ignoreUntil` and `reason`. It opens them again once the date has passed, the entry is gone or an update moved the version. When the job fails because GitHub refused the token, the app lacks the permission *Dependabot alerts* (read and write), as [your own account](own-account.md#8-the-settings-app-optional) shows ([decision 0086](decisions/0086-accepted-advisories-close-their-dependabot-alerts.md)). To see what it would do:

```sh
python3 .github/blueprint.py advisories --dependabot --dry-run
```

## Renovate skips a lock file

**What you see:** a lock file such as `requirements-test.txt` gets no update, also none that fixes a vulnerability, and the issue *Renovate logs problems* lists `pip-compile error` for the repository. The step *Lock files* of `scripts/check.sh` fails and names the file and what Renovate stumbles on, such as `--python-version without = before its value`.

**Why:** Renovate compiles each lock file of pip-compile again with the command in its header, the line that `pip-compile` or `uv pip compile` wrote on top of it. It reads only the options that it knows, those with a value only with an `=` before it, and skips a file whose command it can't read, in every run and with no more than a warning in its log. `uv pip compile --python-version 3.12` writes the header that way, without the `=`, so Renovate reads `3.12` as one more file to compile.

**What to do:** let `blueprint.py` put the `=` between each option and its value, and commit the lock file:

```sh
python3 .github/blueprint.py locks --fix
```

The header then reads `uv pip compile --generate-hashes --python-version=3.12 --output-file=requirements-test.txt requirements-test.in`, and Renovate keeps it so when it compiles the file. An option that Renovate doesn't know, such as `--python-platform`, `--no-header`, another output file or a source file that doesn't exist needs a person: compile the file again in its folder with the options that Renovate knows, as in the example. In a pull request of a branch of the repository, the fix bot runs `locks --fix` itself.

A `requirements*.txt` that is no lock file, such as `docs/requirements.txt` for Read the Docs, needs no command in its header: add it to `ignorePaths` in `.github/renovate.json5`, such as `ignorePaths: ["docs/requirements.txt"]`, and Renovate and the step *Lock files* both leave it out. A name that the pattern `requirements*.txt` doesn't match does the same.

## The check renovate rules fails

**What you see:** in a pull request that changes the rules of Renovate or a lock file, the check *renovate rules* of the Renovate workflow fails, in a repository that runs Renovate itself (the answer `renovate_runner` `self`) and in the blueprint. Its annotations name each problem, such as `Invalid configuration option` for a rule, `pip-compile error` for a lock file, or `Renovate doesn't read the lock file requirements-test.txt.`; its summary and the comment of the PR coach say how to fix it.

**Why:** Renovate refuses every rule it doesn't know and then updates nothing in the repository, and it skips a file that it can't read in every run, with no more than a warning in its log. So the check runs the validator of Renovate on `.github/renovate.json5`, `.github/renovate-blueprint.json5`, `.github/renovate-accepted.json5` and the settings of the bot in `.github/renovate-global.json5`, and then Renovate itself, which reads every committed file of the dependencies, without a token and without looking anything up. A warning or a lock file that it doesn't read fails the check.

**What to do:** correct the rule or the file that the annotations name; for a lock file, `python3 .github/blueprint.py locks --fix` writes its header as Renovate reads it, as [Renovate skips a lock file](#renovate-skips-a-lock-file) shows. With Docker, the same checks run on your machine, the last one on the files of your last commit; the check itself runs the Renovate that `.github/workflows/renovate.yml` pins:

```sh
docker run --rm -v "$PWD:/usr/src/app" -w /usr/src/app ghcr.io/renovatebot/renovate:latest renovate-config-validator --strict .github/renovate.json5 .github/renovate-blueprint.json5 .github/renovate-accepted.json5
docker run --rm -v "$PWD:/usr/src/app" -w /usr/src/app -e RENOVATE_CONFIG_FILE=/usr/src/app/.github/renovate-global.json5 ghcr.io/renovatebot/renovate:latest renovate-config-validator --strict
git archive HEAD | docker run --rm -i -e LOG_LEVEL=info -e RENOVATE_GITHUB_TOKEN_WARN=false -e RENOVATE_CONFIG_FILE=/tmp/repository/.github/renovate-blueprint.json5 ghcr.io/renovatebot/renovate:latest bash -c 'mkdir /tmp/repository && cd /tmp/repository && tar -xf - && sed -i "s#\"local>[^\"]*\",\{0,1\}##" .github/renovate.json5 .github/renovate-blueprint.json5 && renovate --platform=local --dry-run=extract'
```

The last command takes the presets of the blueprint out of the rules, since Renovate on your machine has no platform to fetch them from; the rules of the blueprint come in as those of the bot. Its line `Extracted dependencies` lists every file that Renovate reads, with the lock files of each source of pip-compile under `lockFiles`; a line with `WARN` or `ERROR` names a problem, and after an error Renovate ends with exit code 1. On Windows, run the commands in Git Bash with `MSYS_NO_PATHCONV=1` before `docker`, so that Git Bash leaves the paths in the container alone.

## The website names a picture that git doesn't track

**What you see:** the check *docs*, or `scripts/check.sh` with the tools of the website, fails with a warning such as `index.md shows https://github.com/OWNER/NAME/raw/main/screenshots/settings.png, a file that git doesn't track in the repository, so that the picture would be missing on main`.

**Why:** a README shows its pictures from `main` of its own repository, so that they show wherever the README does, such as on PyPI or in the store of an app. The website serves such a picture from the checkout, so that the pull request that adds a screenshot shows it on its website too, before `main` has it ([decision 0062](decisions/0062-the-website-shows-the-pictures-of-its-repository-from-the-checkout.md)). A picture that git doesn't track would be missing on `main` once the pull request is merged: a new screenshot that isn't committed yet, one that the pull request deletes or moves, or a typo in its address.

**What to do:** commit the picture, such as with `git add screenshots/settings.png`, or correct its address in the README. Without git, such as in a folder without its history, the website downloads the picture from `main` as before.

## A scheduled workflow didn't run

GitHub runs schedules as it can, often hours late and sometimes not at all, so the blueprint starts its bots from events, such as a merge into `main` or the end of a check, and keeps the schedules only as a safety net ([decision 0033](decisions/0033-schedules-are-only-a-safety-net.md)). Every night, the bot-health bot looks at the latest run of every workflow and starts one whose schedule GitHub missed or switched off, also when a push ran it since, because only a run of its schedule or one started by hand counts. The column *Schedule delay* of the [dashboard](https://dennis-otto.github.io/repo-blueprint/dashboard/) shows how late GitHub started the scheduled runs of each repository in the last 7 days, in the median. A workflow with *Run workflow* under *Actions* starts at once by hand.
