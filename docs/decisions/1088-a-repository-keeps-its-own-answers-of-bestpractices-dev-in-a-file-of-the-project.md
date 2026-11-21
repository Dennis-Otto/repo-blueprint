# A repository keeps its own answers of bestpractices.dev in a file of the project

- Status: accepted, amends [0047](0047-every-repository-proposes-the-best-practices-answers-that-the-blueprint-guarantees.md) and [1046](1046-a-bot-notices-a-stale-entry-on-bestpractices-dev.md)
- Date: 2026-11-21

## Context

[Decision 0047](0047-every-repository-proposes-the-best-practices-answers-that-the-blueprint-guarantees.md) made `.bestpractices.json` a file of the blueprint, which every update renders anew, and left the answers that only a project knows to bestpractices.dev. Since 1.23.0, the job *best practices entry* of *Links* compares the public entry with the file every week and keeps an issue whose links force each answer of the file that the entry gives otherwise ([decision 1046](1046-a-bot-notices-a-stale-entry-on-bestpractices-dev.md)). That left no place for an answer that only one repository can give ([#1086](https://github.com/Dennis-Otto/repo-blueprint/issues/1086)):

- An answer of a criterion that the file leaves out, such as `security_review`, stayed as it was typed on the site, but nothing in Git held it, and nothing noticed when it went stale.
- An answer of a criterion that the file answers too, such as the end-to-end tests of homedarts-for-autodarts under `test`, counted as a difference. Saving the links replaced it with the template's words; not saving them left the issue open for ever. The links of [player-switch-for-autodarts#302](https://github.com/Dennis-Otto/player-switch-for-autodarts/issues/302), saved on 2026-11-20, replaced eight answers that way.
- A repository had no way to give such an answer: a change of `.bestpractices.json` gets a notice of the check *lint* and conflicts with the next update that changes the same line, and neither `copier.yml` nor `.github/repository.toml` has a place for it.

On 2026-11-21 the maintainer saved the links of all eight issues, so every entry gave the template's answers, and the answers that only a repository can give were gone from the entries.

## Options

1. **Change `.bestpractices.json` in the repository:** the notice of *lint*, and a conflict with the next update that changes the line.
2. **A question of `copier.yml`, or a key of `.github/repository.toml` or `.github/repository.project.toml`:** the answers of Copier choose what the template renders, and these files are the settings that the settings bot applies; neither is a place for justifications.
3. **A list of fields that the bot skips:** the entry would drift without anyone noticing, and the answer would be nowhere in Git to review.
4. **Render the project's answers into `.bestpractices.json`, or have the fix bot write them there:** Copier can't read a file of the project without `--trust`, and a written file of the blueprint conflicts on the next update.
5. **A file of the project, `.github/bestpractices.project.toml`, beside the blueprint's file,** whose answers the bot compares and forces like those of the file, checked by a step of `scripts/check.sh`.

## Decision

Option 5:

- **The file:** one table for each criterion, named as in `.bestpractices.json`, such as `[test]` or `[osps_br_07_01]`. A table for a criterion that `.bestpractices.json` answers gives only `justification`, which replaces the file's; the status stays the template's `Met`. A table for any other criterion gives `status` and `justification`. The template renders the file once, with a comment alone; it is in `_skip_if_exists` and in the list of the files of the project of `AGENTS.md`, which also says that an answer of the repository alone goes there, never into `.bestpractices.json`, and `INSTEAD` of `blueprint/ownership.py` names it for a pull request that changes a file of the blueprint.
- **The answers of a repository are both files:** `answers()` of `blueprint/best_practices.py` reads `.bestpractices.json` with the tables of the project file in place of the same fields, and `keep_issue()` compares, links and closes on these answers, so `differences()`, `edit_links()` and `body()` have one source. The issue marks each answer that is the project's own and says that it is changed in the file, not on the site, since the next weekly run forces it back over an edit on bestpractices.dev, and that *Save (and continue) 🤖* reads only `.bestpractices.json`. A repository without the project file, or with only the empty one, gets the same issue as before.
- **The check:** `blueprint.py best-practices --verify`, the step *Answers for bestpractices.dev* of `scripts/check.sh`, checks the file without the network and passes when it is missing. It fails on a criterion that `bestpractices-criteria.json` doesn't know or a key other than `status` and `justification`; a status for a criterion that `.bestpractices.json` answers; a criterion of its own without both; a status other than `Met`, `Unmet` or `N/A`, or `N/A` where the criterion doesn't allow it; `Met` without a link where the criterion needs one; a link to a file or a heading of the repository that the checkout doesn't have, as `gone_files()` and `anchors()` read them; a link that doesn't use https; a justification too long for one link of the issue (`LIMIT`); and a justification that `same()` finds equal to the one of `.bestpractices.json`. That every status has its justification is the blueprint's own rule, stricter than the site, so that every answer in Git says why it holds.
- **The fix:** `--verify --fix`, the `autofix` of the step, removes a status `Met` for a criterion that `.bestpractices.json` answers and a justification that only repeats the file's, so a release that starts to answer a criterion fixes itself in the update pull request of every repository. A status `Unmet` or `N/A` for a criterion that the template now guarantees still fails: one of them is wrong, and a person decides which.
- **The blueprint's own answers:** its `.github/bestpractices.project.toml` gives the justifications of `test`, `test_continuous_integration` and `version_tags_signed` that only the blueprint can give, each checked against the repository as it is: the coverage of `blueprint.py` against a simulated GitHub, the tests of the nine kinds and the Variants workflow, and the signed tags since v0.6.0.

This isn't option 2 of 0047, a file copied once that never learns of a change of the blueprint: the template still gives every answer that it guarantees, and an update still brings each of them; the project file holds only what the template can't say.

## Consequences

- An answer that only one repository can give lives in Git, is reviewed in its pull request and reaches the entry through the links of the weekly issue, which closes once the entry gives it.
- `--verify` notices a file or a heading that is gone, and a copy of the template's words, but not words that no longer hold: a person keeps each sentence true, as for every answer of the project.
- Each repository brings back the answers that saving the links of 2026-11-21 replaced by moving them into its own file; the changelog says how.
- Whether bestpractices.dev limits the length of a justification below the length of one link is not measured; the check holds a justification to what one link of the issue can carry.
