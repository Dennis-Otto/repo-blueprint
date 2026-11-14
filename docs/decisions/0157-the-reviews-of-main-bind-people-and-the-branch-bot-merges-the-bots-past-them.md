# The reviews of main bind people, and the branch bot merges the bots past them

- Status: accepted
- Date: 2026-11-14

## Context

The ruleset *Protect main* asked for no approving review and no review of a code owner, with fixed values. That is right for one maintainer, but a team or an organization couldn't require "one approval for each change of a person" with the settings as code ([issue 835](https://github.com/Dennis-Otto/repo-blueprint/issues/835)): a change of *Protect main* in the settings of GitHub is drift, which the settings bot puts back every week, and a second ruleset of its own held every pull request of Renovate, Dependabot, the release bot and the blueprint bot as well, since no person reviews an update and the workflows may not approve pull requests. The roadmap promises the opposite: only updates that pass every check merge on their own, and every other change waits for a person.

GitHub lets a bypass actor of a ruleset merge a pull request past it. Its native auto-merge doesn't: reports of users say that the merge that auto-merge makes once the requirements are met never takes a bypass into account, and GitHub documents nothing else. A merge through the API of a bypass actor does.

## Options

1. Put the reviews into *Protect main*, with the release app as a bypass actor of it, as the issue suggests: the app could then merge without the required checks and the signed commits as well, and auto-merge would still wait for a review.
2. Let a second identity approve the pull requests of the bots, such as the token of a job: it needs the setting that lets the workflows approve pull requests, which then lets every workflow approve any pull request, and the release app can't approve its own.
3. A ruleset of its own for the reviews, *Reviews of main*, which only the release app may pass, in pull requests only, and the branch bot, which runs as the release app, merges a pull request of the bots past it once it is up to date and its required checks have passed.

## Decision

Option 3. `required_approvals` (0 to 10) and `code_owner_review` of `[branch]` in `.github/repository.toml`, 0 and false there, which a project sets in `.github/repository.project.toml`, make the ruleset *Reviews of main*: approving reviews, a review of the code owners, a new approval after every push, of someone other than the person who pushed, and the release app of `RELEASE_AUTOMATION_APP_ID` as its bypass actor for pull requests. *Protect main* stays as it was and binds the app too. `code_owner_review` needs a `CODEOWNERS` file, which the project writes, or the settings refuse to load.

The branch bot merges a pull request past the review only when the bots made it: the release app, whose Renovate and bots commit as the app, Dependabot, or Renovate where the app of Mend runs it, opened it, and each of its commits is of one of them, committed by one of them or by GitHub itself, and signed. The committer counts as well as the author: anyone can write the author of a commit, and GitHub checks the signature against the committer. It merges with the head that it read, squashed under the title and description of the pull request, so GitHub refuses the merge when the head moved or a rule of *Protect main* isn't met. A pull request of a person, one with a commit of a person in it, a run of the bot outside of its workflow and a refusal of GitHub all wait for a review. The bot does this only where `REVIEWS_OF_MAIN` is on: a review that another ruleset wants, such as one of the organization, which the release app can't pass, holds the pull requests of the bots as before.

The settings set the variable `REVIEWS_OF_MAIN` to `on` or `off` with the ruleset. Where it is on, the bots after the checks start the branch bot also after a check that passed for a pull request that a bot pushed to, since nothing else starts it once auto-merge waits for the review; each run of the branch bot cancels the one before it, so the last check to pass decides. Where it is off, nothing changes: no new runs, no new ruleset.

## Consequences

A team gets reviews that last and the bots still merge their green updates by themselves, without a review of a person, as the roadmap says. A repository without the release app gets the reviews without a bypass: its updates wait for a review too. A release pull request that the release workflow merges by itself, after updates of dependencies alone, waits for a review, as the line of the branch bot leaves the release pull request to the release workflow. The behavior of GitHub's auto-merge with a bypass actor is not documented; if GitHub starts to honor the bypass in auto-merge, the bots merge without the branch bot, which then finds nothing left to merge. The issue also suggested that `.bestpractices.json` propose `two_person_review` and OSPS-QA-07.01 where the setting is on; that is declined: `.bestpractices.json` still leaves them to the owner, since the template renders it before a project sets its reviews, and only the owner can say whether the reviews of the project count.
