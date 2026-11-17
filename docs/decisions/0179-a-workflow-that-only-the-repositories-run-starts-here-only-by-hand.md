# A workflow that only the repositories run starts here only by hand

- Status: accepted, amends [0045](0045-every-website-shows-its-automation-written-from-its-workflows.md) and [0083](0083-every-repository-runs-its-schedules-at-times-of-its-own.md) in what the blueprint itself runs
- Date: 2026-11-17

## Context

The blueprint keeps the checks of every kind of project, and a few bots that only the repositories made from it run, in its own `.github/workflows/`, since the template includes them from there. In the blueprint itself each of their jobs carries the line `if: github.repository != 'Dennis-Otto/repo-blueprint'`, which the template removes. The workflows kept their triggers, though, so GitHub made a run for every push of a pull request, every merge into `main` and every schedule, and each of these runs skipped all its jobs.

From 2026-11-10 to 2026-11-16 that made about 3,850 runs in the blueprint that did nothing ([issue 1003](https://github.com/Dennis-Otto/repo-blueprint/issues/1003)): *CI (node)*, *CI (php)*, *CI (generic)*, *CI (home-assistant)*, *CI (container)*, *CI (github-action)* and *Action test* 533 or 532 times each, *Newest Node* 110 times, and *Property tests*, *Upstream* and *Blueprint update* 13 times, four of these because *Bot health* started *Property tests* again for a schedule that it took as late. The release pull request alone, with 173 heads that week, had 1,211 of them. They cost no minutes of a runner, but they filled the list of runs and the checks of every pull request with skipped entries, and each one sent its `workflow_run`, `check_suite` and `check_run` events to every bot that listens.

## Options

1. **Move the files out of `.github/workflows/`,** such as to `.github/stacks/`, where GitHub doesn't run them. Renovate's manager of GitHub Actions, CodeQL's analysis of the workflows, the OpenSSF Scorecard, actionlint and zizmor read only `.github/workflows/`: the pins of the checks of every kind would go stale here, and every repository would get them stale.
2. **A filter on each trigger,** such as `branches-ignore` for every branch. GitHub has no filter on the repository, and a filter that matches nothing still leaves the schedule and makes the files hard to read.
3. **Only `workflow_dispatch` here, the real triggers from the template.** The files stay where every tool reads them; the template puts back the triggers that the blueprint's copy leaves out.

## Decision

Option 3.

- **In the blueprint,** a workflow of which no job runs here, by the rule of `idle()` of `blueprint/website.py` (every job carries the guard or only waits for such jobs), has only `workflow_dispatch` in its block `on:`, with its inputs where it has some, after the comment that `by_hand` of `includes/replace.jinja` holds. GitHub makes no run of it for a pull request, a merge or a schedule, and *Bot health* finds no schedule of it that it could take as late. These are the checks of every kind but Python, *Action test*, *Newest Node*, *Property tests*, *Upstream* and *Blueprint update*.
- **The guard stays,** so that a run started by hand still does nothing here, and the page *Automation* of the website still leaves these workflows out (0045).
- **In every repository,** the template of each workflow replaces `by_hand` with the triggers that the workflow had, through the same `replaced()` that removes the guard; `replaced()` moves each schedule into the slot of the repository after its replacements (0083). The render stops when the blueprint's copy no longer holds `by_hand`. Every repository made from the blueprint gets the same files as before, byte for byte, for every kind and with the answers of every repository in `tests/answers/`. *CI (python)* is the blueprint's own CI and keeps its triggers; the checks of the other kinds get the same events.
- **The real triggers are still checked before a release.** In the blueprint, zizmor and CodeQL see these workflows with `workflow_dispatch` alone, so every leg of the Variants runs zizmor on the workflows of its project, with the version and the configuration of the project's own *Workflow security*, next to the actionlint that it ran before. Its audits that depend on a trigger, such as `dangerous-triggers` and `cache-poisoning`, see the real ones there. It runs offline: the pins are the blueprint's own, whose advisories the blueprint's zizmor looks up.

## What stays

- **No required check and no bot of a repository loses a trigger:** `test_each_kind_gets_the_triggers_that_the_blueprint_leaves_out` renders every kind and compares the block `on:` of each of these workflows with the one it had, the checks of every kind with that of *CI (python)*, each schedule in the slot of the project.
- **Nothing new starts by itself in the blueprint:** `test_a_workflow_of_which_no_job_runs_here_starts_only_by_hand` fails when a workflow of which no job runs here has a trigger other than `workflow_dispatch`, and when a workflow of which a job runs here carries `by_hand`.
- **The concurrency of these workflows,** with `github.event.pull_request.number`, is the same text, and valid for a start by hand, where the number is empty.
- **The list of `workflow_run` of *Bot health*** keeps its names: the template of `bot-health.yml` replaces it word for word, and a workflow that never runs here never ends here either.
- **No required check of the blueprint** named one of these workflows (`required_checks` of `.github/repository.toml`).

## Consequences

About 3,850 runs a week less in the blueprint, and a list of the checks of each pull request without seven skipped entries. A change of the triggers of one of these workflows is made in its template, `template/.github/workflows/`, not in the blueprint's copy; the tests above say where. A new workflow of this kind takes `by_hand` and a template with its triggers, or the test of the idle workflows fails.
