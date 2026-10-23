# release-please reads the title of each merged pull request, and its header survives its own parser

- Status: accepted
- Date: 2026-10-23

## Context

A squash merge makes the description of a pull request the body of its commit (`squash_merge_commit_message = "PR_BODY"`), so that a line `Release-As:` or `BREAKING CHANGE:` of the description reaches release-please. release-please parses the whole message with a strict parser of Conventional Commits, which takes a line such as `**[(Full` or `print("a" % (b, c))` for the start of a footer and gives up on the commit, title included, with no more than `commit could not be parsed` in the log of a run that passes. Renovate quotes the release notes and advisories of an update in its description, so its updates were left out of releases: `fix(deps): update dependency anchore/syft to v1.54.1 (#326)` opened no release pull request, `fix(deps): update dependency pillow to v13 [security] (#383)` is in no notes of the blueprint, and issue-assistant v1.4.0 missed its security fix the same way ([issue 353](https://github.com/Dennis-Otto/repo-blueprint/issues/353)).

release-please also rebuilt its pull request in every run, on the same commit too, which started all its checks again, about 35 jobs in homedarts-for-autodarts: it leaves the pull request alone only when the description that it builds equals the one that it reads back, and it reads the header back trimmed, while ours ended with a line end ([issue 257](https://github.com/Dennis-Otto/repo-blueprint/issues/257)).

## Options

1. Squash with the title alone (`BLANK`): the lines `Release-As:` and `BREAKING CHANGE:` of a description would no longer reach release-please, and the report of a pull request promises them.
2. Merge the updates of the bots with a commit body of their own: Renovate's platform auto-merge takes no body, and a person's description can break the parser too.
3. Fail the release job on `commit could not be parsed`: the log of the action is no output that a later step can read, and a failure fixes nothing.
4. Before release-please runs, write an override into each merged pull request since the last release that can change the release: release-please reads the text between `BEGIN_COMMIT_OVERRIDE` and `END_COMMIT_OVERRIDE` in the description of the pull request of a commit instead of the message.

## Decision

Option 4. `blueprint.py commit-overrides`, a step of the release bot right before release-please, reads the commits since the latest release, and for each `feat`, `fix`, `perf` or `revert`, each `!` and each message with a line `Release-As:` or `BREAKING CHANGE:` writes its title and those lines, each a line of its own, at the end of the description of its pull request, in an HTML comment that the page doesn't show. A message that is no more than that, and a description with an override of its own, stay as they are. The token of the job makes the edit, which starts no workflow.

The header of the release pull request ends with an HTML comment instead of a line end: a trim keeps it as it is, and the `---` below it stays a rule, not the underline of a heading.

## Consequences

- Every change for users reaches the next release and its notes, whatever its description holds, and a paragraph of a description that looks like a Conventional Commit counts no longer as a change of its own.
- The release pull request changes only when its notes change, so its checks run once for each change of `main`.
- The descriptions of merged pull requests get an override at their end; editing it changes what the next release reads of that pull request.
- A fix that was merged before a release and left out of it stays out: an override counts only for a release that is still to come.
