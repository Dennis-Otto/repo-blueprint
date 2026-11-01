# The branch bot takes forks into its line, and approves only the runs of a head that it made itself

- Status: accepted
- Date: 2026-11-01

## Context

The branch bot of [0028](0028-bring-one-pull-request-at-a-time-up-to-date.md) left pull requests from forks out of its line. Pull request 541 of homedarts-for-autodarts, from a fork with maintainer edits allowed and auto-merge on, showed what that costs: it stayed behind while others merged, a person brought it up to date by hand each time, and each new head then waited for a person to approve its ten workflow runs, since the repository's policy is `all_external_contributors`. Its checks ran seven times for nothing, and such a pull request keeps losing the race. It also had an unsigned commit, which the rules of `main` refuse, so all of that was spent on a pull request that couldn't merge.

What the API of GitHub shows, read from that pull request:

- A run that GitHub holds is a run with `status: completed`, `conclusion: action_required` and `run_attempt: 1`. A person's approval starts the same run as its second attempt, so `run_attempt` is 2 from then on, and `/attempts/1` still says `action_required`.
- A merge of the release app for an update has the app's account as its author, `web-flow` as its committer, and a verified signature. *Update branch* pressed by a person has the same, with the person as the author.
- `workflow_run` with `completed` doesn't start for a run that GitHub holds: no burst of runs of the bot started when the ten runs of a head landed in `action_required`, only single ones when something else completed later. Other projects start on `requested` for that.
- One comparison of `main` with a head of a fork lists the commits of the pull request with their signatures and parents, its files, and how far it is behind.

Whether the release app may update the branch of a fork is **not settled**. GitHub's documentation of [the update of a pull request branch](https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request-branch) says that a request on behalf of a GitHub App must "also have permissions to write the contents of the head repository". Its page on [changes to a branch from a fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/allowing-changes-to-a-pull-request-branch-created-from-a-fork) grants them to "anyone with push access to the upstream repository" and doesn't mention apps. A [report from 2019](https://github.com/tibdex/autorebase/issues/43) found that an app couldn't push to such a branch, and *Update branch* by Dennis's own account worked. No test here can prove it, and no fork of a repository of the blueprint has given the answer yet.

## Options

1. Leave forks out, as before. A person keeps doing the work of the bot, and each head of a fork falls behind again.
2. Take forks into the line and leave every approval to a person. The bot would stop at each update of a fork, and the fork would lose its place at each merge.
3. Let the bot approve every run of a fork that waits. That removes the control: it would run whatever a contributor pushes.
4. Take forks into the line, and let the bot approve only the runs of a head that it made itself, on top of commits that a person approved.

## Decision

Option 4, which Dennis decided on 2026-11-01. It is safe because **nothing new from the fork runs**: a person approved everything of the contributor already, and the head adds only what is on `main`. Every other approval stays with a person. The bot still checks out only `main` and runs nothing of a pull request.

**The line.** A pull request from a fork takes its place when auto-merge is on and its author allows edits by maintainers; without that, it stays out, and the summary of the run says why. When the rules of `main` require signed commits and a commit of it has no verified signature, it can't merge, so it waits outside the line with that reason and spends no checks. That takes one comparison, which the bot asks for anyway, and the check for unsigned commits of the PR coach explains it to the contributor. A pull request of the repository itself reads none of this, and behaves as before.

**A head that waits.** A head whose runs wait in `action_required` isn't in flight: it leaves its place to the next pull request, like one whose required check failed, and the bot doesn't update it again until someone has approved, or every merge would start its runs anew for nothing. Once its runs run, it counts as in flight again.

**The approval.** The bot approves only when all of this holds, read from the API in each run, so that a run needs no memory:

- The head is a merge of the bot: its author is the bot's account, its committer is `web-flow`, GitHub verified its signature, and its second parent is on `main`. A contributor who names the bot as the author can't get that verified with GitHub as the committer, and a contributor or a person who presses *Update branch* or pushes a merge is the author of it.
- A person approved what is below it. From the head downwards along the first parents, every commit is such a merge, until one that has runs of the event `pull_request` in a second attempt that ran or runs. A commit that is no such merge and never ran is new, and a person approves it. A run that is queued or that was cancelled shows nothing.
- The pull request changes nothing that decides what a workflow runs: nothing in `.github/`, `.githooks/` or `scripts/`, no local action, and none of the files that name commands or what a job installs, such as `Dockerfile`, `Makefile`, `package.json`, `pyproject.toml`, `mkdocs.yml` and the lock files. A renamed file counts by its old name as well. These are a second lock: a person looks at each new version of them.
- Only runs with exactly this `head_sha` and the conclusion `action_required` are approved, and none while a run of another event waits on that head.

Anything unclear means no approval: a list that GitHub cut short, a commit that it doesn't show, any request that fails. The pull request then waits for a person, and the summary says why. The bot approves a head only when it could merge next: one that is behind is brought up to date first, and one that waits for a review, has a failed check or stands behind another in flight isn't approved. Each approval is in the summary of the run, with the pull request and the run.

**The token.** The token of the job holds `actions: write`, to read the runs, approve them and start the next run of the bot, so the release app gets no new right, in line with Dennis's decision that it holds no more than it needs. [Apache Kafka approves such runs with its `GITHUB_TOKEN`](https://github.com/apache/kafka/blob/trunk/.github/workflows/workflow-requested.yml), so GitHub accepts that kind of token. Should it refuse ours, that is a warning, and the pull request waits for a person.

**The next run.** After it updated a fork's branch, the bot starts its own next run with `workflow_dispatch`, which finds the runs of the new head. The events that report such runs cost too much for what they do: `workflow_run` with `requested` adds a skipped run of the bot for each of about 16 workflows at every push of every pull request, and `pull_request_target` with `synchronize` shows a skipped check on every push of a pull request of the repository, which should behave as before.

**A refusal stays what it was.** Since the update of a fork's branch isn't proven, a refusal is what it is for any other pull request: a warning about that pull request, and the bot goes on with the next one.

## Consequences

The first real pull request from a fork after the rollout shows whether GitHub accepts both. The summary of the run of the workflow *Update branches* says *brought up to date* when the update worked, and *approved run …* when the approval did; the annotation *The branch bot couldn't handle #…: GitHub answered 403* names a refusal. If GitHub refuses the update, a person updates such a pull request as before, and nothing else changes, so the sentence in `after-checks.yml` that no bot may push to a fork stays until a run proves it wrong.

A failed check of a fork now starts the bot through `workflow_run`, and turning on auto-merge through `pull_request_target`, which both only make it read the line from the API. A contributor can't start it more often than their checks fail after an approval.

To turn the approvals off, take `actions: write` out of the job in `update-branches.yml`: the read of the runs then fails, so forks wait out of the line with a warning. Taking `BOT_ACCOUNT` away keeps them in the line and leaves every approval to a person.
