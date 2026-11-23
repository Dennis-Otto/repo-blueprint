# The check lint runs the image of markdownlint-cli2

- Status: accepted, supersedes [0167](0167-the-action-and-the-image-of-markdownlint-cli2-move-together.md) and amends [0163](0163-scripts-check-sh-lints-the-markdown-on-your-machine.md)
- Date: 2026-11-23

## Context

The check *lint* ran markdownlint-cli2 through `DavidAnson/markdownlint-cli2-action`, while `scripts/markdownlint.sh` and the Variants workflow ran the image `davidanson/markdownlint-cli2` by tag and digest. [Decision 0167](0167-the-action-and-the-image-of-markdownlint-cli2-move-together.md) put both into the Renovate group *markdownlint-cli2*, and `pins.py --check` failed while the version that the action runs differed from the image's: an update that came first was to wait in the branch of the group for the other one. That holds only when a release of the action runs the image's version and is due on the same Monday. Of the last six versions, 0.23.3 and 0.24.1 have no release of the action at all, and the image of 0.23.2 was due a Monday before its action, so [#1100](https://github.com/Dennis-Otto/repo-blueprint/pull/1100), the image at 0.24.1, stayed red in the blueprint ([issue 1111](https://github.com/Dennis-Otto/repo-blueprint/issues/1111)).

A repository made from the blueprint gets the group and the script, but not `pins.py`: nothing there compared the two, so the image moved alone and merged by itself in all seven repositories of `.github/fleet.toml`, while their check *lint* stayed on the action's 0.24.0. markdownlint 0.42.1 of 0.24.1 changed MD042 and MD054, so a document can pass `scripts/check.sh` and fail *lint*, or the other way round, which is the gap that decisions 0163 and 0167 were meant to close. And when a release brings a third value to a line that a repository's own Renovate has moved, `copier update` marks a conflict there.

## Options

1. **Keep the pair and wait,** as 0167 did: it stays red for every version that the action skips, and the repositories drift without a word.
2. **A test that accepts two versions, or an image that may run ahead by a patch:** the two linters still disagree on a rule.
3. **Keep the action, derive the image's tag and digest from it in `pins.py`, and turn Renovate off for both in the repositories:** two dependencies still, a lookup on Docker Hub in `pins.py`, the repositories held at the release's version between releases, and an update that overwrites a line that a repository changed, which no update does today.
4. **The check *lint* runs the image itself,** with `docker run`, as it does for actionlint and REUSE: one dependency in three places.

## Decision

Option 4:

- **The Lint workflow:** the job *lint* names the image by tag and digest in `MARKDOWNLINT`, which the custom manager of the images finds as it finds the one of `scripts/markdownlint.sh`. The step *Lint the Markdown of every document*, still with the id `markdown`, runs `docker run --rm --network none --user "$(id -u):$(id -g)" --volume "$PWD:/workdir" "$MARKDOWNLINT" "**/*.md"`, and *Fix what markdownlint can fix* the same with `--fix`, as the user of the runner, so that the files that the fix writes keep their owner for *Keep the files that markdownlint fixed*. The steps and their ids, which the PR coach and the fix bot read, stay as they were.
- **The annotations:** a problem matcher of the step, built against the output of markdownlint-cli2 0.24.0 (`docs/index.md:3:1 error MD018/no-missing-space-atx No space after hash on atx style heading [Context: "#Broken heading"]`, the column left out where a rule names none, `warning` for a rule of that severity), shows each finding at its line, in the files of the pull request too. The step adds it before the lint and removes it after, also when the lint fails, so that the output of the fix and of later steps makes no annotation.
- **Renovate:** the group *markdownlint-cli2* holds the image alone, after the groups of the actions and of the images, so that a new markdownlint, whose rules may fail a document, holds back no other image, and its branch stays the one of [#1100](https://github.com/Dennis-Otto/repo-blueprint/pull/1100). The blueprint's own post-upgrade task of `pins.py` for the pair leaves `.github/renovate.json5`, and the shared rules turn off nothing new: the image moves and merges by itself in every repository, as the other pins do.
- **The record:** `[bundle."DavidAnson/markdownlint-cli2-action"]` leaves `.github/pins.toml`, and with it the bundles of `pins.py`, which no other action used; `pins.py` refuses a record that still has one. `tests/test_pins.py` fails while the Lint workflow, `scripts/markdownlint.sh` or the Variants workflow runs another tag or digest of the image than the other two, and while a workflow names the action; the tests of the template check the same for every kind.
- **The allowed actions:** `DavidAnson/markdownlint-cli2-action@*` leaves `[actions.selected]` of `.github/repository.toml`, as no workflow runs it.

## Consequences

- The check *lint*, `scripts/check.sh` and the Variants workflow lint with one version of markdownlint-cli2 in the blueprint and in every repository, and Renovate moves it in all three files in one pull request that turns green and merges by itself, whether or not a release of the action runs that version.
- The action's own annotations give way to those of the problem matcher, which show the same file, line, column, rule and text, and each run of *lint* pulls the image, about 200 MB unpacked, from Docker Hub, as it pulls the images of actionlint and REUSE.
- A repository whose own Renovate moved the image in `scripts/markdownlint.sh` gets the image of the release in `lint.yml` with the update, and its next Renovate run moves both to the newest version in one pull request; the update itself merges without a conflict, since the release changes no line next to the image's line in the script and removes the action at the commit that every repository still pins.
- `pins.py` keeps no bundles any more: should another action run the package of an image that the scripts run, the workflow runs that image instead, as here.
