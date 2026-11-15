# The action and the image of markdownlint-cli2 move together

- Status: accepted
- Date: 2026-11-15

## Context

The check *lint* runs markdownlint-cli2 through its action, `DavidAnson/markdownlint-cli2-action`, which the Lint workflow pins to a commit and which bundles the markdownlint-cli2 that its `package.json` names at that commit. `scripts/markdownlint.sh`, which `scripts/check.sh` runs since [decision 0163](0163-scripts-check-sh-lints-the-markdown-on-your-machine.md), and the Variants workflow run the image `davidanson/markdownlint-cli2` by tag and digest. Renovate updated the two in pull requests of their own, the action in the group of the actions, a new major version of it in a group of its own, and the image in the group of the images, and nothing compared the version of the image with the one that the action runs. For the days between two such pull requests, the Markdown that passed `scripts/check.sh` could fail *lint* on a rule that only one of the versions knows, or the other way round ([issue 932](https://github.com/Dennis-Otto/repo-blueprint/issues/932)).

## Options

1. One group of Renovate for the action and the image: they land in one pull request when both are due in the same run, but an image that is due first still merges alone, and nothing notices when they differ.
2. A test that knows the version that the action runs, from a table in the tests: every update of the action fails the tests until a person writes the new version into the table, so no update of the action merges on its own.
3. Both: a group, across major versions, that keeps the action and the image in one branch, and a check of `pins.py` that knows the version that the action runs from its `package.json`, which `pins.py` reads anew when the commit moved, as it writes the sha256 of a download that Renovate moved.

## Decision

Option 3. The rules of Renovate that every repository shares put `DavidAnson/markdownlint-cli2-action` and `davidanson/markdownlint-cli2` into the group *markdownlint-cli2*, with `separateMajorMinor: false`, after the groups of the actions and of the images, so that a new major version of the action and the new minor version of the image share one branch. `.github/pins.toml` keeps a table `[bundle."DavidAnson/markdownlint-cli2-action"]` with the commit that the workflows pin, the package that the action runs, its exact version and the image of that package. `python3 pins.py --check`, which `tests/test_pins.py` runs, fails when the workflows pin another commit than the record, and when a script or a workflow runs the image at another version than the one of the record; `python3 pins.py` reads the `package.json` of the action at its new commit from `raw.githubusercontent.com` and writes the version into the record. Renovate runs it after it moved the action, as a post-upgrade task of the blueprint's own rules, and the fix bot runs it too, by the autofix of the step of the tests.

## Consequences

The tests of the blueprint fail while the check *lint* and `scripts/check.sh` would lint with different versions of markdownlint-cli2: an update of the image that comes before the one of the action, or the other way round, waits in its branch, which is the one of the group, until Renovate adds the other one, a week after its release, and then merges on its own. Renovate's own check of the configuration rejects `separateMajorMinor` beside `matchUpdateTypes`, so the rule matches every update of the two, digests too, which keep the branch of their own that the rule of the digests gives them. A repository made from the blueprint gets the group as well, for its copy of `scripts/markdownlint.sh`; `pins.py` and its record stay the blueprint's own, as the workflows that pin the action come from the blueprint. Another action that runs a package of an image, once one comes, gets its own table `[bundle."OWNER/ACTION"]`.
