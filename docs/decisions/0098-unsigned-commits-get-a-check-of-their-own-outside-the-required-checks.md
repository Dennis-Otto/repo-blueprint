# Unsigned commits get a check of their own, outside the required checks

- Status: accepted
- Date: 2026-11-01

## Context

On homedarts-for-autodarts#541, a pull request from a fork with an unsigned commit, the PR coach wrote *Every check passed* and what the merge would make of the next release, while GitHub's merge box said *Commits must have verified signatures*. Nobody noticed for ten hours. The rule `required_signatures` of *Protect main* blocked the merge, but no check looked at signatures, the coach read only the check runs, and `CONTRIBUTING.md` and the template of a pull request asked only for the sign-off, which isn't a signature.

## Options

1. Only the coach: it asks GitHub for the commits and says so. The list of the checks stays green while the pull request can't merge, and a person who reads only that list learns nothing.
2. A step of the job *conventional title*, as decision 0027 joins quick checks. It takes no runner of its own and adds no required check, but a required check named after the title then fails for commits, and the job holds the rights to write labels, which this question doesn't need. A pull request that GitHub blocks already would get a second, misnamed block.
3. A new required check of its own. Its name would enter the settings of every repository, each of which would have to apply them before its update merges, and it would only repeat what the rule enforces already: a repository whose rule requires signatures blocks the merge without it, and one without the rule passes it anyway.
4. A job of its own, *signed commits*, in the workflow *Pull request title*, outside the required checks, and a coach that also asks GitHub itself.

## Decision

Option 4.

- **The rule decides, not a list of the blueprint.** The check and the coach read `repos/<repo>/rules/branches/<base>`, and only with `required_signatures` there each commit of `pulls/<n>/commits`, whose `commit.verification.verified` says what GitHub's merge box goes by. A repository without the rule passes, and so does a private one on a plan without rulesets, whose rules GitHub refuses to show; any other refusal fails, so that the coach gives no all-clear it can't back. A merge of *Update branch* or a commit of a bot through the API is verified.
- **The workflow *Pull request title* starts it.** Its event, `pull_request_target`, starts on every push, also from a fork whose other workflows wait for the approval of a maintainer, and runs the code of the default branch; the job checks out nothing of the pull request, and its token only reads. This one job more is no second wait for a required check: nothing waits for it, and it needs no change of the settings of any repository.
- **The coach doesn't rely on the check.** Every run of the coach asks GitHub itself, so that the report is right before the check has ended or even started, and a run that passed, which GitHub started late, doesn't turn it back. While commits block the merge, the check counts as failed, its section comes first, and the report says neither *Every check passed* nor what the merge would make of the next release.
- **The explanation is an entry of `.github/checks.toml`,** as for every other check, so a project can override it in `.github/checks.project.toml`. `{base}` in a command stands for the branch that the pull request goes into. The branch of the pull request itself stays a word that the reader replaces: a fork names it, and no text of a fork belongs into a command that a maintainer may paste.
- **No bot signs.** Only the key of the author of a commit can sign it, so the explanation says how, with the commands, and no fix bot does it.

## Consequences

- A pull request that can't merge for its signatures shows a red check and an explanation within a minute of its push, also from a fork that waits for approval.
- Every push of every pull request runs one small job more, of a few seconds. Decision 0027 joins quick checks because each job waits for a runner, and nothing waits for this one.
- The list of the required checks stays as it was, so the release needs no `settings apply` before an update.
- `CONTRIBUTING.md`, `AGENTS.md`, the template of a pull request and the comment on a first pull request ask for a signature, in words that keep `-S`, which signs, apart from `-s`, the sign-off of the DCO.
- A pull request lists at most 250 commits through the API, so a commit after those goes unnamed; GitHub's rule still blocks it.
