# A refused ruleset or variable leaves the others applied

- Status: accepted
- Date: 2026-11-17

## Context

The settings as code were applied to a new repository in which the release app was not installed ([issue 1030](https://github.com/Dennis-Otto/repo-blueprint/issues/1030)). GitHub refused the ruleset *Release tag creation*, and *Reviews of main* with the app as its bypass actor, with 422 and the error `Actor … integration must be part of the ruleset source or owner organization`. `settings apply` printed only `Validation Failed`: the reason, a string in `errors`, was dropped. The rulesets went in one request after the other in one `try`, so the refusal also ended the step before the unwanted *Reviews of main* was deleted, and GitHub went on requiring a review that the file no longer asked for. The step of the variables then set `REVIEWS_OF_MAIN` to what the file wanted, the opposite of what GitHub had, and it stopped at the first variable that GitHub refused, which was the empty `RELEASE_AUTOMATION_APP_ID` that the run had used to take the app out of the rulesets. `settings check` was clean while the default branch on GitHub had no `CODEOWNERS` for the review of the code owners, and the line of a drifted ruleset named only its key, on the wrong side.

## Options

1. Keep one request after the other and stop at the first refusal, with GitHub's reason added to the message.
2. Apply each ruleset and each variable by itself, collect the refusals and say at the end what happened to each item; set `REVIEWS_OF_MAIN` from the rulesets that GitHub has after the apply.
3. Check beforehand whether the release app is installed, and leave out the bypass actor where it isn't.

## Decision

Option 2. Each ruleset and each variable goes in a request of its own: a refusal of GitHub is kept, the next item goes all the same, and the unwanted rulesets are deleted whatever happened to the others; the run then names each item with `created`, `updated`, `deleted`, `set` or `refused:` with GitHub's errors and a hint, and still ends with 2. A part that GitHub refused alike for every item, as for a token without the permission, is said once, as before. A rate limit or an outage of GitHub ends the part at once with its hint, as every other request would meet it too. Each error of GitHub's answer comes with the message, also one that is a string.

`REVIEWS_OF_MAIN` follows GitHub: after a refusal in the rulesets, it is `on` only where *Reviews of main* is there, and it stays as it is where the rulesets on GitHub can't be told; a value that `[variables]` sets itself stays. An empty value of a variable says that the repository has no such variable, as GitHub keeps none with an empty value: `settings check` wants none, and an apply deletes it. A repository without the release app sets `RELEASE_APP`, `RELEASE_AUTOMATION_CLIENT_ID` and `RELEASE_AUTOMATION_APP_ID` to `""` in `.github/repository.project.toml`: no ruleset names the app, the environment `release` asks for no private key, and the check is clean. `settings check` names a review of the code owners that the default branch on GitHub has no `CODEOWNERS` for, and the line of a drifted ruleset gives each key with what GitHub has and what the file wants.

Option 3 was declined: whether an app is installed is a question that only the app itself, or a token of the owner with more rights, can answer, and the refusal of GitHub is the answer that counts.

## Consequences

A repository with the release app installed gets exactly the rulesets and variables of before. A refused ruleset no longer leaves a review required that the file dropped, and the bots after the checks start the branch bot only where main requires reviews. A variable that the file sets to `""` is deleted on GitHub, also one that a person set; before, such a value was refused by GitHub and never applied.
