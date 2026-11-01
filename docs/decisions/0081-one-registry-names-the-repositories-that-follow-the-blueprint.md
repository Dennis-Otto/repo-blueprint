# One registry names the repositories that follow the blueprint

- Status: accepted, amended by [0100](0100-a-pull-request-runs-only-the-variants-whose-project-it-changes.md), by which `variants.py` makes the legs of the canaries from `tests/answers/` and the registry no longer writes them into the workflow
- Date: 2026-10-25

## Context

The repositories that follow the blueprint were named by hand in four places: the order of the Rollout in `.github/workflows/rollout.yml`, the showcase *Made with the blueprint* of `README.md` and `README.de.md`, the section *A real repository* of each page of `docs/kinds/`, and the canaries of the Variants in `.github/workflows/variants.yml`, which try every pull request on the answers of a real repository ([decision 0039](0039-try-every-change-on-the-repositories-that-take-the-blueprint.md)). When player-switch-for-autodarts, a Chrome extension of the kind *node-package*, came to the blueprint, it was in none of them: the README still said "five repositories", the page of the Node kind said that no repository of the kind follows the blueprint, and no canary of the Variants tried a change on a Node package of a person before the merge.

## Options

1. Keep the lists by hand, with a checklist for a new repository: the lists drift again with the next one, as they did with this one.
2. Find the repositories at run time, as the dashboard does with every public repository of the owner: the Rollout and the dashboard could, but a README and a page of the website on GitHub can't run code, and a canary needs the answers of its repository in `tests/answers/` before the run.
3. One registry, `.github/fleet.toml`, with the name, the kind, the place in the Rollout, the canary and the words of each repository in English and German, from which `reference.py` writes the four lists between their marks, committed, with a test that fails while one of them differs ([decision 0054](0054-the-reference-is-written-from-its-sources-and-committed.md)).

## Decision

Option 3. `.github/fleet.toml` is the one list. `reference.py` checks every entry, each field with its type, each name once and the places in the Rollout from 1 without a gap, and writes the part `made-with` of both READMEs, the part `real-repository` of each page of a kind, in the singular, the plural or with the text for none, the line `ORDER:` of the Rollout and the legs between the marks `canaries` of the Variants. `tests/test_reference.py` fails while a file differs from the registry or a canary lacks its answers, and `tests/test_template.py` renders the answers of each canary. A copy of the blueprint without the file, such as a fork that no repository follows yet, writes only the reference pages.

A repository that the blueprint made new, with its sample code, keeps `sample_code: true` in its answers after its own code replaced the sample, as player-switch-for-autodarts does: the test of the answers knows these by name, so that every other canary still has to bring its own code.

## Consequences

A new repository takes one entry in the registry and `python3 reference.py`, and a canary takes its answers from its `.copier-answers.yml` as well; the Downstream workflow then keeps them equal to those of the repository. The fix bot writes the READMEs and the pages of the kinds anew when the tests fail, but not the two workflows, which a person commits, as with the pins of `pins.py`. The Rollout already reaches every repository of the release app, a new one first; the registry gives it its place by the time of its checks.

Repositories of other owners that use the blueprint are not in the registry: a weekly search of GitHub for their `.copier-answers.yml`, with a topic to opt out, can show them on the website later.
