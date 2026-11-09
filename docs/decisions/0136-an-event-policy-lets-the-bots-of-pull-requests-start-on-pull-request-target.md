# An event policy lets the bots of pull requests start on pull_request_target

- Status: accepted
- Date: 2026-11-09

## Context

From 2 December 2026, GitHub blocks `pull_request_target` in every public repository, unless an applicable Actions event policy allows it ([changelog of 2 November 2026](https://github.blog/changelog/2026-11-02-pull_request_target-blocked-by-default-december-2), [Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)). Private and internal repositories aren't affected. Before that, GitHub enforces the block in two brownouts, on 9 and 16 November 2026 from 16:00 to 18:00 UTC. In the first one, every workflow of the blueprint's public repositories that starts on the event failed to start, and each failure mailed the owner: *Pull request title*, *Area labels*, *Welcome*, *Dependabot maintenance* and *Update branches*. The required check *conventional title* comes from *Pull request title*, so after 2 December no pull request could merge in any repository of the blueprint.

Six workflows of the blueprint, which every repository renders, start on the event. Each runs the workflow of `main`, and none checks out or runs anything of the pull request (`CONTRIBUTING.md` asks for it, and the tests of `tests/test_template.py` keep it so):

- `pull-request-title.yml`: the required check *conventional title* sets the label of the type and reads the fragments of the changelog, and the job *signed commits* cancels the runs of replaced commits ([decision 0108](0108-the-runs-of-a-replaced-commit-give-their-runner-back.md)): a token that writes, on every push and every edit of the title, also of a fork whose other runs wait for the approval of a maintainer ([decision 0098](0098-unsigned-commits-get-a-check-of-their-own-outside-the-required-checks.md)).
- `area-labels.yml`: the labels of the areas, also of a fork's pull request: a token that writes.
- `welcome.yml`: the comment on a person's first pull request, before the maintainer approves its runs.
- `update-branches.yml`: only when auto-merge is turned on or off, as the release app, whose key the environment `release` holds for `main` alone.
- `dependabot-automerge.yml`: auto-merge as the release app, from the environment `release`; a run of Dependabot on `pull_request` gets none of the secrets of Actions or of an environment.
- `issue-lifecycle.yml`: when a pull request is closed, the sweep labels the issues that it fixes: a token that writes. The blueprint takes the workflow from a release of the issue assistant.

An event policy has a name, an enforcement (`active`, `disabled`, or `evaluate`, which only GitHub Enterprise offers), a condition `workflow_path` with the paths that it `include`s and `exclude`s, and rules; a rule `restrict_action_events` names the events that may start the targeted workflows, an allowlist, as GitHub's guide says ([Governing execution of GitHub Actions workflows](https://docs.github.com/en/actions/how-tos/administer/control-workflow-execution), [REST API](https://docs.github.com/en/rest/actions/policies)). GitHub's own API answers a repository of a user: the list of the policies of the public repositories of the blueprint's owner was empty on 9 November 2026, and a private repository on GitHub Free, a throwaway one made for the test and archived after it, got `403` *Upgrade to GitHub Pro or make this repository public to enable this feature*.

## Options

1. **Every workflow on `pull_request`,** as GitHub recommends where a workflow needs neither a secret nor a token that writes. For a fork, each of the six would lose what it is for: the label, the welcome before the approval, the cancellation of replaced runs, the release app of the branch bot and of Dependabot's auto-merge.
2. **`pull_request` and a `workflow_run` for the part that writes.** It doubles the runs of every push for the title and the labels, moves the required check into two runs, and for a fork the part that writes would wait for the approval as well, so the welcome and the labels would come late. It is clean for none of the six.
3. **One policy that allows `pull_request_target` for every workflow.** Simple, but a new workflow on the event would run without anyone deciding it, which is what GitHub's block is for.
4. **A policy as code for exactly the workflows that need the event,** which the settings bot keeps in every repository, as it keeps the rulesets.
5. **The policy by hand in each repository:** no check of drift, and every new repository would need it.

## Decision

Option 4, after the mix that the maintainer chose on 9 November 2026: a workflow that needs neither a token that writes nor a secret for a pull request of a fork moves to `pull_request`, and the others are allowed by a policy as code. None of the six of the blueprint can move today, for the reasons above. The issue lifecycle can start on the push to `main` instead, which every merge is, as its sweep reads the merged pull requests whatever event starts it; the blueprint takes that workflow from the issue assistant's release, so the move belongs to the issue assistant, and the policy leaves the workflow out by itself once it no longer starts on the event.

- **The list.** `pull_request_target` of `[actions]` in `.github/repository.toml` lists the workflows that may start on the event, each with its reason; a project adds one of its own in `.github/repository.project.toml`.
- **The policy.** The settings make *Allow pull_request_target* from it: `active`, with `workflow_path` including the listed workflows that start on the event and excluding none, and one rule `restrict_action_events` with every event that starts one of them, since the rule allows only the events that it names: the push, schedule, release, `workflow_run` and `workflow_dispatch` of the branch bot and of the issue lifecycle too. `blueprint.py` reads the events from the key `on` of each workflow with the standard library alone, and a test compares what it reads with PyYAML for every workflow of every kind.
- **Drift.** `settings check` names every difference of the policy and every workflow that starts on the event but that the list lacks; `settings apply` creates, changes or deletes the policy of that name and never touches another, and the settings bot runs after every change of a workflow, so a new event of a listed workflow reaches the policy with its merge. A workflow that the list lacks stays out until a person lists it: whether a workflow may start on the event is a decision of trust.
- **The check *lint*.** `settings actions` fails for such a workflow at the line of its event, from the files alone, so that a pull request that adds one hears of it before the merge; the explanation of the check *allowed-actions* says what to do.
- **Private repositories.** GitHub offers no policies to a private repository on GitHub Free and blocks nothing there: the run names it as a notice, which fails nothing.
- **Permission.** GitHub names no permission of a GitHub App for the policies; the settings bot names *Administration*, with which it writes the rest of the settings of Actions, when GitHub refuses to read or write one. A refused read fails the run as a difference of the policy alone, and the other parts of the settings are applied all the same.

## Consequences

Once the release with this change has reached a repository and its settings bot has run, the six workflows keep starting after 2 December 2026, and no other workflow may start on the event. For a pull request of a fork nothing changes: the title check, its labels and the welcome come at once, the other checks after the approval of a maintainer, and the fix bot after the checks suggests its fixes as before. The brownout of 16 November 2026 shows whether GitHub reads the policy as its documentation describes, before the block stays.

A repository whose settings bot can't write the policy fails its run of the settings, with the part and the permission; its owner runs `python3 .github/blueprint.py settings apply`. The way back is an empty list, which deletes the policy, after which GitHub blocks the event as its default does.

The issue assistant moves `issue-lifecycle.yml` of its templates to the push to `main`; with its next release, the sync bot brings that here, and its workflow leaves the policy. None of the repositories made from the blueprint has a workflow of its own on the event, and neither have `repo-pager-control` nor `repo-pager-control-template`, which aren't made from it.
