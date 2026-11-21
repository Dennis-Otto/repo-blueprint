# A pull request that changes what the fuzzing reads waits for it

- Status: accepted
- Date: 2026-11-21
- Amends [0009](0009-run-a-check-only-where-it-can-change-a-result.md)

## Context

Decision 0009 made the fuzzing a scanner with a path filter: it ran only in the pull requests that change the Python code, the targets or the tools, and it was no required check, since a required check that a path filter leaves out never reports and blocks the merge for good. Its consequences say "Nothing that a merge brings goes unchecked, since it brings only what its pull request ran with". That holds for the required checks. A pull request merges by auto-merge three to four seconds after its last required check, so the fuzzing of its last commit ended in time only when it happened to be faster than the slowest required check.

In issue-assistant, the fuzzing takes about 3 minutes 40 seconds (three targets of a minute each and the setup), and its slowest required check about 3 minutes. On 2026-11-20, six of the eight pull requests that fuzzed there merged before the fuzzing of their last commit ended: three runs passed after the merge, and three were cancelled, two of them by the branch bot, which rightly cancels the runs of commits that no pull request has as its head any more. One of them brought a text that `render_issue` read in quadratic time; the fuzzing of the next pull request found it, and it stayed on `main` for two hours ([issue 1074](https://github.com/Dennis-Otto/repo-blueprint/issues/1074)). A minute per target is a random search, so a finished run might have missed it as well, but a run that ends after the merge can't stop anything.

The maintainer decided: a pull request that changes the code that the targets fuzz, the targets or the tools merges only once the fuzzing has passed for its last commit; every other pull request merges as fast as before. The `requirements*.txt` count, as they did in the path filter, because a lock file changes the code that the fuzzer runs: the project's dependencies and Atheris.

## Options

1. **`fuzz` becomes a required check, and the job looks at the change itself.** The workflow runs on every pull request, without a path filter. A first step compares the merge commit with its first parent, `main`, by `git diff --name-only HEAD^1 HEAD` with the four patterns of the old path filter as pathspecs, and the steps that set up and fuzz run only when it lists a file. Any other pull request passes the check in about 15 seconds.
2. **The merge bot or auto-merge waits for a running fuzzing, without a required check.** The merge is GitHub's own auto-merge, seconds after the last required check, before any bot after the checks starts. A bot could only hold it by turning auto-merge off and on again, which resets `enabledAt`, the order of the branch bot's line, and a merge by hand wouldn't wait either.
3. **Fuzzing on `main` after a merge whose pull request run was cancelled, with an issue of Bot health.** It finds the fault after `main` has it, which is what happened, at the cost of a full run after such merges; an issue is a report, not a guard.
4. **A second workflow with `paths-ignore` whose job is also named `fuzz` and passes at once.** Two runs report one check, and on a pull request that matches both, the one that passes in seconds can count while the real one still runs.
5. **The stale-runs bot leaves the fuzzing alone.** The finding would still come after the merge.

## Decision

Option 1. `fuzz.yml` runs on every pull request, every week and by hand, still never after a merge. On a pull request its checkout fetches two commits, as every `ci-<stack>.yml` does for its base, and the step *Look for a change that the fuzzing reads* writes `fuzz=true` when the merge changes a file of `:(glob)**/*.py`, `:(glob)fuzz/**`, `:(glob)**/requirements*.txt` or `.github/workflows/fuzz.yml`. Git matches them as the path filter did, sees every changed file where the paths of GitHub look at the first 300 only, and lists the old name of a file that a rename moved; the step needs no token, so it works the same for a fork. A week and a start by hand fuzz in full, and a repository without a `fuzz/fuzz_*.py` fuzzes nothing. When the job doesn't fuzz, the summary of its check says why, in one line.

`fuzz` joins the required checks of the blueprint and of the kinds that get `fuzz.yml`, `python-package` and `github-action`, under the same condition as the name of the file. The release pull request of the blueprint still skips the job, which passes a required check, as the Canary of `main` does in issue-assistant.

## Consequences

A pull request that changes what the targets read merges only once the fuzzing of its last commit has passed: each such pull request gets a finished run, not a certain find. Every other pull request takes one job of about 15 seconds more, where no job started before, and merges as fast as before. In the blueprint, the fuzzing ends before `check (python)`; in issue-assistant it becomes the slowest required check of the pull requests that change its Python, and since the rules of `main` require a branch to be up to date, each update by the branch bot starts it again. Renovate's updates of a `requirements*.txt` or of what `fuzz.yml` pins itself wait for the fuzzing too.

A finding that isn't one now holds a pull request: the targets measure processor time against a budget, and a slow runner can push a fast reading over it. The log has the input; when the target is fast with it locally, run the failed job again. Bot health still gives the fuzzing no second try, and the flaky-test bot leaves it alone.

An existing repository has nothing to do: the update brings the workflow and `repository.toml`, its merge starts the Settings workflow, and the settings bot adds `fuzz` to the rules of `main`. A pull request whose checks ran before that gets the check once the branch bot brings it up to date, as with `variants` in 0009; one of a fork that the bot can't update waits until its author pushes. The scheme of 0009 gains a third place for a new check: required and without a path filter, a scanner with the paths it reads, or required and looking at the change itself, where a check guards the merge but costs too much to run for every pull request.
