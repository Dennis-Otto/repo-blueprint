# Decisions

The decisions that shape the blueprint, each with its reasons, so that a later change can see why things are as they are. A decision that changes an earlier one gets a new record, and the earlier one says which record replaces it.

Copy [the template](0000-template.md) to the next free number and describe the decision in the pull request that makes it.

| Record | Decision | Status |
| --- | --- | --- |
| [0001](0001-record-decisions.md) | Record the decisions that shape the project | accepted |
| [0002](0002-copier-and-an-update-bot.md) | Generate the repositories with Copier and keep them current with a bot | accepted, amended by [0052](0052-roll-out-every-release-at-once.md) |
| [0003](0003-curated-changelog.md) | Write the changelog in the pull requests, and let the release bot assemble it | accepted |
| [0004](0004-settings-as-code.md) | Keep the settings of every repository as code, applied by a bot | accepted |
| [0005](0005-renovate-instead-of-dependabot.md) | Keep the dependencies current with a self-hosted Renovate | accepted |
| [0006](0006-beta-channel.md) | Publish a beta of the next release after every change for users, where a project wants it | accepted |
| [0007](0007-one-update-pull-request.md) | Keep one update pull request, move it on with each release, and leave a maintainer's commits alone | accepted |
| [0008](0008-no-action-pinned-to-a-branch.md) | Pin no action to a branch: run a tool that follows its branch as an image | accepted |
| [0009](0009-run-a-check-only-where-it-can-change-a-result.md) | Run a check only where it can change a result | accepted, amended by [0073](0073-zizmor-analyzes-every-pull-request-and-each-new-alert-stops-the-merge.md) |
| [0010](0010-roll-out-one-repository-at-a-time.md) | Roll out each release one repository at a time, and report every repository that misses it | accepted |
| [0011](0011-downloads-try-again-and-checks-cache-their-tools.md) | Every download tries again, the checks cache what they download, and the CI skips no check for an unreachable server | accepted |
| [0012](0012-lock-refresh-waits-for-the-maintainer.md) | Refresh every lock file once a week, and let the refresh wait for the maintainer | accepted |
| [0013](0013-name-the-runner-and-try-the-next-one.md) | Name the runner with its version, and try the next one every week before the jobs move | accepted |
| [0014](0014-recover-from-a-stalled-check-without-a-person.md) | Recover from a stalled check without a person, once | accepted |
| [0015](0015-tell-coding-agents-the-rules-in-agents-md.md) | Tell coding agents the rules in AGENTS.md, with the files of a project kept equal to copier.yml | accepted |
| [0016](0016-diagrams-as-pictures-of-their-sources.md) | Show every diagram as a picture drawn from its Mermaid source, because the GitHub app draws no Mermaid | accepted, the website part replaced by [0058](0058-every-website-shows-the-pictures-of-its-diagrams.md) |
| [0017](0017-cache-what-a-check-can-verify-never-a-finding.md) | Cache what a check can verify, never a finding: downloads by their lock files, php-cs-fixer by content, Psalm without a cache | accepted |
| [0018](0018-changelog-fragments.md) | Each pull request writes its entry of the changelog into a file of its own | accepted, amended by [0068](0068-the-website-shows-the-fragments-and-the-fix-bot-heals-their-headings.md) |
| [0019](0019-a-failing-bot-keeps-one-issue-open.md) | A bot that fails keeps one issue open until it passes again | accepted |
| [0020](0020-update-only-to-a-verified-release.md) | Update only to a release that the release workflow made, and let only the release app create release tags | accepted |
| [0021](0021-install-with-uv-and-bound-every-step.md) | Install the tools with uv, start mypy from its cache, and end every step that installs, builds or downloads after five minutes | accepted |
| [0022](0022-every-check-explains-its-failure.md) | Every check explains its failure, in the check and in one comment, also on a pull request from a fork | accepted |
| [0023](0023-pull-requests-fix-themselves.md) | Pull requests fix what a command can fix by themselves: the check fixes, the fix bot commits, suggests or opens a pull request for main | accepted |
| [0024](0024-take-over-each-verified-release-of-the-issue-assistant.md) | Take over each verified release of the issue assistant with a bot of the blueprint, not with Renovate | accepted |
| [0025](0025-run-the-tests-on-every-core.md) | Run the tests of Python projects on every core, with the same coverage gate | accepted, amended by [0070](0070-the-tests-run-on-every-logical-core-at-most-eight.md) |
| [0026](0026-build-the-website-once-and-keep-its-downloads-a-week.md) | Build the website once, in the job of the check, and keep the downloads of Material for a week | accepted |
| [0027](0027-few-jobs-that-each-run-several-checks.md) | Few jobs that each run several checks, so that a pull request waits for fewer runners, in two releases | accepted |
| [0028](0028-bring-one-pull-request-at-a-time-up-to-date.md) | Bring one pull request at a time up to date, in the order of its auto-merge | accepted |
| [0029](0029-a-dependency-dashboard-the-whole-monday-and-pins-with-their-checksum.md) | A dependency dashboard, the whole Monday, fix(deps) for what the users run, and pinned downloads that move with their checksum | accepted, amended by [0057](0057-renovate-keeps-no-dependency-dashboard.md) |
| [0030](0030-one-report-on-each-pull-request.md) | One report on each pull request, which says what it makes | accepted, amended by [0066](0066-the-workflows-of-a-project-add-their-parts-to-the-one-report.md) |
| [0031](0031-mutation-tests-in-parts-with-the-logic-first-and-an-issue-on-a-drop.md) | The mutation tests run in parts, list the survivors that change the logic first and open an issue when the score drops | accepted |
| [0032](0032-the-taint-analysis-knows-nextcloud-and-proves-that-it-still-sees.md) | The taint analysis of a Nextcloud app knows Nextcloud, and proves in every run that it still sees | accepted |
| [0033](0033-schedules-are-only-a-safety-net.md) | Bots start from events, and their schedules are only a safety net | accepted |
| [0034](0034-the-sboms-of-a-release-describe-what-it-ships.md) | The SBOMs of a release describe what it ships, by its name and version | accepted |
| [0035](0035-the-tools-of-a-nextcloud-app-run-on-a-newer-php-than-its-code.md) | The tools of a Nextcloud app run on a newer PHP than its code, which is checked on the oldest | accepted |
| [0036](0036-a-request-to-github-tries-once-more-and-a-refused-write-fails.md) | A request to GitHub tries once more, and a write that GitHub refused fails | accepted |
| [0037](0037-pictures-renew-themselves-by-their-pixels.md) | Pictures renew themselves by their pixels, through one pull request of a bot | accepted, amended by [0067](0067-every-kind-photographs-itself-in-docker-with-the-playwright-of-the-browser.md) |
| [0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md) | New alerts of code scanning and unlisted actions stop a pull request, and secret scanning looks for generic secrets | accepted, amended by [0055](0055-what-github-does-not-do-for-a-repository-fails-no-settings-run.md), [0064](0064-an-image-of-docker-runs-with-docker-run.md) and [0073](0073-zizmor-analyzes-every-pull-request-and-each-new-alert-stops-the-merge.md) |
| [0039](0039-try-every-change-on-the-repositories-that-take-the-blueprint.md) | Try every change of the template on the answers and the files of the repositories that take the blueprint, before its release | accepted |
| [0040](0040-every-step-of-a-bot-that-changes-github-runs-in-a-test.md) | Every step of a bot that changes something on GitHub runs in a test | accepted |
| [0041](0041-every-website-is-accessible-and-quick-and-a-check-proves-it.md) | Every website is accessible and quick on a phone, and a check proves it | accepted |
| [0042](0042-each-language-of-a-website-searches-and-describes-itself.md) | Each language of a website searches and describes itself | accepted |
| [0043](0043-a-node-package-lints-with-biome-and-installs-without-scripts.md) | A Node package lints and formats with Biome, reports its coverage as LCOV and installs without the scripts of its packages | accepted |
| [0044](0044-the-built-website-is-checked-and-every-deployment-is-signed.md) | The built website is checked, and every deployment is signed and asked for its pages | accepted |
| [0045](0045-every-website-shows-its-automation-written-from-its-workflows.md) | Every website shows its automation, written from its workflows at every build | accepted |
| [0046](0046-a-website-leads-to-its-owner-and-asks-github-for-nothing.md) | A website leads to its owner and asks GitHub for nothing: the links of the footer and the version of the latest release come from the build | accepted |
| [0047](0047-every-repository-proposes-the-best-practices-answers-that-the-blueprint-guarantees.md) | Every repository proposes the answers of OpenSSF Best Practices that the blueprint guarantees | accepted |
| [0048](0048-the-dashboard-publishes-its-data-at-addresses-that-stay.md) | The dashboard publishes its data as JSON and a feed of the releases, at addresses that stay | accepted |
| [0049](0049-every-owner-brings-their-own-release-app.md) | Every owner brings their own release app, and only the blueprint's owner gets its defaults | accepted |
| [0050](0050-a-new-copy-becomes-its-repository-with-one-command.md) | A new copy becomes its repository on GitHub with one command that it brings, `blueprint.py create`, always on `main` | accepted |
| [0051](0051-every-owner-chooses-who-runs-renovate-and-whether-an-ai-reads-the-issues.md) | Every owner chooses who runs Renovate, and whether an AI reads the issues | accepted, amended by [0057](0057-renovate-keeps-no-dependency-dashboard.md) |
| [0052](0052-roll-out-every-release-at-once.md) | Bring every release to every repository right after it is verified, and keep the weekly run as a safety net | accepted |
| [0053](0053-answers-render-valid-files-and-every-repository-links-its-website.md) | The answers render valid files, and every new repository links its website and has the topics of its kind | accepted |
| [0054](0054-the-reference-is-written-from-its-sources-and-committed.md) | The reference of the questions, variables and secrets is written from its sources and committed | accepted |
| [0055](0055-what-github-does-not-do-for-a-repository-fails-no-settings-run.md) | What GitHub doesn't do for a repository, such as a switch of security that its plan lacks, fails no run of the settings | accepted |
| [0056](0056-every-function-stays-small-enough-for-the-copies-of-mutmut.md) | Every function stays small enough for the copies of mutmut: the parser of `blueprint.py` adds each group of commands in a function of its own | accepted |
| [0057](0057-renovate-keeps-no-dependency-dashboard.md) | Renovate keeps no dependency dashboard, so that a repository can have no open issue | accepted |
| [0058](0058-every-website-shows-the-pictures-of-its-diagrams.md) | Every website shows the pictures of its diagrams, so that a page with a diagram stays within 1.2 MB | accepted |
| [0059](0059-accept-a-pinned-version-and-tell-renovate.md) | A version that another package pins is accepted with every advisory in `osv-scanner.toml`, and Renovate is told by a rule that `blueprint.py` writes | accepted |
| [0060](0060-release-please-reads-the-title-of-each-merged-pull-request.md) | release-please reads the title of each merged pull request, and the header of the release pull request survives its own parser | accepted |
| [0061](0061-a-download-that-hangs-ends-and-starts-again.md) | A download that hangs ends within its step and starts again: a time limit for every download of the website, a second setup of uv in the Variants, and a container that starts again when the pull of its image failed | accepted |
| [0062](0062-the-website-shows-the-pictures-of-its-repository-from-the-checkout.md) | The website shows the pictures that a page shows from `main` of its own repository from the checkout, so that a pull request shows a new screenshot on its website too | accepted |
| [0063](0063-every-bot-checks-for-the-release-app-before-its-token.md) | Every bot checks for the release app before its token, and fails without it only when its work is the app's; one that helps a pull request along warns | accepted |
| [0064](0064-an-image-of-docker-runs-with-docker-run.md) | An image of Docker runs with `docker run`, and `settings check` names every step that runs one with `docker://`, which GitHub refuses unless every action may run | accepted |
| [0065](0065-the-release-verification-checks-the-zip-that-hacs-installs.md) | The release verification checks the zip that HACS installs, and the zip of a beta has the version of the beta in its `manifest.json` | accepted |
| [0066](0066-the-workflows-of-a-project-add-their-parts-to-the-one-report.md) | The workflows of a project add their parts to the one report of the PR coach: an artifact `pr-report-<name>` with `report.md` for the head, which `[report.<name>]` of the catalog names and the coach shows only as code | accepted |
| [0067](0067-every-kind-photographs-itself-in-docker-with-the-playwright-of-the-browser.md) | Every kind photographs itself in Docker, with the Playwright of the browser's image: the website, the integration in Home Assistant or the app in Nextcloud in both themes, at a clock that stands still, and the pages of GitHub in the blueprint's documentation | accepted |
| [0068](0068-the-website-shows-the-fragments-and-the-fix-bot-heals-their-headings.md) | The website shows the fragments of the changelog under Unreleased, grouped as the release groups them, and the fix bot renames a heading of a fragment that surely means a kind of change, such as `### Fixes` to `### Fixed` | accepted |
| [0069](0069-a-lock-file-and-a-version-fix-themselves-only-where-their-tool-refuses-them.md) | A lock file and a version fix themselves only where their tool refuses them: Composer and npm lock again with the least change, `fix version` writes the version of the release bot back, and REUSE stays for a person | accepted |
| [0070](0070-the-tests-run-on-every-logical-core-at-most-eight.md) | The tests run on every logical core, at most eight, and the tests of the blueprint compile each template once | accepted |
| [0071](0071-every-tool-of-the-checks-shows-its-findings-at-their-lines.md) | Every tool of `scripts/check.sh` shows its findings at their lines, through `blueprint.py annotate` where the tool writes no annotations of its own; a taint analysis fails the CI on every path, and the step *Explanations of the checks* fails on a check without its explanation | accepted |
| [0072](0072-the-issue-of-flaky-tests-counts-in-its-body-and-a-marker-names-other-tests.md) | The issue of flaky tests counts how often each job and test flaked in its body, and the answer `test_marker` names the test of a log that pytest didn't write | accepted |
| [0073](0073-zizmor-analyzes-every-pull-request-and-each-new-alert-stops-the-merge.md) | zizmor analyzes every pull request, the release pull request too, and each new alert of it stops the merge, as the Findings workflow would fail `main` on it | accepted |
| [0074](0074-every-pull-request-follows-the-actions-that-its-workflows-run-in-turn.md) | Every pull request follows the actions that its workflows run, also in turn, and fails while `[actions.selected]` lacks one, through a few queries of GraphQL; the Variants check every kind of project | accepted |
