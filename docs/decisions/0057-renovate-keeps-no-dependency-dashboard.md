# Renovate keeps no dependency dashboard, so that a repository can have no open issue

- Status: accepted
- Date: 2026-10-23

## Context

[0029](0029-a-dependency-dashboard-the-whole-monday-and-pins-with-their-checksum.md) gave every repository an issue *Dependency dashboard*, which Renovate keeps open: the updates that wait and why, those that failed, the known vulnerabilities, and a checkbox for each. The goal of every repository made from the blueprint is now that it has no open issue, no open pull request and no open finding of code scanning once its work is done. The dashboard stood against that goal in each of the six repositories of the owner of the blueprint ([issue 251](https://github.com/Dennis-Otto/repo-blueprint/issues/251)): closed, it came back with the next run of the bot, two hours later.

What the dashboard showed has other places by now. Routine updates merge on their own once every check passes; a major update and the weekly refresh of the lock files, which wait for the maintainer, are open pull requests, and an update that waits for its week comes on its own after it. The warnings and errors of each run, such as a lock file that Renovate couldn't write, reach the issue *Renovate logs problems* ([0019](0019-a-failing-bot-keeps-one-issue-open.md)), which closes itself once the problem is gone, and a vulnerability comes as a pull request at any time.

## Options

1. Keep the dashboard, and count it as the one open issue that the goal allows.
2. Switch the dashboard off for the blueprint alone and keep it in every other repository.
3. Switch it off in the rules of the blueprint, for every repository.

## Decision

Option 3, which replaces point 1 of [0029](0029-a-dependency-dashboard-the-whole-monday-and-pins-with-their-checksum.md); its other points stay. `.github/renovate-blueprint.json5` sets `dependencyDashboard: false` and keeps `dependencyDashboardTitle: "Dependency dashboard"`: once the dashboard is off, Renovate closes the issue with exactly that title, which a repository keeps open from an earlier release. No rule asks for the approval of the dashboard, which would open it again. The checklist of `blueprint.py` ticks Renovate off once one of the latest 100 pull requests of the repository comes from a branch `renovate/`, instead of once the dashboard is open, which replaces that point of [0051](0051-every-owner-chooses-who-runs-renovate-and-whether-an-ai-reads-the-issues.md).

## Consequences

- With the release that brings the rules, the next run of Renovate closes the issue *Dependency dashboard* of each repository, and no new one opens.
- An update that waits for its week or for Monday shows nowhere until its pull request opens, and no checkbox opens an update ahead of its time; the checkbox in the description of a pull request of Renovate still retries or rebases it. What fails shows in *Renovate logs problems*, where the Renovate workflow of the blueprint or of the repository runs it; with the Mend Renovate app, in its log at Mend.
- A new repository counts as one where Renovate runs only once Renovate opened its first pull request, which may be the next Monday.
