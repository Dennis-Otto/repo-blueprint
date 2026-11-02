# Every canary brings its own code

- Status: accepted
- Date: 2026-11-02

## Context

[Decision 0081](0081-one-registry-names-the-repositories-that-follow-the-blueprint.md) let a repository that the blueprint made new keep `sample_code: true` after its own code replaced the sample, and the test of the answers knew such a repository by name, in `MADE_NEW`. player-switch-for-autodarts was the only one. So its update still rendered the sample: each change of the sample in the blueprint reached the code of the repository as a change to merge, and the Variants tried the sample for it, which it no longer has.

The answer `sample_code=false` had a catch nobody had tried. `copier update --data sample_code=false` deletes each file that only the sample renders, also where the repository replaced it: in player-switch-for-autodarts its manifest, its background script, the home page of its website and the screenshot script, 945 lines.

The same repository had become a Chrome extension since, and `tests/answers/` and `.github/fleet.toml` still called it a Node package. The Downstream workflow only warned, and `downstream.py --answers` could not repair it: it took the answer `publish_package`, which the template asks only a package, for a new question that the repository's version predates, and kept it, which also hid it from the warning.

## Options

1. Keep `MADE_NEW`. A list of exceptions for one repository, and that repository keeps getting the sample's changes.
2. Protect the files in the template with `_skip_if_exists`. It doesn't help: Copier keeps such a file when it renders one, but deletes it when the new answer renders none.
3. Let the repository answer no, restore what the update deletes, and have no exception any more.

## Decision

Option 3. Every canary answers `sample_code: false`, the test of the answers says so for each, and `MADE_NEW` is gone. [The FAQ](../faq.md) gives the two commands, and a test of the template runs them through a real update.

The kind of `.github/fleet.toml` must be the `project_type` of the answers, which the test now checks, so that the pages of the kinds and the Variants can't tell different stories.

`downstream.py --answers` asks the template which questions it asks a repository with these answers, by each `when`: an answer of a former kind goes, and shows as a difference until then. It also writes the answers of a new canary of the registry, so that a new canary takes one entry. The fix bot can't write that file, since it adds no file to a pull request, so the explanation of the tests names the command.

## Consequences

A repository made from the sample can leave it at any time, and no update changes its code afterwards. An answer that only warns can still wait unnoticed: the Downstream workflow names it each week, but nothing commits it yet.
