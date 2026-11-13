# A classic branch protection of main is named, never removed

- Status: accepted
- Date: 2026-11-13

## Context

The rulesets protect `main` of every repository made from the blueprint. An existing repository that takes the blueprint may still have a classic branch protection of `main` from before, which GitHub applies on top of the rulesets: one that requires the old names of the checks or an approval keeps every pull request of the bots waiting, and nothing in the rulesets or in `settings check` showed why ([issue 836](https://github.com/Dennis-Otto/repo-blueprint/issues/836)). The settings as code could remove it, but a team may have set it on purpose, such as for the approvals that the rulesets of the blueprint don't ask for yet ([issue 835](https://github.com/Dennis-Otto/repo-blueprint/issues/835)).

## Options

1. Leave it alone, as before: the pull requests of the bots wait, and no check says why.
2. Remove it with `settings apply`: what a person set on purpose goes without a word, and the approvals that it required go with it.
3. Name it as a difference of the settings, with what it requires in words and how to remove it, and leave the removal to a person.

## Decision

Option 3. `settings check` and `settings apply` read `branches/main/protection` once and name a classic protection as the difference *branch protection main*, with what it requires, the command `gh api --method DELETE` that removes it and the page of the settings. `settings apply` never removes it, and it fails until a person has, as it does for a gap of the community profile, so the Settings workflow turns red. The checklist names it in the step *No classic branch protection of main, only the rulesets*. A private repository whose plan offers no branch protection counts as having none, as [0082](0082-a-private-repository-passes-its-checks-without-what-its-plan-lacks.md) has it for what a plan lacks; every other refusal of GitHub fails the run, as it does for the rulesets.

## Consequences

A repository with a classic protection of `main` sees a red run of the settings after the update, with the exact command that ends it, until a person decides. A team that wants its approvals keeps the red run until the rulesets can ask for them (issue 835). The repositories of the fleet had none when this was decided, so their settings bots stay green.
