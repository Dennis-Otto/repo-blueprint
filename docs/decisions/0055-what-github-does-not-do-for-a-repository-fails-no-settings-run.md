# What GitHub doesn't do for a repository fails no run of the settings

- Status: accepted
- Date: 2026-10-19

## Context

[Decision 0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md) asks for the generic patterns of secret scanning, `secret_scanning_non_provider_patterns = true`, and names a switch that GitHub leaves out of its answer for a repository with the line that turns it off. On a repository of a user GitHub doesn't leave the switch out: it names it as `disabled`, answers its write with success, and keeps it off. So `settings apply` found the same difference after every write and exited with 1, and the Settings workflow failed on `main` of the blueprint and of every repository made from it, 18 times in a day, while the rulesets and every other setting were applied ([issue 277](https://github.com/Dennis-Otto/repo-blueprint/issues/277)). A run that fails every day for what no one can change but the plan of the repository teaches everyone to ignore its red.

## Options

1. Stop asking for the generic patterns in the template: a repository of an organization whose plan has them would lose them, and the next switch of the same kind would fail the runs again.
2. Guess from the kind of the owner which switches GitHub keeps: GitHub changes what its plans include, and the guess would be wrong for an organization without the plan.
3. Take what GitHub does with a write as its answer: a switch of `security_and_analysis` that GitHub accepted and kept as it was, and one that its answer leaves out, are a notice of the run, named with the line of `.github/repository.project.toml` that stops asking for it, and fail nothing.

## Decision

Option 3. `settings apply` writes every switch that differs, as before. A switch of `security_and_analysis` that still differs after GitHub accepted its write is named under *GitHub doesn't do this for the repository, which fails nothing*, as is a switch that GitHub doesn't offer at all, with the line that stops asking for it. Only these switches, which GitHub answers that way: a ruleset, a variable or another setting that still differs after its write fails the run as before, since that is a fault of the blueprint or of GitHub that someone has to see. A write that GitHub refused shows nothing about what it keeps, so its switches stay a difference. `settings check` writes nothing and can't tell a switch that GitHub keeps off from one that is off; it names it as a difference, which `settings apply` then turns into the notice.

## Consequences

The Settings workflow passes on every repository of a user again, and its summary still names the generic patterns that GitHub keeps off, with the line that ends the notice. A repository of an organization whose plan has them gets them, without a change of its settings. The checklist still shows *Settings as code applied* as open for such a switch, since it only reads; `settings apply` explains it.
