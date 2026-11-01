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
