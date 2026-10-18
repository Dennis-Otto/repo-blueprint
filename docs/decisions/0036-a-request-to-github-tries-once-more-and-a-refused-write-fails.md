# A request to GitHub tries once more, and a write that GitHub refused fails

- Status: accepted
- Date: 2026-10-18

## Context

Every bot of the blueprint talks to GitHub through `blueprint/github.py`, which runs `gh api`. Three things in it made the settings bot report what didn't happen:

- **A 404 counted as an answer for every request,** also for a write. GitHub answers 404, not 403, to a token that lacks the permission for some changes, so `settings apply` reported a change that GitHub had refused as applied. The check after it then showed the drift with exit code 1 instead of 2, and the hint at the permission that the release app lacks never showed.
- **No request tried again.** A gateway of GitHub that timed out (502, 503, 504) or a rate limit, such as the secondary rate limits that this account met on 2026-10-12, failed the run at once.
- **A list was its first page:** the labels stopped at 100, the rulesets at 30, the secrets of an environment at 30. A label in another case, such as `Bug` for `bug`, was a missing label, and creating it failed, as GitHub ignores the case of a name.

The settings bot also started only on a change of the settings as code, not of its own code, so a release of the blueprint that changed how a setting is applied reached GitHub with the weekly run. A push of `.github/labels.toml` started it and the Labels workflow at once, and both created the same new label: one of them failed.

## Options

1. Keep the requests as they are, and let the check after `settings apply` find what didn't happen. It finds it, but names the wrong cause and no permission.
2. Treat a 404 as an answer only where the caller asks for it, try once more where waiting can change the answer, and read every page of a list.
3. As 2, and try again several times with a growing wait. A bot run that waits minutes holds a runner of the account while the pull requests wait.

## Decision

Option 2.

- **A 404 is an error unless the caller says otherwise.** `Api.request(..., missing_ok=True)` makes it an answer; `get` and `exists` ask what is there, and a few deletes of something that may be gone a moment later, such as a label taken off a pull request, pass it too. Every other write that GitHub answers with 404 raises `GitHubError`, and `settings apply` names the permission that the release app may lack, as for a 403.
- **One more try, after a wait,** for 502, 503 and 504 (5 seconds) and for a rate limit (a minute, as GitHub asks, or the time that its `Retry-After` and `X-RateLimit-Reset` name). A wait of more than 90 seconds isn't worth it: the request fails at once, and the next run tries again; a rate limit is named as such, not as a missing permission.
- **Every page of a list:** `Api.get_all` runs `gh api --paginate --slurp`, and takes the items of a page that holds them in a field, such as the workflow runs. The settings bot reads the labels, the rulesets, the secrets and the branches of the environments with it, and compares the names of the labels without their case: a label in another case is renamed.
- **The settings bot starts on a change of its own code:** in a repository `.github/blueprint.py` and `.github/blueprint/`, which an update of the blueprint brings, and in the blueprint the modules that `settings apply` runs. A change of the labels is the Labels workflow's alone; should both create a label at once all the same, the settings bot updates the one that GitHub says exists already.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/how-a-request-to-github-ends.dark.svg">
  <img src="../images/diagrams/how-a-request-to-github-ends.svg" alt="How a request to GitHub ends: A bot asks GitHub through the GitHub CLI, and a list is read with all its pages. An answer without an error is the answer, and so is a 404 where the bot asked what is there. After a gateway that timed out or a rate limit, the request waits as long as GitHub asks, 5 seconds or a minute, and tries once more, unless the wait would be longer than 90 seconds. Any other error, also a 404 to a change, fails the request, and settings apply names the part and the permission that the release app may lack.">
</picture>

## Consequences

A run of the settings bot in which GitHub refused a change fails with exit code 2 and says which part and which permission; a change of the blueprint's settings code reaches every repository with the merge of its update. A short outage of GitHub costs a bot run 5 seconds, a secondary rate limit a minute, instead of the run. The Labels workflow, the issue assistant's, still fails when it loses a race for a new label against the settings bot; that can happen only on a push that changes the labels and the settings or the bot's code at once. `tests/test_blueprint.py` simulates GitHub with pages, the case of label names and the rules of a ruleset that GitHub refuses, and pins the rulesets in `tests/data/rulesets/`, so that a change of one changes its fixture on purpose.
