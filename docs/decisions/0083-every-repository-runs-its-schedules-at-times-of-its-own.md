# Every repository runs its schedules at times of its own

- Status: accepted
- Date: 2026-10-25

## Context

The workflows of the blueprint have literal crons, and the template includes them word for word, so every repository that follows the blueprint ran each schedule at the same minute. GitHub starts schedules late, but together: on Wednesday 21 October 2026 CodeQL started in six repositories within the same ten minutes, and so did the SBOM and the sweep of the findings; on Saturday 24 October the mutation tests started in five repositories within seven minutes, each with up to four parallel jobs that ran 28 to 85 minutes. The jobs of the issue assistant waited up to 41 minutes for one of the 20 runners that GitHub Free gives an account, and the pull requests of every repository waited behind them.

## Options

1. Keep the times and lower the parallel jobs: the runs still arrive together, only slower.
2. A question of `copier.yml` for the times of each repository: every repository answers it, and an owner has to pick times that don't collide.
3. A slot from the hash of the owner and the name alone: seven repositories in seven days collide with a likelihood of 99 %, so two of them would share their heavy weekly jobs.
4. A slot computed by the template: 0 for the blueprint, the place in the Rollout for a repository of `.github/fleet.toml` ([decision 0081](0081-one-registry-names-the-repositories-that-follow-the-blueprint.md)), and the hash of the owner and the name, from 0 to 27, for any other one; `includes/replace.jinja` moves each schedule of a workflow that it renders by the slot.

## Decision

Option 4. `schedule_slot` of `copier.yml` is computed, never asked and not stored, with the filters that Copier always has, so no `--trust`. `replaced()` of `includes/replace.jinja`, through which every workflow of the blueprint with a schedule renders now, moves each weekly schedule by as many days and every schedule by 8 minutes for each, within its hour: the minutes go round from :59 to :01, never onto the full hour, and the hours stay. The heavy weekly jobs of the blueprint, CodeQL and the SBOM, the mutation tests, the links and OSV-Scanner, and the Scorecard, lie in different hours on different days, so with each job in its hour, two repositories of different slots from 0 to 6 never share an hour of a day for them, and the scanners still finish before the daily sweep of the findings. A cron of another form stops the render. The weekly run of the mutation tests takes two runners at once, a pull request four.

The templates of the issue assistant, `issue-lifecycle.yml` and `findings.yml`, keep their times: its check keeps them equal to those of the action, so they move in Dennis-Otto/issue-assistant.

## Consequences

After the Rollout, no two repositories of the registry have the same cron for a workflow of the blueprint, and a test renders the answers of each and checks it, with the hours of the heavy jobs. A new repository of the registry takes the next place in the Rollout and with it a slot of its own; from the eighth on, the days repeat, 56 minutes later. The order of two jobs within one hour can turn round when the minutes go past :59, which no job relies on. The dashboard and the bot-health bot read each repository's own crons, so they measure the delay and find a missed run as before.
