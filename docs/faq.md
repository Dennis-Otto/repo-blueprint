---
description: "Answers to the common questions about Repo Blueprint: your own account or organization, the AI of the issue assistant, updates that merge themselves, private repositories and the cost of Actions, the files a project may change, and how to leave the blueprint."
---

# Questions and answers

The questions that come up most when a repository takes the blueprint. What to do when something doesn't work is on the page [Troubleshooting](troubleshooting.md), every question of Copier and every variable and secret in the [reference](reference/questions.md).

## Does the blueprint work for my own account or organization?

Yes, for every account and organization on GitHub. A repository made from it names nothing of the blueprint's owner but the links to the blueprint, and every bot acts as an app of yours. You bring two things: a **release app**, once for all of your repositories, which the checklist helps you register, and **your defaults** in Copier's settings file, so that each new repository asks only what is new. Renovate runs in a workflow of each repository or as the Mend Renovate app, by the answer [`renovate_runner`](reference/questions.md#renovate_runner). The page [Your own account](own-account.md) walks through every step, from the copy to a checklist without a cross.

## Why do the bots need a release app?

What a workflow does with the token that GitHub gives it, `GITHUB_TOKEN`, starts no other workflow: a release or update pull request that it opened would run no checks, and a merge with it would start no release. The bots act as a GitHub App of yours instead, whose token starts the checks, may change workflows and creates the release tags, which only this app may create. Only the owner of an app has its private key, so the blueprint can't lend its own. Until the app is there, the bots say in their summary what is missing, rather than fail at a token.

## How do I switch the AI of the issue assistant off?

Change the answer [`issue_assistant_ai`](reference/questions.md#issue_assistant_ai) and commit the update:

```sh
copier update --defaults --vcs-ref=:current: --data issue_assistant_ai=false
```

The settings bot then sets the variable [`ISSUE_ASSISTANT_AI`](reference/variables.md#issue_assistant_ai) to `off`, the environment `issue-assistant` asks for no secret, and `SUPPORT.md` tells reporters that no AI reads their issues. Labels, reminders, closing with the release and the commands of the maintainer work as before. Deleting the secret `CLAUDE_CODE_OAUTH_TOKEN` stops the AI at once as well, but the checklist then asks for it again. `--data issue_assistant_ai=true` turns the AI on later.

## How do I stop the updates of the blueprint from merging themselves?

Set the repository variable [`BLUEPRINT_AUTOMERGE`](reference/variables.md#blueprint_automerge) to `off`: every update of the blueprint then waits for you, with its notes and the files it changes in its description. Set it in `[variables]` of `.github/repository.project.toml`, which the settings bot applies, or under *Settings → Secrets and variables → Actions → Variables*. To let them merge themselves again, set it to `on` there, or delete the variable on GitHub, with `gh variable delete BLUEPRINT_AUTOMERGE` or on that page: the settings bot sets variables but never deletes one, so a line removed from the file leaves `off` in place. An update with conflicts always waits, and so does one whose auto-merge you switched off, which stays off.

The other bots that merge their own pull requests have switches of their own:

- **The upstream bot of a Nextcloud app** waits with [`UPSTREAM_AUTOMERGE`](reference/variables.md#upstream_automerge) set to `off`.
- **Renovate** merges what the rules of `.github/renovate.json5` let it, which a rule with `"automerge": false` stops for the packages that it names; the weekly refresh of the lock files waits for you anyway.

## Can a repository be private, and what does it cost?

Yes: `python3 .github/blueprint.py create --private` creates a private repository. Public repositories run GitHub Actions for free. A private one on GitHub Free has 2,000 minutes a month, and GitHub rounds every job up to a whole minute. The schedules of a project, and the runs that they start, come to about 20 runs a day, about 600 a month; the checks of the pull requests cost more, which is why the blueprint runs a check only where it can change a result and keeps the jobs few (decisions [0009](decisions/0009-run-a-check-only-where-it-can-change-a-result.md) and [0027](decisions/0027-few-jobs-that-each-run-several-checks.md)).

Some of what the blueprint turns on is free only for public repositories, and the blueprint makes do without it ([decision 0081](decisions/0081-a-private-repository-passes-its-checks-without-what-its-plan-lacks.md)):

| Part | Public | Private, Free | Private, Pro or Team | With Code Security |
| --- | --- | --- | --- | --- |
| Actions | free | 2,000 minutes | 3,000 minutes | by the plan |
| Rulesets for `main` | yes | no | yes | yes |
| Website | Pages | artifact | Pages | Pages |
| Code scanning | yes | in the checks | in the checks | yes |
| Dependency review | yes | OSV-Scanner | OSV-Scanner | yes |
| Secret scanning | yes | gitleaks | gitleaks | with Secret Protection |

GitHub Code Security and GitHub Secret Protection are for organizations on GitHub Team or Enterprise. Without them, every required check still runs and passes where nothing is wrong:

- **`settings apply`** reads whether the repository is private and has GitHub Code Security. Without it, it sets the variables [`CODE_SCANNING`](reference/variables.md#code_scanning) and [`DEPENDENCY_REVIEW`](reference/variables.md#dependency_review) to `off`, and the ruleset of `main` no longer waits for an analysis of code scanning. What GitHub refuses for the plan, such as the rulesets and GitHub Pages on GitHub Free, it names as a notice, which fails nothing; it sets them once the repository is public or on a plan that has them, and sets the variables back to `on`.
- **CodeQL** still analyzes every pull request. It keeps the results as the artifact `codeql-sarif` of the run, lists them in the summary of the check *codeql*, and fails on an error or a security alert of high or critical severity, as the ruleset would stop them.
- **zizmor** fails on each finding, with an annotation at its line; **OSV-Scanner** and the **Scorecard** keep their findings in their checks.
- **The dependency review** leaves the vulnerabilities to the check *osv-scanner (pull request)*, which compares the lock files of the pull request with those of its base. The licenses of new dependencies go unchecked.
- **The website** of every run on `main` is the artifact `website`, as that of a pull request is.
- **Secret scanning** is the check *gitleaks* of every pull request; GitHub's push protection, which stops a secret before it is pushed, is missing.

On GitHub Free nothing protects `main`: a push goes past the checks, so keep to pull requests. `python3 .github/blueprint.py checklist` shows a private repository's step *GitHub Code Security on*.

## Which files may a project change?

Every file, and each change survives the updates:

- **The files of the project,** such as the README, the changelog, the code, the tests, the manifests and the pages of the website, are never overwritten by an update. The [reference](reference/questions.md#the-files-of-a-project) lists their patterns, from `_skip_if_exists` of `copier.yml`.
- **The files of the blueprint,** such as the workflows and `scripts/check.sh`, take the changes of each update: `copier update` merges them with the changes of the repository, line by line, and marks a conflict only where both changed the same lines.

So that updates rarely conflict, a project adds its own beside the blueprint's files rather than in them: its settings in `.github/repository.project.toml`, its checks in `scripts/check-project.sh` and `scripts/check-site.sh`, their explanations in `.github/checks.project.toml`, its notes for coding agents in `.github/agents.project.md`, and workflows in files of their own. A fix that every repository needs belongs in the blueprint, whose next release brings it to all of them.

## How do I change an answer later?

Run `copier update` with the new answer and commit the update, such as for the topics:

```sh
copier update --defaults --vcs-ref=:current: --data "topics=python, pypi, cli"
```

`--vcs-ref=:current:` keeps the release of the blueprint that the repository is on, and `--defaults` takes every other answer from `.copier-answers.yml`. The settings bot applies what the answer changes in `.github/repository.toml`, such as a variable or the topics, after the merge.

## How do I leave the blueprint?

Delete `.github/workflows/blueprint-update.yml`, and no update of the blueprint comes any more; the Rollout of the blueprint leaves a repository without the blueprint bot out. Everything else stays and works as it is, since it is a file of your repository: the workflows, the checks, the settings as code with `.github/blueprint.py` and the other bots. The license of the blueprint, [MIT No Attribution](https://github.com/Dennis-Otto/repo-blueprint/blob/main/LICENSE), asks nothing of what you keep, not even a notice. Keep `.copier-answers.yml` if you might come back: `copier update` starts from the release that it names.

To pause the updates rather than leave, set [`BLUEPRINT_AUTOMERGE`](reference/variables.md#blueprint_automerge) to `off` and leave the update pull request open; a newer release moves it on.
