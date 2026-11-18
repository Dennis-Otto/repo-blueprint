# After the checks dismisses the accepted alerts of a pull request

- Status: accepted, amends [0019](0019-a-failing-bot-keeps-one-issue-open.md)
- Date: 2026-11-18

## Context

Findings started on `workflow_run` at the end of every run of CodeQL, OpenSSF Scorecard, Workflow security and OSV-Scanner, also of their runs for pull requests. After the scan of a pull request, its only work was to dismiss the alerts of the pull request that `.github/findings.toml` accepts, so that their review threads don't block the merge (decision 0028 of the issue assistant). The bot-health bot watches Findings, so each of these runs started one of it as well. From 2026-11-10 to 2026-11-16, the blueprint and the seven repositories that follow it ran 3,591 such scans: about 3,600 runs of Findings and 3,600 of the bot-health bot behind them did nothing else ([issue 1011](https://github.com/Dennis-Otto/repo-blueprint/issues/1011)).

*After the checks* already starts at the end of each of these scans. Release 1.14.0 of the issue assistant, which the blueprint takes since #1035, has the key `[findings] pull_requests` of `config.toml` (Dennis-Otto/issue-assistant#456): with `false`, `install` writes `findings.yml` with `branches: [main]` under `workflow_run`, and `check` expects that form and fails while no other workflow on `workflow_run` calls `reusable-findings.yml`. The reusable workflow decides by the event of the scan alone, and its group for a pull request, `findings-pull-request-<branch>`, is the same for every caller.

A run of Findings got three things that a job of *After the checks* doesn't get by itself: a second try from the bot-health bot after a stop of Harden-Runner ([0134](0134-a-job-stops-when-harden-runner-doesnt-block.md), [0141](0141-the-bot-health-bot-runs-every-bot-again-that-harden-runner-stopped.md)); an issue *Findings fails on main* when it failed, as GitHub gives a run after the scan of a pull request the branch `main` (0019); and a pin that the Issue assistant sync moves, which matched only `Dennis-Otto/issue-assistant@<commit>`.

## Options

1. Keep Findings after the scans of pull requests: about 7,200 runs a week that only dismiss.
2. Move the dismissal into the scanner workflows: their event is `pull_request`, which the reusable workflow doesn't take for a dismissal, and the alerts arrive only after the upload of the scan, so its own job can't see them.
3. A job of *After the checks* calls the reusable workflow after the scans of a pull request, with a second try and a comment on the pull request in the same run, and Findings runs for `main` alone.

## Decision

Option 3, in one pull request with the key, so that no state of `main` lacks a dismissal.

- `.github/issue-assistant/config.toml` and its template set `[findings] pull_requests = false`, and `findings.yml` is the form that `install` of the pinned release writes for it, which the template includes for every kind of project.
- The job *dismiss the accepted alerts of the pull request* of `after-checks.yml` calls `reusable-findings.yml` at the pin of `findings.yml`, with `contents: read` and `security-events: write` and no dry run, after a run of CodeQL, Workflow security or OSV-Scanner on `pull_request` from a branch of this repository whose commit is still the head of its open pull request, whatever the scan found. Never after a scan of a fork, never after one of `main`, and OpenSSF Scorecard runs on `main` alone. It keeps the group of the reusable workflow for the branch of the pull request, in which the newest scan dismisses every accepted alert of it, and takes none of its own.
- The job *dismiss the accepted alerts again* needs the first and runs only when it failed, on a new runner a few seconds later. The dismissal of a pull request fails for no alert, so a second try repeats nothing of its own result and may follow any failure. A first try that a newer scan replaced in the group ends as cancelled and gets none: the newer one dismisses everything. Decision 0141 turned a second look in the same run down for the bot-health bot, as it leaves the run failed; here nothing reads the conclusion of *After the checks*, whose runs the nightly look leaves out.
- When the second try fails as well, the job *say on the pull request that the accepted alerts stay* says so on the pull request, once for each commit by a mark in the comment and a group for each commit: the scan, the link to the run, and that the review threads may block the merge until the failed jobs pass again or a person resolves them. It holds `pull-requests: write` alone, blocks every host but `api.github.com`, stops when Harden-Runner doesn't block, and ends with a notice in an outage of GitHub ([0136](0136-an-outage-of-github-starts-no-bot-failure.md)).
- The Issue assistant sync moves every pin of the issue assistant, `Dennis-Otto/issue-assistant/.github/workflows/reusable-<name>.yml@<commit> # vX.Y.Z` as well, in every workflow of the blueprint, and `pinned` names one release only while that pin agrees.

This amends 0019: a failure of the dismissal of a pull request shows on that pull request, not in the issue *Findings fails on main*, as a run for a pull request opens no issue there either.

## Consequences

About 3,600 runs of Findings and 3,600 of the bot-health bot less in a week like that of 2026-11-10; the runs of *After the checks* were there already. The accepted alerts of a pull request are still dismissed right after each of its scans, before the merge. A new alert on `main` still fails one run of Findings after each scan of `main`, every morning and after a push of `findings.toml`, and the bot-health bot still opens and closes its issue. A run of *After the checks* whose first try failed stays failed although the second try dismissed the alerts; nothing reads it. A dismissal that breaks for good, such as after a release of the issue assistant, says so on every pull request of the repository, once for each commit, while Findings on `main` may still pass, as the issue assistant takes another path for it. A repository whose default branch isn't `main` takes the key out, as `check` asks.
