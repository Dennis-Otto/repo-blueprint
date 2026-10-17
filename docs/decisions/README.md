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
| [0011](0011-downloads-try-again-and-checks-cache-their-tools.md) | Every download tries again, the checks cache what they download, and the CI skips no check for an unreachable server | accepted |
| [0012](0012-lock-refresh-waits-for-the-maintainer.md) | Refresh every lock file once a week, and let the refresh wait for the maintainer | accepted |
| [0013](0013-name-the-runner-and-try-the-next-one.md) | Name the runner with its version, and try the next one every week before the jobs move | accepted |
| [0014](0014-recover-from-a-stalled-check-without-a-person.md) | Recover from a stalled check without a person, once | accepted |
| [0015](0015-tell-coding-agents-the-rules-in-agents-md.md) | Tell coding agents the rules in AGENTS.md, with the files of a project kept equal to copier.yml | accepted |
| [0016](0016-diagrams-as-pictures-of-their-sources.md) | Show every diagram as a picture drawn from its Mermaid source, because the GitHub app draws no Mermaid | accepted |
| [0017](0017-cache-what-a-check-can-verify-never-a-finding.md) | Cache what a check can verify, never a finding: downloads by their lock files, php-cs-fixer by content, Psalm without a cache | accepted |
| [0018](0018-changelog-fragments.md) | Each pull request writes its entry of the changelog into a file of its own | accepted |
| [0019](0019-a-failing-bot-keeps-one-issue-open.md) | A bot that fails keeps one issue open until it passes again | accepted |
| [0020](0020-update-only-to-a-verified-release.md) | Update only to a release that the release workflow made, and let only the release app create release tags | accepted |
| [0021](0021-install-with-uv-and-bound-every-step.md) | Install the tools with uv, start mypy from its cache, and end every step that installs, builds or downloads after five minutes | accepted |
| [0022](0022-every-check-explains-its-failure.md) | Every check explains its failure, in the check and in one comment, also on a pull request from a fork | accepted |
| [0023](0023-pull-requests-fix-themselves.md) | Pull requests fix what a command can fix by themselves: the check fixes, the fix bot commits, suggests or opens a pull request for main | accepted |
| [0024](0024-take-over-each-verified-release-of-the-issue-assistant.md) | Take over each verified release of the issue assistant with a bot of the blueprint, not with Renovate | accepted |
| [0025](0025-run-the-tests-on-every-core.md) | Run the tests of Python projects on every core, with the same coverage gate | accepted |
| [0026](0026-build-the-website-once-and-keep-its-downloads-a-week.md) | Build the website once, in the job of the check, and keep the downloads of Material for a week | accepted |
| [0027](0027-few-jobs-that-each-run-several-checks.md) | Few jobs that each run several checks, so that a pull request waits for fewer runners, in two releases | accepted |
| [0029](0029-a-dependency-dashboard-the-whole-monday-and-pins-with-their-checksum.md) | A dependency dashboard, the whole Monday, fix(deps) for what the users run, and pinned downloads that move with their checksum | accepted |
