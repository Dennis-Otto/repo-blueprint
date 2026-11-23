# The empty commit of a refresh with nothing to bring needs nothing

- Status: accepted, amends [0019](0019-a-failing-bot-keeps-one-issue-open.md) and [0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md)
- Date: 2026-11-23

## Context

The bot-health bot of [0019](0019-a-failing-bot-keeps-one-issue-open.md) keeps one issue, *Renovate logs problems*, with every line of level 40 or more in the log of Renovate, and closes it after three complete runs without one. On 2026-11-23 it opened #1127 for two lines `Detected empty commit - aborting git push` on `renovate/pip-compile-refresh`, of dennis-otto.github.io and issue-assistant, a few hours after both had merged that Monday's refresh. Nothing was to be done.

The empty commit is what the refresh of [0137](0137-the-refresh-of-the-lock-files-merges-by-itself-from-versions-a-week-old.md) is built to produce: Renovate compiles the newest versions, `locks --refresh` compiles again from uploads a week old and puts Renovate's compile into the index first, so that Renovate takes what it wrote. When the week takes every pin back to that of `main`, the file equals `HEAD`, and Renovate 44.249.1 warns of the empty commit in `commitFiles` of `lib/util/git/index.ts`, pushes nothing and creates no branch. As it builds the refresh again whenever its branch is missing, the warning comes back in every run of that Monday, so the issue can't count a quiet run before the day ends. In the 60 days before, the empty commit of a refresh came 8 times; 7 needed nothing, and the 8th came while the pull request of the refresh was open, from a refresh that #1015 fixed.

On another branch, the same warning means a fix that can't land: on the branch of a security update it needed the maintainer in #212 and #384, as `docs/troubleshooting.md` describes for a version that another package pins.

The empty commit had a second cause. When PyPI didn't answer for a version of `main` that the refresh moved, after the last attempt of `ask`, `pypi_uploaded` returned none as for a version that PyPI can't date, the refresh kept that version as `main` has it, and when that happened for every moved package, the refresh was empty and missed that Monday without a word.

## Options

1. **`logLevelRemap` for the message, or a filter by level:** it applies to the whole repository and matches the message alone, so it would hide the security fix that can't land as well.
2. **Count how often the warning comes back:** it comes back in every run of a Monday on which the refresh has nothing left to bring.
3. **Let Renovate commit its own compile:** it would bring versions younger than a week.
4. **A list of the warnings that need nothing in the bot, by message, branch and repository, with the reason of each,** that applies only when nothing else points to a problem of the branch; and a refresh that PyPI didn't answer about, which would be empty, fails.

## Decision

Option 4. `NEEDLESS` of `blueprint/bot_health.py` holds the empty commit on two branches where `locks --refresh` runs: `renovate/pip-compile-refresh`, Renovate's branch of the refresh of pip-compile, in any repository, and `renovate/lock-file-maintenance-the-tools-of-the-blueprint's-tests` in Dennis-Otto/repo-blueprint alone, whose group refreshes `requirements-dev.txt` only. Not the prefix `lock-file-maintenance-`: the group of a project can be a refresh of npm, such as that of `.github/a11y` in the blueprint, where no `locks --refresh` runs.

The bot decides on the field `branch` of each line, not on the place that the issue shows, which names the lock file of an artifact error. Such a line needs nothing only in a public repository, when no other warning or error of that repository in the run has the same branch, and when GitHub answers that no pull request of the branch is open. An error of GitHub and a 404 count as no answer, so the warning stays a problem, as it does in a private repository that the token of the job can't read; the job keeps its permissions, `contents: read` and `issues: write`. A complete run with only such warnings counts as quiet, and the summary of the job names each with its reason.

`ask` of `blueprint/lock_age.py` raises `Unanswered`, a kind of `Undated`, for an `OSError` or a 5xx after its last attempt, and `Undated` alone for a refusal or an answer without a date. The refresh keeps a version that PyPI didn't answer about as `main` has it, as before, and names it. When at least one moved version is of that kind and no lock file of the refresh differs from `HEAD`, `locks --refresh` exits 1: Renovate records the artifact error, logs `Branch not created because artifact update failed`, which the bot lists at once, and its next run of the day tries again. A refresh that still brings something passes as before, and no pull request waits for the maintainer because PyPI didn't answer.

## Consequences

- After a refresh merged on a Monday, the later runs of Renovate that day leave the issue quiet, and the summary *problems of Renovate* says what the bot left out and why.
- The empty commit stays a problem everywhere else: on the branch of a security update, on any other update, on a refresh of npm, and on the refresh while its pull request is open or while another line names its branch.
- Each such warning costs one request for the open pull requests of its branch, of each repository once, only for the branches of the list.
- A new branch that needs nothing comes into `NEEDLESS` with its reason and its tests; the refresh of pip-compile in a group of a project stays a problem, since only the blueprint's own group is known to be one.
