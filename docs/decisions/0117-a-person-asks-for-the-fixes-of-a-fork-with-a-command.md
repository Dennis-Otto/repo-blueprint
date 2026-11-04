# A person asks for the fixes of a fork with a command

- Status: accepted
- Date: 2026-11-04

## Context

The fix bot commits what a command fixes onto a branch of the repository and only suggests it on a pull request from a fork ([decision 0023](0023-pull-requests-fix-themselves.md)): no token was known to push onto the branch of a fork, and a bot that pushed there by itself would change the work of a contributor who never asked for it. A contributor takes each suggestion with a click, ten at a time, and a fix that no suggestion shows, such as line endings, stays with the command of the PR coach. A maintainer who wants the fixes in has to do the same clicks, or ask the contributor.

GitHub lets "anyone with push access to the upstream repository" change the branch of a fork whose author allows edits by maintainers, and doesn't say whether that covers a GitHub App. The branch bot tries it since [decision 0099](0099-the-branch-bot-takes-forks-into-its-line-and-approves-only-its-own-heads.md), and no real pull request has shown the answer yet. [#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429) asked for a command `/fix` with a check of the permission of the person who gives it.

## Options

1. Keep the suggestions alone. Nothing new can go wrong, and a maintainer keeps clicking.
2. Let the bot after the checks push onto every fork that allows edits. Nobody asked for that commit, a contributor's next push may conflict with it, and each fix would start the checks of a fork again, which GitHub may hold for a person.
3. A command of a person with write access: the bot commits the fixes of the head onto its branch, also onto that of a fork that allows edits, and falls back to the suggestions where GitHub refuses the commit or the fork allows no edits.

## Decision

Option 3, in the new workflow `commands.yml`, with `fix command` and `fix commit --pull` of `blueprint/fixes.py`.

- **The command:** `/fix` as the first line of a comment on an open pull request, alone, so that a comment that only talks about it starts nothing. The condition of the job lets through only a comment that starts with `/fix` by a person whom GitHub names as the owner, a member or a collaborator, so that no other comment takes a runner. `blueprint.py` of `main` then reads the comment from the API, as it says now, and starts nothing for any other.
- **Who may:** only a person whose permission on the repository GitHub answers as `admin` or `write` at the time of the command, which counts `maintain` as `write` and `triage` as `read`. Anybody else gets that answer and nothing else, and a person whom GitHub doesn't know has the permission `none`.
- **What the bot commits:** what the checks of the head kept as artifacts `fixes-*`, from the workflows of the list of `after-checks.yml` of `main`, as data, with every limit of the bot after the checks: only text files that the commit has already, by plain paths, outside `.git` and the workflows. The bot waits for the checks of the head that keep fixes, also for one that has yet to fail, as a person may give the command while they run; when one still runs after a quarter of an hour, it commits nothing, so that one commit holds every fix, and says to give the command again.
- **What a fork takes:** only the files that the pull request changes, and none that decides what a workflow runs, by the rule of the branch bot: no file of `.github/`, `.githooks/` or `scripts/`, and none of the files that name commands or what a job installs, such as `pyproject.toml` or `package.json`. Whether GitHub holds the runs of a commit of the app on a fork for a person isn't documented, so nothing that the commit changes may run as a new command; the code that it fixes is code that a person reviews in the pull request anyway. What the bot leaves out, the answer lists with the reason, and it stays a suggestion.
- **A refusal is no failure:** when GitHub refuses the commit onto the branch of a fork while that branch is still at the head, the bot suggests the fixes at their lines with the token of the job, as a fork gets them without the command, and the answer quotes GitHub's refusal. A fork that allows no edits gets the suggestions at once, and the answer says how to allow them. A refusal on a branch of the repository fails the job, as it does after the checks. A branch that moved on meanwhile takes no commit: the commit names the head that it expects.
- **The label `no-bot-fixes`** stops the bot's own commits, not one that a person asks for by name.
- **The answer:** a pair of eyes on the comment at once, then one comment of the bot with what it did and why, also when it failed, so that the person who waits for it learns it.
- **The token:** the job checks out `main` alone and runs nothing of the pull request. The token of the job reads the runs and their artifacts and writes the suggestions and the answer; the token of the release app holds only `contents: write` for the commit and `pull-requests: read` for the files of the pull request.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-command-fix.dark.svg">
  <img src="../images/diagrams/the-command-fix.svg" alt="The command /fix: A person comments /fix on a pull request. Only someone with write access starts the bot, and anybody else gets that answer. The bot waits for the checks of the head that keep fixes and takes their fixes as data; while one still runs, it commits nothing and asks for the command again later. A branch of the repository gets the commit. A fork whose author allows no edits by maintainers gets the suggestions at their lines. On a fork that allows them, the bot commits the files that the pull request changes, and none that decides what a workflow runs. When GitHub refuses that commit, the fork gets the suggestions instead. One comment answers each command with what the bot did.">
</picture>

## Consequences

A maintainer gets the fixes of a fork in with one comment, where GitHub lets the app push, and otherwise the same suggestions as before, with a note that says why. The first `/fix` on a real pull request from a fork shows whether GitHub takes the commit: the answer says *The fix bot committed* when it did, and *GitHub refused the commit of the fix bot* with GitHub's words when it didn't. In that case nothing else changes, and the sentence of `after-checks.yml` that no bot may push to a fork stays true for the bot after the checks.

The commit of the bot on a fork is no merge, so the branch bot never approves the runs of its head by itself ([decision 0099](0099-the-branch-bot-takes-forks-into-its-line-and-approves-only-its-own-heads.md)): a person approves them where GitHub holds them. A person with write access can now start a job with the release app by a comment, which only commits fixes that the checks computed and only onto the branch of that pull request. A comment that starts with `/fix` of a member takes a runner for a few seconds even when it is no command.

To turn the command off, delete `.github/workflows/commands.yml` in a repository, or take the release app out of its environment `release`: a fork then gets the suggestions, and a branch of the repository the answer that the app is missing.
