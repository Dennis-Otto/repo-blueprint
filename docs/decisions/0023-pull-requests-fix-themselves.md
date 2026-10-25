# Pull requests fix what a command can fix by themselves

- Status: accepted
- Date: 2026-10-14

## Context

The PR coach ([decision 0022](0022-every-check-explains-its-failure.md)) explains every check that fails, with the command that fixes it. For a large share of the failures, that command is all there is to it: the format of the code, trailing whitespace or CRLF line endings, a rule of markdownlint, a table of a page that sets columns side by side. A person still has to read the explanation, set up the tools, run the command, commit and push, and a dependency update of Renovate, which no person watches, stays red when a new version of Ruff formats differently. Every such round trip is time that a machine could save, and some contributors give up on it.

Fixing needs the code of the pull request and its tools, which only an unprivileged job may run, while committing needs a token that can write, which must never run the code of a pull request. A pull request from a fork can't be pushed to by any bot without the consent of its author, and `main` takes changes only through pull requests that pass every check.

## Options

1. **Leave it to the explanation:** the coach names the command, and the person runs it. Nothing to build, but every mechanical failure costs a round trip.
2. **pre-commit.ci or a similar service:** fixes and pushes on its own, but it is an external app with access to the repositories, it runs only hooks, and the blueprint installs no apps.
3. **A bot that checks out the pull request with a token that can write and runs the fixers:** simple, but it runs the code and the configuration of a pull request, such as a `.php-cs-fixer.dist.php` or a configuration of markdownlint in JavaScript, with that token.
4. **The failing check fixes in its own unprivileged job and keeps what changed; a bot after the checks commits those files as data, suggests them on a fork and opens a pull request for `main`.**

## Decision

Option 4: fix first, explain second.

- **The catalog decides:** every explanation of `.github/checks.toml` and `.github/checks.project.toml` says in `autofix` either the commands that fix what its check finds, or a sentence with the reason why no command can. A test of the blueprint fails for an explanation without one, and `blueprint.py coach verify` lists them in a repository, so that no new check skips the question.
- **The check fixes:** when a check fails, its job runs the commands of `autofix`, on the head of the pull request rather than its merge into `main`, or on `main`, with the tools that it installed already; those of the check of `scripts/check.sh` are the commands of each of its steps. It keeps every file of the commit that they changed as an artifact `fixes-*`. markdownlint fixes with the same action that checks.
- **The fix bot commits data, never code that runs:** after the checks, a job of `after-checks.yml` waits until the checks of the commit that fix have ended, so that one commit holds all their fixes. It checks out `blueprint.py` of `main` only, and takes from the artifacts only text files that the commit has already, by plain paths, outside `.git` and `.github/workflows/`, a hundred at most; it never adds, deletes or links a file.
- **Three layers:** on a pull request from a branch of the repository, also one of Renovate or another bot, the bot commits the fixes onto the branch through the API, as the release app, with its sign-off, and the checks run again; the report of the PR coach names the files. On a pull request from a fork, it suggests the fixes at their lines, ten at most in one review and none twice, and names the files whose fix no suggestion shows. On `main`, it keeps one pull request from `bot/self-heal` with the fixes, which merges itself, and closes it once `main` needs none.
- **Never a loop, and never against a wish:** the bot makes one more commit onto its own, because the checks of a commit end at different times and one check may fix a file after another one did, but never a third in a row; it stops with an error instead. A pull request with the label `no-bot-fixes` gets no commit. A failure says so on the pull request, and on `main` it keeps one issue open until the bot passes again.

## Consequences

Most failures that a command fixes are gone a minute after the checks, without a person: the format, the whitespace, the rules of markdownlint and the pages in one column, also on the branches of Renovate, so that an update of a formatter stays green and merges itself. A contributor from a fork applies the fixes with a click. A check that a project adds can fix itself by a command in its explanation, and a step that it adds to its workflow.

The artifacts of a branch of the repository run the dependencies of that branch, as every check does; the bot commits what they changed after checks of its paths and kinds, as the diagram bot commits what its check drew, and each such commit shows in the pull request. A commit through the API keeps the mode of a file and can't set one, so a hook that isn't executable stays a finding for a person. The jobs of the checks that fail take a few seconds longer, the fix bot runs once for each run of Lint and of the CI that failed, and once for each run of the CI on `main`, a few seconds each. The fixes of the versions of the release bot and of the lock files of Composer and npm followed in [#225](https://github.com/Dennis-Otto/repo-blueprint/issues/225), by [decision 0068](0068-a-lock-file-and-a-version-fix-themselves-only-where-their-tool-refuses-them.md); a command for a `/fix` of a maintainer on a fork, a fix for the lock files of pip-compile and a draft of the entry of the changelog follow in [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429), with the fixes of the workflows of a project of its own.
