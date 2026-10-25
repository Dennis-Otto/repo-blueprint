# Every pull request follows the actions that its workflows run, also in turn, through a few queries of GraphQL

- Status: accepted, amends [0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md)
- Date: 2026-10-25

## Context

GitHub starts a workflow only when `[actions.selected]` allows every action and reusable workflow that it runs, also those that these run in turn at the commit of their pin ([decision 0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md)). Two gaps let a pull request break that:

- **Only the settings bot followed the actions in turn, after the merge.** A test renders every kind of project and checks the actions that its workflows name, but what a composite action or a reusable workflow runs in turn is in the files of other repositories, which no test reads. An update of Renovate that made an action run a new one in turn passed every check of its pull request; after the merge, every workflow that ran the action failed to start, and in the blueprint every repository after the release, until `settings check` named the missing pattern ([#275](https://github.com/Dennis-Otto/repo-blueprint/issues/275)).
- **Following them cost a request for each file.** `settings check` asked the contents API for the file of each action, about 40 requests and 70 with the actions in turn for a repository of the blueprint, one after the other. The token of a workflow has 1,000 requests in an hour for all the workflows of its repository, so a check in every pull request would have used up the hour of a busy night.

## Options

1. Keep the settings bot as the only one that follows the actions in turn.
2. A step of the check *lint* that follows them in every pull request, through the contents API.
3. As 2, through GraphQL: one query reads the files of up to 50 actions, so the check takes one query for each level of the actions in turn, three for a repository of the blueprint; and the Variants run it for every kind of project.
4. As 3, and the Rollout widens the list on GitHub to that of the release before it pushes the update.

## Decision

Option 3.

- **The check of every pull request.** `python3 .github/blueprint.py settings actions` follows every action and reusable workflow that the workflows and actions of the repository run, also in turn, and fails for each one that `[actions]` of `.github/repository.toml` with `.github/repository.project.toml` doesn't allow, from the files alone, with an annotation at the line of the workflow that names it, what runs it in turn and the pattern to add; also for a step with `docker://`, and for an action whose file GitHub refused, since what it runs in turn is then unknown. The step *Check that the allowed actions let every action start* of *lint* runs it with the read-only token of the job, which reads the files of public actions on every pull request, also from a fork, and none of the settings on GitHub. The Variants run it in each project that they render, new, updated and with the answers of each repository, so that a change of the blueprint fails its own pull request, not every repository of a kind after the release.
- **GraphQL reads the files.** One query asks for the file of up to 50 actions, each at the commit of its pin, the owner, the name and the place of each file as variables, never as text of the query. A repository or a file that GitHub doesn't know runs nothing, as with the contents API; a refusal of one, or of the whole query, names the action whose file is missing. `settings check` reads them the same way, so the settings bot takes three requests where it took about 70.
- **No fix by a bot.** Whether an action may run is a decision of trust for the project: the check names the pattern and the file, and a person adds it. The fix bot never widens the list.

Option 4 needs a token that may change the settings of the actions, a permission of *Administration* that the token of the Rollout and of the blueprint bot lacks on purpose. It waits for a decision on such a token, tracked in [#440](https://github.com/Dennis-Otto/repo-blueprint/issues/440): until then, the update pull request of a release that adds an action waits for `settings apply` from its branch, as decision 0038 says, but no longer for a pattern that the release forgot. [Decision 0076](0076-a-second-app-writes-the-administration.md) gives the blueprint bot that token from a second app, the settings app, once the owner sets it up.

## Consequences

A pull request that makes a workflow run an action that the list lacks, also one that a composite action or a reusable workflow runs in turn after an update, fails *lint* with the pattern to add, in the blueprint and in every repository of it. The check needs GitHub and its token: on your machine it runs with the GitHub CLI, and `scripts/check.sh` doesn't run it, since it runs without the network. A pull request that changes no workflow reads the same files again, three queries of GraphQL, which count far less against the hour of the token than the contents API did. A repository or file that the token can't see, private or deleted, counts as running nothing and isn't followed, as with the contents API before; a gateway that timed out is asked once more, and a refusal of GitHub that passes, such as its rate limit, fails it until it runs again.
