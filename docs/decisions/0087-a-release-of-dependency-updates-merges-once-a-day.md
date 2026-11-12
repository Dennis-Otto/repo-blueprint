# A release of dependency updates merges once a day, and at once with the fix of a vulnerability

- Status: accepted
- Date: 2026-10-26

## Context

The release bot set the auto-merge of a release pull request that holds nothing but dependency updates in the run of each merge into `main`. Renovate merges its updates one by one, so each of them made a release of its own: in the night of 2026-10-25, five releases of the blueprint, v1.1.1 to v1.1.5, each of which the Rollout brought to six repositories as a pull request with all its checks. The free plan shares about 20 jobs at a time across every repository of the owner, and a release of the blueprint is worth its Rollout only once.

## Options

1. Keep a release for each update: the most current, and the most runs for nothing.
2. Leave every release to the maintainer: no runs for nothing, but the updates wait for a person, also the fix of a vulnerability.
3. Merge a release of dependency updates once a day, in the daily run of the release bot, and at once when one of its updates fixes a vulnerability; every other release waits for the maintainer, as before.

## Decision

Option 3.

- **The daily run:** the run of the schedule of `release.yml`, which existed as a safety net and moves into the slot of each repository ([decision 0083](0083-every-repository-runs-its-schedules-at-times-of-its-own.md)), and a run started by hand, set the auto-merge of the open release pull request when every commit since the last release is a dependency update (`fix(deps)`, `chore(deps)`, `build(deps)`, also `-dev`). A pull request whose checks have all passed already, on which GitHub sets no auto-merge, merges at once; the rules of `main` hold for it either way.
- **A fix of a vulnerability:** a commit whose title carries `[security]`, which Renovate adds to every update of its `vulnerabilityAlerts`, makes the run of its merge set the auto-merge, with the updates before it.
- **Everything else** stays as it was: a release with a change of a person waits for the maintainer, and the first release too.

## Consequences

The updates of a day make one release, and one Rollout, in place of one each; a routine update reaches the users of a repository up to a day later, its release notes list all of the day's updates together, and a fix of a vulnerability is not delayed. The maintainer can release the waiting updates at once by starting the Release workflow by hand. GitHub runs schedules late and drops some; a dropped one the bot-health bot starts within the day, since only a run of the schedule or by hand counts for it, so the updates wait at most about a day longer.

## Amendment of 2026-11-12: what the release is made of counts

The rule looked at the titles of every commit since the last release, so a commit of a bot that release-please makes nothing of held a release of dependency updates back as if a person had changed something: `docs: renew the pictures`, which the screenshot bot merges here, and `chore: update to the blueprint vX` and `docs: update the screenshots`, which the blueprint bot and the screenshot bot merge almost every day in the repositories made from the blueprint. The run that held it ended green, so nobody heard of it, and the update of the issue assistant of 10 November 2026 waited in the release pull request #815 ([#841](https://github.com/Dennis-Otto/repo-blueprint/issues/841)).

Now `blueprint.py release dependency-only` decides, in `blueprint/dependency_release.py`, by each commit since the last release:

- **A dependency update** (`fix(deps)`, `chore(deps)`, `build(deps)`, also `-dev`) doesn't hold the release back, unless it gives the release a version of its own: a `!` after its type, a line `BREAKING CHANGE:`, such as one of the release notes that Renovate quotes, or `Release-As:`, which release-please reads as well.
- **A commit that release-please puts into the release**, as `matters()` of `blueprint/overrides.py` says (a kind that the notes show, `!`, `BREAKING CHANGE`, `Release-As`), holds it back, also when a bot made it.
- **A commit that release-please makes nothing of**, such as `docs:`, `chore:`, `ci:` or `refactor:`, holds it back only when a person made it: GitHub names a GitHub App as the author of the squash commit of its pull request, and an author that GitHub doesn't know counts as a person.

The issue asked to count only the commits that release-please makes something of. A change of a person that release-please makes nothing of, such as a `refactor:` of the template, still reaches every repository with the release; the maintainer's review of every release with a change of a person stays the last guard of the template ([security](../security.md)), so such a commit still waits. A bot's commit adds nothing to trust: it merged after every required check, and every release brings it either way. The author of a squash commit is the author of its pull request, so a pull request that a bot opened counts as the bot's even when a person later pushed to it, such as the maintainer who resolves a conflict of the update of the blueprint; only someone with write access to the repository can push to the branch of a bot, and the commit passed every required check like any other. The step writes the reason into the summary of its run as well, so a release that waits can be seen without the log.
