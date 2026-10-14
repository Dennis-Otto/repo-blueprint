# Every check explains its failure, in the check and in one comment

- Status: accepted
- Date: 2026-10-13

## Context

A contributor whose pull request failed a check saw a red cross and the raw log of a tool. Nothing said in plain words what was wrong, why the project cares and which command fixes it, and a pull request from a fork got no comment at all: its runs have a token that can only read, so they can't write to the pull request. Every mistake cost a round trip with a maintainer, and a first contribution often ended there.

The blueprint runs about two dozen checks in every repository, from the tests and the format of the code to the sign-off of each commit, and each repository adds checks of its own, such as end-to-end tests. Whatever explains them must work for every check, also one that a project adds, and must never run the code of a pull request with a token that can write.

## Options

1. **Leave it to the logs:** the tools say what they found; the contributing guide says the rest. Nothing to build, but the person who needs the explanation is the one who doesn't know where to look.
2. **Each check comments on the pull request itself:** simple where the run may write, but impossible for a fork without `pull_request_target`, which would run the code of the pull request with a token that can write, and every check would leave a comment of its own.
3. **Each check uploads its findings as an artifact, and a workflow after the checks turns them into one comment:** works for forks, but the artifact of a fork is data that the pull request wrote, which the privileged workflow must download and parse, every job needs a step to upload it, a check of another app has none, and artifacts expire.
4. **An explanation for each check in the repository, a step at the end of every job that shows it when the job fails, and a workflow after the checks that reads the check runs and their annotations from the API and keeps one comment up to date.**

## Decision

Option 4, the PR coach.

- **One catalog:** `.github/checks.toml` explains every check of the blueprint by the name that GitHub shows, and every step of `scripts/check.sh` by the name that it prints: what it found, why that matters, how to fix it, the commands and a link. `.github/checks.project.toml` belongs to the project, explains its own checks and wins. A test of the blueprint fails for a required check or a step without an explanation, and `blueprint.py coach verify` lists them in a repository.
- **In the check:** the last step of every job, `if: failure()`, runs `blueprint.py coach explain` with the name of its check, which writes the explanation into the summary of the job and as an annotation. `scripts/check.sh` does so for the step that stopped it, by a trap on its exit, also on a machine. Tools that know the line, such as Ruff and the check of the text files, annotate it in the CI.
- **One comment after the checks:** a job of `after-checks.yml` runs after every workflow of the checks of a pull request, also one from a fork, with the token of the repository. It reads the check runs of the head commit and the annotations of those that failed from the API, which GitHub records for every check, also one of another app, so nothing is uploaded and nothing of the pull request is downloaded or run. The step that stopped `scripts/check.sh` comes from the title of its annotation. The comment has one section for each check that failed and a suggested title when the title is no Conventional Commit; a pull request whose checks never failed gets none, and one whose checks pass again gets a short all-clear.
- **Untrusted text only as code:** a name, a message, a path or a title that a pull request controls appears only as inline code, on one line, without control characters and cut to a short length, so it can't mention anybody, link anywhere, add HTML or end its section. Only links to GitHub itself appear as links. The comment stays below the limit of GitHub, and only the comment of the bot with its marker is ever changed.

## Consequences

A contributor reads in the pull request what failed and how to fix it, with the commands, without asking anybody, also from a fork; the maintainer explains a mistake once, in the catalog, instead of in every pull request. A new check, or a new step of `scripts/check.sh`, comes with its explanation in the same pull request, or a test fails. Each job of a check gets one more step that runs only on failure; a job that checks nothing out, such as one that sums up a matrix, checks out `.github` and `blueprint` only then. The workflow after the checks runs after the scanners of the pull requests as well, a few seconds for each run, one at a time for each commit. The coverage of a pull request keeps its own comment for now; moving it into the report of the coach, and annotations of further tools such as ShellCheck and mypy, can follow.
