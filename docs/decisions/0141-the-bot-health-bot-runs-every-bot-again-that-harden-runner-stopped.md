# The bot-health bot runs every bot again that Harden-Runner stopped

- Status: accepted, follows up [0134](0134-a-job-stops-when-harden-runner-doesnt-block.md)
- Date: 2026-11-10

## Context

Since [decision 0134](0134-a-job-stops-when-harden-runner-doesnt-block.md), a job that blocks stops when Harden-Runner has no agent that blocks, mostly because GitHub's downloads failed. The job stops with the annotation *Harden-Runner doesn't block*, and a bot then runs it again once: the flaky-test bot for a test, the job *run the checks again that Harden-Runner stopped* of *After the checks* for the other checks of a pull request, the bot for failed releases for the release, and the bot-health bot for a bot of the default branch.

Its consequences left these workflows to their next event or to a person:

- **The bots of events,** *Area labels*, *Welcome* and *Dependabot maintenance*, which start on `pull_request_target`, also for a fork. The bot-health bot leaves every run of a pull request alone, and *After the checks* leaves these bots alone on purpose: neither the fix bot nor the PR coach has anything to do after them. *Welcome* runs only when a pull request opens, so a stopped run's welcome never comes, and a stopped *Area labels* or *Dependabot maintenance* waits for the next push.
- **The workflows that keep an issue of their own,** *Newest Node*, *Newest Python* and *Next runner*. The bot-health bot doesn't watch them, so that a failure of the newest Node, which their issue reports, opens no second one. A stopped job *report* leaves that issue as it was until the next week's run.

Two more workflows have the same gap on `main`. *Diagrams* keeps an issue of its own too, and its jobs *pull-request* and *report* block. *Commands*, the fix bot at `/fix`, starts on `issue_comment`, and when it stops before it answers, the person who gave the command gets no answer at all. The bot-health bot does watch *Mutation*, but as a workflow of one try it gets no second try, even when Harden-Runner stopped only its short job *mutation issue*: the bot opens an issue about a failure that a second try would have fixed.

## Options

1. **The next event or a person,** as decision 0134 left it. *Welcome* never comes, `/fix` stays without an answer, and the issue of *Newest Node* waits a week.
2. ***After the checks*** watches these workflows as well. Its jobs choose their workflows by lists of names: the flaky-test bot takes every watched workflow that its list doesn't name for a test, the PR coach follows every watched run of a pull request, and the fix bot reads the list as the checks that may keep fixes, so each of its jobs would need the new names left out, for bots that are no checks.
3. **The bot-health bot watches them with a job of its own,** *run a bot again that Harden-Runner stopped*, which runs the failed jobs once more only when Harden-Runner stopped one of them at the first attempt, and opens no issue.
4. **The daily look** of the bot-health bot runs the stopped runs of the last day again. That starts no extra run after each event, but the welcome and the answer to `/fix` would come up to a day late, and the look would have to read every failed run of a pull request in the repository.

## Decision

Option 3: the bot that already gives every bot of the default branch its second try gives it to the bots that no other bot runs again too, for the one failure that is none of theirs.

- **The workflows.** *Bot health* follows the end of *Area labels*, *Commands*, *Dependabot maintenance* and *Welcome*, the bots of events in `EVENT_BOTS` of `blueprint/bot_health.py`, and of *Diagrams*, *Newest Node*, *Newest Python* and, in the blueprint, *Next runner*, those with an issue of their own in `OWN_ISSUE`. Its job *look at the end of a bot's run* leaves them out by name.
- **The job.** *run a bot again that Harden-Runner stopped* starts at the end of their first attempt when it failed, also for a pull request, and for one of a fork, where the run of `pull_request_target` runs the workflow of the base again and nothing of the fork. `blueprint.py bot-health stopped RUN` asks GitHub for the failed jobs of that attempt and their annotations. When the annotation of the step *Make sure that Harden-Runner blocks* is on one of them, it runs the failed jobs once more; otherwise the run stays failed, and the pull request, the answer to the command or the workflow's own issue shows why. It opens no issue. When another bot was quicker, it leaves the run to that bot. When GitHub refuses the second try, it fails, as a refused write does ([decision 0036](0036-a-request-to-github-tries-once-more-and-a-refused-write-fails.md)), and when GitHub keeps failing, it ends with a notice ([decision 0136](0136-an-outage-of-github-starts-no-bot-failure.md)). It may run jobs again and read their annotations, nothing else, and it blocks every host but GitHub's, as decision 0134 asks of it.
- **A workflow of one try,** such as *Mutation*, gets its second try when Harden-Runner stopped each of its jobs that failed: then the second try repeats nothing of its failure. If any other job failed, it gets none, as before, since that try would only measure the same again.
- **Tests keep it so:** a test fails when the words that the bot looks for are missing from the step that stops a job, or from the step of *After the checks* that looks for the same words; when the job leaves out a bot of events or a workflow with an issue of its own, in the blueprint or in any kind of project; and when the job *look at the end of a bot's run* takes one of them. The tests of the bot run every bot of events and every workflow with an issue of its own after a stop, for a pull request, a fork, a comment, a push and a schedule. They also cover a failure that isn't Harden-Runner's, a later attempt, another bot that was quicker, a refusal, and a workflow of one try with and without another failure.

## Consequences

A stop by Harden-Runner fixes itself in every workflow that the blueprint brings: the welcome of a new pull request still comes, `/fix` still answers, and the issue of the newest Node is current again. A run that stops at its second attempt as well stays failed, and its annotation tells a person to run it again once the outage is over.

Every run of these bots now starts a run of *Bot health*, as every check of a pull request starts one of *After the checks*. Unless the bot failed at its first attempt, its jobs skip and take no runner, so they cost no minutes in a private repository either, but the list of runs of *Bot health* shows them. *Commands* starts on every comment, also one without a command.

*Update branches* is left as it was. The bot-health bot runs it again on `main`. Its runs for a pull request, when auto-merge is turned on or off, get no second try, because the next push to `main`, the next check that ends, or its schedule every six hours runs the branch bot again.

The workflows that a project adds itself stay as decision 0134 left them, since the list of *Bot health* belongs to the blueprint: a check that the answer `test_workflows` names gets its second try from the flaky-test bot, and any other one from its next event or a person.
