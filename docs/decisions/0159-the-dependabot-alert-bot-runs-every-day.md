# The Dependabot alert bot runs every day, in the Release workflow

- Status: accepted
- Date: 2026-11-14

## Context

The job *dependabot alerts* closes each Dependabot alert that an `osv-scanner.toml` accepts and warns of each acceptance that ends within two weeks ([decision 0086](0086-accepted-advisories-close-their-dependabot-alerts.md), [decision 0147](0147-an-acceptance-of-advisories-warns-two-weeks-before-it-ends.md)). It ran in the OSV-Scanner workflow: after a push to `main`, every Monday and by hand. GitHub opens an alert whenever an advisory is published, not when `main` changes: the alert #52 of the blueprint, of the Pillow that `stacks/home-assistant/osv-scanner.toml` accepts, opened on 11 November 2026, a day after the last push, and would have stayed open until the Monday after ([issue 852](https://github.com/Dennis-Otto/repo-blueprint/issues/852)). In a repository with a quiet `main` the wait is up to seven days, with an alert on the Security tab and on the dashboard of a version that the project accepted.

## Options

1. A daily schedule of the OSV-Scanner workflow on which only the job runs: one more scheduled run every day in every repository, which counts against the limit of a dozen runs a day that the schedules of a project keep.
2. The daily run of the Findings workflow runs the same command: the workflow is the issue assistant's, which its sync bot keeps equal to the template of the issue assistant ([decision 0024](0024-take-over-each-verified-release-of-the-issue-assistant.md)), so a job of the blueprint there would go with the next sync.
3. The job moves into a workflow of the blueprint that runs every day anyway and after every push to `main`: the Release workflow, whose job *release pull request* already enters the environment `release`, where the private keys of the release app and of the settings app are.

## Decision

Option 3, as Dennis decided on 14 November 2026: no new scheduled run, the limit of the schedules stays. The job *dependabot alerts* is a job of the Release workflow, with the same steps, the same permissions and the same check name, which the PR coach explains; it runs after every push to `main`, on the daily schedule of the workflow and by hand, never in a fork. OSV-Scanner keeps its scan of every lock file after a push to `main` and every Monday. The input `dry_run` of the OSV-Scanner workflow goes, since nothing there reads it any more; a maintainer sees what the job would do with `blueprint.py advisories --dependabot --dry-run` and `--ending --dry-run`, as the PR coach shows.

## Consequences

An alert of an accepted version closes within a day of its advisory, and the warning of an acceptance that ends soon comes every day, so the issue that names such acceptances follows a change on the day. The run of the release bot takes the minute of the job as well, in its group, which never cancels a run; a failure of the job is a failure of the Release workflow, which the bot-health bot watches as before. A refused token of the app says to run the workflow *Release* again.
