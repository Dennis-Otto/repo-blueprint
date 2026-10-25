# Few jobs that each run several checks, in two releases

- Status: accepted
- Date: 2026-10-14

## Context

The account of GitHub runs about 20 jobs at once, for every repository together, and the blueprint rolls a release out to five repositories at a time. Each job of a push waits for a runner of its own, and the quick checks spent far longer in that queue than at their work:

- **The blueprint:** a push to a pull request started 35 to 38 jobs. The six jobs of Lint, `workflow-lint`, `reuse`, `markdown`, `prose`, `dco` and `issue-assistant`, worked for 13 to 22 seconds each, 7 of them for harden-runner, after a median of 93 to 132 seconds in the queue. The REUSE action built an image of its own in every run, for 8 seconds.
- **CodeQL** ran one job for each language of a matrix, and one more, `codeql`, the required check, which waited a median of 20 seconds, at most 133, for a runner of its own only to report the result of the others.
- **The title of a pull request** took two jobs, `conventional title` and `changelog`, which both only ask the API, and both ran again for every edit of the title.
- **The other repositories:** a push started 24 to 28 jobs; in ha-autodarts, half of them waited more than a minute for a runner, the tiny jobs of Lint a median of two and a p90 of ten minutes, and `hacs` and `hassfest` a minute and a half each.

## Options

1. **Keep a job for each check.** Every check shows on its own, and a slow one holds up no other, but every one of them waits for a runner, and the queue grows with every repository that runs at the same time.
2. **One job for each group of checks that share their set-up**, with every check as a step that runs also when one before it failed. The job starts once and checks the repository out once, and still reports every check, but a pull request no longer shows each one by its own name.
3. **Move the checks into `scripts/check.sh`.** One job less again, but the linters need Docker, Node and the action of the issue assistant, which the check of a kind of project doesn't have, and the check of the code waits for them.

## Decision

Option 2. One job, *lint*, runs every linter: actionlint, REUSE from its pinned image instead of the action, markdownlint, the check of the issue assistant, the sign-off of every commit and the hints at the prose, which never fail it. The job of the title, *conventional title*, checks the entry in the changelog as well. One job, *codeql*, analyzes every language one after the other, downloads CodeQL once, and files the results of each language under the category that its analysis always had, `/language:<name>`, under which code scanning keeps its alerts. For a Home Assistant integration, one job, *home-assistant*, runs HACS and hassfest. Each step of such a job runs also when one before it failed, so that the check reports everything at once, and the PR coach explains each check that failed in it, with its own fix, by the name of the job that ran it.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="../images/diagrams/the-jobs-of-a-pull-request.dark.svg">
  <img src="../images/diagrams/the-jobs-of-a-pull-request.svg" alt="The jobs of a pull request: Each job of a push waits for a runner of its own, and the account runs about 20 jobs at once. So the quick checks share their jobs: lint runs every linter, the title job checks the title and the entry in the changelog, codeql analyzes every language under the category of its alerts, and home-assistant runs HACS and hassfest. Each step runs also when one before it failed, and the PR coach explains each check of a job that failed.">
</picture>

The new jobs replace the old ones in the required checks of `.github/repository.toml` in two releases, so that no pull request waits for a check that no longer runs:

1. **This release** adds the jobs that run several checks and requires them instead of the old ones; the old jobs still run, without the hints at the prose, which no rule required. The settings bot of each repository applies the new required checks after the update merged, and until then the old jobs satisfy the old ones.
2. **The next release** removes the old jobs, once every repository runs this one. It followed once the rulesets of all seven repositories required the new jobs and none of the old ones (#447).

## Consequences

- A push to a pull request of the blueprint starts two jobs fewer with this release and eight fewer with the next one; one of another kind of project seven to nine fewer, and the required checks start in the first wave of runners.
- The check of a group fails when one of its checks fails: its summary, its annotations and the comment of the PR coach name which one, each with its fix.
- CodeQL analyzes its languages one after the other instead of side by side, but waits for one runner instead of three and downloads CodeQL once.
- A check that joins a group comes as a step with `if: ${{ !cancelled() }}`, an `id`, and a line in the list of the parts that its job explains; a test of the blueprint checks that every required check of a group is explained.
