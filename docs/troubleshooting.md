---
description: "What to do when something in a repository of Repo Blueprint doesn't work: an update that conflicts, a required check that never reports, settings apply without administrator rights, a switch of the security that GitHub keeps off, a release pull request without checks, and Renovate that opens no updates."
---

# Troubleshooting

Most problems explain themselves where they happen: a check that fails says in its summary and in the report of the PR coach what it found and how to fix it, a bot says in the summary of its run what is missing, and the bot-health bot keeps one issue open for each bot that fails on `main`. This page covers what needs a person beyond that. The common questions are on the page [Questions and answers](faq.md).

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
- **The workflow didn't start.** Its run under *Actions* shows a *startup failure* when it uses an action that the list of the allowed actions lacks. `python3 .github/blueprint.py settings check` names each one; add its pattern to `[actions.selected]` of `.github/repository.project.toml` for a workflow of the project, and apply the settings.
- **The pull request comes from a token that starts no workflow,** such as the token of a job: see [The release pull request has no checks](#the-release-pull-request-has-no-checks).
- **The pull request comes from the fork of an outside contributor:** its workflows wait for a maintainer, who starts them with *Approve and run* on the pull request.
- **A check of the project alone** that `.github/repository.project.toml` requires runs in a workflow with a path filter, so a pull request that changes other files never starts it. A required check runs in every pull request: remove the filter, or let the job decide inside its steps what to skip, so that it still reports success.

## Applying the settings without administrator rights

**What you see:** `python3 .github/blueprint.py settings apply` ends with lines such as *the rulesets could not be applied: … the token may lack the permission Administration (read and write)*.

**Why:** most of the settings as code, such as the rulesets, the security and the permissions of Actions, need an administrator of the repository. `blueprint.py` uses the account that `gh auth login` signed in, and applies every part that GitHub accepts; it names each part that GitHub refused with the permission that it needs.

**What to do:**

- **Let the settings bot apply them:** it runs as the release app, which has the permission *Administration*, after every change of the settings as code on `main`, every week and on demand under *Actions → Settings → Run workflow*. Change `.github/repository.project.toml` in a pull request, and the settings follow its merge.
- **Ask an administrator** to run `settings apply` once, for a new repository whose release app is not set up yet.
- **See what differs** with `python3 .github/blueprint.py settings check`, which changes nothing; some parts, such as who may bypass a ruleset, show only to an administrator.

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

1. Register the release app and name it, as the page [Your own account](own-account.md#3-register-the-release-app) shows; the variable [`RELEASE_AUTOMATION_CLIENT_ID`](reference/variables.md#release_automation_client_id) then names it.
2. Install the app on the repository, and set its private key as the secret [`RELEASE_AUTOMATION_PRIVATE_KEY`](reference/variables.md#release_automation_private_key) of the environment `release`: `python3 .github/blueprint.py checklist` prints the command.
3. Start the Release workflow under *Actions → Release → Run workflow*, or merge the next pull request. It updates the release pull request as the app, and its checks start.

When the token of the app fails, as for an app that isn't installed on the repository or a key that doesn't belong to it, the step that asks for the token fails, and the bot-health bot keeps an issue open until a run passes. A pull request whose checks didn't start for another reason starts them when a person closes and reopens it.

## Renovate opens no updates

**What you see:** no pull request of Renovate, or the issue *Dependency dashboard* is missing.

**Why, and what to do:** first, the rules may hold an update back: it comes a week after its release, on a Monday, unless it fixes a vulnerability, and the issue *Dependency dashboard* lists every update that waits or failed, with a checkbox to retry it. Otherwise it depends on who runs Renovate, by the answer [`renovate_runner`](reference/questions.md#renovate_runner):

- **`self`, a workflow of the repository:** `.github/workflows/renovate.yml` runs as the release app; a run without the app says in its summary what is missing. *Actions → Renovate → Run workflow* starts one at once, and a pull request that changes the rules or a lock file shows whether Renovate still accepts and reads them.
- **`mend`, the Mend Renovate app:** install the [Mend Renovate app](https://github.com/apps/renovate) on the repository; it comes at every push.
- **`hub`, the Renovate workflow of the blueprint,** for the repositories of the blueprint's owner: the release app must be installed on the repository, which needs a `.github/renovate.json5`.

Where a Renovate workflow runs, the bot-health bot keeps one issue open with the warnings and errors of Renovate.

## A scheduled workflow didn't run

GitHub runs schedules as it can, often hours late and sometimes not at all, so the blueprint starts its bots from events, such as a merge into `main` or the end of a check, and keeps the schedules only as a safety net ([decision 0033](decisions/0033-schedules-are-only-a-safety-net.md)). Every night, the bot-health bot looks at the latest run of every workflow and starts one whose schedule GitHub missed or switched off. A workflow with *Run workflow* under *Actions* starts at once by hand.
