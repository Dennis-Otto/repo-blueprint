# A pull request hears when it changes a file of the blueprint, from a list that names each file

- Status: accepted
- Date: 2026-11-01

## Context

The next update of the blueprint merges each of its files with the changes of the repository, line by line, and marks a conflict where both changed the same lines. An update with conflicts doesn't merge itself, so the Rollout stops at that repository until a person resolves it. player-switch-for-autodarts #26 waited on conflicts in four workflows and `CONTRIBUTING.md`.

Nothing told the author of such a change. `AGENTS.md` lists the ownership, but only coding agents read it, and the [PR coach](0022-every-check-explains-its-failure.md) explains failures, not who owns a file.

A file belongs to the blueprint when the blueprint renders it and `_skip_if_exists` doesn't hold it. The second half alone can't tell: a workflow of the project alone, such as `e2e.yml`, is held by no pattern either, and it is exactly where the change should go.

## Options

1. A list of the patterns of `_skip_if_exists` in the repository. Every other file would count as the blueprint's, so that the notice would send a person away from the workflow of their own that it recommends.
2. Ask at the time of the check: render the release of the repository with Copier in the job and compare. That takes a download and a second on every pull request, and it runs the template in the job of a pull request.
3. A list of every file that the blueprint renders for this kind of project, as a file that the blueprint brings, whose conditions come from the names of the files of the template.
4. A failure instead of a notice for everybody. The change can be right, such as a fix that can't wait for a release: `copier update` keeps it as long as nobody else changes the same lines.

## Decision

Option 3, as a notice by default.

- **The list** is `.github/blueprint/owned.txt`, from `template/.github/blueprint/owned.txt.jinja`, which `reference.py` writes from the files of `template/` and the patterns of `_skip_if_exists`, read as Copier reads them, without its library, since the Issue assistant sync runs the script on the Python of the runner. A file of the template carries its condition in its name, and the line of the list carries the same condition, so a project lists only what it got. `.copier-answers.yml` stays out: a command writes it, and the FAQ says to change an answer that way. `.vale.ini` stays out too: its first lines say that a project changes it there. `tests/test_reference.py` fails on a list that differs from the template, and `tests/test_template.py` compares it with the files that each kind of project really gets.
- **The notice has two places.** A step of the job *lint* annotates each file, which the files of the pull request show. The one report of the PR coach names them with where the change belongs instead and adds the label `blueprint-file`; it runs after the checks with a token that may write, also for a pull request from a fork, and it reads the list of the default branch, which no pull request controls. The report is a part of its own in the coach, not a part of a workflow, since a part of a workflow shows its links only as code and this one has a link to follow.
- **The way out is a link:** a new issue in the blueprint, filled in with the files through the fields of its form.
- **A failure is a choice of the owner:** the repository variable `BLUEPRINT_OWNERSHIP` set to `fail` makes the step of *lint* fail, and the coach explains it as the check *ownership*.
- **Bots get no notice:** the update of the blueprint on `blueprint/update`, the branches `bot/*` of this repository and every pull request of an account of a GitHub App. A fork that names its branch the same still gets it. The blueprint itself has no list, so it needs no exception by its name, and neither does a fork of it.
- **The label comes with its description from the report** when `.github/labels.toml` of the repository lacks it, as that file belongs to the project and no update brings a new label. When GitHub refuses the label, the report still follows.

## Consequences

Every new file of the template needs a run of `python3 reference.py`; the test that fails says so.

The step of *lint* runs from the merge of the pull request, so a pull request can change the step or the list and pass with `fail`. The report still names the files, from the list of the default branch. The variable keeps honest people from a mistake and is no security control.

A notice can be wrong for the moment: a person may need a fix before the next release of the blueprint. It stays a notice for that reason, and the change survives every update that leaves its lines alone.
