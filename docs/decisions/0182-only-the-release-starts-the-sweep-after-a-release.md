# Only the release starts the sweep after a release

- Status: accepted, amends [0173](0173-only-a-run-that-published-a-release-starts-its-followers.md)
- Date: 2026-11-18

## Context

Since [0173](0173-only-a-run-that-published-a-release-starts-its-followers.md), the last job of a run of *Release* that published a release starts *Issue lifecycle* with `dry_run` false, which closes the issues that the release fixes with its link. *Issue lifecycle* kept its own start after the end of every run of *Release*, though: `issue-lifecycle.yml` is a template of the issue assistant, which its check in *Lint* compares exactly ([0024](0024-take-over-each-verified-release-of-the-issue-assistant.md)), and that template had no form without the trigger. So every run of *Release* still started a sweep, most of them after a run that published nothing, and a release swept the issues twice ([issue 1000](https://github.com/Dennis-Otto/repo-blueprint/issues/1000)).

Release 1.14.0 of the issue assistant has the key `[releases] sweep_after_release_workflow` of `config.toml` (Dennis-Otto/issue-assistant#457): with `false`, `install` writes `issue-lifecycle.yml` without the `workflow_run` on *Release*, and with no other difference, and `check` expects that form. The blueprint takes 1.14.0 since #1035. The job of 0173 does start the sweep: the run of *Release* that published 1.22.0 on 2026-11-18 started *Issue lifecycle* by `workflow_dispatch`, and that sweep closed the seven issues that 1.22.0 fixed, each with its link and under the milestone of the release.

## Options

1. Keep the trigger: every run of *Release* that publishes nothing still starts a sweep with nothing to do, and a run of the bot-health bot behind it, and a release sweeps twice.
2. Set `sweep_after_release_workflow = false` in the blueprint's own `config.toml` and in `template/.github/issue-assistant/config.toml.jinja`, and let `install` of the pinned issue assistant write `issue-lifecycle.yml` without the trigger.

## Decision

Option 2. Both files set the key, and `issue-lifecycle.yml` is the form that `install` writes for it, which the template includes for every kind of project. The template of the issue assistant keeps the trigger for every repository whose release workflow doesn't start the sweep itself.

## Consequences

Only a run of *Release* that published a final release starts a sweep after it, once. The morning sweep, a merged pull request and a release that a person publishes, by `release: published`, still start *Issue lifecycle*, and the morning sweep stays the safety net when GitHub doesn't start the sweep of a release. A rerun of a whole run of *Release* whose release was already published finds no release left to make and no longer starts a sweep: the morning sweep closes what that release fixed, if the first run didn't. A release whose verification or another job failed starts the sweep once a rerun of its failed jobs passes, as before. The event policy of the settings, which names each event of a workflow that starts on `pull_request_target`, no longer names `workflow_run` for *Issue lifecycle*, and the next apply of the settings takes that over.
