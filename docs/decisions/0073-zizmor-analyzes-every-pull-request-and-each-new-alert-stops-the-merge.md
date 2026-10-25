# zizmor analyzes every pull request, and each new alert of it stops the merge

- Status: accepted
- Date: 2026-10-25

## Context

[Decision 0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md) gave *Protect main* a rule *code scanning* with CodeQL alone, because a tool of the rule whose analysis is missing stops the merge as well. zizmor ran only in the pull requests that change a workflow, an action, the settings of Dependabot or `.github/zizmor.yml` ([decision 0009](0009-run-a-check-only-where-it-can-change-a-result.md)), and never in the release pull request. A pull request that added a weakness to a workflow, such as an expression of the event in a script, merged, and its alert showed only afterwards, when the Findings workflow turned `main` red: the gap that decision 0038 closed for CodeQL, in the files that run with the token of the repository ([#274](https://github.com/Dennis-Otto/repo-blueprint/issues/274)).

## Options

1. Keep zizmor behind Findings.
2. Run zizmor in the job *lint*, which runs in every pull request. Code scanning keeps an analysis by its workflow and job as well as by its category, so an analysis from `lint.yml` would have no counterpart on `main`, where *lint* doesn't run, and every alert of `main` would look new in every pull request.
3. Upload an empty analysis of zizmor in the pull requests that change none of its files. Every alert that `main` has would look fixed in them, and the check would say so.
4. Run the job *zizmor* of `zizmor.yml` in every pull request into `main`, the release pull request included, and add zizmor to the rule.

## Decision

Option 4.

- **Every pull request into `main`** runs `zizmor.yml`, without a path filter and without the condition that skipped the release pull request. The pull request and `main` share the workflow, the job and the category `zizmor`, so code scanning compares their analyses.
- **Every new alert stops the merge.** `code_scanning_tools` in `[branch]` of `.github/repository.toml` lists `{ tool = "zizmor", alerts_threshold = "all", security_alerts_threshold = "none" }`. zizmor writes a finding of high severity as an error, one of medium severity as a warning and a low or informational one as a note, and gives none a security severity. The Findings workflow fails `main` on every open alert, whatever its severity, so the rule stops each one before the merge rather than after it. CodeQL keeps its thresholds, errors and security alerts of high or critical severity, since its notes and warnings need a maintainer to dismiss, while a finding of zizmor is accepted in `.github/zizmor.yml` within the same pull request.
- **The same zizmor on both sides.** zizmor runs in the version that its action pins to a commit, with its online audits, in a pull request as on `main`. Newer audits come with an update of the action, in a pull request of their own that shows what they find, never as alerts of a pull request that changes no workflow. A test renders every kind of project and fails while a tool of the rule has a path filter or a condition on its job, or while the step of zizmor names a version of its own or audits offline.
- A project relaxes the thresholds of zizmor, or takes it out of the rule, in `.github/repository.project.toml`, as for CodeQL.

## Consequences

A pull request that adds a weakness to a workflow shows the alert at its line and waits until it is fixed or accepted, and `main` no longer turns red for it. Each pull request runs one more job of about a minute, the release pull request too, of the about 20 jobs that an account runs at once.

zizmor asks GitHub for the advisories of the actions that the workflows pin, and `main` is analyzed after every merge and every week. An advisory published since the last analysis of `main` shows as a new alert of the next pull request, whatever it changes; the PR coach tells a maintainer to start *Workflow security* on `main`, which gives `main` the alert for Findings to report, and to run the checks again. An analysis of `main` every day would close that window, but the schedules of a project stay within a dozen runs a day.

The settings bot applies the rule after the merge, and every other repository gets it with the update of the blueprint. A pull request whose checks ran before then has no analysis of zizmor and waits until the branch bot brings it up to date, which starts the workflow.
