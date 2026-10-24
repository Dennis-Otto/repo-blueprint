# An image of Docker runs with docker run, and settings check names every step that runs one with docker://

- Status: accepted
- Date: 2026-10-24

## Context

[Decision 0038](0038-new-alerts-and-unlisted-actions-stop-a-pull-request.md) lets only the actions of GitHub and the patterns of `[actions.selected]` run, and `settings check` names each action that a workflow runs and the list lacks. It took the images of Docker that a step names with `uses: docker://…` for no action, since no pattern names an image, and left them out. GitHub counts such a step as an action, though, and refuses it unless every action may run: once the settings bot had switched the blueprint to the selected actions, Lint, whose step ran actionlint with `docker://`, ended in a *startup failure* on every pull request ([#279](https://github.com/Dennis-Otto/repo-blueprint/issues/279)). The check had passed, so nothing had warned of it, and nothing would warn of the next such step either ([#281](https://github.com/Dennis-Otto/repo-blueprint/issues/281)).

## Options

1. Leave the images out of the check and rely on review: the next `docker://` step breaks its workflow again, after the merge, in the blueprint or in any repository made from it.
2. Allow every action again: it ends the protection of decision 0038 for the sake of one kind of step.
3. Count an image as an action that no pattern allows, and name every step that runs one: the fix is the same for every image, a `run:` step with `docker run`, as Lint and REUSE already do.

## Decision

Option 3. `references()` in `blueprint/settings.py` takes the images too, and `allows()` lets none run, whatever the patterns, `*` among them. While `allowed_actions` is `selected` or `local_only`, `settings check` names every image that a step runs with `docker://` as `actions.allowed_actions refuses docker://…`, with the file or the action that runs it and the `docker run --rm` that replaces it; a check with every action allowed names none. As for an action that the list lacks, `settings apply` then never narrows the actions that may run on GitHub: it doesn't switch to the selected actions, and a list that GitHub uses already only grows. `settings check` reads no file of an image from GitHub, as an image runs no action in turn.

## Consequences

A pull request that adds a `docker://` step fails the check of the settings with the line that fixes it, before the step can stop its workflow, and the settings bot keeps every workflow able to start meanwhile. `test_only_the_listed_actions_run` in `tests/test_template.py` keeps the workflows of the blueprint and of every kind of project free of such steps. Every image runs with `docker run` in a `run:` step, pinned by its digest, which Renovate moves; the problem matcher of a tool, as for actionlint, brings its annotations back.
