# The fix bot reads the fixes of every workflow of its list

- Status: accepted, amended by [0112](0112-the-fix-bot-leaves-a-commit-to-the-run-that-ends-last.md), by which a check that outlasts the wait gets the one commit instead of a commit of the others before it
- Date: 2026-11-02

## Context

The fix bot took the fixes of Lint and of `CI (*)` alone, by a pattern in `blueprint/fixes.py` and the same names in the condition of its job ([decision 0023](0023-pull-requests-fix-themselves.md)). A check in a workflow of a project's own, such as the end-to-end tests or the visual tests of HomeDarts for Autodarts, could name its commands in `autofix` for a person, and no more. Self-healing, part 3 ([#429](https://github.com/Dennis-Otto/repo-blueprint/issues/429)) wants every check with a fix to fix itself, in every repository.

A repository already says which workflows count: the list `workflows:` of `after-checks.yml`, which the blueprint writes for each kind of project, with `Docker E2E` and what the answer `test_workflows` names. The bot starts only after those. Two things need care. A pull request names its runs as it likes, so the names can't decide alone. And the bot waits for the other checks of the commit, so that one commit holds all their fixes: waiting for the whole list would hold a fix of Lint back for the end-to-end tests of twenty minutes and for CodeQL, which keep nothing.

## Options

1. Read the artifacts of every run of the commit, whatever its workflow. The simplest, but a workflow that a pull request adds would count, and nothing would bound the wait.
2. A list of its own, in `.github/checks.project.toml`, of the workflows that keep fixes. It says exactly what the bot needs, but it is one more place to fill in and to forget, next to the step in the workflow and the answer `test_workflows`.
3. Read the workflows of the list of `after-checks.yml` of `main`, and leave out those that never keep a fix by a list in the code, as the flaky-test bot leaves out the scanners. A list in the code knows nothing of a project, so every project's end-to-end tests would hold up every fix.
4. Read every workflow of that list, and wait only for those whose files on `main` name an artifact `fixes-*`.

## Decision

Option 4.

- **The list of `main` decides what counts:** `blueprint.py fix collect` reads `.github/workflows/after-checks.yml` from the checkout of the default branch. A run whose name isn't on it stays unread, and a list that it can't read, or that names nothing, stops the bot with an error before it asks GitHub for anything. A pull request can still name a run of its own after a workflow of the list, as it can change its Lint today: its artifact remains data, which passes the same checks of paths and kinds.
- **The files of `main` decide what to wait for:** a workflow of the list whose file has a line `name: fixes-…` keeps fixes, and the bot waits for it, up to the quarter of an hour that it always waited. It waits for no other run. Docs keeps fixes on `main` alone, so on a pull request nothing waits for it.
- **A wrong guess costs one more commit, never a fix:** a workflow that keeps its artifact by a composite action isn't waited for, but its own failure starts the bot, which reads it then. The bot may commit once more onto its own commit for just such a check that ends later.
- **The bot starts after any workflow of the list that failed,** on a pull request and on `main`, by a push, by its schedule or by hand, with no list of names in the condition of its job. On a pull request, a commit whose failed runs kept no fix ends the job at once; the commit decides and not the run that started the job, because GitHub keeps one pending job of a branch, and the newest replaces the one before it. After a run that passed, it starts only for a push to `main` and only for Lint, Docs and the CI, as before: that is what closes the pull request of the fixes of `main`.
- **Only a run that failed keeps fixes,** and Docs that passes only for a push to `main`. The bot now sees Docs on a pull request as well, so this rule asks for the event itself instead of counting on the run being left out.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/which-workflows-the-fix-bot-reads.dark.svg">
  <img src="../images/diagrams/which-workflows-the-fix-bot-reads.svg" alt="Which workflows the fix bot reads: A run of a workflow fails. A workflow that the list of after-checks.yml of main doesn't name starts no bot, and the bot reads none of its fixes, whatever a pull request names it. For a workflow of the list, also one of the project's own such as Docker E2E, the bot looks for an artifact fixes-*. Without one, the PR coach explains the check. With one, the bot waits for the workflows whose files on main keep such an artifact, and for no long run that keeps none, up to a quarter of an hour. Then it takes the fixes of every run of the list that failed as data, only text files that the commit has, and commits them as one commit onto a branch of the repository, suggests them on a pull request from a fork, or keeps one pull request with the fixes of main. While a run still goes after the wait, a branch gets no commit: the job after the end of that run makes it.">
</picture>

## Consequences

A check of a project fixes itself with its `autofix` in `.github/checks.project.toml`, the answer `test_workflows` for a workflow that isn't on the list yet, and two steps that it copies from its `ci.yml`, with an artifact `fixes-<name>` of its own, one for each leg of a matrix job. A workflow that keeps no fix holds nothing up. A project whose check does keep one waits for it, so a fix of Lint waits for its end-to-end tests up to a quarter of an hour; that is what makes one commit of them.

One repository already has such an artifact, for another bot: Docker E2E of paperless-sync keeps `fixes-paperless-ngx-<line>` for its fixture bot, which also acts on a run that passed. Under this rule its fixes of Lint and of the CI would wait for that workflow, and both bots would act on a failed run. So paperless-sync renames the artifact to `fixtures-paperless-ngx-<line>` when this release reaches it: the name `fixes-*` means the fix bot's, and a bot of a project's own picks another. Until then the worst case is a slower fix and a second bot that finds its branch moved on.

A run of a scanner that fails on a pull request now starts the job of the bot for a few seconds, which the condition of the job could avoid only with a list of names to keep. On `main`, such a run can't close the pull request of the fixes of `main` by mistake: a failed run of the commit whose fixes have expired, after three days, leaves that pull request open until its check runs again. The first waiting rule still applies: a check that ends after the bot's wait comes in the next commit, which the further point on late runs of #429 deals with.

An existing repository gets this with its next update of the blueprint. Each project adds the steps to its own workflows itself, since they belong to the project.
