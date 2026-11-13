# The bots in bash sit out an outage of GitHub too

- Status: accepted, follows up [0136](0136-an-outage-of-github-starts-no-bot-failure.md)
- Date: 2026-11-13

## Context

[Decision 0136](0136-an-outage-of-github-starts-no-bot-failure.md) made `blueprint.py`, the flaky-test bot, the bot for failed releases, the bot for stopped checks and the PR coach's fetch of the coverage try GitHub again after a 5xx or no answer, and end with the notice *GitHub is unavailable* when GitHub keeps failing. Each of those four steps had its own copy of the functions `tried` and `unavailable`. The other steps of *After the checks* that call `gh` in bash still failed at the first error of GitHub and mailed the maintainer: the report of the flaky tests, the bot for cancelled checks, the fix bot's say on the pull request and its issue of `main`, the bot of the title and the entry, and the diagram bot. So did every step that creates a token of the release app with `actions/create-github-app-token`, in those jobs and before the branch bot of *Update branches*: the action tries three more times within seconds, then fails the job ([issue 786](https://github.com/Dennis-Otto/repo-blueprint/issues/786)).

## Options

1. **A copy of the functions in each step,** as before: a dozen copies of 35 lines, which drift apart.
2. **A script in `.github/` that each step sources:** the jobs `report` and `cancelled` check out nothing, and a checkout calls GitHub, so it fails in an outage itself, before the step that would sit it out.
3. **The functions in a variable of the workflow, `OUTAGE`,** which each step runs first with `eval "$OUTAGE"`: one copy in each workflow, which needs no checkout, and a test keeps the copies of *After the checks* and *Update branches* the same.

For the token: the action can't be told to try longer, and GitHub's answer stays in its log, which no later step of the job can read.

## Decision

Option 3, and a step after each token.

- **`OUTAGE` holds `tried`, `once`, `given_up` and the trap,** as the steps of 0136 had them. `tried` runs a call of `gh` again after a 5xx or no answer, 10, 20 and 40 seconds apart. `once` runs a call that writes, such as a comment, a new issue, the closing of an issue with its comment or a commit of GraphQL, only once, as GitHub may have done it before it failed, which 0036 asks of a POST too; an edit or a rerun, which does the same twice, goes through `tried`. Either leaves a mark when GitHub failed, and the trap turns the step's end on that mark into the notice and a pass. A step names in `INSTEAD` what it does instead of nothing, as the coach does.
- **Every call of `gh` in the jobs of the bots after the checks and of the branch bot** goes through `tried` or `once`, after `eval "$OUTAGE"` as the first line of the step, which a test keeps so. A call whose failure the step already took for an answer still does: a log or an artifact that isn't there is no outage, but one that GitHub keeps failing is.
- **`blueprint.py fix`** ends with the notice as well, as `next-branch` and `coach report` do, for each action of the fix bot after the checks. Its command `/fix` on a comment still fails, as its failure tells the person who asked.
- **A token of the release app** that GitHub fails no longer fails the job at once: the step goes on with `continue-on-error`, and the next step, *Tell an outage of GitHub from a refused token*, asks GitHub for the repository with the job's token through `tried`. When GitHub keeps failing, the step ends with the notice; when GitHub answers, it refused the token, and the step fails with an error that names the causes, such as an app that isn't installed or a key of another app, before any step that says on a pull request that the bot failed.

## Consequences

An outage of GitHub that lets the runs start but fails the API fails no run of the bots after the checks and of the branch bot: each ends with a notice, and its next event catches up. A comment or a commit that GitHub failed, but made, may be missing its follow-up, such as the counts of the issue of flaky tests, until the next report; none goes out twice.

A token that GitHub refuses fails the job one step later than before, with an error that names the causes, and the run of a bot whose token GitHub failed in an outage waits up to 70 seconds more before it passes. A step that a project adds to these workflows sources nothing by itself: it runs `eval "$OUTAGE"` to sit out an outage.
