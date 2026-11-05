# GitHub registers every workflow of a new repository by a pull request

- Status: accepted
- Date: 2026-11-05

## Context

GitHub starts a workflow only once it has registered it. In dennis-otto-pager, which `blueprint.py create` made from v1.10.0, four workflows stayed unknown: `blueprint-update.yml`, `cleanup.yml`, `sbom.yml` and `verify-release.yml` ([#652](https://github.com/Dennis-Otto/repo-blueprint/issues/652)). Each of the 27 others had run, and GitHub knew exactly those, so the first push of `gh repo create --push` had registered none, and each workflow was registered by its first run. The four have only triggers that no push or pull request fires: a schedule, a release, `workflow_call` and a start by hand. `gh workflow run` answered 404 for them, and the schedule of the blueprint bot on 2026-11-05 04:56 UTC started no run either. So the Rollout failed three times in the pager without a reason, and the pager stayed on an old release.

A push that changes the file of a workflow registers it: [dennis-otto-pager#37](https://github.com/Dennis-Otto/dennis-otto-pager/pull/37) added a comment to each of the four, and its merge registered them; [#38](https://github.com/Dennis-Otto/dennis-otto-pager/pull/38) took the comments out again. Whether a first push made after `gh repo create` without `--push` registers every workflow, only a test in a repository made for it can show, which waits for the owner.

## Options

1. Make the first push differently, such as `gh repo create` without `--push` and a `git push` after it. Nothing shows yet that this registers the workflows, and a repository made before still needs a repair.
2. Let `create` push two commits to `main` right after the first one, one that changes the unknown workflows and one that takes the change out, before the settings protect `main`. A repository whose rules are on can't take them, so it needs another repair, and the history of every new repository starts with two commits of noise.
3. A command that opens the repair as pull requests, as in the pager: one commit that GitHub signs, which adds a comment to the end of each workflow that GitHub doesn't know, and after its merge, the one that takes the comments out. `create` runs it when GitHub still doesn't know a workflow a minute after the push; the checklist names what is left; the Rollout names the case.

## Decision

Option 3, `python3 .github/blueprint.py workflows register`.

- **What GitHub doesn't know:** the files of `.github/workflows/` on `main` against the paths of `GET /repos/{repo}/actions/workflows`. One query of GraphQL reads the head of `main` and the text of every workflow, so that both are of the same commit.
- **The first pull request** comes from `bot/register-workflows`, a branch of a bot, so the ownership check gives it no notice, with one commit of `createCommitOnBranch`, which GitHub signs, so that the rule of signed commits lets it merge whatever Git of the person signs. Its sign-off names the author that GitHub gives the commit: the name and the private address of the account, or, when GitHub took another address, the commit once more with the sign-off of that one, before the pull request is opened.
- **The second pull request,** which the command opens when `main` still holds the comment, takes it out again, so that the files are the blueprint's and an update merges them without a conflict. While one of the two is open, the command names it and changes nothing.
- **`create`** asks GitHub up to six times, ten seconds apart, after its push: GitHub registers a workflow as its first run starts, a moment after the push. It names what is left and opens the first pull request before it applies the settings.
- **The checklist** names each workflow of the checkout that GitHub doesn't know, and each comment that is left.
- **The Rollout** fails at once when GitHub answers 404 to the start of a blueprint bot whose file is there, and its summary names the case and the command, rather than ask three times.

## Consequences

- A new repository starts with every workflow that GitHub knows once the first pull request has merged, and an older one gets the same repair from one command.
- A person merges two small pull requests; the comment stays on `main` only until the second merges.
- When the test of option 1 shows a first push that registers every workflow, `create` can push that way; the look, the command, the checklist and the Rollout stay, for the repositories made before.
