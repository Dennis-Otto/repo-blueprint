# Each fix names the paths that it writes

- Status: accepted, follows up [0142](0142-the-fix-bot-commits-nothing-that-runs-with-rights-where-nobody-reads-its-commit.md)
- Date: 2026-11-15

## Context

Decision 0142 keeps every file that decides what a workflow runs, or that runs later with the rights of the release app, out of the fix bot's commits where nobody reads them: on a pull request of a bot, on one whose auto-merge is on, and on that of `main`. The other files of an artifact `fixes-<name>`, such as the documentation, the tests and the code of a project outside the guarded folders, still came from whatever ran in the job of a check, a dependency of the branch or one of its tools, as data that nobody reads before such a pull request merges. Nothing tied a file to the command that was meant to fix it. Decision 0142 left that as its option 4 ([#864](https://github.com/Dennis-Otto/repo-blueprint/issues/864)), with one more case: a person's pull request counts as read when the bot plans its commit, so one that turns auto-merge on afterwards, or that is merged right after it turns green, takes the bot's commit of a guarded file without another look.

Three questions shape the answer:

- **Which check an artifact belongs to.** The bot knows the name of each artifact, `fixes-check` of the CI, `fixes-lint`, `fixes-docs`, `fixes-downstream`, and those of a project, such as `fixes-e2e-<index>` of a leg of a matrix job. A workflow of a pull request names its artifacts, but a dependency that runs in a step of a check writes files, not the name of the upload.
- **What a project without globs gets.** The catalog format changes for every project with an update, and a check of a project that keeps fixes has no `writes` yet.
- **Whether the globs alone close the gap.** The text files and Ruff fix nearly every path, `blueprint/` included, so they narrow it, as the issue says, and the guard of 0142 stays.

## Options

1. **Globs only where nobody reads the commit.** A fix that its check doesn't name would still reach a person's own pull request.
2. **Globs on every pull request, from the catalog of `main`,** with a default for an explanation without them: every path where a person reads the commit, none where nobody does.
3. **A list of the checks of each job,** so that `fixes-lint` takes the globs of the check *markdown*, which its job runs: a second list beside the steps of `lint.yml` that names them for the PR coach, for one job that keeps one fixer.

## Decision

Option 2.

- **The key:** each explanation of `.github/checks.toml` and `.github/checks.project.toml` may name in `writes` the globs of the paths that its fixes write, from the root of the repository, with `**` for any folders, `*` for any part of a name and `?` for one character, as the `ignorePaths` of Renovate match them. `Catalog.load` refuses a glob that leaves the repository or names a folder alone.
- **Which check:** the bot reads the catalog and `scripts/check.sh` of `main`, as it runs from there. `fixes-<name>` takes the check `<name>`, or `<name> (*)`, also without the `-<index>` of a leg; `fixes-check`, the job of `scripts/check.sh` of `check (*)`, takes the globs of each of its steps whose commands fix files. The entry of the job names the globs where its job keeps the fixes of a check that it runs: `lint` those of markdownlint, `docs` `.github/a11y-accepted.toml`, `downstream` `tests/answers/*.yml`.
- **Every pull request:** a file that the check names stays a fix, and one that it doesn't name stays with a person, with the reason, also on a person's own pull request and in the suggestions on a fork: it isn't what the commands of the check make. Where two artifacts hold one file, the first that allows its path wins.
- **The default:** a fix from a check whose explanation names no `writes`, or from an artifact that no check of the catalog names, is *unnamed*. It reaches a pull request whose author reads the commit, as before, and stays with a person where nobody does, with the guarded files of 0142. A project's own checks keep working on its own pull requests after the update, and give their globs to get the fixes onto those of Renovate.
- **The blueprint's own:** every step of `scripts/check.sh` whose commands fix files, and every check whose workflow of the blueprint keeps an artifact `fixes-*`, names its globs; tests keep them equal to what their fixers write, such as `MOVABLE` of the migrations, the files of `PLACES` of the version and the pages of `reference.py`.
- **The case that stays:** the bot decides whether its commit is read when it plans it, and it can't know whether a person who turns on auto-merge later, or who merges right after green, reads it. Where a person reads the commit and it changes a file that decides what a workflow runs or runs with its rights, its message and the summary of the bot name those files and ask for a look before the merge and before auto-merge goes on. A team that needs that look for sure requires approvals with `required_approvals` of `[branch]`, whose ruleset asks for a new approval after every push, the bot's included ([decision 0157](0157-the-reviews-of-main-bind-people-and-the-branch-bot-merges-the-bots-past-them.md)).

## Consequences

What runs in a check can bring onto a pull request that nobody reads only what the commands of that check are meant to write, and onto any other only that, too. The text files and Ruff still name broad globs, `**` and `**/*.py`, so the guard of 0142 stays the one that keeps code that runs with rights out. A new fixer of the blueprint names its globs, or a test fails. A project whose own check keeps fixes without `writes` loses them on the pull requests of Renovate and on those whose auto-merge is on until it names them; the summary of the bot says why, and the changelog and the starter of `.github/checks.project.toml` say how. The names of the artifacts stay as they were, so no workflow of a repository changes.
