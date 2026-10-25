# Fix bot and self-healing

What a repository fixes by itself: the findings that a command can fix, tests that fail once, checks that stop, releases and bots that fail.

## Fix bot

A check that fails fixes what a command can fix, such as the format of the code, trailing whitespace and line endings, the rules of markdownlint and the pages in one column: the bot commits the fixes onto a branch of the repository, also one of Renovate, as one commit, suggests them at their lines on a pull request from a fork, and keeps one pull request with the fixes of `main` that merges itself; `python3 .github/blueprint.py fix run` makes the same fixes on your machine.

**How:** `autofix` in `.github/checks.toml`, `after-checks.yml`.

## Pull requests fix themselves

Fix first, explain second: what a command can fix of a check that failed, the pull request fixes by itself, also a pull request of Renovate, and `main` too.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/pull-requests-fix-themselves.dark.svg">
  <img src="../images/diagrams/pull-requests-fix-themselves.svg" alt="Pull requests fix themselves: A check fails. Where a command fixes what it found, such as the format of the code, the whitespace of a text file or the rules of markdownlint, the job of the check runs the commands of autofix from .github/checks.toml and keeps the files that they changed. After the checks, the fix bot takes these files as data, only text files that the commit has: on a pull request from a branch of the repository, also one of Renovate, it commits them as one commit onto the branch, and the checks run again; on a pull request from a fork, it suggests them at their lines; on main, it keeps one pull request from bot/self-heal that merges itself. What no command fixes, the PR coach explains.">
</picture>

- **The check fixes:** each explanation of `.github/checks.toml` says in `autofix` which commands fix what its check finds, or why no command can; a test of the blueprint fails for one that doesn't say. When a check fails, its job runs those commands on the head of the pull request, with the tools that it installed already: the text files, the pages in one column, the version of the release bot, Ruff, php-cs-fixer or Biome, and a lock file of Composer or npm that its tool refuses, locked again with the least change, for `scripts/check.sh`, markdownlint for the Markdown. It keeps the files that they changed as an artifact.
- **One commit on a branch of the repository:** once the checks of the commit that fix have ended, the fix bot commits all their fixes as one commit onto the branch, as the release app, with its sign-off, and the checks run again; the comment of the PR coach names the files. This works on the branches of Renovate and the other bots as well, so that an update of a formatter stays green and merges itself.
- **Suggestions on a fork:** no bot pushes to a fork, so the bot suggests the fixes at their lines of the pull request, ten at most in one review and none twice; **Commit suggestion** takes one. A fix that no suggestion shows, such as line endings, names its file, and the PR coach the command.
- **main heals itself:** when a check of `main` fails with fixes, one pull request from `bot/self-heal` holds them and merges itself once every check passes; the bot closes it once `main` needs none, and a failure of the bot keeps one issue open.
- **Safe with any pull request:** the bot runs nothing of a pull request with a token that can write. It takes the fixes as data, with `blueprint.py` of `main`, and lets through only text files that the commit has already, by plain paths, outside `.git` and the workflows. It commits at most twice in a row (once more for a check that ends later), never a third time, and a pull request with the label `no-bot-fixes` gets no commit.
- **On your machine:** `python3 .github/blueprint.py fix run` runs the commands of every step of `scripts/check.sh`, `python3 .github/blueprint.py fix text` fixes the text files alone, and `python3 .github/blueprint.py fix version` writes the version of the release bot back where a hand changed it.

## Flaky tests

A test run that fails, or whose job runs out of time, runs its failed jobs once more, unless the same jobs broke for the commit before; a job that passes then is reported as flaky in one issue, with the step, the test and the error that failed, and the issue counts how often each job and test flaked.

**How:** `after-checks.yml`.

## Cancelled checks

The quick checks run once for each commit, so that no run for another commit cancels them; a run of a longer required check for the latest commit of a pull request that a late run for an older commit cancelled starts again by itself instead of blocking the merge; a newer push to `main` cancels the tests and scanners of the push before, and their run for the head of `main` starts again as well when a late run cancelled it.

**How:** `after-checks.yml`.

## Failed releases

The release of a merge that fails, as at a push of its tag that GitHub refuses for a moment, runs its failed jobs once more by itself, where they stopped.

**How:** `after-checks.yml`.

## When a check fails or stops

