# Each check ends after a limit measured against its slowest runs: 12 minutes for Python, 15 for a GitHub Action

- Status: accepted, amends [0021](0021-install-with-uv-and-bound-every-step.md)
- Date: 2026-11-23

## Context

[0021](0021-install-with-uv-and-bound-every-step.md) let each job end "after a few times its longest run" and brought `check (python)` and `check (github-action)` from 15 minutes down to 8 ([#207](https://github.com/Dennis-Otto/repo-blueprint/pull/207)). [#547](https://github.com/Dennis-Otto/repo-blueprint/pull/547) raised Python to 12 when its check had grown from about 260 to 367 seconds; the record still said 8. The action kept its 8 minutes, and a repository can't change them: its `ci.yml` is `ci-github-action.yml` of the blueprint, rendered.

Dennis-Otto/issue-assistant, the only repository of that kind, outgrew them ([#1132](https://github.com/Dennis-Otto/repo-blueprint/issues/1132)). Between 2026-11-22 05:06 and 2026-11-23 07:30 UTC, GitHub cancelled 12 attempts of its `check (github-action)` at the limit, and no job of any other kind in the eight repositories of the fleet ran out of time in the 30 days before. The slowest of them needed 8:01 to 8:05 for steps that all passed: at Dennis-Otto/issue-assistant@ce79311, `scripts/check.sh` passed after 7:26 and 4 seconds were left for the coverage, the fix bot, the uploads and the PR coach; on the slow runner of Dennis-Otto/issue-assistant#544, all 8,407 tests passed in 443 seconds and the job was cancelled at 8:01. On `main`, the check takes 4:16 to 6:42 since the tests run on every core, the 6:42 at Dennis-Otto/issue-assistant@13d744e. A cancelled required check blocks the merge until a bot or a person runs it again, and the flaky-test bot gives a second attempt that runs out of time no third.

No step limit ends the job first: *Run the checks* and the steps after it have none, and those that install, restore a cache or upload end after five minutes.

## Options

1. **Keep 8 minutes and make the action's checks faster.** Dennis-Otto/issue-assistant#532 and Dennis-Otto/issue-assistant#543 ruled out fewer tests, tries, texts or readings and a looser bound, and a check that already passed was what got cancelled.
2. **12 minutes, as for Python.** It leaves only about 4 minutes over the slowest attempts, for a check that grew by about a minute in one pull request.
3. **15 minutes, as `check (node)`, `check (php)` and `check (home-assistant)` have.** 1.9 times the slowest attempts and 2.2 times today's worst on `main`, still 24 times below GitHub's six hours.
4. **A limit for each repository,** from a question of `copier.yml` or a variable of the settings as code, each below a ceiling of the blueprint. Worth it only when one kind has repositories whose checks take very different times; today each kind has one or two.
5. **A limit computed from the runs of the last month.** GitHub evaluates `timeout-minutes` before the job starts, from contexts without history; it would need a job with an API call before every required check, and a check that grows slower would raise its own limit.

## Decision

Option 3. Each limit of a check is measured against its slowest runs, and the comment above it names them with their date:

- **`check (python)`** ends after 12 minutes, since [#547](https://github.com/Dennis-Otto/repo-blueprint/pull/547); the worst of the last 30 runs on `main` of the blueprint took 8:05 on 2026-11-23.
- **`check (github-action)`** ends after 15 minutes; the slowest attempts of Dennis-Otto/issue-assistant needed 8:01 to 8:05 on 2026-11-22 and 23.
- **Everything else of 0021 stays:** each step that installs, builds or downloads ends after five minutes, *Run the checks* gets no limit of its own below the job's, since it would only move the cancel, and a job that ran out of time runs once more ([0088](0088-jobs-that-block-wait-for-their-hosts-and-try-again-when-they-hang.md)).
- **The limits of Python and of an action are not tied:** `check (python)` measures the blueprint's own checks, which render every kind, `check (github-action)` the tests of the action.

`JOB_LIMITS` of `tests/test_template.py` holds both, and a test renders a project of the kind github-action and reads 15 minutes in its `ci.yml`.

## Consequences

- A slow runner no longer cancels the check of an action after every test passed; one that hangs still ends after 15 minutes.
- Dennis-Otto/issue-assistant gets the limit with the update of the next release; the update pull request's own check already has it, since a run of a pull request takes the workflow of its merge. Until then, a first attempt that runs out of time runs once more as before.
- A limit is a measurement and ages with the check: when a check comes near its limit again, it is measured anew and its comment and this list change with it.
