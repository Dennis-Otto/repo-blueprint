# Pin no action to a branch: run a tool that follows its branch as an image

- Status: accepted
- Date: 2026-10-13

## Context

Every action of the workflows is pinned to the commit hash of a version, with the version in a comment, and zizmor checks that the comment matches the commit (`ref-version-mismatch`). The Home Assistant integrations used two actions that have no versions: `hacs/action` and `home-assistant/actions/hassfest`, pinned to a commit of `main` and `master`. Both only start an image that moves on purpose, `ghcr.io/hacs/action:main` and `ghcr.io/home-assistant/hassfest:latest`, so that an integration is validated against the rules of today; the pin protected nothing.

On 2026-10-12, `home-assistant/actions` got two commits that didn't touch hassfest. zizmor reported the pin as soon as `master` moved on, and the Findings workflow failed every run in the blueprint and in the integration ha-autodarts (their alerts #236 and #12). Renovate could not catch up: it updates once a week and waits a week after a release, and for an action that follows a branch every commit to the branch is a release that starts the week anew.

## Options

1. Accept `ref-version-mismatch` in `.github/zizmor.yml` or with an inline `# zizmor: ignore[…]`. That weakens the check, an ignore by line drifts with every rendered kind, and Renovate drops an action whose `uses:` line carries the inline comment.
2. Keep the pins and let Renovate follow a branch at once. Findings would still fail after each commit to the branch, for the hours until Renovate's pull request merges, and each commit brings a pull request.
3. Run both images the way their actions do, with `docker run`, without the actions; and let Renovate follow any other action pinned to a branch at once.

## Decision

Option 3. hassfest runs `docker run --rm --volume "$PWD:/github/workspace:ro" ghcr.io/home-assistant/hassfest:latest`, the same command as in the Variants workflow, with the problem matcher of its action, so that its errors still show as annotations. HACS gets the inputs of its action as `INPUT_` variables and the event as a file, as GitHub runs a Docker action; it reads the repository through the API and needs no checkout. No workflow of the blueprint pins an action to a branch, which `test_no_workflow_pins_an_action_to_a_branch` keeps. For an action pinned to a branch in a workflow of a project, a rule of `.github/renovate-blueprint.json5` makes Renovate follow the branch in its next run, without the week of waiting, and merge the update once every check passes.

## Consequences

Findings stays green when the branches of these projects move, and nothing about the validation changes: both images are the ones the actions ran. The HACS step depends on the variables that the image of `hacs/action` reads; if HACS changes them, the `hacs` check of the integrations fails, and the step follows the new `action.yml`. A pin to a branch that a project adds still makes Findings fail for a few hours after each commit to the branch, until Renovate's update merges.