A check that a runner, a site or GitHub fails for a moment, or that a race of two runs cancels, needs no person: the bots after the checks run it once more, and leave red only what fails for a reason.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/when-a-check-fails-or-stops.dark.svg">
  <img src="../images/diagrams/when-a-check-fails-or-stops.svg" alt="When a check fails or stops: When a run of the checks or of the release ends, the bots after the checks look at how. Tests that failed or ran out of time at first run their failed jobs once more, unless the same jobs broke for the commit before; a job that passes then goes into the issue of flaky tests with its step, its test and its error, and one that fails again stays red. A required check that a late run for an older commit cancelled starts again. The release of a merge that failed runs its failed jobs once more, where they stopped.">
</picture>

- **A download that hangs starts again, before a bot is needed:** each download of the website that sets no time limit of its own, such as one of the social plugin, gets 10 seconds to connect and 30 for each next part of the file, and every download starts again twice. In the Variants, a setup of uv that doesn't end within two minutes gives way to a second one from the releases of uv on GitHub, and a container whose image failed to download starts again. Only what fails every attempt fails its step (decision 0061 of the [decisions](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)).
- **Once, not again and again:** the flaky-test bot runs the failed jobs of the first attempt of a test run once more, and so does the bot for failed releases with a release that a merge started; a release that you already run again is yours, and the bot leaves it alone; the bot for cancelled checks starts a run twice at most. A job that GitHub stops at its time limit ends cancelled, not failed, and runs once more as well. A run that you or a newer run cancelled stays cancelled, even when a job that waits for the others failed because of it.
- **A failure that repeats is real:** when the same jobs broke for the commit before on the same branch, after they ran once more, the jobs don't run again, so that a broken test doesn't keep a runner busy for nothing.
- **The issue of flaky tests** gets a comment for each run that passed when it ran again, with a table: each job that failed at first, with a link to its log, the step that broke, the tests that pytest names in the log, and the first error. Its body counts how often each job and test flaked, and links the run in which it last did, the latest first, so the test that flakes most stands out without reading every comment.
- **Tests that pytest doesn't run,** such as the browser tests of a Docker E2E, name the test that failed as well, with `copier update --data "test_marker=Browser step:"`: when the log of such a job writes that text before the name of each test or step as it starts, the bot names the one that the log names last before the failure, in the step of the job and the worker that failed, and takes the first exception after it as the error when no annotation names one.
- **What the issue shows of a pull request:** a name or a line of a log is written as plain code, so a pull request can't end the table or mention anybody with it, and the branch of a fork, which it names as it likes, isn't named.
- **The quick checks run once for each commit:** the title and the changelog, the dependency review, the secret scan, the area labels and the website. A late run for an older commit, such as one that an edit of the release pull request starts while release-please pushes to it, no longer cancels them for the head. The checks that take minutes, the tests, Lint, CodeQL and the variants, still cancel the run for an older commit; the bot for cancelled checks repairs a race there.
- **A newer push to `main` cancels the checks of the push before:** the tests, CodeQL, the link check, OSV-Scanner and the workflow security check of `main` only tell the state of `main`, which the run of the newer commit tells as well, so they stop, as in a pull request, and leave their runners to the runs that matter. The website, the release and the bots that commit or change GitHub end what they started, and no push cancels a run on a schedule or by hand. When a late run for an older commit cancelled the run for the head of `main`, the bot for cancelled checks starts it again, so that the coverage of `main`, the alerts of code scanning and the fix bot always see its newest commit (decision 0076 of the [decisions](https://github.com/Dennis-Otto/repo-blueprint/blob/main/docs/decisions/README.md)).
- **Other workflows of tests** that a repository has, such as visual tests, join the CI and Docker E2E with `copier update --data "test_workflows=Visual check, Screenshot bot"`.
- **The link check of a pull request** reads the documents that it changes, and every document when it changes the rules, or moves or deletes a file that a document may link to. lychee keeps the answers of the sites for a day and asks again for a link that failed, so that a site that is down for a moment fails only the pull requests that link to it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-a-newer-push-to-main-cancels.dark.svg">
  <img src="../images/diagrams/what-a-newer-push-to-main-cancels.svg" alt="What a newer push to main cancels: A merge pushes to main while the runs of the push before may still go. The tests, CodeQL and the scanners of the push before only tell what the run of the newer commit tells as well, so the newer push cancels them, as a newer push to a pull request does. When a late run for an older commit cancelled the run for the head of main instead, the bot for cancelled checks starts it again. The website, the release and the bots that commit or change GitHub end the run that they started, and only the newest run that waits comes next. No push cancels a run on a schedule or by hand.">
</picture>

## When a bot fails

A bot or a scheduled workflow that fails on `main` runs its failed jobs once more where a second try can pass, and otherwise keeps one issue per workflow open, with the failed jobs, their steps and their first errors, which the next run that passes closes; every night, a look at the latest run of every workflow, those of the project too, which starts a workflow whose schedule GitHub missed or switched off; where a Renovate workflow runs, one issue with the warnings and errors of Renovate.

**How:** `bot-health.yml`, `blueprint.py bot-health`.

GitHub mails the failure of a scheduled run only to whoever last changed its schedule, and that of another run to whoever started it, in these repositories the release app for most runs: a red bot used to show only in the Actions tab, as when Findings, Mutation and Renovate failed for days. The bot-health bot (`bot-health.yml`) makes each such failure an issue, and closes it once the bot passes again.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/what-the-bot-health-bot-does-when-a-bot-fails.dark.svg">
  <img src="../images/diagrams/what-the-bot-health-bot-does-when-a-bot-fails.svg" alt="What the bot-health bot does when a bot fails: When a run of a bot or a scheduled workflow ends on the default branch, the bot-health bot looks at it; runs of pull requests start nothing. A first failure that a second try can fix runs its failed jobs once more. A failure that stays opens one issue for the workflow, or updates it, with the failed jobs, their steps and their first errors. A run that passes closes the issue. Every night, the bot looks at the latest run of every workflow, in case GitHub lost an event, but leaves a workflow that keeps an issue of its own to that issue. It starts a workflow whose schedule GitHub missed or switched off: one with no run of its schedule or by hand since the time of its schedule, whatever pushes ran it since.">
</picture>

- **One issue per workflow,** titled like *Findings fails on main*, with the labels `bot-failure` and `maintenance`. It names the latest failed run, its attempt and its trigger, and a table of the failed jobs with the step that failed and the first error of each, from the annotations of the run. A later failure in the same place only updates it, without a notification; a failure in another job or step adds a comment. The next run that passes closes it with a link to that run.
- **A second try only where it can pass:** a first failure runs its failed jobs once more, as the flaky-test bot does for the tests, unless another bot already did. Findings, which fails while an alert is open, Mutation, which takes hours to measure the same again, and the property tests and the fuzzing, which failed on an input that they found, are reported at once. A run that GitHub couldn't start, because its workflow file is invalid, too.
- **Which runs count:** those of the bots and scheduled workflows that `bot-health.yml` lists, on the default branch, from a schedule, a push, a start by hand or another workflow, never from a pull request or a fork. The checks that run in pull requests, such as the CI, the website or CodeQL, and the workflows of the project count in the nightly look, which takes the latest finished run of every workflow on the default branch, so that none of their runs for a pull request starts a run of the bot. GitHub gives a run that the end of a check of a pull request starts, as it starts After the checks, the default branch too, so the nightly look counts only the other runs of such a workflow. The Diagrams workflow, Newest Node, Newest Python and the Next runner keep an issue of their own, and so does a workflow of the project that says so in a comment line `# bot-health: own-issue`, such as end-to-end tests whose weekly run against the coming release keeps issues of its own: the nightly look opens and closes none for them, only the one that it opened before the line came, and still starts a schedule that GitHub missed.
- **Missed schedules:** GitHub runs a schedule late at busy times, sometimes not at all, and switches the schedules of a repository off after 60 days without activity. Every night, a workflow without a run of its schedule or by hand since the latest time of its schedule, six hours ago or more, starts by hand, at most four a night so that the pull requests keep their runners; a push since doesn't count, because its run may leave out what only the schedule does, such as the tests of the coming release; Findings, Issue lifecycle and the Issue assistant sync of the blueprint start with `dry_run` off, as their schedule runs them. A schedule that GitHub switched off is switched on again.
- **Renovate's problems:** Renovate, which runs in the blueprint for the repositories of its owner and in a repository of any other owner for that one, logs a lock file that it can't read as a warning, without failing. The Renovate workflow keeps one issue, *Renovate logs problems*, with the warnings and errors of its latest run that had any, by repository, and closes it after three runs in a row without one. A public issue names public repositories only.
- The bot reads runs, jobs and annotations and writes issues with the `GITHUB_TOKEN` of its job, and checks out only the default branch, never the code of a pull request. A repository whose `.github/labels.toml`, which belongs to the project, lacks `bot-failure` gets the label from the bot; add it to the file to keep its color and description in one place.
