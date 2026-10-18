# Bring every release to every repository right after it is verified, and keep the weekly run as a safety net

- Status: accepted
- Date: 2026-10-18

## Context

[0002](0002-copier-and-an-update-bot.md) let the blueprint bot of each repository run `copier update` once a week, on Tuesday morning, so that the releases of a week arrived as one update pull request, and said that once a week was enough. It wasn't. A release of the blueprint mostly fixes something in every repository at once: a check that fails there, such as Findings once hassfest moved on, fixed in 0.10.2, a hook before a push that never ran outside Windows, fixed in 0.10.3, or a hole in a bot, such as the blueprint bot, which took any published release of the blueprint until 0.12.0. With a weekly run, every repository kept the failure or the hole for up to seven days after its fix was released, and a release that broke something showed days after its change, when nobody remembered it. The blueprint released nine times from 12 to 14 October 2026, 0.9.0 to 0.12.0.

0.9.0 added the Rollout workflow, which starts the blueprint bots right after a release, and [0010](0010-roll-out-one-repository-at-a-time.md) decided how it goes from one repository to the next. No record said why every release goes out at once instead of once a week; this one does.

## Options

1. **Once a week, as 0002 decided.** One update pull request brings the releases of a week, and the checks of each repository run once for them. But a fix waits up to seven days, the maintainer starts the bot of every repository by hand for a release that can't wait, and a release that breaks a repository shows long after its change.
2. **Every release, right after the Release workflow has published and verified it.** A fix arrives within minutes, a release that breaks a repository shows in its update pull request while its change is fresh, and each update is small. But every release runs the checks of every repository once more, and releases close together bring their updates close together.
3. **In batches, at most once a day for example.** Fewer runs of the checks than option 2, but a fix still waits, and a batch of releases makes it harder to tell which change broke a repository. The blueprint can batch anyway, before the release: its release pull request collects every change until the maintainer merges it.

## Decision

Option 2. The Rollout workflow starts the blueprint bot of every repository of the release app once a run of the Release workflow has published and verified a release, one repository after the other, as 0010 describes. Whether changes go out one by one or together is decided where it is cheapest, before the release: the release pull request collects the changes until it merges, and a release of dependency updates alone merges and publishes itself.

The weekly run of the bot stays, as the safety net of [0033](0033-schedules-are-only-a-safety-net.md): it brings a release that the Rollout missed, and every release to a repository outside the release app of the blueprint, such as one of another owner ([0049](0049-every-owner-brings-their-own-release-app.md)).

## Consequences

- Each repository of the release app has its update pull request within minutes of a release, the first one, and up to about 15 minutes for each repository before it, the last one. It merges itself once every check passes. A repository whose bot fails fails the run of the Rollout by its name.
- Releases that come close together don't pile up: each repository keeps one update pull request, which a newer release moves on ([0007](0007-one-update-pull-request.md)). Rollouts overlap, but never in the same repository: there the newer release takes the place of an older one that still waits, and a bot always updates to the latest release.
- Every release costs a run of the checks in every repository. The Rollout gives each repository the runners of the account in turn, and the Downstream workflow tries every change of the template on the answers and the files of these repositories before it merges ([0039](0039-try-every-change-on-the-repositories-that-take-the-blueprint.md)), so that a release seldom breaks one.
- A release reaches the repositories as soon as it exists, so the blueprint bot takes only a release that the release workflow of the blueprint made and signed ([0020](0020-update-only-to-a-verified-release.md)), and a tag that someone else pushed reaches no repository.
- The repository variable `BLUEPRINT_AUTOMERGE` set to `off` keeps the pace for a maintainer who wants to look first: the update pull request still comes right after the release, and waits for a person to merge it. An update with conflicts waits as well.
- 0002 keeps its choice of Copier and of a bot in every repository; this record amends only how often the bot runs.
