# Decisions

The decisions that shape the blueprint, each with its reasons, so that a later change can see why things are as they are. A decision that changes an earlier one gets a new record, and the earlier one says which record replaces it.

Copy [the template](0000-template.md) to the next free number and describe the decision in the pull request that makes it.

| Record | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-decisions.md) | Record the decisions that shape the project | accepted |
| [0002](0002-copier-and-an-update-bot.md) | Generate the repositories with Copier and keep them current with a bot | accepted |
| [0003](0003-curated-changelog.md) | Write the changelog in the pull requests, and let the release bot assemble it | accepted |
| [0004](0004-settings-as-code.md) | Keep the settings of every repository as code, applied by a bot | accepted |
| [0005](0005-renovate-instead-of-dependabot.md) | Keep the dependencies current with a self-hosted Renovate | accepted |
| [0006](0006-beta-channel.md) | Publish a beta of the next release after every change for users, where a project wants it | accepted |
| [0007](0007-one-update-pull-request.md) | Keep one update pull request, move it on with each release, and leave a maintainer's commits alone | accepted |
| [0008](0008-no-action-pinned-to-a-branch.md) | Pin no action to a branch: run a tool that follows its branch as an image | accepted |
| [0009](0009-run-a-check-only-where-it-can-change-a-result.md) | Run a check only where it can change a result | accepted |
| [0010](0010-roll-out-one-repository-at-a-time.md) | Roll out each release one repository at a time, and report every repository that misses it | accepted |
| [0012](0012-lock-refresh-waits-for-the-maintainer.md) | Refresh every lock file once a week, and let the refresh wait for the maintainer | accepted |
| [0013](0013-name-the-runner-and-try-the-next-one.md) | Name the runner with its version, and try the next one every week before the jobs move | accepted |
| [0014](0014-a-failing-bot-keeps-one-issue-open.md) | A bot that fails keeps one issue open until it passes again | accepted |
